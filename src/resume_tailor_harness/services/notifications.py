"""Persist inbound Gmail status proposals as reviewable notifications."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import update
from sqlmodel import Session, col

from resume_tailor_harness.gmail.classify import classify_email
from resume_tailor_harness.gmail.client import EmailMessage
from resume_tailor_harness.gmail.propose import _is_forward, propose_transitions
from resume_tailor_harness.services.application_events import (
    EventValidationError,
    create_event,
)
from resume_tailor_harness.tracking.event_vocab import KIND_IMPLIES_STATUS
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


class NotificationConflictError(Exception):
    """A reviewed proposal is no longer current enough to capture an event."""


def notification_revision(notification: Notification) -> str:
    """Identify the exact proposal shown during a timeline review.

    Pending proposals can be corrected in place during sync. State is checked
    separately by the atomic claim; account-qualified message ids stay intact.
    """
    snapshot = [
        notification.id,
        notification.application_id,
        notification.message_id,
        notification.kind,
        notification.proposed_status,
        notification.evidence,
    ]
    return sha256(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")).hexdigest()


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


def _proposal_event(
    notification: Notification, event: dict[str, Any]
) -> dict[str, Any]:
    if not notification.proposed_status or (
        KIND_IMPLIES_STATUS.get(event.get("kind", "")) != notification.proposed_status
    ):
        raise EventValidationError(
            "Event stage must match the proposed application status"
        )
    occurred_at = event.get("occurred_at")
    if not isinstance(occurred_at, datetime) or occurred_at.utcoffset() is None:
        raise EventValidationError("Confirm an event date with a UTC offset")
    if not event.get("all_day", False) and not (event.get("timezone") or "").strip():
        raise EventValidationError("Confirm an IANA timezone for a timed event")
    # The saved source evidence cannot be lost by editing the draft notes. Keep
    # the full account-qualified identity, even for equal provider message ids.
    provenance = f"Message: {notification.message_id}\n{notification.evidence}"
    notes = (event.get("notes") or "").strip()
    if notes == notification.evidence.strip():
        notes = ""
    return {
        **event,
        "source": "mailbox",
        "notes": "\n\n".join(filter(None, [notes, provenance])),
    }


def accept_notification(
    session: Session,
    notification_id: int,
    *,
    event: dict[str, Any] | None = None,
    expected_revision: str | None = None,
    event_details_confirmed: bool = False,
) -> Notification | None:
    """Accept once; optional reviewed timeline capture shares the same commit.

    Status-only acceptance keeps its historical stale-proposal acknowledgement
    behavior. Timeline capture instead rejects a stale status or review so it
    cannot create an appointment from a superseded proposal.
    """
    try:
        # Claim before loading: the write serializes concurrent accept/sync
        # transactions and a stale identity-map object cannot bypass this gate.
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
        notification = get_notification(session, notification_id)
        if notification is None:
            raise RuntimeError("Claimed notification disappeared")
        session.refresh(notification)
        event_payload = None
        if event is not None:
            if not event_details_confirmed:
                raise EventValidationError(
                    "Confirm the timeline event details before accepting"
                )
            if expected_revision != notification_revision(notification):
                raise NotificationConflictError(
                    "This application update changed. Review the latest proposal."
                )
            event_payload = _proposal_event(notification, event)
        # Reminder kinds carry no status proposal — accepting only acknowledges.
        if notification.proposed_status:
            allowed = [
                status.value
                for status in ApplicationStatus
                if _is_forward(status.value, notification.proposed_status)
            ]
            changed = session.execute(
                update(Application)
                .where(
                    col(Application.id) == notification.application_id,
                    col(Application.status).in_(allowed),
                )
                .values(status=notification.proposed_status)
                .returning(col(Application.job_id))
            ).first()
            if event_payload is not None:
                if changed is None:
                    raise NotificationConflictError(
                        "The application status changed. Review the latest "
                        "application before adding an event."
                    )
                # create_event owns all ordinary event validation, chronology
                # and status rules, but this command owns the single commit.
                created = create_event(session, changed[0], event_payload, commit=False)
                if created.application_id != notification.application_id:
                    raise EventValidationError(
                        "The proposal no longer identifies this application's timeline"
                    )
        session.commit()
        session.refresh(notification)
        return notification
    except BaseException:
        session.rollback()
        raise


def dismiss_notification(session: Session, notification_id: int) -> Notification | None:
    claimed = session.execute(
        update(Notification)
        .where(
            col(Notification.id) == notification_id,
            col(Notification.state) == "pending",
        )
        .values(state="dismissed")
        .returning(col(Notification.id))
    ).first()
    if claimed is None:
        session.rollback()
        return None
    session.commit()
    notification = get_notification(session, notification_id)
    if notification is not None:
        session.refresh(notification)
    return notification


def list_pending(session: Session) -> list[Notification]:
    return pending_notifications(session)


def clear_notification_history(session: Session) -> int:
    from resume_tailor_harness.services.run_completions import clear_run_history

    # Application actions have their own Accept/Dismiss controls. Clearing run
    # history must neither hide pending proposals nor erase prior decisions.
    return clear_run_history(session, surface="notifications")
