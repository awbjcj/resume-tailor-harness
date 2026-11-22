import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_tailor_harness.config import Settings
from resume_tailor_harness import decisions
from resume_tailor_harness.decisions import ChoiceQuestion, DecisionClient
from resume_tailor_harness.audio_input import DecodedAudio
from resume_tailor_harness.services import official_audio
from resume_tailor_harness.tenancy.context import UserContext, use_context
from resume_tailor_harness.tenancy.costs import (
    OPENAI_TRANSCRIBE_MODEL,
    MeteredUsage,
    calculate_cost,
    invalidate_rate_cache,
)
from resume_tailor_harness.tenancy.openai_credit_budget import (
    CreditBudgetError,
    mark_submitted,
    reconcile,
    reserve,
    snapshot,
)
from resume_tailor_harness.tenancy.system_db import (
    OpenAICreditReservation,
    OpenAICreditReconciliation,
    LlmRate,
    UsageEvent,
    UsageLineItem,
    User,
    init_system_db,
    make_system_engine,
)
from resume_tailor_harness.tenancy.usage import record_direct_usage
from resume_tailor_harness.tenancy.workspace import WorkspacePaths, effective_settings


@pytest.fixture
def context(tmp_path):
    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    with Session(engine) as session:
        session.add(User(id="audio-user", username="audio", password_hash="", role="admin"))
        session.commit()
    now = datetime.now(timezone.utc)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_credit_budget_enabled=True,
        openai_credit_project_isolated=True,
        openai_credit_cycle_start=(now - timedelta(days=1)).isoformat(),
        openai_credit_cycle_end=(now + timedelta(days=1)).isoformat(),
        openai_credit_project_cap_micros=100_000,
    )
    yield UserContext(
        user_id="audio-user", username="audio", role="admin",
        paths=WorkspacePaths(tmp_path), settings=settings, engine=None,
        system_engine=engine, own_key_providers=frozenset(),
    )
    engine.dispose()


def test_duration_is_priced_and_recorded_without_token_fabrication(context):
    usage = MeteredUsage(provider="openai", model=OPENAI_TRANSCRIBE_MODEL, audio_input_microseconds=1_250_000)
    priced = calculate_cost(context.system_engine, usage)
    assert priced.total_micros == 94
    assert [(line.kind, line.units, line.rate_micros) for line in priced.lines] == [
        ("AUDIO_DURATION_US", 1_250_000, 4_500)
    ]
    with use_context(context):
        hold = reserve(request_id=str(uuid4()), operation="transcribe", model=OPENAI_TRANSCRIBE_MODEL, fingerprint="abc", amount_micros=150)
        mark_submitted(hold.id, usage)
        record_direct_usage(usage, own_key=False, request_id=hold.id, credit_reservation_id=hold.id, credit_result_text="edited later")
        state = snapshot()
    assert (state.spent_micros, state.held_micros) == (94, 0)
    with Session(context.system_engine) as session:
        event = session.scalar(select(UsageEvent))
        line = session.scalar(select(UsageLineItem))
        row = session.get(OpenAICreditReservation, hold.id)
        assert event is not None and event.audio_input_microseconds == 1_250_000
        assert event.input_tokens == event.output_tokens == 0
        assert line is not None and line.kind == "AUDIO_DURATION_US"
        assert row is not None and row.status == "settled"


def test_duplicate_request_cannot_be_submitted_twice(context):
    key = str(uuid4())
    with use_context(context):
        hold = reserve(request_id=key, operation="transcribe", model=OPENAI_TRANSCRIBE_MODEL, fingerprint="abc", amount_micros=100)
        mark_submitted(hold.id, MeteredUsage(provider="openai", model=OPENAI_TRANSCRIBE_MODEL, audio_input_microseconds=1_000_000))
        with pytest.raises(CreditBudgetError, match="already processing"):
            reserve(request_id=key, operation="transcribe", model=OPENAI_TRANSCRIBE_MODEL, fingerprint="abc", amount_micros=100)
        assert snapshot().held_micros == 100


