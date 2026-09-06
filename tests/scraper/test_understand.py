from types import SimpleNamespace

from resume_tailor_harness.discovery.scraper.browser_worker import snapshot_from_html
from resume_tailor_harness.discovery.scraper.contracts import PageUnderstanding
from resume_tailor_harness.discovery.scraper.understand import understand


def test_page_classification_passes_bounded_untrusted_content():
    class Runner:
        def run(self, message):
            assert "snapshot_id" in message
            assert len(message) < 70000
            return SimpleNamespace(content=PageUnderstanding(kind="unrelated"))

    result = understand(
        snapshot_from_html("https://example.com", "<nav>" + "x" * 90000 + "</nav>"),
        Runner(),
    )
    assert result.kind == "unrelated"
