import pytest
from sqlalchemy import create_engine

from resume_tailor_harness.discovery.scraper.contracts import CrawlLimits
from resume_tailor_harness.discovery.scraper.pacing import (
    BudgetExceeded,
    CrawlBudget,
    HostScheduler,
    retry_delay,
    robots_decision,
)


def test_independent_workers_share_lease_cooldown_and_fencing(tmp_path):
    now = [10.0]
    url = f"sqlite:///{tmp_path / 'system.db'}"
    a = HostScheduler(create_engine(url), lambda: now[0])
    b = HostScheduler(create_engine(url), lambda: now[0])
    first = a.acquire("example.com", "a", 200)
    assert first is not None
    assert b.acquire("example.com", "b", 200) is None
    now[0] = 80
    second = b.acquire("example.com", "b", 200)
    assert second is not None
    assert a.renew(first) is False
    a.release(first, 3)
    assert a.acquire("example.com", "a", 200) is None
    b.release(second, 3)
    now[0] = 82
    assert a.acquire("example.com", "a", 200) is None
    now[0] = 84
    assert a.acquire("example.com", "a", 200) is not None


def test_elapsed_budget_includes_wait_and_counts_inline_details():
    now = [0.0]
    budget = CrawlBudget(
        CrawlLimits(detail_pages=1, elapsed_seconds=10), clock=lambda: now[0]
    )
    budget.charge_detail()
    with pytest.raises(BudgetExceeded, match="detail"):
        budget.charge_detail()
    now[0] = 11
    with pytest.raises(BudgetExceeded, match="elapsed"):
        budget.check_deadline()


def test_page_budget_tracks_total_transferred_bytes():
    budget = CrawlBudget(CrawlLimits())
    budget.charge_request(20 * 1024 * 1024)
    with pytest.raises(BudgetExceeded, match="bytes"):
        budget.charge_bytes(1)


@pytest.mark.parametrize(
    "status,allowed",
    [(404, True), (410, True), (403, False), (500, False), (429, False)],
)
def test_robots_failure_is_not_an_empty_board(status, allowed):
    assert robots_decision("https://example.com/jobs", status, "").allowed is allowed


def test_robots_rules_and_delay_apply_to_target_path():
    text = "User-agent: *\nDisallow: /private\nCrawl-delay: 12\n"
    assert not robots_decision("https://example.com/private/jobs", 200, text).allowed
    assert robots_decision("https://example.com/jobs", 200, text).delay_seconds == 12


def test_retry_after_never_shortens_server_delay():
    assert retry_delay("120", 0, now=0) == 120
    assert retry_delay("Thu, 01 Jan 1970 00:02:00 GMT", 0, now=0) == 120
    assert retry_delay(None, 0, now=0) == 30
    assert retry_delay(None, 1, now=0) == 60
