"""Select one schema.org posting without mixing in recommended jobs."""

import json
from collections.abc import Iterator
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup


def postings(value, path: str = "", depth: int = 0) -> Iterator[tuple[str, dict]]:
    if depth > 40:
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from postings(item, f"{path}.{index}".strip("."), depth + 1)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        types = [types] if isinstance(types, str) else types
        if isinstance(types, list) and any(
            str(item).rstrip("/").rsplit("/", 1)[-1].casefold() == "jobposting"
            for item in types
        ):
            yield path, value
        for key in ("@graph", "itemListElement", "item", "mainEntity"):
            if key in value:
                yield from postings(value[key], f"{path}.{key}".strip("."), depth + 1)


def json_ld(raw_html: str) -> list:
    result = []
    for script in BeautifulSoup(raw_html, "html.parser").select(
        'script[type="application/ld+json"]'
    ):
        try:
            result.append(json.loads(script.get_text()))
        except (ValueError, TypeError, RecursionError):
            continue
    return result


def _identity(url: str) -> str:
    parsed = urlsplit(url)
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"trk", "trackingid", "refid", "gclid", "fbclid"}
    )
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            urlencode(query),
            parsed.fragment,
        )
    )


def select_posting(value, url: str | None = None) -> tuple[str, dict] | None:
    candidates = list(postings(value))
    if url:
        matched = []
        for path, job in candidates:
            references = [job.get("url"), job.get("mainEntityOfPage")]
            for reference in references:
                if isinstance(reference, dict):
                    reference = reference.get("@id")
                try:
                    matches = isinstance(reference, str) and _identity(
                        urljoin(url, reference)
                    ) == _identity(url)
                except ValueError:
                    matches = False
                if matches:
                    matched.append((path, job))
                    break
        if len(matched) == 1:
            return matched[0]
        if matched:
            # Identical desktop/mobile markup is harmless; differing facts are not.
            return (
                matched[0] if all(job == matched[0][1] for _, job in matched) else None
            )
    # A single unaddressed posting is common. An addressed, different posting
    # is a recommendation, not a fallback for the requested job.
    if len(candidates) == 1 and (
        not url
        or not any(candidates[0][1].get(key) for key in ("url", "mainEntityOfPage"))
    ):
        return candidates[0]
    return None
