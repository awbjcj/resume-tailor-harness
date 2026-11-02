"""The next useful work for a Job, independent of its processing high-water mark."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select as sql_select
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, col, select

from resume_tailor_harness.services.application_materials import (
    resume_application_eligible,
)
from resume_tailor_harness.tenancy.storage import resolve_artifact_pdf
from resume_tailor_harness.tracking.tables import (
    Application,
    ApplicationEvent,
    Job,
    ResumeVersion,
)

NextStepKind = Literal[
    "triage", "approve", "tailor", "review", "render", "apply", "track"
]


@dataclass(frozen=True)
class ApplicationNextStep:
    job_id: int
    kind: NextStepKind
    href: str
    resume_version_id: int | None = None


@dataclass(frozen=True)
class _ResumeCandidate:
    id: int
    eligible: bool
    pdf_path: str | None
    score: int
    round: int


def _resume_next_step(
    versions: list[_ResumeCandidate], selected_id: int | None
) -> tuple[NextStepKind, int | None]:
    if selected_id:
        version = next((row for row in versions if row.id == selected_id), None)
    else:
        version = max(
            versions,
            key=lambda row: (row.eligible, row.score, row.round, row.id),
            default=None,
        )
    if version is None:
        return ("review" if selected_id else "tailor"), None
    if not version.eligible:
        return "review", version.id
    if resolve_artifact_pdf(version.pdf_path):
        return "apply", version.id
    return "render", version.id


_DESTINATIONS = {
    "triage": ("triage", "job"),
    "approve": ("shortlist", "job"),
    "track": ("pipeline", "tracking"),
}


def application_progress_clause() -> ColumnElement[bool]:
    """Submission history survives a manual reset of the current status."""
    submitted_events = select(ApplicationEvent.application_id).where(
        ApplicationEvent.kind == "application_submitted"
    )
    return or_(
        col(Application.status) != "ready",
        col(Application.submitted_at).is_not(None),
        col(Application.id).in_(submitted_events),
    )


def application_next_steps(
    session: Session,
    job_ids: Collection[int] | None = None,
    *,
    include_archived: bool = False,
) -> dict[int, ApplicationNextStep]:
    """Batch projection: no full descriptions/resume content, no writes, no N+1.

    An explicit selection wins even when it needs repair; choosing a different
    safe resume silently would make preparation disagree with the user's choice.
    """
    if job_ids is not None and not job_ids:
        return {}
    jobs_query = select(Job.id, Job.status).order_by(col(Job.id))
    if not include_archived:
        jobs_query = jobs_query.where(col(Job.archived_at).is_(None))
    if job_ids is not None:
        jobs_query = jobs_query.where(col(Job.id).in_(job_ids))
    jobs = session.exec(jobs_query).all()
    ids = [job_id for job_id, _ in jobs if job_id is not None]
    if not ids:
        return {}
    progressed = set(
        session.exec(
            select(Application.job_id).where(
                col(Application.job_id).in_(ids), application_progress_clause()
            )
        ).all()
    )
    selected: dict[int, int] = {}
    for job_id, version_id in session.exec(
        select(Application.job_id, Application.resume_version_id)
        .where(col(Application.job_id).in_(ids))
        .order_by(col(Application.id))
    ).all():
        if version_id is not None:
            selected.setdefault(job_id, version_id)
    versions: dict[int, list[_ResumeCandidate]] = {}
    for (
        version_id,
        job_id,
        passed,
        path,
        critiques,
        gates,
        score,
        round_number,
    ) in session.execute(
        sql_select(
            col(ResumeVersion.id),
            col(ResumeVersion.job_id),
            col(ResumeVersion.fact_check_passed),
            col(ResumeVersion.pdf_path),
            col(ResumeVersion.critique_json),
            col(ResumeVersion.gate_reviewers_json),
            col(ResumeVersion.review_score),
            col(ResumeVersion.round),
        ).where(col(ResumeVersion.job_id).in_(ids))
    ).all():
        if version_id is not None:
            versions.setdefault(job_id, []).append(
                _ResumeCandidate(
                    id=version_id,
                    eligible=resume_application_eligible(passed, critiques, gates),
                    pdf_path=path,
                    score=score if score is not None else -1,
                    round=round_number,
                )
            )
    result: dict[int, ApplicationNextStep] = {}
    for job_id, status in jobs:
        if job_id is None:
            continue
        version_id = None
        if job_id in progressed:
            kind: NextStepKind = "track"
        elif status == "rejected":
            continue
        elif status in {"raw", "extracted", "filtered"}:
            kind = "triage"
        elif status == "shortlisted":
            kind = "approve"
        else:
            kind, version_id = _resume_next_step(
                versions.get(job_id, []), selected.get(job_id)
            )
        board, tab = _DESTINATIONS.get(kind, ("pipeline", "resumes"))
        result[job_id] = ApplicationNextStep(
            job_id, kind, f"/{board}?job={job_id}&tab={tab}", version_id
        )
    return result
