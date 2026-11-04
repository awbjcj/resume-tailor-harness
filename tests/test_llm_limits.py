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


def test_closed_waiter_loop_cannot_leak_an_admitted_slot(policy):
    limiter = llm_limits._limiter
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()
    first = llm_limits._Waiter()
    abandoned = llm_limits._Waiter(closed_loop, asyncio.Event())
    with limiter._condition:
        limiter._waiters.extend([first, abandoned])
        assert limiter._try_acquire(first, policy) == (True, None)
    limiter.release()
    assert limiter._active == 0
    assert not limiter._waiters
    with llm_call():
        assert limiter._active == 1


@pytest.mark.parametrize("mode", ["sync", "async", "stream", "worker_stream"])
@pytest.mark.parametrize(
    "denial", ["allowance", "global", "global_admin", "revoked", "rate"]
)
async def test_queued_agents_recheck_persisted_funding(
    policy, monkeypatch, tmp_path, mode, denial
):
    from datetime import datetime, timezone

    from sqlalchemy.orm import Session

    from resume_tailor_harness.sessions.stream import Completed, Failed
    from resume_tailor_harness.tenancy.context import use_context
    from resume_tailor_harness.tenancy.costs import invalidate_rate_cache
    from resume_tailor_harness.tenancy.limits import (
        BudgetExceededError,
        CostRateUnavailableError,
    )
    from resume_tailor_harness.tenancy.quotas import (
        CostQuotaExceededError,
        GlobalCostQuotaExceededError,
        charge_shared_cost,
    )
    from resume_tailor_harness.tenancy.system_db import LlmRate, UsageEvent, User
    from tests.tenancy.test_spend_gate import _context, _engine
    from tests.test_agno_integration import _response

    policy.llm_global_concurrency = 1
    settings = policy.model_copy(
        update={
            "openai_api_key": "shared-key",
            "openai_base_url": "https://provider.invalid/v1",
            "openai_route_mode": "api",
            "cost_quota_enforcement": "enforce",
            "global_monthly_cost_quota_micros": 1_000,
            "llm_retries": 2,
            "llm_retry_delay": 0,
        }
    )
    role = "admin" if denial == "global_admin" else "user"
    engine = _engine(tmp_path, role=role)
    context = _context(
        tmp_path,
        engine,
        settings=settings,
        role=role,
        platform_provider_keys={"openai": "shared-key"},
        # A fallback must never authorize the already-bound shared credential.
        user_provider_keys={"openai": "personal-key"},
    )
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=_response("gpt-6.1-terra", []))

    with use_context(context):
        model = build_model("openai:gpt-6.1-terra", settings=settings)
        asynchronous = mode in {"async", "worker_stream"}
        client = (
            httpx.AsyncClient(transport=httpx.MockTransport(respond))
            if asynchronous
            else httpx.Client(transport=httpx.MockTransport(respond))
        )
        model.http_client = client
        runner = AgentRunner(Agent(model=model, telemetry=False), settings=settings)
        try:
            async with async_llm_call():
                if mode == "async":
                    pending = asyncio.create_task(runner.arun("Hello"))
                elif mode == "sync":
                    pending = asyncio.create_task(
                        asyncio.to_thread(runner.run, "Hello")
                    )
                else:
                    pending = asyncio.create_task(
                        asyncio.to_thread(
                            lambda: list(
                                runner.stream(
                                    "Hello",
                                    checkpoint=(lambda: None)
                                    if mode == "worker_stream"
                                    else None,
                                )
                            )
                        )
                    )
                await _wait_until(lambda: len(llm_limits._limiter._waiters) == 1)
                assert model.api_key == "shared-key"
                assert context.selected_model_own_keys[id(model)] is False
                if denial == "allowance":
                    charge_shared_cost(engine, context.user_id, 2_000_000)
                    error = CostQuotaExceededError
                else:
                    with Session(engine) as session:
                        if denial in {"global", "global_admin"}:
                            session.add(
                                UsageEvent(
                                    user_id=context.user_id,
                                    ts=datetime.now(timezone.utc),
                                    cost_micros=2_000,
                                    own_key=False,
                                )
                            )
                            error = GlobalCostQuotaExceededError
                        elif denial == "rate":
                            session.query(LlmRate).filter_by(
                                provider="openai", model="gpt-6.1-terra"
                            ).delete()
                            invalidate_rate_cache(engine)
                            error = CostRateUnavailableError
                        else:
                            user = session.get(User, context.user_id)
                            assert user is not None
                            user.shared_key_access = False
                            error = BudgetExceededError
                        session.commit()
                # A concurrent BYOK call can change this provider-wide hint.
                context.selected_own_key_providers["openai"] = True
            if mode in {"sync", "async"}:
                with pytest.raises(error):
                    await pending
            else:
                events = await pending
                assert not any(isinstance(event, Completed) for event in events)
                failure = events[-1]
                assert isinstance(failure, Failed)
                assert failure.code == error.__name__
            assert requests == []
            assert model.api_key == "shared-key"
            assert context.selected_model_own_keys[id(model)] is False
            assert llm_limits._limiter._active == 0
            with Session(engine) as session:
                assert session.query(UsageEvent).count() == int(
                    denial in {"global", "global_admin"}
                )
        finally:
            await runner.aclose()
            if isinstance(client, httpx.AsyncClient):
                await client.aclose()
            else:
                client.close()


