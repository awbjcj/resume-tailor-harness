"""Microsoft delegated Mail.Read only. Fixed origins; no token-bearing redirects."""

import base64
from contextlib import nullcontext
import json
import re
import time
from hashlib import sha256
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import ValidationError

from resume_tailor_harness.config import Settings
from resume_tailor_harness.discovery.connectors.text import html_to_text
from resume_tailor_harness.gmail.client import EmailMessage, authored_text
from resume_tailor_harness.mailboxes.models import MailboxError, MailboxProviderResponse
from resume_tailor_harness.mailboxes.microsoft_payloads import (
    DeltaPayload,
    ProfilePayload,
    TokenPayload,
)
from resume_tailor_harness.mailboxes.store import account_id

AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
GRAPH = "https://graph.microsoft.com/v1.0"
DELTA = GRAPH + "/me/mailFolders/inbox/messages/delta"
SCOPES = "offline_access User.Read Mail.Read"


def available(settings: Settings) -> bool:
    return bool(
        settings.microsoft_oauth_client_id and settings.microsoft_oauth_client_secret
    )


def authorization_url(
    settings: Settings, redirect: str, state: str, verifier: str
) -> str:
    if not available(settings):
        raise MailboxError(
            "Microsoft sign-in is not configured. Ask the administrator to configure its OAuth client."
        )
    challenge = (
        base64.urlsafe_b64encode(sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return (
        AUTHORITY
        + "/authorize?"
        + urlencode(
            {
                "client_id": settings.microsoft_oauth_client_id,
                "response_type": "code",
                "redirect_uri": redirect,
                "response_mode": "query",
                "scope": SCOPES,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
    )


def _token(settings: Settings, params: dict) -> dict:
    try:
        with httpx.Client(
            timeout=20, trust_env=False, follow_redirects=False
        ) as client:
            response = client.post(
                AUTHORITY + "/token",
                data={
                    "client_id": settings.microsoft_oauth_client_id,
                    "client_secret": settings.microsoft_oauth_client_secret,
                    "scope": SCOPES,
                    **params,
                },
            )
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid token response")
        if response.status_code != 200:
            if data.get("error") == "invalid_grant":
                raise MicrosoftReconnect(
                    "Microsoft authorization expired. Reconnect this mailbox."
                )
            raise MailboxError(
                "Microsoft could not authorize the connection. Try again later."
            )
        token = TokenPayload.model_validate(data)
        scopes = {scope.lower().rsplit("/", 1)[-1] for scope in token.scope.split()}
        if "mail.read" not in scopes or "user.read" not in scopes:
            raise MicrosoftReconnect(
                "Approve read access to your Microsoft mailbox to connect."
            )
        return {
            **token.model_dump(exclude_none=True),
            "expires_at": time.time() + token.expires_in,
        }
    except ValidationError:
        raise MailboxProviderResponse(
            "Microsoft returned an invalid authorization response. Try again later."
        ) from None
    except (httpx.HTTPError, ValueError) as exc:
        raise MailboxError(
            "Microsoft authorization is temporarily unavailable."
        ) from exc


class MicrosoftReconnect(MailboxError):
    code = "MAILBOX_RECONNECT"
    status_code = 409


def _validate_graph_url(url: str) -> None:
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
    except ValueError:
        parsed = None
    # nextLink/deltaLink is untrusted provider data persisted in user backups.
    if (
        parsed is None
        or parsed.scheme != "https"
        or parsed.netloc != "graph.microsoft.com"
        or not (
            parsed.path == "/v1.0/me"
            or re.fullmatch(
                r"/v1\.0/me/mailFolders(?:/[^/]+|\('[^/']+'\))/messages/delta",
                parsed.path,
            )
        )
        or parsed.fragment
        or len(url) > 16384
    ):
        raise MailboxError(
            "Invalid Microsoft mailbox continuation. Reconnect the mailbox."
        )


def open_mailbox() -> httpx.Client:
    """Own one credential-free connection pool for a single account pass."""
    return httpx.Client(timeout=30, trust_env=False, follow_redirects=False)


def graph_get(
    url: str, access_token: str, *, client: httpx.Client | None = None
) -> dict:
    _validate_graph_url(url)
    try:
        with nullcontext(client) if client is not None else open_mailbox() as client:
            with client.stream(
                "GET",
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Prefer": 'outlook.body-content-type="text", IdType="ImmutableId", odata.maxpagesize=50',
                },
            ) as response:
                if response.status_code in {401, 403}:
                    raise MicrosoftReconnect(
                        "Microsoft mailbox access was denied. Reconnect this mailbox."
                    )
                if response.status_code == 410:
                    raise DeltaExpired()
                raw = bytearray()
                for chunk in response.iter_bytes(65536):
                    raw.extend(chunk)
                    if len(raw) > 5 * 1024 * 1024:
                        raise MailboxError(
                            "Microsoft returned an oversized email page."
                        )
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("Invalid response")
                if response.status_code != 200:
                    error = data.get("error")
                    error_code = (
                        str(error.get("code", "")).lower()
                        if isinstance(error, dict)
                        else ""
                    )
                    if response.status_code in {400, 404} and error_code in {
                        "syncstatenotfound",
                        "errorinvalidsyncstatedata",
                        "resyncrequired",
                    }:
                        raise DeltaExpired()
                    raise MailboxError(
                        "Microsoft mail is temporarily unavailable. Retry sync later."
                    )
                return data
    except (httpx.HTTPError, ValueError) as exc:
        raise MailboxError(
            "Microsoft mail could not be read. Retry sync later."
        ) from exc


class DeltaExpired(MailboxError):
    pass


def connect(settings: Settings, redirect: str, code: str, verifier: str) -> dict:
    token = _token(
        settings,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect,
            "code_verifier": verifier,
        },
    )
    if not token.get("refresh_token"):
        raise MailboxError(
            "Microsoft did not grant offline access. Reconnect and approve access."
        )
    try:
        profile = ProfilePayload.model_validate(
            graph_get(
                GRAPH + "/me?$select=id,mail,userPrincipalName", token["access_token"]
            )
        )
    except ValidationError:
        raise MailboxProviderResponse(
            "Microsoft returned an invalid mailbox identity."
        ) from None
    email = profile.mail or profile.userPrincipalName
    if not email:
        raise MailboxError("Microsoft did not return a mailbox identity.")
    # Verify mail access before showing a connected account.
    graph_get(DELTA + "?$select=id&$top=1", token["access_token"])
    return {
        "id": account_id("microsoft", profile.id),
        "provider": "microsoft",
        "email": email,
        "token": token,
        "folder": "INBOX",
    }


def refresh(account: dict, settings: Settings) -> bool:
    token = account["token"]
    if token.get("expires_at", 0) > time.time() + 120:
        return False
    updated = _token(
        settings,
        {"grant_type": "refresh_token", "refresh_token": token["refresh_token"]},
    )
    updated.setdefault("refresh_token", token["refresh_token"])
    account["token"] = updated
    return True


def read_page(
    account: dict,
    cursor: dict,
    *,
    client: httpx.Client | None = None,
) -> tuple[list[EmailMessage], dict, bool]:
    initial = (
        DELTA
        + "?"
        + urlencode(
            {
                "$select": "id,subject,from,body,bodyPreview,receivedDateTime,isDraft",
            }
        )
    )
    url = cursor.get("next") or cursor.get("delta") or initial
    transport = {"client": client} if client is not None else {}
    try:
        page = graph_get(url, account["token"]["access_token"], **transport)
    except DeltaExpired:
        page = graph_get(initial, account["token"]["access_token"], **transport)
    try:
        validated = DeltaPayload.model_validate(page)
    except ValidationError:
        raise MailboxProviderResponse(
            "Microsoft returned an invalid email page. Retry sync later."
        ) from None
    next_url, delta = validated.next, validated.delta
    if not next_url and not delta:
        raise MailboxProviderResponse("Microsoft returned no mailbox continuation.")
    for continuation in (next_url, delta):
        if continuation:
            _validate_graph_url(continuation)
    if next_url == url:
        raise MailboxProviderResponse(
            "Microsoft repeated a page cursor. Retry sync later."
        )
    emails = []
    for item in validated.value:
        if item.removed is not None or item.isDraft:
            continue
        address = (
            item.sender.emailAddress.address
            if item.sender and item.sender.emailAddress
            else None
        ) or ""
        body = item.body
        content = (body.content if body else None) or item.bodyPreview or ""
        if body and (body.contentType or "").lower() == "html":
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")
            for quote in soup.select("blockquote, .gmail_quote, .yahoo_quoted"):
                quote.decompose()
            content = html_to_text(str(soup))
        content = authored_text(content)[:4000]
        if item.receivedDateTime is None:
            raise MailboxProviderResponse(
                "Microsoft returned an email without a valid receipt date."
            ) from None
        received = int(item.receivedDateTime.timestamp() * 1000)
        emails.append(
            EmailMessage(
                sender=address[:1000],
                sender_domain=address.rpartition("@")[2].lower(),
                subject=(item.subject or "")[:1000],
                snippet=content[:400],
                body=content,
                message_id=item.id,
                internal_date=received,
                recruiting_candidate=True,
            )
        )
    return emails, {"next": next_url, "delta": delta}, bool(next_url)
