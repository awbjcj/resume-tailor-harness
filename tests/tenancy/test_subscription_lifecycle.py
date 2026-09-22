from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from resume_tailor_harness.config import Settings
from resume_tailor_harness.tenancy.context import UserContext, use_context
from resume_tailor_harness.tenancy.quotas import (
    CostQuotaExceededError,
    IdempotencyConflictError,
    charge_shared_cost,
    grant_credit,
    quota_snapshot,
)
from resume_tailor_harness.tenancy.spend import SpendGate
from resume_tailor_harness.tenancy.subscriptions import apply_subscription
from resume_tailor_harness.tenancy.system_db import (
    QuotaAccount,
    QuotaLedgerEntry,
    UsageEvent,
    UsageLineItem,
    UsageReceipt,
    User,
    init_system_db,
    make_system_engine,
)
from resume_tailor_harness.tenancy.usage import UsageSettlementError, record_call
from resume_tailor_harness.tenancy.workspace import WorkspacePaths

USER = "abc123def456"
NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


@pytest.fixture
def engine(tmp_path):
    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    with Session(engine) as session:
        session.add(User(id=USER, username="alice", password_hash="hash", role="user"))
        session.commit()
    yield engine
    engine.dispose()


def command(engine, *, action="ACTIVATE", key="activate-once", now=NOW, **kwargs):
    return apply_subscription(
        engine,
        USER,
        actor_user_id="operator",
        action=action,
        tier_id="SUBSCRIBER",
        cycles=1,
        reason="paid invoice",
        idempotency_key=key,
        now=now,
        **kwargs,
    )


def context(tmp_path, engine, **settings):
    return UserContext(
        user_id=USER,
        username="alice",
        role="user",
        paths=WorkspacePaths(tmp_path / "users" / USER),
        settings=Settings(_env_file=None, cost_quota_enforcement="enforce", **settings),
        engine=None,
        system_engine=engine,
        own_key_providers=frozenset(),
        platform_provider_keys={"anthropic": "platform-key"},
    )


def test_subscription_renewal_is_repeat_safe_and_does_not_reset_consumption(engine):
    first = command(engine)
    assert first["expires_at"] == "2026-09-30T12:00:00+00:00"
    charge_shared_cost(engine, USER, 500_000, now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: command(engine, action="RENEW", key="renew-once"), range(2)
            )
        )
    assert results[0] == results[1]
    assert results[0]["expires_at"] == "2026-10-31T12:00:00+00:00"
    snapshot = quota_snapshot(engine, USER, now=NOW)
    assert snapshot.spent_micros == 500_000
    assert snapshot.remaining_micros == 19_500_000
    with pytest.raises(IdempotencyConflictError):
        command(engine, action="REVOKE", key="renew-once")


def test_expiry_and_restart_preserve_credits_without_granting_paid_allowance(
    engine, tmp_path
):
    command(engine)
    grant_credit(engine, USER, 300_000, now=NOW)
    engine.dispose()
    reopened = make_system_engine(tmp_path)
    try:
        init_system_db(reopened)
        snapshot = quota_snapshot(
            reopened, USER, now=datetime(2026, 9, 30, 12, tzinfo=UTC)
        )
        assert snapshot.tier_id == "FREE"
        assert snapshot.subscription_status == "EXPIRED"
        assert snapshot.credit_balance_micros == 300_000
        assert snapshot.remaining_micros == 1_300_000
        with Session(reopened) as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(QuotaLedgerEntry)
                    .where(QuotaLedgerEntry.kind == "SUBSCRIPTION_EXPIRED")
                )
                == 1
            )
    finally:
        reopened.dispose()