@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_bound_byok_survives_shared_quota_exhaustion(policy, tmp_path, mode):
    from datetime import datetime, timezone

    from sqlalchemy.orm import Session

    from resume_tailor_harness.tenancy.context import use_context
    from resume_tailor_harness.tenancy.system_db import UsageEvent
    from tests.tenancy.test_spend_gate import _context, _engine
    from tests.test_agno_integration import _response

    policy.llm_global_concurrency = 1
    settings = policy.model_copy(
        update={
            "openai_route_mode": "api",
            "cost_quota_enforcement": "enforce",
            "global_monthly_cost_quota_micros": 1_000,
        }
    )
    engine = _engine(tmp_path)
    context = _context(
        tmp_path,
        engine,
        settings=settings,
        platform_provider_keys={},
        user_provider_keys={"openai": "personal-key"},
    )
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=_response("gpt-6.1-terra", []))

    with use_context(context):
        model = build_model("openai:gpt-6.1-terra", settings=settings)
        client = (
            httpx.AsyncClient(transport=httpx.MockTransport(respond))
            if mode == "async"
            else httpx.Client(transport=httpx.MockTransport(respond))
        )
        model.http_client = client
        runner = AgentRunner(Agent(model=model, telemetry=False), settings=settings)
        try:
            async with async_llm_call():
                pending = asyncio.create_task(
                    runner.arun("Hello")
                    if mode == "async"
                    else asyncio.to_thread(runner.run, "Hello")
                )
                await _wait_until(lambda: len(llm_limits._limiter._waiters) == 1)
                with Session(engine) as session:
                    session.add(
                        UsageEvent(
                            user_id=context.user_id,
                            ts=datetime.now(timezone.utc),
                            cost_micros=2_000,
                            own_key=False,
                        )
                    )
                    session.commit()
                context.selected_own_key_providers["openai"] = False
            await pending
            assert len(requests) == 1
            assert requests[0].headers["authorization"] == "Bearer personal-key"
            with Session(engine) as session:
                charged = session.query(UsageEvent).filter_by(own_key=True).one()
                assert charged.quota_cost_micros == 0
        finally:
            await runner.aclose()
            if isinstance(client, httpx.AsyncClient):
                await client.aclose()
            else:
                client.close()


@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_later_tool_hop_rechecks_funding_and_preserves_usage(
    policy, tmp_path, mode
):
    from sqlalchemy.orm import Session

    from resume_tailor_harness.tenancy.context import use_context
    from resume_tailor_harness.tenancy.limits import BudgetExceededError
    from resume_tailor_harness.tenancy.system_db import UsageEvent, User
    from tests.tenancy.test_spend_gate import _context, _engine
    from tests.test_agno_integration import _response

    settings = policy.model_copy(
        update={
            "openai_route_mode": "api",
            "cost_quota_enforcement": "enforce",
        }
    )
    engine = _engine(tmp_path)
    context = _context(
        tmp_path,
        engine,
        settings=settings,
        platform_provider_keys={"openai": "shared-key"},
    )

    def revoke_access() -> str:
        """Simulate a concurrent revocation between provider hops."""
        with Session(engine) as session:
            user = session.get(User, context.user_id)
            assert user is not None
            user.shared_key_access = False
            session.commit()
        return "Access was revoked"

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json=_response(
                "gpt-6.1-terra",
                [
                    {
                        "type": "function_call",
                        "id": "fc_revoke",
                        "call_id": "call_revoke",
                        "name": "revoke_access",
                        "arguments": "{}",
                        "status": "completed",
                    }
                ],
            ),
        )

    with use_context(context):
        model = build_model("openai:gpt-6.1-terra", settings=settings)
        client = (
            httpx.AsyncClient(transport=httpx.MockTransport(respond))
            if mode == "async"
            else httpx.Client(transport=httpx.MockTransport(respond))
        )
        model.http_client = client
        runner = AgentRunner(
            Agent(model=model, tools=[revoke_access], telemetry=False),
            settings=settings,
        )
        try:
            with pytest.raises(BudgetExceededError):
                if mode == "async":
                    await runner.arun("Call the tool, then answer")
                else:
                    await asyncio.to_thread(runner.run, "Call the tool, then answer")
            assert len(requests) == 1
            with Session(engine) as session:
                usage = session.query(UsageEvent).one()
                assert usage.input_tokens > 0
                assert usage.quota_cost_micros > 0
        finally:
            await runner.aclose()
            if isinstance(client, httpx.AsyncClient):
                await client.aclose()
            else:
                client.close()


