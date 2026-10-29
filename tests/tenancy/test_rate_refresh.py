from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_tailor_harness.tenancy.costs import (
    MeteredUsage,
    calculate_cost,
    find_rate,
    seed_llm_rates,
)
from resume_tailor_harness.tenancy.system_db import (
    LlmRate,
    init_system_db,
    make_system_engine,
)


@pytest.fixture
def engine(tmp_path):
    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    yield engine
    engine.dispose()


@pytest.mark.parametrize(
    "model,short,long",
    [
        (
            "gpt-5.6-sol",
            (4_000_000, 400_000, 5_000_000, 20_000_000),
            (8_000_000, 800_000, 10_000_000, 30_000_000),
        ),
        (
            "gpt-5.6-terra",
            (2_000_000, 200_000, 2_500_000, 12_000_000),
            (4_000_000, 400_000, 5_000_000, 18_000_000),
        ),
        (
            "gpt-5.6-luna",
            (200_000, 20_000, 250_000, 1_200_000),
            (400_000, 40_000, 500_000, 1_800_000),
        ),
        (
            "gpt-5.5",
            (5_000_000, 500_000, None, 30_000_000),
            (10_000_000, 1_000_000, None, 45_000_000),
        ),
        (
            "gpt-5.5-pro",
            (30_000_000, None, None, 180_000_000),
            (60_000_000, None, None, 270_000_000),
        ),
    ],
)
def test_refresh_openai_context_bands_preserve_history(engine, model, short, long):
    before = datetime(2026, 10, 22, 23, 59, tzinfo=UTC)
    historical = find_rate(engine, "openai", model, input_tokens=272_001, now=before)
    assert historical is not None
    historical_id = historical.id
    seed_llm_rates(engine)
    now = datetime(2026, 10, 23, tzinfo=UTC)
    for count, expected in ((272_000, short), (272_001, long)):
        rate = find_rate(engine, "openai", model, input_tokens=count, now=now)
        assert rate is not None
        assert (
            rate.input_micros_per_million,
            rate.cache_read_micros_per_million,
            rate.cache_write_micros_per_million,
            rate.output_micros_per_million,
        ) == expected
        priced = calculate_cost(
            engine,
            MeteredUsage(
                provider="openai", model=model, input_tokens=count, output_tokens=1000
            ),
            now=now,
        )
        assert priced.total_micros == (
            (count * expected[0] + 999_999) // 1_000_000
            + (1000 * expected[3] + 999_999) // 1_000_000
        )
    preserved = find_rate(engine, "openai", model, input_tokens=272_001, now=before)
    assert preserved is not None and preserved.id == historical_id
    assert preserved.input_micros_per_million == short[0]
    with Session(engine) as session:
        rows = session.scalars(
            select(LlmRate).where(LlmRate.model == model, LlmRate.effective_from == now)
        ).all()
        assert len(rows) == 2


def test_sonnet_cache_cut_preserves_history_and_repairs_existing_rate(engine):
    model = "claude-sonnet-5-5"
    before = datetime(2026, 10, 6, 23, 59, tzinfo=UTC)
    after = datetime(2026, 10, 7, tzinfo=UTC)
    usage = MeteredUsage(provider="anthropic", model=model, cache_read_tokens=1_000_000)
    assert calculate_cost(engine, usage, now=before).total_micros == 200_000
    assert calculate_cost(engine, usage, now=after).total_micros == 100_000
    rate = find_rate(engine, "anthropic", model, now=after)
    assert rate is not None
    rate_id = rate.id
    with Session(engine) as session:
        row = session.get(LlmRate, rate_id)
        assert row is not None
        row.cache_read_micros_per_million = 200_000
        session.commit()
    seed_llm_rates(engine)
    repaired = find_rate(engine, "anthropic", model, now=after)
    assert repaired is not None and repaired.id == rate_id
    assert calculate_cost(engine, usage, now=after).total_micros == 100_000
    assert calculate_cost(engine, usage, now=before).total_micros == 200_000


@pytest.mark.parametrize(
    "model,start,expiry,promo,regular",
    [
        (
            "gemini-4-argon",
            datetime(2026, 10, 13, tzinfo=UTC),
            datetime(2026, 12, 1, tzinfo=UTC),
            (2_000_000, 100_000, 10_000_000),
            (4_000_000, 200_000, 20_000_000),
        ),
        (
            "gemini-3.5-flash",
            datetime(2026, 10, 23, tzinfo=UTC),
            datetime(2027, 1, 1, tzinfo=UTC),
            (750_000, 75_000, 3_750_000),
            (1_500_000, 150_000, 7_500_000),
        ),
    ],
)
def test_gemini_promotion_boundaries_and_cache_accounting(
    engine, model, start, expiry, promo, regular
):
    if model == "gemini-4-argon":
        assert find_rate(engine, "gemini", model, now=start.replace(day=12)) is None
    else:
        prior = find_rate(engine, "gemini", model, now=start.replace(day=22))
        assert prior is not None and prior.output_micros_per_million == 9_000_000
    for moment, expected in (
        (start, promo),
        (expiry - timedelta(microseconds=1), promo),
        (expiry, regular),
    ):
        rate = find_rate(engine, "gemini", model, now=moment)
        assert rate is not None
        assert (
            rate.input_micros_per_million,
            rate.cache_read_micros_per_million,
            rate.output_micros_per_million,
        ) == expected
        usage = MeteredUsage(
            provider="gemini",
            model=model,
            input_tokens=1_000_000,
            cache_read_tokens=1_000_000,
            output_tokens=1_000_000,
            tool_units=2,
        )
        assert calculate_cost(engine, usage, now=moment).total_micros == (
            expected[1] + expected[2] + 28_000
        )
    seed_llm_rates(engine)
    with Session(engine) as session:
        rows = session.scalars(
            select(LlmRate).where(
                LlmRate.model == model, LlmRate.effective_from >= start
            )
        ).all()
        assert len(rows) == 2
