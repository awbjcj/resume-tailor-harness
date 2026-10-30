"""Account notices committed with their operation and delivered by the mail worker."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event

from sqlalchemy import or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from resume_tailor_harness.api.public_url import validate_public_origin
from resume_tailor_harness.config import Settings
from resume_tailor_harness.mail.mailer import Mailer, mail_configured
from resume_tailor_harness.mail.templates import render_email
from resume_tailor_harness.mail.localization import translate
from resume_tailor_harness.tenancy.system_db import (
    AccountEmail,
    MemberSubscription,
    QuotaAccount,
    QuotaLedgerEntry,
    QuotaPeriod,
    User,
)
from resume_tailor_harness.tenancy.workspace import workspace_paths

logger = logging.getLogger(__name__)
MAX_DELIVERY_ATTEMPTS = 8

EVENTS = {
    "account_created": ("Your account was created", "Your account is ready to use."),
    "account_deleted": (
        "Your account was deleted",
        "An administrator deleted your account and workspace.",
    ),
    "account_updated": (
        "Your account was updated",
        "An administrator changed your account settings.",
    ),
    "password_reset": (
        "Your password was reset by an administrator",
        "Your password was reset and your existing sessions were revoked.",
    ),
    "password_changed": (
        "Your password was changed",
        "Your password was changed and your previous sign-in sessions were revoked.",
    ),
    "google_linked": (
        "Google sign-in was linked to your account",
        "A Google identity was linked to your account.",
    ),
    "google_unlinked": (
        "Google sign-in was removed from your account",
        "The linked Google identity was removed from your account.",
    ),
    "sessions_revoked": (
        "Your sessions were revoked",
        "Your previous sign-in sessions were revoked.",
    ),
    "token_created": (
        "An access token was created",
        "A personal access token was created for your account.",
    ),
    "token_revoked": (
        "An access token was revoked",
        "A personal access token was revoked for your account.",
    ),
    "email_changed": (
        "Your account email was changed",
        "The registered email address for your account was updated.",
    ),
    "quota_renewed": (
        "Your quota period was renewed",
        "Your recurring allowance has reset for a new quota period.",
    ),
    "RESET": (
        "Your quota was reset",
        "Your usage in the current quota period was reset. Durable credits spent in this period were restored.",
    ),
    "CREDIT_GRANT": (
        "Your credit balance was increased",
        "Credits were added to your account.",
    ),
    "CREDIT_DEBIT": (
        "Your credit balance was decreased",
        "Credits were removed from your account.",
    ),
    "CREDIT_PURCHASE": (
        "Your credit purchase was applied",
        "Your payment was confirmed and credits were added to your account.",
    ),
    "CREDIT_REFUND": (
        "Your credit purchase was refunded",
        "A refund was applied to your credit purchase.",
    ),
    "PAYMENT_DISPUTED": (
        "Your shared-key access was suspended",
        "A payment dispute suspended shared-key access. Contact your administrator to review your account.",
    ),
    "SUBSCRIPTION_ACTIVATED": (
        "Your subscription was activated",
        "Your subscription is now active.",
    ),
    "SUBSCRIPTION_RENEWED": (
        "Your subscription was renewed",
        "Your subscription term was extended.",
    ),
    "SUBSCRIPTION_REVOKED": (
        "Your subscription was revoked",
        "Your subscription was revoked and your account returned to the Free tier. Your durable credits remain available.",
    ),
    "SUBSCRIPTION_EXPIRED": (
        "Your subscription expired",
        "Your subscription expired and your account returned to the Free tier. Your durable credits remain available.",
    ),
    "subscription_cancellation": (
        "Your subscription cancellation was updated",
        "The scheduled cancellation of your subscription was changed.",
    ),
    "TIER_CHANGE": (
        "Your quota tier was changed",
        "Your account was assigned a new quota tier.",
    ),
    "TIER_ALLOWANCE_CHANGE": (
        "Your tier allowance was changed",
        "An administrator changed the allowance for your quota tier.",
    ),
    "OVERRIDE_CHANGE": (
        "Your quota allowance was changed",
        "An administrator changed your individual quota allowance.",
    ),
    "tier_updated": (
        "Your quota tier settings were changed",
        "An administrator updated the settings for your quota tier.",
    ),
}


def money(micros: int | None) -> str:
    return "Unlimited" if micros is None else f"USD {Decimal(micros) / 1_000_000:.6f}"


def enqueue_account_email(
    session: Session,
    user: User | None,
    event: str,
    details: dict[str, str] | None = None,
    *,
    ready: bool = True,
) -> AccountEmail | None:
    """Snapshot only the registered, verified address. Never commit or send here."""
    title, summary = EVENTS[event]
    if user is None or not user.email or user.email_verified_at is None:
        return None
    row = AccountEmail(
        id=uuid.uuid4().hex,
        user_id=user.id,
        recipient=user.email,
        event=event,
        ready=ready,
        context_json=json.dumps(
            {
                "username": user.username,
                "language": user.dashboard_language,
                "title": title,
                "summary": summary,
                "details": details or {},
            }
        ),
    )
    session.add(row)
    return row


def release_deletion_notices(engine: Engine, data_dir: Path) -> None:
    """Recover a crash after cleanup but before releasing a deletion notice."""
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        rows = session.scalars(
            select(AccountEmail).where(
                AccountEmail.ready.is_(False),
                AccountEmail.event == "account_deleted",
            )
        )
        for row in rows:
            root = workspace_paths(data_dir, row.user_id).root
            if (
                session.get(User, row.user_id) is None
                and not root.exists()
                and not any(root.parent.glob(f".{row.user_id}.deleting-*"))
            ):
                row.ready = True
        session.commit()


def add_quota_entry(session: Session, entry: QuotaLedgerEntry) -> None:
    """Record audited adjustments and their notices together; usage stays silent."""
    session.add(entry)
    if entry.kind not in EVENTS:
        return
    snapshot = json.loads(entry.snapshot_json or "{}")
    if (
        entry.kind in {"OVERRIDE_CHANGE", "TIER_ALLOWANCE_CHANGE"}
        and "before" in snapshot
        and snapshot["before"] == snapshot.get("after")
    ):
        return
    details = {}
    account = session.get(QuotaAccount, entry.user_id)
    period = session.get(QuotaPeriod, entry.period_id) if entry.period_id else None
    if account is not None:
        details["Quota tier"] = account.tier_id
        details["Credit balance"] = money(account.credit_balance_micros)
    if period is not None:
        details["Recurring allowance"] = money(period.allowance_micros)
        details["Period ends (UTC)"] = period.ends_at.isoformat()
    if entry.kind in {
        "CREDIT_GRANT",
        "CREDIT_DEBIT",
        "CREDIT_PURCHASE",
        "CREDIT_REFUND",
    }:
        details["Adjustment"] = money(entry.amount_micros)
    if entry.kind == "CREDIT_REFUND" and entry.credit_micros is not None:
        details["Credits removed"] = money(abs(entry.credit_micros))
    if entry.reason:
        details["Reason"] = entry.reason
    if entry.kind.startswith("SUBSCRIPTION_"):
        subscription = session.get(MemberSubscription, entry.user_id)
        if subscription is not None:
            details["Subscription tier"] = subscription.tier_id
            details["Subscription status"] = subscription.status
            details["Term ends (UTC)"] = subscription.expires_at.isoformat()
    user = session.get(User, entry.user_id)
    if user is not None:
        details["Shared-key access"] = (
            "Granted" if user.shared_key_access else "Revoked"
        )
    enqueue_account_email(session, user, entry.kind, details)


def deliver_account_emails(
    engine: Engine,
    mailer: Mailer,
    settings: Settings,
    *,
    now: datetime | None = None,
    stop: Event | None = None,
    limit: int = 50,
) -> int:
    """Lease requests before network I/O so no SQLite writer lock spans delivery."""
    if not mail_configured(settings):
        return 0
    sent = 0
    for _ in range(limit):
        moment = now or datetime.now(UTC)
        if stop is not None and stop.is_set():
            break
        with Session(engine, expire_on_commit=False) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            row = session.scalars(
                select(AccountEmail)
                .where(
                    AccountEmail.ready.is_(True),
                    AccountEmail.sent_at.is_(None),
                    AccountEmail.failed_at.is_(None),
                    AccountEmail.next_attempt_at <= moment,
                    or_(
                        AccountEmail.lease_until.is_(None),
                        AccountEmail.lease_until <= moment,
                    ),
                )
                .order_by(AccountEmail.created_at, AccountEmail.id)
                .limit(1)
            ).first()
            if row is None:
                break
            if row.payload_json is None:
                url = ""
                if settings.app_base_url:
                    try:
                        url = validate_public_origin(settings.app_base_url) + "/account"
                    except RuntimeError:
                        pass
                context = json.loads(row.context_json)
                owner = session.get(User, row.user_id)
                language = (
                    owner.dashboard_language if owner else context.get("language", "en")
                )
                context.pop("language", None)
                body, html = render_email(
                    "account_event",
                    **context,
                    language=language,
                    occurred_at=row.created_at.isoformat(),
                    account_url=url,
                )
                row.payload_json = json.dumps(
                    {
                        "to": row.recipient,
                        "subject": f"{translate(context['title'], language)} - Résumé Tailor Harness",
                        "body": body,
                        "html": html,
                        "idempotency_key": f"account-{row.id}",
                    }
                )
            payload = json.loads(row.payload_json)
            row.attempts += 1
            row.lease_until = moment + timedelta(minutes=2)
            row_id, attempts = row.id, row.attempts
            session.commit()
        delivered = False
        retryable = True
        try:
            mailer.send(**payload)
            delivered = True
        except Exception as error:
            retryable = getattr(error, "retryable", True)
            # Do not log the rendered payload, account details or credentials.
            logger.warning("Account email %s failed on attempt %s", row_id, attempts)
        with Session(engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            row = session.get(AccountEmail, row_id)
            if row is not None and row.sent_at is None and row.attempts == attempts:
                row.lease_until = None
                if delivered:
                    row.sent_at = moment
                    sent += 1
                elif not retryable or attempts >= MAX_DELIVERY_ATTEMPTS:
                    row.failed_at = moment
                    row.failure_reason = (
                        "permanent_delivery_error"
                        if not retryable
                        else "retry_exhausted"
                    )
                else:
                    row.next_attempt_at = moment + timedelta(
                        minutes=min(360, 2 ** min(attempts, 9))
                    )
                session.commit()
    return sent
