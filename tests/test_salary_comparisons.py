import pytest
from sqlmodel import Session

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.discovery.filter import apply_filters
from resume_tailor_harness.discovery.search_config import SearchConfig
from resume_tailor_harness.models.job import JobCriteria, SalaryRange
from resume_tailor_harness.tracking.board_query import BoardFilter, board_page
from resume_tailor_harness.tracking.tables import Job


@pytest.mark.parametrize(
    "amount,currency,period,keep",
    [
        (100, "USD", "hour", True),
        (10_000, "USD", "month", False),
        (12_500, "usd", "month", True),
        (120_000, "EUR", "year", True),
        (120_000, "USD", "unknown", True),
        (120_000, "USD", "year", False),
    ],
)
def test_discovery_salary_threshold_compares_only_annual_usd(
    amount, currency, period, keep
):
    criteria = JobCriteria(
        salary_range=SalaryRange(maximum=amount, currency=currency, period=period)
    )
    assert apply_filters(criteria, SearchConfig(min_salary=150_000)).keep is keep


def test_board_salary_filter_and_sort_share_comparable_units(tmp_path):
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as session:
        for title, amount, currency, period in [
            ("hourly", 100, "USD", "hour"),
            ("annual", 180_000, "USD", "year"),
            ("monthly", 10_000, "USD", "month"),
            ("foreign", 5_000_000, "JPY", "year"),
        ]:
            session.add(
                Job(
                    source="manual",
                    title=title,
                    status="shortlisted",
                    criteria_json={
                        "salary_range": {
                            "maximum": amount,
                            "currency": currency,
                            "period": period,
                        }
                    },
                )
            )
        session.commit()
        jobs, count = board_page(
            session,
            "shortlist",
            BoardFilter(min_salary=150_000, sort="salary"),
            page=1,
            page_size=20,
            aliases_path=tmp_path / "aliases.json",
        )
        assert count == 3
        assert [job.title for job in jobs] == ["hourly", "annual", "foreign"]
    engine.dispose()