@pytest.mark.parametrize(
    "operation",
    ["decisions", "search", "embeddings", "transcribe", "gemini_transcribe", "speech"],
)
async def test_queued_direct_calls_recheck_shared_access(
    policy, monkeypatch, tmp_path, operation
):
    import openai
    from google import genai
    from sqlalchemy.orm import Session

    from resume_tailor_harness import llm_runner
    from resume_tailor_harness.decisions import ChoiceQuestion, DecisionClient
    from resume_tailor_harness.deepseek_search import DeepSeekSearchTools
    from resume_tailor_harness.taxonomy.embeddings import (
        EmbeddingUnavailable,
        OpenAIEmbeddingProvider,
    )
    from resume_tailor_harness.tenancy.context import use_context
    from resume_tailor_harness.tenancy.limits import BudgetExceededError
    from resume_tailor_harness.tenancy.system_db import User
    from tests.tenancy.test_spend_gate import _context, _engine

    policy.llm_global_concurrency = 1
    settings = policy.model_copy(
        update={
            "openai_api_key": "shared-key",
            "gemini_api_key": "shared-key",
            "deepseek_api_key": "shared-key",
            "openai_route_mode": "api",
            "gemini_route_mode": "api",
            "deepseek_route_mode": "api",
            "openai_decisions_enabled": True,
            "openai_decisions_api_key": "dedicated-key",
            "cost_quota_enforcement": "shadow",
        }
    )
    engine = _engine(tmp_path)
    context = _context(
        tmp_path,
        engine,
        settings=settings,
        platform_provider_keys={
            provider: "shared-key" for provider in ("openai", "gemini", "deepseek")
        },
        user_provider_keys={
            provider: "personal-key" for provider in ("openai", "gemini", "deepseek")
        },
    )
    requests = []

    def forbidden(*args, **kwargs):
        requests.append((args, kwargs))
        raise AssertionError("A denied call must not reach the provider")

    endpoint = SimpleNamespace(create=forbidden)
    fake_client = SimpleNamespace(
        embeddings=endpoint,
        audio=SimpleNamespace(transcriptions=endpoint, speech=endpoint),
        models=SimpleNamespace(generate_content=forbidden),
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: fake_client)
    monkeypatch.setattr(genai, "Client", lambda **kwargs: fake_client)
    monkeypatch.setattr(llm_runner, "get_settings", lambda: settings)
    original_sync = httpx.Client
    original_async = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_sync(
            transport=httpx.MockTransport(forbidden), **kwargs
        ),
    )
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async(
            transport=httpx.MockTransport(forbidden), **kwargs
        ),
    )
    decisions = DecisionClient(settings)
    sizes = []
    with use_context(context):
        async with async_llm_call():
            if operation == "decisions":
                pending = asyncio.create_task(
                    decisions.choose(
                        [
                            ChoiceQuestion(
                                "python", "Classify", {"language": "Language"}
                            )
                        ],
                        before_request=sizes.append,
                    )
                )
            else:

                def call():
                    if operation == "search":
                        return DeepSeekSearchTools(settings=settings).web_search(
                            "Python"
                        )
                    if operation == "embeddings":
                        return OpenAIEmbeddingProvider()._embed_sync(["Python"])
                    if operation == "speech":
                        return llm_runner.synthesize_speech(
                            "Hello", model_id="openai:gpt-4o-mini-tts"
                        )
                    model_id = (
                        "gemini:gemini-3.5-flash-lite"
                        if operation == "gemini_transcribe"
                        else "openai:gpt-4o-mini-transcribe"
                    )
                    return llm_runner.transcribe(
                        b"audio", "audio/webm", model_id=model_id
                    )

                pending = asyncio.create_task(asyncio.to_thread(call))
            await _wait_until(lambda: len(llm_limits._limiter._waiters) == 1)
            with Session(engine) as session:
                user = session.get(User, context.user_id)
                assert user is not None
                user.shared_key_access = False
                session.commit()
        if operation == "decisions":
            assert await pending == {}
            assert decisions.failed and decisions.calls == 0
            assert sizes == []
        elif operation == "embeddings":
            with pytest.raises(EmbeddingUnavailable) as caught:
                await pending
            assert isinstance(caught.value.__cause__, BudgetExceededError)
        else:
            with pytest.raises(BudgetExceededError):
                await pending
        assert requests == []
        assert llm_limits._limiter._active == 0
