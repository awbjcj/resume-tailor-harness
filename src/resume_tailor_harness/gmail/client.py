import base64
import re
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Any

from resume_tailor_harness.discovery.connectors.text import html_to_text
from resume_tailor_harness.gmail.auth import (  # noqa: F401 — CLI compat re-export
    build_gmail_service_interactive as build_gmail_service,
)
from resume_tailor_harness.gmail.requests import execute_read

BODY_CHAR_LIMIT = 4000
# A separate budget prevents ordinary inbox traffic from hiding recruiting mail.
RECRUITING_QUERY = (
    "newer_than:90d -in:sent -in:drafts -in:spam -in:trash "
    '{application interview assessment "coding challenge" "phone screen" '
    '"offer letter" "not moving forward" "decided not to" '
    "from:myworkday.com from:greenhouse.io from:lever.co from:ashbyhq.com}"
)
BACKFILL_QUERY = RECRUITING_QUERY.replace("newer_than:90d ", "")
BATCH_SIZE = 25


@dataclass
class EmailMessage:
    """The minimal email shape the matcher/classifier need."""

    sender: str
    sender_domain: str
    subject: str
    snippet: str
    thread_id: str | None = None
    message_id: str | None = None
    body: str | None = None
    internal_date: int = 0
    recruiting_candidate: bool = False
    incoming: bool = True


def _decode(data: str) -> str:
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode(
            "utf-8", errors="replace"
        )
    except (ValueError, TypeError):
        return ""


def _walk_parts(payload: dict):
    if payload.get("filename"):
        return
    yield payload
    for part in payload.get("parts") or []:
        yield from _walk_parts(part)


def extract_body(payload: dict) -> str:
    """text/plain part preferred, else html→text; truncated for classification."""
    html = ""
    for part in _walk_parts(payload):
        data = (part.get("body") or {}).get("data") or ""
        if not data:
            continue
        if part.get("mimeType") == "text/plain":
            plain = _decode(data).strip()
            if plain:
                return plain[:BODY_CHAR_LIMIT]
        if part.get("mimeType") == "text/html" and not html:
            html = _decode(data)
    if not html:
        return ""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for quoted in soup.select("blockquote, .gmail_quote, .yahoo_quoted"):
        quoted.decompose()
    return html_to_text(str(soup))[:BODY_CHAR_LIMIT].strip()


def fetch_message_body(service, message_id: str) -> str:
    msg = execute_read(
        service.users().messages().get(userId="me", id=message_id, format="full"),
        allow_missing=True,
    )
    return extract_body((msg or {}).get("payload", {}))


def _header(headers: list[dict], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _domain(sender: str) -> str:
    return parseaddr(sender)[1].rpartition("@")[2].lower()


def authored_text(text: str) -> str:
    """Exclude quoted correspondence from role matching and decision rules."""
    text = re.split(
        r"(?im)^\s*(?:On .+wrote:|[-_]{2,}\s*Original Message|From:\s)", text
    )[0]
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith(">")
    )


def email_from_payload(
    message_id: str, payload: dict, *, recruiting: bool
) -> EmailMessage:
    headers = payload.get("payload", {}).get("headers", [])
    sender = _header(headers, "From")
    labels = set(payload.get("labelIds", []))
    return EmailMessage(
        sender=sender,
        sender_domain=_domain(sender),
        subject=_header(headers, "Subject"),
        snippet=payload.get("snippet", ""),
        thread_id=payload.get("threadId"),
        message_id=message_id,
        internal_date=int(payload.get("internalDate") or 0),
        recruiting_candidate=recruiting,
        incoming=not bool(labels & {"SENT", "DRAFT", "SPAM", "TRASH"}),
    )


