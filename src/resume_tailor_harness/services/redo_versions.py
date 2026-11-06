"""Track the resume versions a Redo run can replace."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, select

from resume_tailor_harness.db import workspace_write
from resume_tailor_harness.render.export import export_job_artifacts, resume_json_name
from resume_tailor_harness.services.application_materials import (
    resume_application_eligible,
)
from resume_tailor_harness.tenancy.storage import resolve_artifact_pdf
from resume_tailor_harness.tracking.repository import delete_artifact_rows
from resume_tailor_harness.tracking.tables import (
    Application,
    CoverLetter,
    ResumeVersion,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VersionRef:
    id: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: ResumeVersion) -> "VersionRef":
        assert row.id is not None
        return cls(row.id, row.created_at)


@dataclass(frozen=True)
class VersionCleanup:
    removed_ids: tuple[int, ...] = ()
    error: str | None = None


def _unused_tailored_versions(job_ids: Sequence[int]):
    selected = col(Application.resume_version_id)
    revised = col(ResumeVersion.parent_version_id)
    letter_source = col(CoverLetter.resume_version_id)
    version_id = col(ResumeVersion.id)
    return (
        col(ResumeVersion.job_id).in_(job_ids),
        ResumeVersion.origin == "tailor",
        version_id.not_in(select(selected).where(selected.is_not(None))),
        version_id.not_in(select(revised).where(revised.is_not(None))),
        version_id.not_in(select(letter_source).where(letter_source.is_not(None))),
    )


def snapshot_previous_versions(
    session: Session, job_ids: Sequence[int]
) -> dict[int, set[VersionRef]]:
    """Remember eligible IDs before any new versions are written by this run."""
    previous: dict[int, set[VersionRef]] = {}
    for job_id, version_id, created_at in session.exec(
        select(ResumeVersion.job_id, ResumeVersion.id, ResumeVersion.created_at).where(
            *_unused_tailored_versions(job_ids)
        )
    ):
        assert version_id is not None
        previous.setdefault(job_id, set()).add(VersionRef(version_id, created_at))
    return previous


def remove_superseded_versions(
    session: Session,
    job_id: int,
    previous: set[VersionRef],
    replacement: VersionRef,
    *,
    checkpoint: Callable[[], None] | None = None,
) -> VersionCleanup:
    """Delete only earlier, unreferenced rounds with a fact-checked replacement."""
    # Serialize the eligibility read and delete with application selection and
    # artifact publication. The provider and renderer have already finished.
    with workspace_write(session):
        if checkpoint is not None:
            checkpoint()
        version = session.get(ResumeVersion, replacement.id, populate_existing=True)
        if (
            version is None
            or version.job_id != job_id
            or VersionRef.from_row(version) != replacement
            or not resume_application_eligible(
                version.fact_check_passed,
                version.critique_json,
                version.gate_reviewers_json,
            )
        ):
            return VersionCleanup()

        has_pdf = resolve_artifact_pdf(version.pdf_path) is not None
        candidates = session.exec(
            select(ResumeVersion)
            .where(
                *_unused_tailored_versions([job_id]),
                col(ResumeVersion.id).in_([ref.id for ref in previous]),
                ResumeVersion.id != replacement.id,
            )
            .order_by(col(ResumeVersion.id))
            .execution_options(populate_existing=True)
        )
        # A saved PDF remains useful until the replacement has its own PDF.
        rows = [
            row
            for row in candidates
            if VersionRef.from_row(row) in previous and (has_pdf or not row.pdf_path)
        ]
        if not rows:
            return VersionCleanup()

        removed = tuple(VersionRef.from_row(row).id for row in rows)
        sidecars = tuple(resume_json_name(row) for row in rows)
        if checkpoint is not None:
            checkpoint()
        delete_artifact_rows(session, versions=rows)
    try:
        export_job_artifacts(session, job_id, removed_resume_sidecars=sidecars)
    except Exception:
        # The database deletion has committed. Report the deleted IDs even if
        # a derived export could not be refreshed.
        logger.warning("could not refresh exports for job=%s", job_id, exc_info=True)
        return VersionCleanup(removed, "Could not refresh the resume export files")
    return VersionCleanup(removed)
