from decimal import Decimal

import pytest
from pydantic import ValidationError

from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    CrawlLimits,
    JobFacts,
    SalaryBand,
)


def test_unknown_facts_are_not_inferred():
    facts = JobFacts(source_url="https://example.com/jobs/1")
    assert facts.remote_policy is None
    assert facts.salary_bands is None
    assert facts.locations is None


def test_location_salary_bands_round_trip_without_conversion():
    facts = JobFacts(
        source_url="https://example.com/jobs/1",
        salary_bands=[
            SalaryBand(
                minimum=Decimal("40.50"),
                period="hour",
                raw_text="$40.50/hr",
                locations=["NY"],
            ),
            SalaryBand(
                minimum=Decimal("80"),
                currency="CAD",
                raw_text="CAD 80",
                locations=["Toronto"],
            ),
        ],
    )
    restored = JobFacts.model_validate_json(facts.model_dump_json())
    assert restored == facts
    assert restored.salary_bands[0].maximum is None


@pytest.mark.parametrize(
    "limits",
    [
        {"listing_pages": 51},
        {"detail_pages": 201},
        {"elapsed_seconds": 901},
        {"detail_pages": 0},
    ],
)
def test_crawl_limits_cannot_exceed_operator_caps(limits):
    with pytest.raises(ValidationError):
        CrawlLimits(**limits)


def test_board_without_pagination_needs_no_control():
    plan = BoardPlan(
        card_selector="article", detail_mode="inline", detail_selector=".description"
    )
    assert plan.pagination == "none"


@pytest.mark.parametrize(
    "values",
    [
        {"detail_mode": "link"},
        {"detail_mode": "panel", "open_selector": "button"},
        {"detail_mode": "inline", "pagination": "next"},
    ],
)
def test_plans_require_observable_navigation_controls(values):
    with pytest.raises(ValidationError):
        BoardPlan(card_selector="article", **values)


def test_negative_or_reversed_salary_rejected():
    with pytest.raises(ValidationError):
        SalaryBand(minimum=Decimal("100"), maximum=Decimal("50"), raw_text="100-50")
