"""Bounded, read-only IMAP pages. SMTP is only tested, never used to send."""

import imaplib
import re
import smtplib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime

from resume_tailor_harness.discovery.connectors.text import html_to_text
from resume_tailor_harness.gmail.client import (
    BODY_CHAR_LIMIT,
    EmailMessage,
    authored_text,
)
from resume_tailor_harness.mailboxes.models import (
    MailboxConnectIn,
    MailboxCredentials,
    MailboxError,
    MailboxFolder,
    MailServer,
)
from resume_tailor_harness.security.mail_transport import (
    IMAP_BATCH_SIZE,
    IMAP_LITERAL_LIMIT,
    PublicIMAP,
    PublicIMAPSSL,
    PublicSMTP,
    PublicSMTPSSL,
    TIMEOUT,
    tls_context,
)

MAX_MESSAGE_BYTES = IMAP_LITERAL_LIMIT
UID_WINDOW = 2000


@contextmanager
def open_mailbox(server: MailServer, folder: str):
    client = None
    try:
        context = tls_context()
        if server.security == "tls":
            client = PublicIMAPSSL(
                server.host, server.port, ssl_context=context, timeout=TIMEOUT
            )
        else:
            client = PublicIMAP(server.host, server.port, timeout=TIMEOUT)
            client.starttls(ssl_context=context)
        try:
            client.login(server.username, server.password.get_secret_value())
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error as exc:
            raise MailboxCredentials(
                "IMAP sign-in failed. Check the username and app password.",
                fields=("imap.username", "imap.password"),
            ) from exc
        # Quote explicitly: imaplib.select does not escape mailbox names.
        quoted = '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'
        status, _ = client.select(quoted, readonly=True)
        if status != "OK":
            raise MailboxFolder(
                "The IMAP folder could not be opened.", fields=("folder",)
            )
        yield client
    except imaplib.IMAP4.error as exc:
        raise MailboxError(
            "IMAP access failed. Check the folder, username, and app password."
        ) from exc
    except (OSError, ValueError) as exc:
        raise MailboxError(
            "Cannot reach a public IMAP server securely. Check the host, port, and TLS mode."
        ) from exc
    finally:
        if client is not None:
            try:
                client.logout()
            except (OSError, imaplib.IMAP4.error):
                pass


def verify_connection(body: MailboxConnectIn) -> None:
    with open_mailbox(body.imap, body.folder):
        pass
    if body.smtp is None:
        return
    server = body.smtp
    try:
        context = tls_context()
        if server.security == "tls":
            client = PublicSMTPSSL(
                server.host, server.port, context=context, timeout=TIMEOUT
            )
        else:
            client = PublicSMTP(server.host, server.port, timeout=TIMEOUT)
        with client:
            if server.security == "starttls":
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            client.login(server.username, server.password.get_secret_value())
    except smtplib.SMTPAuthenticationError as exc:
        raise MailboxCredentials(
            "SMTP sign-in failed. Check the username and app password. No email was sent.",
            fields=("smtp.username", "smtp.password"),
        ) from exc
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        raise MailboxError(
            "SMTP verification failed. Check the server and app password. No email was sent."
        ) from exc


def _number(client, name: str) -> int:
    _, data = client.response(name)
    if not data or not data[0] or not data[0].isdigit():
        raise MailboxError("The IMAP server did not return stable mailbox identifiers.")
    return int(data[0])


def parse_message(raw: bytes, message_id: str, internal_date: int) -> EmailMessage:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    text = ""
    # get_body excludes attachments and prefers a plain alternative.
    part = message.get_body(preferencelist=("plain", "html"))
    if part is not None:
        try:
            text = part.get_content()
        except (LookupError, ValueError):
            payload = part.get_payload(decode=True)
            text = (
                payload.decode("utf-8", "replace") if isinstance(payload, bytes) else ""
            )
        if part.get_content_type() == "text/html":
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(text, "html.parser")
            for quote in soup.select("blockquote, .gmail_quote, .yahoo_quoted"):
                quote.decompose()
            text = html_to_text(str(soup))
    sender = str(message.get("From", ""))[:1000]
    text = authored_text(text)[:BODY_CHAR_LIMIT]
    return EmailMessage(
        sender=sender,
        sender_domain=parseaddr(sender)[1].rpartition("@")[2].lower(),
        subject=str(message.get("Subject", ""))[:1000],
        snippet=text[:400],
        body=text,
        message_id=message_id,
        internal_date=internal_date,
        recruiting_candidate=True,
    )


def mailbox_bounds(client) -> tuple[int, int]:
    return _number(client, "UIDVALIDITY"), _number(client, "UIDNEXT") - 1


