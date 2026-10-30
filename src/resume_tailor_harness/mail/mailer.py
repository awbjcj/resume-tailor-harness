import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

from resume_tailor_harness.config import Settings


logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


class MailDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class Mailer(Protocol):
    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> None: ...

    def notify(self, *, to: str, subject: str, body: str) -> None: ...


def sender_address(settings: Settings) -> str:
    """The From address, resolved once for every backend.

    ``smtp_from``/``smtp_username`` are the fallbacks so a deploy that predates
    the HTTPS backend keeps its existing sender without renaming a variable.
    """
    return next(
        (
            value.strip()
            for value in (
                settings.mail_from,
                settings.smtp_from,
                settings.smtp_username,
            )
            if value.strip()
        ),
        "",
    )


class _NotifyBySend:
    """Shared ``notify``: a best-effort send that never propagates failure."""

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> None:  # pragma: no cover
        raise NotImplementedError

    def notify(self, *, to: str, subject: str, body: str) -> None:
        try:
            self.send(to=to, subject=subject, body=body)
        except Exception:  # security notices never roll back completed state changes
            logger.exception("Security notification to %s failed", to)


class NullMailer(_NotifyBySend):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        self.sent.append((to, subject, body))
        logger.warning(
            "MAIL NOT CONFIGURED - would send to %s: %s\n%s", to, subject, body
        )


class ResendMailer(_NotifyBySend):
    """Delivery over Resend's HTTPS API.

    Required wherever outbound SMTP is blocked: Railway disables it below the
    Pro plan, so ``smtp.gmail.com:587`` fails with ``[Errno 101] Network is
    unreachable`` no matter how the credentials are set.
    """

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        http = self._client if self._client is not None else httpx.Client(timeout=10.0)
        try:
            response = http.post(
                RESEND_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.settings.resend_api_key}",
                    **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
                },
                json={
                    "from": sender_address(self.settings),
                    "to": [to],
                    "subject": subject,
                    "text": body,
                    **({"html": html} if html is not None else {}),
                    **({"headers": headers} if headers else {}),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            # Callers turn this into a fixed "503 MAIL_UNAVAILABLE" body, so the
            # cause is recorded here or it is lost. Resend explains a refusal
            # (unverified domain, bad key) in the response body, not the status
            # line -- and the key rides a header, so it is never in either.
            failure = getattr(error, "response", None)
            detail = (
                f"{failure.status_code} {failure.text.strip()}"
                if failure is not None
                else str(error)
            )
            logger.warning(
                "Resend delivery to %s failed from %s: %s",
                to,
                sender_address(self.settings),
                detail,
            )
            status = failure.status_code if failure is not None else None
            retryable = (
                status is None or status >= 500 or status in {408, 409, 425, 429}
            )
            raise MailDeliveryError(detail, retryable=retryable) from error
        finally:
            if self._client is None:
                http.close()


class SmtpMailer(_NotifyBySend):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        message = EmailMessage()
        message["From"] = sender_address(self.settings)
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if html is not None:
            message.add_alternative(html, subtype="html")
        for name, value in (headers or {}).items():
            message[name] = value
        if idempotency_key:
            message["Message-ID"] = f"<{idempotency_key}@resume-tailor-harness>"
        implicit_tls = self.settings.smtp_port == 465
        opener = smtplib.SMTP_SSL if implicit_tls else smtplib.SMTP
        try:
            with opener(
                self.settings.smtp_host, self.settings.smtp_port, timeout=10
            ) as client:
                if self.settings.smtp_starttls and not implicit_tls:
                    client.starttls()
                if self.settings.smtp_username:
                    client.login(
                        self.settings.smtp_username, self.settings.smtp_password
                    )
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            # Callers turn this into a fixed "503 MAIL_UNAVAILABLE" body, so the
            # cause is recorded here or it is lost. Never log the password.
            logger.warning(
                "SMTP delivery to %s failed via %s:%s (starttls=%s, auth=%s): %s",
                to,
                self.settings.smtp_host,
                self.settings.smtp_port,
                self.settings.smtp_starttls,
                "on" if self.settings.smtp_username else "off",
                error,
            )
            permanent = (
                isinstance(error, smtplib.SMTPResponseException)
                and 500 <= error.smtp_code < 600
            )
            if isinstance(error, smtplib.SMTPRecipientsRefused):
                permanent = bool(error.recipients) and all(
                    500 <= code < 600 for code, _ in error.recipients.values()
                )
            raise MailDeliveryError(str(error), retryable=not permanent) from error


def mail_configured(settings: Settings) -> bool:
    return bool(
        sender_address(settings) and (settings.resend_api_key or settings.smtp_host)
    )


def build_mailer(settings: Settings) -> Mailer:
    """Pick a backend. HTTPS wins over SMTP; setting the key is the opt-out."""
    if settings.resend_api_key:
        return ResendMailer(settings)
    if settings.smtp_host:
        return SmtpMailer(settings)
    return NullMailer()
