from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from resume_tailor_harness.tenancy import costs
from resume_tailor_harness.tenancy.system_db import LlmRate, SystemBase


@pytest.mark.parametrize(
    "has_old,has_new", [(True, True), (False, True), (True, False)]
)
def test_pricing_and_funding_caches_follow_effective_dates(
    tmp_path, monkeypatch, has_old, has_new
):
    engine = create_engine(f"sqlite:///{tmp_path / 'rates.db'}")
    SystemBase.metadata.create_all(engine)
    cut = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    with Session(engine) as session:
        for enabled, rate_id, start, end in [
            (has_old, "old", cut - timedelta(days=1), cut),
            (has_new, "new", cut, None),
        ]:
            if enabled:
                session.add(
                    LlmRate(
                        id=rate_id,
                        provider="anthropic",
                        model="boundary",
                        effective_from=start,
                        effective_to=end,
                        input_micros_per_million=1,
                        output_micros_per_million=1,
                        source_url="https://example.com/rates",
                    )
                )
        session.commit()
    clock = [cut - timedelta(seconds=1)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(costs, "datetime", Clock)
    assert costs.has_active_rate(engine, "anthropic", "boundary") is has_old
    before = costs.find_rate(engine, "anthropic", "boundary")
    assert (before.id if before else None) == ("old" if has_old else None)
    clock[0] = cut + timedelta(seconds=1)
    assert costs.has_active_rate(engine, "anthropic", "boundary") is has_new
    after = costs.find_rate(engine, "anthropic", "boundary")
    assert (after.id if after else None) == ("new" if has_new else None)
    engine.dispose()