def _fetch_message_records(payload) -> Iterator[tuple[bytes, bytes]]:
    """Join imaplib's literal prefix/trailer without treating body bytes as metadata."""
    parts: list[bytes] = []
    body: bytes | None = None
    for item in payload:
        if isinstance(item, tuple):
            prefix, literal = item
            if not re.match(rb"[0-9]+ \(", prefix):
                raise MailboxError(
                    "IMAP returned an invalid message batch. Retry sync."
                )
            if body is not None:
                yield b"".join(parts), body
            parts, body = [prefix], literal
        elif isinstance(item, bytes):
            if re.match(rb"[0-9]+ \(", item):
                # A separate FETCH response (e.g. an unsolicited FLAGS update).
                if body is not None:
                    yield b"".join(parts), body
                parts, body = [], None
            elif body is not None:
                # UID and INTERNALDATE may follow the body literal.
                parts.append(item)
    if body is not None:
        yield b"".join(parts), body


def _fetch_attributes(envelope: bytes) -> tuple[int, bytes | None]:
    """Read top-level attributes, excluding quoted strings and nested FLAGS lists."""
    tokens: list[bytes] = []
    depth = end = 0
    for match in re.finditer(rb'"(?:[^"\\]|\\.)*"|[()]|[^()"\s]+', envelope):
        if envelope[end : match.start()].strip():
            raise MailboxError("IMAP returned invalid message metadata. Retry sync.")
        end = match.end()
        token = match[0]
        if token == b"(":
            depth += 1
        elif token == b")":
            depth -= 1
            if depth < 0:
                raise MailboxError(
                    "IMAP returned invalid message metadata. Retry sync."
                )
        elif depth == 1:
            tokens.append(token)
    if depth or envelope[end:].strip():
        raise MailboxError("IMAP returned incomplete message metadata. Retry sync.")
    values = {
        name: [
            tokens[index + 1]
            for index, token in enumerate(tokens[:-1])
            if token.upper() == name
        ]
        for name in (b"UID", b"INTERNALDATE")
    }
    ids, dates = values[b"UID"], values[b"INTERNALDATE"]
    if len(ids) != 1 or not ids[0].isdigit() or len(dates) > 1:
        raise MailboxError("IMAP returned invalid message metadata. Retry sync.")
    date = dates[0] if dates else None
    if date is not None and not (date.startswith(b'"') and date.endswith(b'"')):
        raise MailboxError("IMAP returned an invalid receipt date. Retry sync.")
    return int(ids[0]), date[1:-1] if date is not None else None


def read_page(
    client, cursor: dict, limit: int, checkpoint, *, bounds: tuple[int, int]
) -> tuple[list[EmailMessage], dict, bool]:
    validity, upper = bounds
    state = dict(cursor)
    if state.get("validity") != validity:
        state = {"validity": validity, "high": upper, "before": upper}
    # New arrivals get a page before historical backfill on every pass.
    new = upper > state["high"]
    high = min(upper, state["high"] + UID_WINDOW) if new else state["before"]
    low = state["high"] + 1 if new else max(1, high - UID_WINDOW + 1)
    if high < low:
        return [], state, False
    status, data = client.uid("search", None, "UID", f"{low}:{high}")
    if status != "OK":
        raise MailboxError("IMAP message discovery failed. Retry sync.")
    ids = sorted(
        {
            int(uid)
            for uid in (data[0] or b"").split()
            if uid.isdigit() and low <= int(uid) <= high
        },
        reverse=not new,
    )
    selected = ids[:limit]
    emails = []
    for offset in range(0, len(selected), IMAP_BATCH_SIZE):
        batch = selected[offset : offset + IMAP_BATCH_SIZE]
        checkpoint()
        with client.bounded_response(checkpoint):
            status, payload = client.uid(
                "fetch",
                ",".join(map(str, batch)),
                f"(UID INTERNALDATE BODY.PEEK[]<0.{MAX_MESSAGE_BYTES}>)",
            )
        if status != "OK":
            raise MailboxError("An IMAP message could not be read. Retry sync.")
        found = {}
        for envelope, raw in _fetch_message_records(payload):
            checkpoint()
            uid, received_at = _fetch_attributes(envelope)
            if uid not in batch or uid in found or len(raw) > MAX_MESSAGE_BYTES:
                raise MailboxError(
                    "IMAP returned an invalid message batch. Retry sync."
                )
            if received_at is not None:
                received = datetime.strptime(
                    received_at.decode("ascii"), "%d-%b-%Y %H:%M:%S %z"
                )
            else:
                header = BytesParser(policy=policy.default).parsebytes(
                    raw, headersonly=True
                )
                try:
                    received = parsedate_to_datetime(str(header.get("Date", "")))
                except (ValueError, TypeError):
                    raise MailboxError(
                        "An IMAP message has no valid receipt date."
                    ) from None
            found[uid] = parse_message(
                raw, f"{validity}:{uid}", int(received.timestamp() * 1000)
            )
        # Servers may return messages in any order; cursor order is ours.
        emails.extend(found[uid] for uid in batch if uid in found)
    if new:
        state["high"] = selected[-1] if len(ids) > limit else high
    else:
        state["before"] = selected[-1] - 1 if len(ids) > limit else low - 1
    return emails, state, upper > state["high"] or state["before"] > 0
