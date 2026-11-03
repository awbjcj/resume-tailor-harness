import asyncio
import json

import httpx
import pytest

from resume_tailor_harness import decisions
from resume_tailor_harness.config import Settings
from resume_tailor_harness.decisions import ChoiceQuestion, DecisionClient
from resume_tailor_harness.tenancy.usage import UsageSettlementError
from resume_tailor_harness.tenancy.limits import (
    BudgetExceededError,
    CostRateUnavailableError,
)
from resume_tailor_harness.tenancy.quotas import (
    CostQuotaExceededError,
    GlobalCostQuotaExceededError,
)


def enabled_settings(**kwargs):
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_decisions_enabled=True,
        openai_decisions_api_key="direct-test-key",
        **kwargs,
    )


def answer(name="q0", choice="o0", confidence=0.99):
    return {
        "type": "choice",
        "name": name,
        "choice": choice,
        "confidence": confidence,
        "probabilities": [
            {"value": "o0", "probability": 0.99},
            {"value": "defer", "probability": 0.01},
        ],
    }


def receipt(answers=None):
    return {
        "id": "dec-test",
        "model": "gpt-6-luna",
        "answers": answers if answers is not None else [answer()],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 0,
            "total_tokens": 100,
            "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 10},
        },
    }


@pytest.fixture
def transport(monkeypatch):
    calls = []
    receipts = []
    options = []
    original = httpx.AsyncClient

    def install(handler):
        def capture(request):
            calls.append(request)
            return handler(request)

        def client(**kwargs):
            options.append(kwargs)
            return original(transport=httpx.MockTransport(capture), **kwargs)

        monkeypatch.setattr(decisions.httpx, "AsyncClient", client)

    monkeypatch.setattr(
        decisions,
        "record_direct_usage",
        lambda usage, **kwargs: receipts.append((usage, kwargs)),
    )
    return install, calls, receipts, options


async def test_direct_route_ignores_gateway_base_url_and_records_explicit_shared_usage(
    transport,
):
    install, calls, receipts, options = transport
    install(lambda _: httpx.Response(200, json=receipt()))
    client = DecisionClient(
        enabled_settings(
            openai_base_url="https://untrusted.example/v1",
            openai_route_mode="subscription",
            sub2api_openai_key="gateway-test-key",
            sub2api_base_url="https://gateway.example",
        )
    )
    sizes = []
    result = await client.choose(
        [
            ChoiceQuestion(
                "python", "Classify python", {"languages": "Programming Languages"}
            )
        ],
        before_request=sizes.append,
    )
    assert result == {"python": "languages"}
    assert str(calls[0].url) == decisions.ENDPOINT
    assert calls[0].headers["authorization"] == "Bearer direct-test-key"
    assert options[0]["follow_redirects"] is False and options[0]["trust_env"] is False
    payload = json.loads(calls[0].content)
    assert payload["model"] == "gpt-6-luna"
    assert payload["questions"][0]["choices"][-1]["value"] == "defer"
    assert sizes == [len(calls[0].content)]
    usage, kwargs = receipts[0]
    assert (
        usage.input_tokens,
        usage.cache_read_tokens,
        usage.cache_write_tokens,
        usage.output_tokens,
    ) == (100, 20, 10, 0)
    assert kwargs == {"own_key": False, "request_id": "decisions:dec-test"}
    assert client.calls == client.accepted == 1


@pytest.mark.parametrize(
    "configured,enabled", [(False, False), (True, False), (False, True)]
)
async def test_default_or_unconfigured_client_never_sends(
    transport, configured, enabled
):
    install, calls, _, _ = transport
    install(lambda _: pytest.fail("unexpected paid request"))
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_decisions_api_key="key" if configured else "",
        openai_decisions_enabled=enabled,
    )
    assert (
        await DecisionClient(settings).choose(
            [ChoiceQuestion("python", "Classify", {"a": "A"})]
        )
        == {}
    )
    assert not calls


@pytest.mark.parametrize("status", [401, 429, 500, 307])
async def test_provider_failure_opens_operation_circuit_without_retries(
    transport, status
):
    install, calls, receipts, _ = transport
    install(
        lambda _: httpx.Response(
            status,
            text="private provider error",
            headers={"location": "https://evil.example"},
        )
    )
    client = DecisionClient(enabled_settings())
    questions = [ChoiceQuestion("python", "Classify", {"a": "A"})]
    assert await client.choose(questions) == {}
    assert await client.choose(questions) == {}
    assert len(calls) == 1 and not receipts


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "refusal", "name": "q0"},
        answer(choice="invented"),
        answer(choice="defer"),
        answer(confidence=0.89),
        answer(confidence=float("nan")),
        answer(confidence=True),
        {
            **answer(),
            "probabilities": [
                {"value": "o0", "probability": 0.55},
                {"value": "defer", "probability": 0.45},
            ],
        },
        {**answer(), "probabilities": [{"value": "o0", "probability": 0.99}]},
    ],
)
def test_uncertain_or_malformed_answers_are_not_published(bad):
    assert (
        decisions._answers(
            {"answers": [bad]},
            [ChoiceQuestion("python", "Classify", {"languages": "Languages"})],
        )
        == {}
    )


