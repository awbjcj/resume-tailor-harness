"""Choose the public scraper only after known-ATS redirect detection."""

from resume_tailor_harness.discovery.connectors.detect import identify_host
from resume_tailor_harness.discovery.url_ingest.fetch import fetch_static


def public_extraction_url(url: str) -> str | None:
    if identify_host(url) is not None:
        return None
    final_url = fetch_static(url).final_url
    return final_url if identify_host(final_url) is None else None
