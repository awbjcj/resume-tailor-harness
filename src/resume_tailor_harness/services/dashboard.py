"""Read-only dashboard projection: one query pass, no business logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, col, func, select

from resume_tailor_harness.tracking.tables import (
    Application,
    ErrorRecord,
    Job,
    JobStatus,
)
from resume_tailor_harness.services.application_continuation import (
    ApplicationNextStep,
    application_next_steps,
    application_progress_clause,
)


@dataclass(frozen=True)
class DashboardSummary:
    status_counts: dict[str, int] = field(default_factory=dict)
    queues: dict[str, int] = field(default_factory=dict)
    applied: int = 0
    queue_targets: dict[str, ApplicationNextStep] = field(default_factory=dict)


@dataclass(frozen=True)
class PracticeStats:
    completed_sessions: int = 0
    scored_sessions: int = 0
    average_score: float | None = None
    latest_score: float | None = None
    change_from_first: float | None = None


@dataclass(frozen=True)
class SourceHealth:
    open_failures: int = 0
    affected_sources: list[str] = field(default_factory=list)
    latest_failure_at: datetime | None = None


def summarize_dashboard(session: Session) -> DashboardSummary:
    rows = session.exec(
        select(Job.status, func.count())
        .where(Job.archived_at == None)  # noqa: E711 — SQL IS NULL
        .group_by(Job.status)
    ).all()
    counts = {status.value: 0 for status in JobStatus}
    for status, count in rows:
        counts[status] = count
    steps = application_next_steps(session)
    queues: dict[str, int] = dict.fromkeys(
        ("triage", "approve", "tailor", "review", "render", "apply"), 0
    )
    targets: dict[str, ApplicationNextStep] = {}
    for step in steps.values():
        if step.kind in queues:
            queues[step.kind] += 1
            targets.setdefault(step.kind, step)
    applied = session.exec(
        select(func.count(col(Application.job_id).distinct()))
        .select_from(Application)
        .join(Job, col(Application.job_id) == Job.id)
        .where(application_progress_clause(), Job.archived_at == None)  # noqa: E711
    ).one()
    return DashboardSummary(
        status_counts=counts, queues=queues, applied=applied, queue_targets=targets
    )


def summarize_practice(rows: list[dict]) -> PracticeStats:
    ordered = sorted(
        rows, key=lambda row: (row.get("startedAt", ""), row.get("sessionId", ""))
    )
    scores = [
        float(row["overallScore"])
        for row in ordered
        if row.get("overallScore") is not None
    ]
    return PracticeStats(
        completed_sessions=len(rows),
        scored_sessions=len(scores),
        average_score=round(sum(scores) / len(scores), 1) if scores else None,
        latest_score=scores[-1] if scores else None,
        change_from_first=(
            round(scores[-1] - scores[0], 1) if len(scores) >= 2 else None
        ),
    )


def summarize_source_health(session: Session) -> SourceHealth:
    rows = session.exec(
        select(ErrorRecord)
        .where(ErrorRecord.kind == "source", ErrorRecord.status == "open")
        .order_by(col(ErrorRecord.last_seen_at).desc())
    ).all()
    sources = list(dict.fromkeys(row.source_label for row in rows))
    return SourceHealth(
        open_failures=len(rows),
        affected_sources=sources,
        latest_failure_at=rows[0].last_seen_at if rows else None,
    )