def test_duplicates_fail_closed_and_shuffled_names_are_matched():
    questions = [
        ChoiceQuestion("python", "Classify", {"languages": "Languages"}),
        ChoiceQuestion("docker", "Classify", {"cloud": "Cloud"}),
    ]
    assert decisions._answers({"answers": [answer("q1"), answer("q0")]}, questions) == {
        "python": "languages",
        "docker": "cloud",
    }
    assert decisions._answers(
        {"answers": [answer("q0"), answer("q0"), answer("q1")]}, questions
    ) == {"docker": "cloud"}


async def test_refused_outputs_are_still_metered(transport):
    install, _, receipts, _ = transport
    install(
        lambda _: httpx.Response(200, json=receipt([{"type": "refusal", "name": "q0"}]))
    )
    assert (
        await DecisionClient(enabled_settings()).choose(
            [ChoiceQuestion("x", "Classify", {"a": "A"})]
        )
        == {}
    )
    assert len(receipts) == 1


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"input_tokens": -1},
        {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11},
    ],
)
async def test_invalid_receipts_surface_accounting_error(transport, usage):
    install, _, _, _ = transport
    install(lambda _: httpx.Response(200, json={**receipt(), "usage": usage}))
    with pytest.raises(UsageSettlementError):
        await DecisionClient(enabled_settings()).choose(
            [ChoiceQuestion("x", "Classify", {"a": "A"})]
        )


async def test_settlement_failure_is_not_a_silent_fallback(transport, monkeypatch):
    install, calls, _, _ = transport
    install(lambda _: httpx.Response(200, json=receipt()))

    def fail(*args, **kwargs):
        raise UsageSettlementError("ledger unavailable")

    monkeypatch.setattr(decisions, "record_direct_usage", fail)
    with pytest.raises(UsageSettlementError):
        await DecisionClient(enabled_settings()).choose(
            [ChoiceQuestion("x", "Classify", {"a": "A"})]
        )
    assert len(calls) == 1


async def test_admission_limit_prevents_http(transport):
    install, calls, _, _ = transport
    install(lambda _: pytest.fail("budget exceeded"))

    def reject(_size):
        raise RuntimeError("budget exceeded")

    with pytest.raises(RuntimeError, match="budget exceeded"):
        await DecisionClient(enabled_settings()).choose(
            [ChoiceQuestion("x", "Classify", {"a": "A"})], before_request=reject
        )
    assert not calls


@pytest.mark.parametrize(
    "denial",
    [
        BudgetExceededError,
        CostRateUnavailableError,
        CostQuotaExceededError,
        GlobalCostQuotaExceededError,
    ],
)
async def test_shared_spend_denial_retains_standard_path_without_buying_requests(
    transport, monkeypatch, denial
):
    install, calls, receipts, _ = transport
    install(lambda _: pytest.fail("shared spending denied"))

    def reject(_gate):
        raise denial("shared funding unavailable")

    monkeypatch.setattr(decisions.SpendGate, "open_decisions", reject)
    client = DecisionClient(enabled_settings())
    questions = [ChoiceQuestion("python", "Classify", {"languages": "Languages"})]
    assert await client.choose(questions) == {}
    assert await client.choose(questions) == {}
    assert not calls and not receipts and client.calls == 0


async def test_disabled_sync_client_does_not_start_an_event_loop():
    client = DecisionClient(Settings(_env_file=None, openai_decisions_enabled=False))  # type: ignore[call-arg]
    assert (
        client.choose_sync(
            [ChoiceQuestion("python", "Classify", {"languages": "Languages"})]
        )
        == {}
    )


async def test_total_request_deadline_opens_circuit_without_retry(
    transport, monkeypatch
):
    install, calls, receipts, _ = transport

    async def slow(_request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=receipt())

    install(slow)
    monkeypatch.setattr(decisions, "REQUEST_TIMEOUT_SECONDS", 0.01)
    client = DecisionClient(enabled_settings())
    questions = [ChoiceQuestion("python", "Classify", {"languages": "Languages"})]
    assert await client.choose(questions) == {}
    assert await client.choose(questions) == {}
    assert len(calls) == 1 and not receipts and client.failed


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "different-model"},
        {"usage": {**receipt()["usage"], "input_tokens_details": []}},
    ],
)
async def test_incompatible_model_or_cache_receipt_cannot_be_mispriced(
    transport, changes
):
    install, _, receipts, _ = transport
    install(lambda _: httpx.Response(200, json={**receipt(), **changes}))
    with pytest.raises(UsageSettlementError):
        await DecisionClient(enabled_settings()).choose(
            [ChoiceQuestion("python", "Classify", {"languages": "Languages"})]
        )
    assert not receipts