def test_concurrent_reservations_cannot_exceed_optional_threshold(context):
    def attempt(_):
        with use_context(context):
            try:
                reserve(request_id=str(uuid4()), operation="transcribe", model=OPENAI_TRANSCRIBE_MODEL, fingerprint="abc", amount_micros=20_000)
                return True
            except CreditBudgetError:
                return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(attempt, range(8)))
    assert sum(accepted) == 4
    with use_context(context):
        state = snapshot()
    assert state.held_micros == 80_000 and state.warning


@pytest.mark.asyncio
async def test_decisions_usage_is_settled_in_the_same_credit_period(context, monkeypatch):
    settings = context.settings.model_copy(update={
        "openai_decisions_enabled": True, "openai_decisions_api_key": "test-key",
    })
    context = replace(context, settings=settings)
    original_client = httpx.AsyncClient
    calls = []

    def client(**kwargs):
        def handle(_request):
            calls.append(True)
            return httpx.Response(200, json={
                "id": "decision-1", "model": "gpt-6-luna", "answers": [],
                "usage": {"input_tokens": 100, "output_tokens": 0, "total_tokens": 100},
            })
        return original_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(decisions.httpx, "AsyncClient", client)
    with use_context(context):
        assert await DecisionClient(settings).choose([ChoiceQuestion("x", "Classify", {"a": "A"})]) == {}
        assert await DecisionClient(settings).choose([ChoiceQuestion("x", "Classify", {"a": "A"})]) == {}
        state = snapshot()
    assert (state.spent_micros, state.held_micros) == (10, 0)
    assert len(calls) == 1
    with Session(context.system_engine) as session:
        event = session.scalar(select(UsageEvent))
        assert event is not None and event.reasoning_mode == "decisions"


@pytest.mark.asyncio
async def test_cancelled_decisions_submission_keeps_its_hold(context, monkeypatch):
    settings = context.settings.model_copy(update={
        "openai_decisions_enabled": True, "openai_decisions_api_key": "test-key",
    })
    context = replace(context, settings=settings)
    original_client = httpx.AsyncClient
    submitted = asyncio.Event()
    calls = []

    async def block(_request):
        calls.append(True)
        submitted.set()
        await asyncio.Event().wait()
        return httpx.Response(500)

    def client(**kwargs):
        return original_client(transport=httpx.MockTransport(block), **kwargs)

    monkeypatch.setattr(decisions.httpx, "AsyncClient", client)
    with use_context(context):
        task = asyncio.create_task(DecisionClient(settings).choose([ChoiceQuestion("x", "Classify", {"a": "A"})]))
        await submitted.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await DecisionClient(settings).choose([ChoiceQuestion("x", "Classify", {"a": "A"})]) == {}
        state = snapshot()
    assert len(calls) == 1 and state.spent_micros == 0 and state.held_micros > 0


@pytest.mark.asyncio
async def test_decisions_falls_back_when_credit_changes_before_submission(context, monkeypatch):
    settings = context.settings.model_copy(update={
        "openai_decisions_enabled": True, "openai_decisions_api_key": "test-key",
    })
    context = replace(context, settings=settings)

    def deny(*_args, **_kwargs):
        raise CreditBudgetError("credit changed")

    monkeypatch.setattr(decisions, "mark_submitted", deny)
    with use_context(context):
        assert await DecisionClient(settings).choose([ChoiceQuestion("x", "Classify", {"a": "A"})]) == {}
        assert snapshot().held_micros == 0


