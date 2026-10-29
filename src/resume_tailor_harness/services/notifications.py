"""Persist inbound Gmail status proposals as reviewable notifications."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import update
from sqlmodel import Session, col

from resume_tailor_harness.gmail.classify import classify_email
from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.gmail.propose import _is_forward, propose_transitions
from resume_tailor_harness.tracking.queries import application_job_pairs
from resume_tailor_harness.tracking.repository import (
    get_notification,
    notification_by_key,
    pending_notifications,
    save_notification,
)
from resume_tailor_harness.tracking.tables import (
    Application,
    ApplicationStatus,
    Notification,
)


def sync_notifications(
    session: Session,
    emails: Sequence[EmailMessage],
    *,
    classify: Callable[[EmailMessage], str] = classify_email,
    hydrate: Callable[[EmailMessage], None] | None = None,
) -> list[Notification]:
    for proposal in propose_transitions(
        emails, application_job_pairs(session), classify, hydrate=hydrate
    ):
        if not proposal.message_id:
            continue
        existing = notification_by_key(
            session, proposal.application_id, proposal.message_id
        )
        if existing is not None:
            continue
        save_notification(
            session,
            Notification(
                application_id=proposal.application_id,
                kind=proposal.proposed_status,
                proposed_status=proposal.proposed_status,
                evidence=proposal.evidence,
                message_id=proposal.message_id,
            ),
        )
    return pending_notifications(session)


def accept_notification(session: Session, notification_id: int) -> Notification | None:
    notification = get_notification(session, notification_id)
    if notification is None or notification.state != "pending":
        return None
    claimed = session.execute(
        update(Notification)
        .where(
            col(Notification.id) == notification_id,
            col(Notification.state) == "pending",
        )
        .values(state="accepted")
        .returning(col(Notification.id))
    ).first()
    if claimed is None:
        session.rollback()
        return None
    # Reminder kinds carry no status proposal — accepting only acknowledges.
    if notification.proposed_status:
        allowed = [
            status.value
            for status in ApplicationStatus
            if _is_forward(status.value, notification.proposed_status)
        ]
        session.execute(
            update(Application)
            .where(
                col(Application.id) == notification.application_id,
                col(Application.status).in_(allowed),
            )
            .values(status=notification.proposed_status)
        )
    session.commit()
    session.refresh(notification)
    return notification


def dismiss_notification(session: Session, notification_id: int) -> Notification | None:
    notification = get_notification(session, notification_id)
    if notification is None:
        return None
    notification.state = "dismissed"
    return save_notification(session, notification)


def list_pending(session: Session) -> list[Notification]:
    return pending_notifications(session)


def clear_notification_history(session: Session) -> int:
    from resume_tailor_harness.services.run_completions import clear_run_history

    # Application actions have their own Accept/Dismiss controls. Clearing run
    # history must neither hide pending proposals nor erase prior decisions.
    return clear_run_history(session, surface="notifications")
