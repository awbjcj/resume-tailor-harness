"""Verified workspace digests using the platform's account-email transport."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from collections.abc import Callable

from sqlalchemy import func, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from resume_tailor_harness.api.public_url import validate_public_origin
from resume_tailor_harness.config import Settings
from resume_tailor_harness.mail.mailer import Mailer, MailDeliveryError, mail_configured
from resume_tailor_harness.mail.tables import EmailNotificationPreference as Preference
from resume_tailor_harness.mail.templates import render_email
from resume_tailor_harness.tracking.queries import reminder_event_job_rows
from resume_tailor_harness.services.reminders import (
    _REMINDABLE_INTERVIEW_KINDS,
    follow_up_key,
)
from resume_tailor_harness.tracking.tables import Application, Job, Notification


INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
}


class NotificationError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def delivery_available(settings: Settings) -> bool:
    if not mail_configured(settings) or not settings.app_base_url:
        return False
    try:
        validate_public_origin(settings.app_base_url)
    except RuntimeError:
        return False
    return True


def get_preference(engine: Engine) -> Preference:
    with Session(engine, expire_on_commit=False) as session:
        return session.get(Preference, 1) or Preference()


def _clear_delivery(row: Preference) -> None:
    row.pending_payload = ""
    row.pending_since = None
    row.retry_at = None
    row.delivery_failures = 0


def update_preference(
    engine: Engine, values: dict, *, now: datetime | None = None
) -> Preference:
    moment = utc(now or now_utc())
    with Session(engine, expire_on_commit=False) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(Preference, 1) or Preference()
        changed_address = row.email != values["email"]
        reschedule = (
            changed_address
            or row.enabled != values["enabled"]
            or row.frequency != values["frequency"]
        )
        if changed_address:
            row.verified_at = None
            row.last_sent_at = None
            row.code_hash = ""
            row.expires_at = None
            row.attempts = 0
            row.unsubscribe_token = secrets.token_urlsafe(32)
        for key in (
            "email",
            "enabled",
            "frequency",
            "pending_reviews",
            "statistics",
            "reminders",
        ):
            setattr(row, key, values[key])
        if not row.enabled:
            row.code_hash = ""
            row.expires_at = None
        _clear_delivery(row)
        if not row.enabled or row.verified_at is None:
            row.next_send_at = None
        elif reschedule or row.next_send_at is None:
            row.next_send_at = moment + INTERVALS[row.frequency]
        session.add(row)
        session.commit()
        return row


def _code_hash(email: str, code: str, settings: Settings) -> str:
    return hashlib.sha256(
        f"notification:{email}:{code}:{settings.session_secret}".encode()
    ).hexdigest()


def request_verification(
    engine: Engine,
    mailer: Mailer,
    settings: Settings,
    *,
    now: datetime | None = None,
    reserve_send: Callable[[str], bool] | None = None,
) -> None:
    if not delivery_available(settings):
        raise NotificationError(
            "MAIL_UNAVAILABLE",
            "Email delivery is not configured. Contact your administrator.",
            503,
        )
    moment = utc(now or now_utc())
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(Preference, 1)
        if row is None or not row.email or not row.enabled:
            raise NotificationError(
                "EMAIL_REQUIRED", "Save an email address and opt in first."
            )
        if row.verified_at is not None:
            return
        if row.send_window_at is None or utc(row.send_window_at) <= moment - timedelta(
            hours=1
        ):
            row.send_window_at, row.send_count = moment, 0
        if row.send_count >= 3 or (
            row.code_sent_at and utc(row.code_sent_at) > moment - timedelta(seconds=60)
        ):
            raise NotificationError(
                "RATE_LIMITED",
                "Please wait before requesting another code. Up to three codes can be sent per hour.",
                429,
            )
        # Reserve shared send allowance only after checking eligibility under lock.
        if reserve_send is not None and not reserve_send(row.email):
            raise NotificationError(
                "RATE_LIMITED", "Please wait before requesting another code.", 429
            )
        code = f"{secrets.randbelow(1_000_000):06d}"
        row.code_hash = _code_hash(row.email, code, settings)
        row.expires_at = moment + timedelta(minutes=15)
        row.attempts = 0
        row.code_sent_at = moment
        row.send_count += 1
        body, html = render_email("verify_notifications", code=code)
        # Keep the rate budget on delivery failure, but invalidate the failed code.
        try:
            mailer.send(
                to=row.email,
                subject="Verify your notification email",
                body=body,
                html=html,
            )
        except MailDeliveryError:
            row.code_hash = ""
            row.expires_at = None
            session.add(row)
            session.commit()
            raise NotificationError(
                "MAIL_UNAVAILABLE",
                "Could not send the verification email. Please try again later.",
                503,
            ) from None
        session.add(row)
        session.commit()


def verify_address(
    engine: Engine,
    email: str,
    code: str,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> Preference:
    moment = utc(now or now_utc())
    with Session(engine, expire_on_commit=False) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(Preference, 1)
        if (
            row is None
            or row.email != email.strip().casefold()
            or not row.enabled
            or not row.code_hash
            or row.expires_at is None
            or utc(row.expires_at) <= moment
            or row.attempts >= 5
        ):
            raise NotificationError(
                "INVALID_CODE", "The code is invalid or expired. Request a new code."
            )
        if not hmac.compare_digest(
            row.code_hash, _code_hash(row.email, code, settings)
        ):
            row.attempts += 1
            session.add(row)
            session.commit()
            raise NotificationError(
                "INVALID_CODE", "The code is invalid or expired. Request a new code."
            )
        row.verified_at = moment
        row.code_hash = ""
        row.expires_at = None
        row.next_send_at = moment + INTERVALS[row.frequency]
        session.add(row)
        session.commit()
        return row


def unsubscribe(engine: Engine, token: str) -> bool:
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(Preference, 1)
        if (
            row is None
            or not row.unsubscribe_token
            or not hmac.compare_digest(row.unsubscribe_token, token)
        ):
            return False
        row.enabled = False
        row.next_send_at = None
        row.code_hash = ""
        row.expires_at = None
        _clear_delivery(row)
        session.add(row)
        session.commit()
        return True


def _digest_context(
    session: Session, row: Preference, settings: Settings, moment: datetime
) -> dict:
    active = col(Job.archived_at).is_(None)
    shortlisted = (active, Job.status == "shortlisted")
    jobs = (
        session.exec(
            select(Job)
            .where(*shortlisted)
            .order_by(col(Job.created_at).desc(), col(Job.id).desc())
            .limit(10)
        ).all()
        if row.pending_reviews
        else []
    )
    pending_count = (
        session.exec(select(func.count()).select_from(Job).where(*shortlisted)).one()
        if row.pending_reviews
        else 0
    )
    stats = {}
    if row.statistics:
        stats["active_jobs"] = session.exec(
            select(func.count()).select_from(Job).where(active)
        ).one()
        stats["applications"] = session.exec(
            select(func.count())
            .select_from(Application)
            .where(col(Application.submitted_at).is_not(None))
        ).one()
        for name, status in (("interviews", "interview"), ("offers", "offer")):
            stats[name] = session.exec(
                select(func.count())
                .select_from(Application)
                .where(Application.status == status)
            ).one()
    reminders: list[str] = []
    if row.reminders:
        events = reminder_event_job_rows(
            session,
            after=moment,
            before=moment + INTERVALS[row.frequency],
            kinds=_REMINDABLE_INTERVIEW_KINDS | {"offer_deadline"},
            dead_results={"cancelled", "withdrew", "rejected"},
        )
        for event, _, job in sorted(
            events, key=lambda item: utc(item[0].occurred_at or moment)
        )[:10]:
            label = (
                "Offer deadline"
                if event.kind == "offer_deadline"
                else "Interview / assessment"
            )
            date = utc(event.occurred_at or moment).strftime(
                "%b %d" if event.all_day else "%b %d, %H:%M UTC"
            )
            reminders.append(f"{label} {date}: {job.company or ''} — {job.title or ''}")
        if settings.follow_up_days > 0:
            followups = session.exec(
                select(Application, Job)
                .join(Job, col(Application.job_id) == Job.id)
                .where(
                    active,
                    col(Application.status).in_({"submitted", "interview"}),
                    col(Application.updated_at)
                    <= moment - timedelta(days=settings.follow_up_days),
                )
                .order_by(Application.updated_at)
            ).all()
            completed = set(
                session.exec(
                    select(Notification.application_id, Notification.message_id).where(
                        Notification.kind == "follow_up",
                        col(Notification.state).in_(
                            {"accepted", "dismissed", "cleared"}
                        ),
                    )
                ).all()
            )
            actionable = [
                (application, job)
                for application, job in followups
                if (
                    application.id,
                    follow_up_key(application.id, application.updated_at),
                )
                not in completed
            ]
            for application, job in actionable[:10]:
                reminders.append(
                    f"Follow up after {(moment - utc(application.updated_at)).days} days without activity: {job.company or ''} — {job.title or ''}"
                )
    return dict(
        date=moment.strftime("%b %d, %Y"),
        frequency={"daily": "Daily", "weekly": "Weekly", "monthly": "Every 30 days"}[
            row.frequency
        ],
        pending_reviews=row.pending_reviews,
        statistics=row.statistics,
        reminders=row.reminders,
        jobs=jobs,
        pending_count=pending_count,
        stats=stats,
        reminder_items=reminders,
    )


def deliver_due(
    engine: Engine,
    mailer: Mailer,
    settings: Settings,
    user_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Serialize dispatch with preference edits; preserve requests across retries.

    The short provider timeout bounds the SQLite writer lock during send. This
    ensures opt-out or address changes cannot race a stale send, including when
    multiple server processes wake together. SMTP cannot guarantee exactly-once
    delivery after an ambiguous disconnect; Resend uses the persisted request ID.
    """
    if not delivery_available(settings):
        return False
    moment = utc(now or now_utc())
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(Preference, 1)
        if (
            row is None
            or not row.enabled
            or row.verified_at is None
            or not row.next_send_at
            or utc(row.next_send_at) > moment
            or (row.retry_at and utc(row.retry_at) > moment)
        ):
            return False
        # Retire uncertain deliveries before Resend's 24-hour idempotency window
        # expires. Resume on the next normal interval without replaying old mail.
        if row.pending_since and utc(row.pending_since) <= moment - timedelta(hours=12):
            _clear_delivery(row)
            row.next_send_at = moment + INTERVALS[row.frequency]
            session.add(row)
            session.commit()
            return False
        if not row.pending_payload:
            context = _digest_context(session, row, settings, moment)
            if (
                not row.statistics
                and not context["pending_count"]
                and not context["reminder_items"]
            ):
                row.next_send_at = moment + INTERVALS[row.frequency]
                session.add(row)
                session.commit()
                return False
            base_url = validate_public_origin(settings.app_base_url)
            unsubscribe_url = f"{base_url}/api/email-notifications/unsubscribe/{user_id}/{row.unsubscribe_token}"
            body, html = render_email(
                "digest", **context, base_url=base_url, unsubscribe_url=unsubscribe_url
            )
            row.pending_payload = json.dumps(
                dict(
                    to=row.email,
                    subject="Your job-search digest",
                    body=body,
                    html=html,
                    headers={
                        "List-Unsubscribe": f"<{unsubscribe_url}>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    },
                    idempotency_key=f"digest-{secrets.token_hex(24)}",
                )
            )
            row.pending_since = moment
            session.add(row)
            session.commit()
            # Re-read after committing the snapshot: another process or opt-out
            # can win this lock, and must be respected before delivery.
            session.execute(text("BEGIN IMMEDIATE"))
            session.refresh(row)
            if (
                not row.enabled
                or not row.pending_payload
                or row.verified_at is None
                or (row.retry_at and utc(row.retry_at) > moment)
            ):
                return False
        try:
            mailer.send(**json.loads(row.pending_payload))
        except MailDeliveryError:
            row.delivery_failures += 1
            row.retry_at = moment + timedelta(
                minutes=min(60 * 2 ** min(row.delivery_failures - 1, 3), 360)
            )
            session.add(row)
            session.commit()
            return False
        _clear_delivery(row)
        row.last_sent_at = moment
        row.next_send_at = moment + INTERVALS[row.frequency]
        session.add(row)
        session.commit()
        return True