def test_workspace_cannot_override_credit_policy_or_official_key(context):
    context.paths.root.mkdir(parents=True, exist_ok=True)
    context.paths.secrets_env.write_text(
        "OFFICIAL_AUDIO_API_KEY=attacker\nOPENAI_CREDIT_CYCLE_START=2000-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    settings = context.settings.model_copy(update={"official_audio_api_key": "platform-key"})
    overlay = effective_settings(settings, context.paths)
    assert overlay.settings.official_audio_api_key == "platform-key"
    assert overlay.settings.openai_credit_cycle_start == settings.openai_credit_cycle_start


def test_changed_rate_is_rechecked_before_submission(context):
    usage = MeteredUsage(provider="openai", model=OPENAI_TRANSCRIBE_MODEL, audio_input_microseconds=1_000_000)
    with use_context(context):
        hold = reserve(request_id=str(uuid4()), operation="transcribe", model=OPENAI_TRANSCRIBE_MODEL, fingerprint="abc", amount_micros=75)
        with Session(context.system_engine) as session:
            rate = session.scalar(select(LlmRate).where(LlmRate.model == OPENAI_TRANSCRIBE_MODEL))
            assert rate is not None
            rate.audio_input_micros_per_minute = 9_000
            session.commit()
        invalidate_rate_cache(context.system_engine)
        with pytest.raises(CreditBudgetError, match="rate exceeds"):
            mark_submitted(hold.id, usage)
        assert snapshot().held_micros == 75


def test_admin_reconciles_reported_usage_once_with_an_audit_record(context):
    usage = MeteredUsage(provider="openai", model=OPENAI_TRANSCRIBE_MODEL, audio_input_microseconds=2_000_000)
    with use_context(context):
        hold = reserve(request_id=str(uuid4()), operation="transcribe", model=OPENAI_TRANSCRIBE_MODEL, fingerprint="abc", amount_micros=150)
        mark_submitted(hold.id, usage)
        reconcile(hold.id, unbilled=False, reason="provider receipt 123", audio_input_microseconds=2_000_000)
        with pytest.raises(CreditBudgetError, match="not awaiting"):
            reconcile(hold.id, unbilled=False, reason="duplicate", audio_input_microseconds=2_000_000)
        assert snapshot().spent_micros == 150
        assert snapshot().held_micros == 0
    with Session(context.system_engine) as session:
        audits = list(session.scalars(select(OpenAICreditReconciliation)))
        assert len(audits) == 1
        assert (audits[0].actor_user_id, audits[0].outcome, audits[0].reason) == (context.user_id, "settled", "provider receipt 123")
        assert len(list(session.scalars(select(UsageEvent)))) == 1


def test_admin_can_release_only_a_confirmed_unbilled_hold(context):
    usage = MeteredUsage(provider="openai", model=OPENAI_TRANSCRIBE_MODEL, audio_input_microseconds=1_000_000)
    with use_context(context):
        hold = reserve(request_id=str(uuid4()), operation="transcribe", model=OPENAI_TRANSCRIBE_MODEL, fingerprint="abc", amount_micros=75)
        mark_submitted(hold.id, usage)
    with use_context(replace(context, role="user")):
        with pytest.raises(CreditBudgetError, match="administrator"):
            reconcile(hold.id, unbilled=True, reason="provider confirmed no charge")
    with use_context(context):
        reconcile(hold.id, unbilled=True, reason="provider confirmed no charge")
        assert snapshot().held_micros == 0
    with Session(context.system_engine) as session:
        audit = session.scalar(select(OpenAICreditReconciliation))
        assert audit is not None and audit.outcome == "unbilled"


def test_reconciliation_charges_the_original_member(context):
    with Session(context.system_engine) as session:
        session.add(User(id="member-user", username="member", password_hash="", role="user"))
        session.commit()
    member = replace(context, user_id="member-user", username="member", role="user")
    usage = MeteredUsage(provider="openai", model=OPENAI_TRANSCRIBE_MODEL, audio_input_microseconds=1_000_000)
    with use_context(member):
        hold = reserve(request_id=str(uuid4()), operation="transcribe", model=OPENAI_TRANSCRIBE_MODEL, fingerprint="abc", amount_micros=75)
        mark_submitted(hold.id, usage)
    with use_context(context):
        reconcile(hold.id, unbilled=False, reason="provider receipt", audio_input_microseconds=1_000_000)
    with Session(context.system_engine) as session:
        event = session.scalar(select(UsageEvent))
        assert event is not None and event.user_id == "member-user"
        assert event.quota_cost_micros == 75


def test_official_transcription_is_retry_safe_and_uses_fixed_endpoint(context, monkeypatch):
    settings = context.settings.model_copy(update={
        "official_audio_enabled": True, "official_audio_api_key": "dedicated-key",
        "openai_api_key": "other-key", "openai_base_url": "https://untrusted.example",
    })
    context = replace(context, settings=settings)
    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="editable transcript", usage=SimpleNamespace(type="duration", seconds=1.25))

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    recording = DecodedAudio(wav=b"validated-wav", sample_count=20_000)
    key = str(uuid4())
    with use_context(context):
        first = official_audio.transcribe(recording, key)
        repeated = official_audio.transcribe(recording, key)
        state = snapshot()
    assert first == repeated == official_audio.Transcript("editable transcript", False)
    assert len(calls) == 2
    assert calls[0]["api_key"] == "dedicated-key"
    assert calls[0]["base_url"] == "https://api.openai.com/v1"
    assert calls[0]["max_retries"] == 0
    assert calls[1]["model"] == OPENAI_TRANSCRIBE_MODEL
    assert state.spent_micros == 94 and state.held_micros == 0


