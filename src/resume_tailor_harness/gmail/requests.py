"""Bounded retries and safe, actionable errors for read-only Gmail requests."""

from typing import Any

from resume_tailor_harness.gmail.errors import (
    GmailApiError,
    GmailNotConnected,
    GmailScopeMissing,
)


def execute_read(request: Any, *, allow_missing: bool = False) -> dict | None:
    from google.auth.exceptions import RefreshError, TransportError
    from googleapiclient.errors import HttpError
    from httplib2 import HttpLib2Error

    try:
        # The SDK retries 429, rate-limit 403s, 5xx and transport errors with jitter.
        # Do not use this seam for draft creation (a retry could duplicate writes).
        return request.execute(num_retries=3)
    except HttpError as exc:
        status = exc.resp.status
        if status == 404 and allow_missing:
            return None
        if status == 401:
            raise GmailNotConnected(
                "Connect Gmail again in Settings to resume syncing."
            ) from exc
        if status == 403 and "insufficientPermissions" in str(exc):
            raise GmailScopeMissing(
                "Reconnect Gmail in Settings and approve Gmail read access."
            ) from exc
        raise GmailApiError(
            "Gmail could not complete the scan after retries. Try syncing again later."
        ) from exc
    except RefreshError as exc:
        if exc.retryable:
            raise GmailApiError(
                "Gmail could not refresh its connection. Try syncing again later."
            ) from exc
        raise GmailNotConnected(
            "Connect Gmail again in Settings to resume syncing."
        ) from exc
    except (TransportError, HttpLib2Error, OSError) as exc:
        raise GmailApiError(
            "Google is temporarily unreachable. Try syncing again later."
        ) from exc