def batch_read_messages(
    service,
    ids: list[str],
    *,
    full: bool = False,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, dict | None]:
    """Small serial HTTP batches; retry only failed parts through execute_read.

    Batching reduces network round trips, not Gmail quota usage. The SDK's
    shared HTTP transport is never used concurrently across threads.
    """
    from google.auth.exceptions import RefreshError, TransportError
    from googleapiclient.errors import HttpError
    from httplib2 import HttpLib2Error

    results: dict[str, dict | None] = {}
    for start in range(0, len(ids), BATCH_SIZE):
        if checkpoint:
            checkpoint()
        requests: dict[str, Any] = {}
        failures: set[str] = set()

        def callback(request_id, response, exception):
            if exception is not None:
                failures.add(request_id)
            else:
                results[request_id] = response

        batch = service.new_batch_http_request(callback=callback)
        for message_id in ids[start : start + BATCH_SIZE]:
            params = {} if full else {"metadataHeaders": ["From", "Subject"]}
            request = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="full" if full else "metadata",
                    **params,
                )
            )
            requests[message_id] = request
            batch.add(request, request_id=message_id)
        try:
            batch.execute()
        except (HttpError, RefreshError, TransportError, HttpLib2Error, OSError):
            failures.update(requests.keys() - results.keys())
        for message_id, request in requests.items():
            if message_id in failures or message_id not in results:
                results[message_id] = execute_read(request, allow_missing=True)
    return results


def _list_message_ids(
    service,
    max_results: int,
    query: str | None,
    on_progress: Callable[[int, int], None] | None,
    on_warning: Callable[[str], None] | None,
) -> list[str]:
    refs: dict[str, None] = {}
    page_token = None
    seen_pages: set[str] = set()
    while len(refs) < max_results:
        if on_progress:
            on_progress(0, max_results)
        params = {"pageToken": page_token} if page_token else {}
        listing = (
            execute_read(
                service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=min(500, max_results - len(refs)),
                    **({"q": query} if query else {"labelIds": ["INBOX"]}),
                    **params,
                )
            )
            or {}
        )
        previous_count = len(refs)
        for ref in listing.get("messages", []):
            refs[ref["id"]] = None
            if len(refs) >= max_results:
                break
        page_token = listing.get("nextPageToken")
        if not page_token:
            break
        if page_token in seen_pages or len(refs) == previous_count:
            if on_warning:
                on_warning("Gmail repeated a results page. The scan may be incomplete.")
            break
        seen_pages.add(page_token)
    if page_token and len(refs) >= max_results and on_warning:
        scope = "recruiting-mail" if query else "inbox"
        on_warning(
            f"Reached the {max_results}-message {scope} scan limit. "
            "Older messages may be missing; increase GMAIL_MAX_MESSAGES to scan more."
        )
    return list(refs)


def fetch_recent_messages(
    service,
    max_results: int = 50,
    *,
    include_recruiting: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
    on_warning: Callable[[str], None] | None = None,
) -> list[EmailMessage]:
    """Read the inbox, optionally plus a separately bounded recruiting search.

    Each search gets max_results messages. Merge before fetching metadata so
    overlapping results cost one read, then order by Gmail's receipt timestamp.
    """
    refs = _list_message_ids(service, max_results, None, on_progress, on_warning)
    recruiting_ids = (
        _list_message_ids(
            service, max_results, RECRUITING_QUERY, on_progress, on_warning
        )
        if include_recruiting
        else []
    )
    refs = list(dict.fromkeys([*refs, *recruiting_ids]))
    recruiting_set = set(recruiting_ids)
    messages: list[EmailMessage] = []
    for index, ref in enumerate(refs):
        if on_progress:
            on_progress(index, len(refs))
        msg = execute_read(
            service.users()
            .messages()
            .get(
                userId="me",
                id=ref,
                format="metadata",
                metadataHeaders=["From", "Subject"],
            ),
            allow_missing=True,
        )
        # A message can be deleted between listing and fetching metadata.
        if msg is None:
            continue
        headers = msg.get("payload", {}).get("headers", [])
        sender = _header(headers, "From")
        messages.append(
            EmailMessage(
                sender=sender,
                sender_domain=_domain(sender),
                subject=_header(headers, "Subject"),
                snippet=msg.get("snippet", ""),
                thread_id=msg.get("threadId"),
                message_id=ref,
                internal_date=int(msg.get("internalDate") or 0),
                recruiting_candidate=ref in recruiting_set,
            )
        )
    if on_progress:
        on_progress(len(refs), len(refs))
    return sorted(messages, key=lambda email: email.internal_date, reverse=True)
