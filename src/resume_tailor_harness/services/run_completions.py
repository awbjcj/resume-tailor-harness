"""Durable terminal run history and read state."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import insert, literal
from sqlmodel import Session, col, select

from resume_tailor_harness.tracking.tables import (
    ClearedRunHistory,
    RunCompletion,
    RunOperationLog,
    utcnow,
)

RUN_COMPLETION_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


def record_run_completion(
    session: Session,
    *,
    run_id: str,
    kind: str,
    label: str,
    status: str,
    error: str | None,
    completed_at: datetime,
    logs: list[dict[str, str]] | None = None,
) -> RunCompletion:
    if status not in RUN_COMPLETION_STATUSES:
        raise ValueError(f"unsupported run completion status: {status}")
    existing = session.exec(
        select(RunCompletion).where(RunCompletion.run_id == run_id)
    ).first()
    if existing is not None:
        return existing
    row = RunCompletion(
        run_id=run_id,
        kind=kind,
        label=label,
        status=status,
        error=error,
        completed_at=completed_at,
    )
    session.add(row)
    session.add(RunOperationLog(run_id=run_id, entries=logs or []))
    session.commit()
    session.refresh(row)
    return row


def list_run_completions(
    session: Session,
    *,
    limit: int = 50,
    unread_only: bool = False,
    surface: str = "operations",
) -> list[RunCompletion]:
    hidden = select(ClearedRunHistory.run_id).where(
        ClearedRunHistory.surface == surface
    )
    query = (
        select(RunCompletion)
        .where(col(RunCompletion.run_id).not_in(hidden))
        .order_by(col(RunCompletion.completed_at).desc(), col(RunCompletion.id).desc())
    )
    if unread_only:
        query = query.where(col(RunCompletion.read_at).is_(None))
    return list(session.exec(query.limit(limit)).all())


def mark_run_completion_read(
    session: Session, completion_id: int
) -> RunCompletion | None:
    row = session.get(RunCompletion, completion_id)
    if row is None:
        return None
    if row.read_at is None:
        row.read_at = utcnow()
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def mark_all_run_completions_read(session: Session) -> int:
    rows = session.exec(
        select(RunCompletion).where(col(RunCompletion.read_at).is_(None))
    ).all()
    if not rows:
        return 0
    read_at = utcnow()
    for row in rows:
        row.read_at = read_at
        session.add(row)
    session.commit()
    return len(rows)


def clear_run_history(session: Session, *, surface: str) -> int:
    hidden = select(ClearedRunHistory.run_id).where(
        ClearedRunHistory.surface == surface
    )
    # One statement makes concurrent clear requests idempotent, including SQLite.
    statement = insert(ClearedRunHistory).from_select(
        ["run_id", "surface"],
        select(RunCompletion.run_id, literal(surface)).where(
            col(RunCompletion.run_id).not_in(hidden)
        ),
    )
    result = session.connection().execute(statement)
    session.commit()
    return result.rowcount


def operation_logs(session: Session, completion_id: int) -> list[dict[str, str]] | None:
    row = session.get(RunCompletion, completion_id)
    if row is None or session.get(ClearedRunHistory, (row.run_id, "operations")):
        return None
    log = session.get(RunOperationLog, row.run_id)
    return log.entries if log else []
