import base64
from collections.abc import Callable
from dataclasses import dataclass

from resume_tailor_harness.discovery.connectors.text import html_to_text
from resume_tailor_harness.gmail.auth import (  # noqa: F401 — CLI compat re-export
    build_gmail_service_interactive as build_gmail_service,
)
from resume_tailor_harness.gmail.requests import execute_read

BODY_CHAR_LIMIT = 4000


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


def _decode(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _walk_parts(payload: dict):
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
            return _decode(data)[:BODY_CHAR_LIMIT].strip()
        if part.get("mimeType") == "text/html" and not html:
            html = _decode(data)
    return html_to_text(html)[:BODY_CHAR_LIMIT].strip() if html else ""


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
    if "@" not in sender:
        return ""
    return sender.split("@", 1)[1].rstrip(">").strip().lower()


def fetch_recent_messages(
    service,
    max_results: int = 50,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[EmailMessage]:
    """Fetch recent inbox messages as EmailMessages (read-only)."""
    refs: list[dict] = []
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
                    labelIds=["INBOX"],
                    **params,
                )
            )
            or {}
        )
        refs.extend(listing.get("messages", [])[: max_results - len(refs)])
        page_token = listing.get("nextPageToken")
        if not page_token or page_token in seen_pages:
            break
        seen_pages.add(page_token)
    messages: list[EmailMessage] = []
    for index, ref in enumerate(refs):
        if on_progress:
            on_progress(index, len(refs))
        msg = execute_read(
            service.users()
            .messages()
            .get(
                userId="me",
                id=ref["id"],
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
                message_id=ref["id"],
            )
        )
    if on_progress:
        on_progress(len(refs), len(refs))
    return messages
