"""Opt-in Gmail rejection updates and their application timeline audit trail."""

from datetime import datetime, timezone
from urllib.parse import quote

from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased
from sqlmodel import Session, col, select

from resume_tailor_harness.db import workspace_write
from resume_tailor_harness.gmail.catalog import ApplicationCatalog
from resume_tailor_harness.gmail.classify import confirmed_rejection
from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.gmail.tables import GmailAutomationPreference, GmailReceipt
from resume_tailor_harness.services.application_events import create_event
from resume_tailor_harness.tracking.tables import Application, Job, Notification, utcnow


def preference(session: Session) -> GmailAutomationPreference | None:
    return session.get(GmailAutomationPreference, 1)


def set_automation(session: Session, account: str | None) -> None:
    """Grant one connected mailbox consent, or clear consent on disconnect."""
    with workspace_write(session):
        current = preference(session)
        if account is None and current is not None:
            session.delete(current)
        elif account is not None:
            if current is None:
                session.add(GmailAutomationPreference(account=account))
            elif current.account != account:
                current.account = account
                current.enabled_at = utcnow()
        session.commit()


def apply_confirmed_rejections(
    session: Session, account: str, catalog: ApplicationCatalog
) -> int:
    # Serialize with preference changes, edits and explicit proposal review.
    if preference(session) is None:
        return 0
    with workspace_write(session):
        session.expire_all()
        settings = preference(session)
        if settings is None or settings.account != account:
            return 0

        since = int(settings.enabled_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
        now = int(utcnow().timestamp() * 1000)
        catalog.refresh(session)
        other = aliased(GmailReceipt)
        conflicting_decision = (
            select(col(other.message_id))
            .where(
                col(other.application_id) == col(GmailReceipt.application_id),
                col(other.internal_date) >= col(GmailReceipt.internal_date),
                or_(
                    col(other.account) != account,
                    col(other.message_id) != col(GmailReceipt.message_id),
                ),
                or_(col(other.label) != "none", col(other.outcome) == "retry"),
            )
            .exists()
        )
        candidates = session.exec(
            select(Notification, GmailReceipt, Application)
            .join(
                GmailReceipt,
                and_(
                    col(GmailReceipt.account) == account,
                    col(Notification.message_id)
                    == f"gmail:{account}:" + col(GmailReceipt.message_id),
                    col(Notification.application_id)
                    == col(GmailReceipt.application_id),
                ),
            )
            .join(Application, col(Application.id) == col(Notification.application_id))
            .join(Job, col(Job.id) == col(Application.job_id))
            .where(
                col(Notification.state) == "pending",
                col(Notification.proposed_status) == "rejected",
                col(Application.status) == "submitted",
                col(Job.archived_at).is_(None),
                col(GmailReceipt.label) == "rejection",
                col(GmailReceipt.revision) == catalog.revision,
                col(GmailReceipt.internal_date) > since,
                col(GmailReceipt.internal_date) <= now,
                ~conflicting_decision,
            )
        ).all()
        applied = 0
        for notice, receipt, application in candidates:
            occurred_at = datetime.fromtimestamp(
                receipt.internal_date / 1000, timezone.utc
            )
            submitted_at = application.submitted_at
            if submitted_at and occurred_at < submitted_at.replace(tzinfo=timezone.utc):
                continue
            email = EmailMessage(**receipt.email_json)
            if not (
                email.incoming
                and confirmed_rejection(email)
                and catalog.matcher.confirms_requisition(email, application.job_id)
            ):
                continue
            link = f"https://mail.google.com/mail/#all/{quote(receipt.message_id, safe='')}"
            create_event(
                session,
                application.job_id,
                {
                    "kind": "rejected",
                    "occurred_at": occurred_at,
                    "timezone": "UTC",
                    "result": "rejected",
                    "source": "mailbox",
                    "notes": f"Automatically applied from Gmail.\n{link}\n\n{notice.evidence}",
                },
                commit=False,
            )
            notice.state = "accepted"
            session.add(notice)
            applied += 1
        session.commit()
        return applied