def test_revoke_then_renew_starts_a_new_term(engine):
    command(engine)
    command(engine, action="REVOKE", key="revoke-once", now=NOW + timedelta(days=1))
    assert quota_snapshot(engine, USER, now=NOW + timedelta(days=1)).tier_id == "FREE"
    result = command(
        engine, action="RENEW", key="renew-later", now=NOW + timedelta(days=2)
    )
    assert result["starts_at"] == (NOW + timedelta(days=2)).isoformat()
    assert (
        quota_snapshot(engine, USER, now=NOW + timedelta(days=2)).remaining_micros
        == 20_000_000
    )


def test_gateway_calls_consume_allowance_then_credit_and_exhaust(engine, tmp_path):
    ctx = context(
        tmp_path,
        engine,
        sub2api_base_url="https://gateway.example",
        sub2api_anthropic_key="gateway-key",
    )
    now = datetime.now(UTC)
    grant_credit(engine, USER, 1_000_000, now=now)
    response = SimpleNamespace(
        run_id="gateway-call",
        model="claude-sonnet-5",
        model_provider="anthropic",
        metrics={"input_tokens": 1_000_000},
    )
    with use_context(ctx):
        decision = SpendGate().open("claude-sonnet-5")
        assert not decision.own_key
        assert decision.api_key == "gateway-key"
        record_call(SimpleNamespace(), response)
        record_call(SimpleNamespace(), response)
        with pytest.raises(CostQuotaExceededError):
            SpendGate().open("claude-sonnet-5")
    snapshot = quota_snapshot(engine, USER)
    assert snapshot.remaining_micros == 0
    assert snapshot.spent_micros == 2_000_000
    assert snapshot.credit_spent_micros == 1_000_000
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(UsageEvent)) == 1
        assert session.scalar(select(func.count()).select_from(UsageReceipt)) == 1
        charge = session.scalar(
            select(QuotaLedgerEntry).where(QuotaLedgerEntry.kind == "USAGE")
        )
        assert charge.recurring_micros + charge.credit_micros == -charge.amount_micros


def test_transaction_failure_rolls_back_usage_and_can_retry(
    engine, tmp_path, monkeypatch
):
    from resume_tailor_harness.tenancy import usage

    ctx = context(tmp_path, engine)
    response = SimpleNamespace(
        run_id="retry-after-failure",
        model="claude-sonnet-5",
        model_provider="anthropic",
        metrics={"input_tokens": 100},
    )
    original = usage.charge_in_session

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated interrupted settlement")

    monkeypatch.setattr(usage, "charge_in_session", fail)
    with use_context(ctx), pytest.raises(UsageSettlementError):
        record_call(SimpleNamespace(), response)
    with Session(engine) as session:
        for table in (
            UsageEvent,
            UsageLineItem,
            UsageReceipt,
            QuotaAccount,
            QuotaLedgerEntry,
        ):
            assert session.scalar(select(func.count()).select_from(table)) == 0
    monkeypatch.setattr(usage, "charge_in_session", original)
    with use_context(ctx):
        record_call(SimpleNamespace(), response)
    assert quota_snapshot(engine, USER).spent_micros == 200


def test_concurrent_duplicate_settlement_charges_once(engine, tmp_path):
    response = SimpleNamespace(
        run_id="concurrent-call",
        model="claude-sonnet-5",
        model_provider="anthropic",
        metrics={"input_tokens": 100},
    )

    def settle(_):
        with use_context(context(tmp_path, engine)):
            record_call(SimpleNamespace(), response)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(settle, range(4)))
    assert quota_snapshot(engine, USER).spent_micros == 200
    response.metrics = {"input_tokens": 200}
    with use_context(context(tmp_path, engine)), pytest.raises(UsageSettlementError):
        record_call(SimpleNamespace(), response)


def test_cached_phase_observes_spend_from_other_requests(engine, tmp_path):
    with use_context(context(tmp_path, engine)):
        SpendGate().open("claude-sonnet-5")
        charge_shared_cost(engine, USER, 1_000_000)
        with pytest.raises(CostQuotaExceededError):
            SpendGate().open("claude-sonnet-5")
        grant_credit(engine, USER, 1000)
        SpendGate().open("claude-sonnet-5")
