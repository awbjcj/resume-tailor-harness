import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from agno.agent import Agent

from resume_tailor_harness import llm_limits
from resume_tailor_harness.config import Settings
from resume_tailor_harness.llm_limits import (
    CallLimiter,
    LLMQueueTimeout,
    async_llm_call,
    llm_call,
    retry_after_seconds,
)
from resume_tailor_harness.llm_runner import AgentRunner, build_model
from resume_tailor_harness.provider_stream import StreamLifecycle


@pytest.fixture
def policy(monkeypatch):
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_global_concurrency=2,
        llm_queue_timeout_seconds=10,
        llm_rate_limit_cooldown_seconds=0,
        llm_retries=0,
        anthropic_api_key="",
        openai_api_key="",
        gemini_api_key="",
        deepseek_api_key="",
        sub2api_anthropic_key="",
        sub2api_openai_key="",
        sub2api_gemini_key="",
        sub2api_deepseek_key="",
    )
    monkeypatch.setattr(llm_limits, "env_settings", lambda: settings)
    monkeypatch.setattr(llm_limits, "_limiter", CallLimiter())
    return settings


async def _wait_until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.001)


async def test_real_agents_share_capacity_across_keys_threads_and_event_loops(policy):
    from tests.test_agno_integration import _response

    active = peak = 0
    calls = []
    lock = threading.Lock()

    def enter(request):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append(request.headers["authorization"])

    def reply():
        nonlocal active
        with lock:
            active -= 1
        return httpx.Response(200, json=_response("gpt-6.1-terra", []))

    def sync_respond(request):
        enter(request)
        time.sleep(0.02)
        return reply()

    async def async_respond(request):
        enter(request)
        await asyncio.sleep(0.02)
        return reply()

    def runner(index, client):
        settings = policy.model_copy(
            update={
                "openai_api_key": f"account-key-{index % 2}",
                "openai_base_url": "https://provider.invalid/v1",
                "openai_route_mode": "api",
                # A tenant/runner setting cannot raise deployment capacity.
                "llm_global_concurrency": 100,
            }
        )
        model = build_model("openai:gpt-6.1-terra", settings=settings)
        model.http_client = client
        return AgentRunner(Agent(model=model, telemetry=False), settings=settings)

    with httpx.Client(transport=httpx.MockTransport(sync_respond)) as sync_client:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(async_respond)
        ) as async_client:
            runners = [
                runner(i, sync_client if i < 3 else async_client) for i in range(8)
            ]
            try:
                # Include an independent event loop in an executor thread.
                await asyncio.gather(
                    *(asyncio.to_thread(r.run, "Say hello") for r in runners[:3]),
                    asyncio.to_thread(
                        lambda: asyncio.run(runners[3].arun("Say hello"))
                    ),
                    *(r.arun("Say hello") for r in runners[4:]),
                )
            finally:
                for item in runners:
                    await item.aclose()
    assert len(calls) == 8
    assert len(set(calls)) == 2
    assert peak == 2
    assert active == 0


async def test_async_waiters_are_fifo_and_cancel_without_consuming_slots(policy):
    policy.llm_global_concurrency = 1
    order = []

    async def work(number):
        async with async_llm_call():
            order.append(number)

    async with async_llm_call():
        tasks = []
        for number in range(4):
            tasks.append(asyncio.create_task(work(number)))
            await _wait_until(lambda: len(llm_limits._limiter._waiters) == number + 1)
        tasks[1].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[1]
    await asyncio.gather(tasks[0], *tasks[2:])
    assert order == [0, 2, 3]
    async with async_llm_call():
        pass


async def test_async_waiting_does_not_occupy_the_executor(policy):
    policy.llm_global_concurrency = 1
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        async with async_llm_call():
            waiters = [asyncio.create_task(_one_call()) for _ in range(20)]
            await _wait_until(lambda: len(llm_limits._limiter._waiters) == 20)
            assert (
                await asyncio.wait_for(loop.run_in_executor(pool, lambda: "free"), 1)
                == "free"
            )
        await asyncio.gather(*waiters)


async def _one_call():
    async with async_llm_call():
        pass


@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_queue_timeout_releases_waiter_and_is_not_a_provider_retry(policy, mode):
    from resume_tailor_harness.llm_runner import is_transient

    policy.llm_global_concurrency = 1
    policy.llm_queue_timeout_seconds = 0.02
    async with async_llm_call():
        with pytest.raises(LLMQueueTimeout) as caught:
            if mode == "async":
                await _one_call()
            else:
                await asyncio.to_thread(lambda: llm_limits._limiter.acquire(policy))
        assert not is_transient(caught.value)
    await _one_call()


async def test_rolling_minute_limit_applies_even_with_a_free_concurrency_slot(
    policy, monkeypatch
):
    clock = [100.0]
    monkeypatch.setattr(llm_limits, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    policy.llm_global_requests_per_minute = 1
    policy.llm_queue_timeout_seconds = 120
    entered = asyncio.Event()

    async def second():
        async with async_llm_call():
            entered.set()

    async with async_llm_call():
        task = asyncio.create_task(second())
        await _wait_until(lambda: len(llm_limits._limiter._waiters) == 1)
        assert not entered.is_set()  # Slot 2 is free, but the minute is full.
        clock[0] = 160.0
    await task
    assert entered.is_set()


def test_stream_keeps_its_slot_until_the_provider_is_closed(policy):
    policy.llm_global_concurrency = 1
    closed = threading.Event()
    admitted = threading.Event()

    class Backend:
        def invoke_stream(self):
            try:
                yield SimpleNamespace(response_usage=None)
                yield SimpleNamespace(response_usage=None)
            finally:
                closed.set()

    class Model(StreamLifecycle, Backend):
        pass

    def later():
        with llm_call():
            assert closed.is_set()
            admitted.set()

    stream = Model().invoke_stream()
    next(stream)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(later)
        assert not admitted.wait(0.02)
        stream.close()
        pending.result(timeout=1)
    assert admitted.is_set()


async def test_cancelled_active_async_stream_closes_before_releasing_capacity(policy):
    policy.llm_global_concurrency = 1
    started = asyncio.Event()
    closed = asyncio.Event()

    class Backend:
        async def ainvoke_stream(self):
            try:
                started.set()
                await asyncio.Event().wait()
                yield SimpleNamespace(response_usage=None)
            finally:
                closed.set()

    class Model(StreamLifecycle, Backend):
        pass

    async def consume():
        async for _ in Model().ainvoke_stream():
            pass

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with async_llm_call():
        assert closed.is_set()


async def test_429_cooldown_is_shared_by_queued_calls_and_honors_retry_after(policy):
    request = httpx.Request("POST", "https://provider.invalid/v1/responses")
    response = httpx.Response(429, headers={"Retry-After": "0.03"}, request=request)
    with pytest.raises(httpx.HTTPStatusError):
        with llm_call():
            response.raise_for_status()
    started = time.monotonic()
    async with async_llm_call():
        assert time.monotonic() - started >= 0.02


@pytest.mark.parametrize(
    "header, expected",
    [
        ("3", 3.0),
        ("0.5", 0.5),
        ("NaN", None),
        ("inf", None),
        ("-1", None),
        ("garbage", None),
    ],
)
def test_retry_after_is_read_through_provider_exception_wrappers(header, expected):
    cause = RuntimeError("original")
    cause.response = httpx.Response(429, headers={"Retry-After": header})  # type: ignore[attr-defined]
    wrapper = RuntimeError("Agno wrapper")
    wrapper.__cause__ = cause
    assert retry_after_seconds(wrapper) == expected
