import pytest

from resume_tailor_harness.discovery.scraper.identity import (
    board_key,
    normalize_board_url,
    observed_job_key,
)


def test_board_identity_preserves_query_and_spa_routes():
    urls = [
        "https://example.com/jobs?team=a",
        "https://example.com/jobs?team=b",
        "https://example.com/#/jobs",
        "https://example.com/#/internships",
    ]
    assert len({board_key(url) for url in urls}) == 4


def test_normalization_only_removes_tracking_and_default_ports():
    assert (
        normalize_board_url(
            "https://EXAMPLE.com:443/jobs?team=a&utm_source=email#/list"
        )
        == "https://example.com/jobs?team=a#/list"
    )
    assert board_key("https://www.example.com/jobs") != board_key(
        "https://example.com/jobs"
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/jobs",
        "https://user:pass@example.com",
        "https://example.com:bad",
        "not a url",
    ],
)
def test_invalid_source_urls_rejected(url):
    with pytest.raises(ValueError):
        normalize_board_url(url)


def test_inline_job_without_stable_identity_needs_review():
    assert observed_job_key("board", None, None) is None
    assert observed_job_key("board", "id-1", None) != observed_job_key(
        "other", "id-1", None
    )