def test_unreported_transcription_usage_keeps_the_hold_and_replays_text(context, monkeypatch):
    settings = context.settings.model_copy(update={"official_audio_enabled": True, "official_audio_api_key": "key"})
    context = replace(context, settings=settings)
    calls = []

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self.create))

        def create(self, **_kwargs):
            calls.append(True)
            return SimpleNamespace(text="retained transcript", usage=None)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    recording = DecodedAudio(wav=b"validated-wav", sample_count=20_000)
    key = str(uuid4())
    with use_context(context):
        assert official_audio.transcribe(recording, key).billing_pending
        assert official_audio.transcribe(recording, key).text == "retained transcript"
        state = snapshot()
    assert len(calls) == 1
    assert state.spent_micros == 0 and state.held_micros > 0


@pytest.mark.asyncio
async def test_cancelling_browser_wait_does_not_release_a_submitted_charge(context, monkeypatch):
    from starlette.concurrency import run_in_threadpool

    settings = context.settings.model_copy(update={"official_audio_enabled": True, "official_audio_api_key": "key"})
    context = replace(context, settings=settings)
    submitted = threading.Event()
    finish = threading.Event()

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self.create))

        def create(self, **_kwargs):
            submitted.set()
            assert finish.wait(10)
            return SimpleNamespace(text="result", usage=SimpleNamespace(type="duration", seconds=1.25))

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    with use_context(context):
        task = asyncio.create_task(run_in_threadpool(official_audio.transcribe, DecodedAudio(b"wav", 20_000), str(uuid4())))
        assert await asyncio.to_thread(submitted.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert snapshot().held_micros > 0
        finish.set()
        state = snapshot()
        for _ in range(100):
            state = snapshot()
            if state.held_micros == 0:
                break
            await asyncio.sleep(0.02)
        assert state.spent_micros == 94 and state.held_micros == 0


def test_official_speech_uses_the_same_credit_ledger(context, monkeypatch):
    settings = context.settings.model_copy(update={"official_audio_enabled": True, "official_audio_api_key": "key"})
    context = replace(context, settings=settings)
    calls = []
    monkeypatch.setattr(official_audio.realtime_speech, "encoder_available", lambda: True)

    def render(text, **kwargs):
        calls.append((text, kwargs))
        return b"\0\0", {
            "id": "speech-1", "status": "completed",
            "usage": {
                "input_tokens": 90, "output_tokens": 105, "total_tokens": 195,
                "input_token_details": {"cached_tokens": 20, "audio_tokens": 0},
                "output_token_details": {"audio_tokens": 100},
            },
        }

    monkeypatch.setattr(official_audio.realtime_speech, "render", render)
    monkeypatch.setattr(official_audio.realtime_speech, "pcm_to_mp3", lambda _: b"mp3")
    key = str(uuid4())
    with use_context(context):
        assert official_audio.synthesize("Practice question", key) == b"mp3"
        with pytest.raises(CreditBudgetError, match="already processing"):
            official_audio.synthesize("Practice question", key)
        state = snapshot()
    assert len(calls) == 1
    assert calls[0][1]["api_key"] == "key"
    assert calls[0][1]["base_url"] == "https://api.openai.com/v1"
    assert state.spent_micros > 0 and state.held_micros == 0


def test_failed_official_speech_retains_its_reservation(context, monkeypatch):
    settings = context.settings.model_copy(update={"official_audio_enabled": True, "official_audio_api_key": "key"})
    context = replace(context, settings=settings)
    monkeypatch.setattr(official_audio.realtime_speech, "encoder_available", lambda: True)

    def fail(*_args, **_kwargs):
        raise TimeoutError("no receipt")

    monkeypatch.setattr(official_audio.realtime_speech, "render", fail)
    with use_context(context):
        with pytest.raises(TimeoutError):
            official_audio.synthesize("Practice question", str(uuid4()))
        assert snapshot().held_micros > 0
