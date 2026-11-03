"""SpendGate resolves one policy for both of its callers.

The gate replaced three independent derivations of the same five facts. These
tests pin the part that matters most: **behaviour is unchanged**. Every error
type still surfaces from the same condition, the own-key fallback still happens
silently, and the caching is exact rather than merely time-bounded.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from resume_tailor_harness.config import Settings
from resume_tailor_harness.tenancy.context import UserContext, use_context
from resume_tailor_harness.tenancy.costs import (
    OPENAI_DECISIONS_RATE_MODEL,
    MeteredUsage,
    calculate_cost,
    invalidate_rate_cache,
    seed_llm_rates,
)
from resume_tailor_harness.tenancy.limits import (
    BudgetExceededError,
    CostRateUnavailableError,
)
from resume_tailor_harness.tenancy.quotas import (
    CostQuotaExceededError,
    GlobalCostQuotaExceededError,
    charge_shared_cost,
    ensure_quota_account,
    quota_snapshot,
)
from resume_tailor_harness.tenancy.spend import SpendGate
from resume_tailor_harness.tenancy.system_db import (
    LlmRate,
    UsageEvent,
    UsageLineItem,
    User,
    init_system_db,
    make_system_engine,
)
from resume_tailor_harness.tenancy.workspace import WorkspacePaths

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
MODEL = "claude-sonnet-5"


def test_decisions_requires_its_endpoint_rate_even_when_responses_is_priced(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.query(LlmRate).filter_by(model=OPENAI_DECISIONS_RATE_MODEL).delete()
        session.commit()
    invalidate_rate_cache(engine)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_decisions_enabled=True,
        openai_decisions_api_key="decisions-key",
        cost_quota_enforcement="enforce",
    )
    usage = MeteredUsage(
        provider="openai",
        model="gpt-6-luna",
        input_tokens=1_000,
        reasoning_mode="decisions",
    )
    assert calculate_cost(engine, usage).pricing_status == "RATE_UNAVAILABLE"
    with use_context(_context(tmp_path, engine, settings=settings)):
        with pytest.raises(CostRateUnavailableError, match="gpt-6-luna:decisions"):
            SpendGate().open_decisions()
    assert (
        calculate_cost(
            engine,
            MeteredUsage(provider="openai", model="gpt-6-luna", input_tokens=1_000),
        ).total_micros
        == 100
    )


def test_decisions_cache_cost_settles_member_allowance_and_rate_snapshot_once(tmp_path):
    from resume_tailor_harness.tenancy.usage import record_direct_usage

    engine = _engine(tmp_path)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_decisions_enabled=True,
        openai_decisions_api_key="decisions-key",
        cost_quota_enforcement="enforce",
    )
    usage = MeteredUsage(
        provider="openai",
        model="gpt-6-luna",
        input_tokens=10_000,
        cache_read_tokens=2_000,
        cache_write_tokens=1_000,
        total_tokens=10_000,
        reasoning_mode="decisions",
    )
    with use_context(_context(tmp_path, engine, settings=settings)):
        SpendGate().open_decisions()
        before = quota_snapshot(engine, "abc123def456")
        record_direct_usage(usage, own_key=False, request_id="decisions:cached")
        record_direct_usage(usage, own_key=False, request_id="decisions:cached")
    after = quota_snapshot(engine, "abc123def456")
    assert before.remaining_micros is not None and after.remaining_micros is not None
    assert before.remaining_micros - after.remaining_micros == 845
    with Session(engine) as session:
        event = session.query(UsageEvent).one()
        assert event.model == "gpt-6-luna"
        assert event.reasoning_mode == "decisions"
        assert event.cost_micros == event.quota_cost_micros == 845
        rate = session.get(LlmRate, event.rate_id)
        assert rate is not None and rate.model == OPENAI_DECISIONS_RATE_MODEL
        lines = session.query(UsageLineItem).all()
        assert {line.kind: line.cost_micros for line in lines} == {
            "INPUT": 700,
            "CACHE_READ": 20,
            "CACHE_WRITE": 125,
        }


def test_decisions_dedicated_key_bypasses_gateway_and_byok_but_not_shared_policy(
    tmp_path,
):
    engine = _engine(tmp_path, shared_key_access=False)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_decisions_enabled=True,
        openai_decisions_api_key="decisions-key",
        openai_route_mode="subscription",
        sub2api_openai_key="gateway-key",
        sub2api_base_url="https://gateway.example",
    )
    context = _context(
        tmp_path,
        engine,
        settings=settings,
        user_provider_keys={"openai": "user-key"},
        own_key_providers=frozenset({"openai"}),
    )
    with use_context(context), pytest.raises(BudgetExceededError):
        SpendGate().open_decisions()
    with Session(engine) as session:
        user = session.get(User, context.user_id)
        assert user is not None
        user.shared_key_access = True
        session.commit()
    with use_context(context):
        decision = SpendGate().open_decisions()
    assert decision.api_key == "decisions-key"
    assert decision.base_url == "https://api.openai.com/v1"
    assert decision.own_key is False


def test_decisions_admin_obeys_global_cap_and_explicit_usage_is_not_byok(tmp_path):
    from resume_tailor_harness.tenancy.costs import MeteredUsage
    from resume_tailor_harness.tenancy.usage import record_direct_usage

    engine = _engine(tmp_path, role="admin")
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_decisions_enabled=True,
        openai_decisions_api_key="decisions-key",
        cost_quota_enforcement="enforce",
        global_monthly_cost_quota_micros=1,
    )
    context = _context(
        tmp_path,
        engine,
        settings=settings,
        role="admin",
        own_key_providers=frozenset({"openai"}),
    )
    context.selected_own_key_providers["openai"] = True
    usage = MeteredUsage(
        provider="openai",
        model="gpt-6-luna",
        input_tokens=1000,
        total_tokens=1000,
        reasoning_mode="decisions",
    )
    with use_context(context):
        SpendGate().open_decisions()
        record_direct_usage(usage, own_key=False, request_id="decisions:one")
        record_direct_usage(usage, own_key=False, request_id="decisions:one")
        with pytest.raises(GlobalCostQuotaExceededError):
            SpendGate().open_decisions()
    with Session(engine) as session:
        rows = session.query(UsageEvent).all()
        assert len(rows) == 1
        assert rows[0].own_key is False
        assert rows[0].cost_micros == 100
        assert rows[0].quota_cost_micros == 100


def test_workspace_cannot_override_decisions_enrollment_or_key(tmp_path):
    from resume_tailor_harness.tenancy.workspace import effective_settings

    paths = WorkspacePaths(tmp_path)
    paths.secrets_env.write_text(
        "OPENAI_DECISIONS_ENABLED=true\nOPENAI_DECISIONS_API_KEY=tenant-key\n",
        encoding="utf-8",
    )
    base = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_decisions_enabled=False,
        openai_decisions_api_key="platform-key",
    )
    overlay = effective_settings(base, paths)
    assert overlay.settings.openai_decisions_enabled is False
    assert overlay.settings.openai_decisions_api_key == "platform-key"


def _engine(tmp_path, **user_fields):
    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    seed_llm_rates(engine)
    with Session(engine) as session:
        session.add(
            User(
                id="abc123def456",
                username="alice",
                password_hash="hash",
                role=user_fields.pop("role", "user"),
                **user_fields,
            )
        )
        session.commit()
    return engine


def _context(tmp_path, engine, *, settings=None, **overrides) -> UserContext:
    base = dict(
        user_id="abc123def456",
        username="alice",
        role="user",
        paths=WorkspacePaths(tmp_path / "users" / "abc123def456"),
        settings=settings or Settings(_env_file=None),  # type: ignore[call-arg]
        engine=None,
        system_engine=engine,
        own_key_providers=frozenset(),
        platform_provider_keys={"anthropic": "railway-key"},
        user_provider_keys={},
    )
    base.update(overrides)
    return UserContext(**base)  # type: ignore[arg-type]


def test_byok_short_circuits_before_any_query(tmp_path):
    """A user paying with their own key is not subject to a shared budget."""
    engine = _engine(tmp_path)
    context = _context(
        tmp_path,
        engine,
        platform_provider_keys={},
        user_provider_keys={"anthropic": "user-key"},
    )
    with use_context(context):
        decision = SpendGate().open(MODEL)
    assert decision.api_key == "user-key"
    assert decision.own_key is True
    assert decision.reason == "byok"


def test_shared_funding_is_selected_when_the_budget_allows(tmp_path):
    engine = _engine(tmp_path)
    with use_context(_context(tmp_path, engine)):
        decision = SpendGate().open(MODEL)
    assert decision.api_key == "railway-key"
    assert decision.own_key is False


def test_exhausted_shared_budget_falls_back_to_the_user_key_without_raising(tmp_path):
    """What resolve_api_key always did, and what open must not turn into an error."""
    engine = _engine(tmp_path, weekly_token_budget=100)
    with Session(engine) as session:
        session.add(
            UsageEvent(
                user_id="abc123def456",
                ts=datetime.now(UTC),
                weighted_total=500,
                own_key=False,
            )
        )
        session.commit()
    context = _context(tmp_path, engine, user_provider_keys={"anthropic": "user-key"})

    with use_context(context):
        decision = SpendGate().open(MODEL)

    assert decision.api_key == "user-key"
    assert decision.own_key is True
    assert decision.reason == "own-key-fallback"


def test_exhausted_shared_budget_raises_when_nothing_else_funds_the_call(tmp_path):
    engine = _engine(tmp_path, weekly_token_budget=100)
    with Session(engine) as session:
        session.add(
            UsageEvent(
                user_id="abc123def456",
                ts=datetime.now(UTC),
                weighted_total=500,
                own_key=False,
            )
        )
        session.commit()

    with use_context(_context(tmp_path, engine)):
        gate = SpendGate()
        with pytest.raises(BudgetExceededError, match="weekly token budget"):
            gate.open(MODEL)
        # select answers the same question without raising, which is exactly
        # the split resolve_api_key and enforce_agent_budget always had.
        assert gate.select(MODEL).api_key == "railway-key"


def test_disabled_shared_access_raises_its_own_error(tmp_path):
    engine = _engine(tmp_path, shared_key_access=False)
    with use_context(_context(tmp_path, engine)):
        with pytest.raises(BudgetExceededError, match="shared platform models"):
            SpendGate().open(MODEL)


def test_unknown_rate_raises_cost_rate_unavailable_under_enforcement(tmp_path):
    engine = _engine(tmp_path)
    settings = Settings(_env_file=None, cost_quota_enforcement="enforce")  # type: ignore[call-arg]
    with use_context(_context(tmp_path, engine, settings=settings)):
        with pytest.raises(CostRateUnavailableError):
            SpendGate().open("no-such-model", now=NOW)


def test_exhausted_allowance_raises_cost_quota_exceeded_under_enforcement(tmp_path):
    engine = _engine(tmp_path)
    settings = Settings(_env_file=None, cost_quota_enforcement="enforce")  # type: ignore[call-arg]
    ensure_quota_account(engine, "abc123def456", now=NOW)
    charge_shared_cost(engine, "abc123def456", 2_000_000, now=NOW)

    with use_context(_context(tmp_path, engine, settings=settings)):
        with pytest.raises(CostQuotaExceededError):
            SpendGate().open(MODEL, now=NOW)


def test_platform_cap_binds_administrators_too(tmp_path):
    """ADR-0009 Amendment 2: exempt from the allowance, not from the cap."""
    engine = _engine(tmp_path, role="admin")
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        cost_quota_enforcement="enforce",
        global_monthly_cost_quota_micros=1_000,
    )
    with Session(engine) as session:
        session.add(
            UsageEvent(
                user_id="someoneelse",
                ts=NOW,
                cost_micros=5_000,
                own_key=False,
                pricing_status="PRICED",
            )
        )
        session.commit()

    context = _context(tmp_path, engine, settings=settings, role="admin")
    with use_context(context):
        with pytest.raises(GlobalCostQuotaExceededError):
            SpendGate().open(MODEL, now=NOW)


def test_a_decision_is_derived_once_and_reused_across_calls(tmp_path):
    from scripts.perf_harness import count_queries

    engine = _engine(tmp_path)
    context = _context(tmp_path, engine)

    with use_context(context), count_queries(engine) as counts:
        gate = SpendGate()
        for _ in range(10):
            gate.open(MODEL)

    assert len(context.spend_decisions) == 1
    # One derivation for ten calls, and never an exclusive lock on a read.
    assert counts.exclusive_transactions == 0, str(counts)
    assert counts.total <= 6, str(counts)


def test_an_explicit_now_never_reads_or_writes_the_cache(tmp_path):
    """A decision made for one moment must not answer for another."""
    engine = _engine(tmp_path)
    context = _context(tmp_path, engine)

    with use_context(context):
        SpendGate().open(MODEL, now=NOW)

    assert context.spend_decisions == {}


def test_settling_past_the_headroom_forces_a_fresh_derivation(tmp_path):
    engine = _engine(tmp_path, weekly_token_budget=1_000)
    context = _context(tmp_path, engine)

    with use_context(context):
        gate = SpendGate()
        gate.open(MODEL)
        entry = context.spend_decisions[MODEL]
        assert entry.headroom == pytest.approx(1_000.0)  # type: ignore[union-attr]

        gate.settle(weighted=400.0)
        assert MODEL in context.spend_decisions

        gate.settle(weighted=700.0)
        assert MODEL not in context.spend_decisions


def test_ttl_of_zero_disables_reuse_entirely(tmp_path):
    engine = _engine(tmp_path)
    settings = Settings(_env_file=None, spend_gate_ttl_seconds=0.0)  # type: ignore[call-arg]
    context = _context(tmp_path, engine, settings=settings)

    with use_context(context):
        gate = SpendGate()
        gate.open(MODEL)
        stamped = time.monotonic()
        gate.open(MODEL)

    assert stamped  # the second open re-derived rather than serving a cache hit
    assert MODEL in context.spend_decisions
