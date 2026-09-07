"""Revision-checked job corrections with narrow canonical projection."""

from sqlmodel import Session, col, select

from resume_tailor_harness.discovery.connectors.dates import parse_iso_datetime
from resume_tailor_harness.discovery.merge import IncomingJob
from resume_tailor_harness.discovery.scraper.contracts import (
    FieldName,
    Observation,
    OverridePatch,
)
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.discovery.scraper.tables import ScrapeObservationRow
from resume_tailor_harness.tracking.repository import (
    company_rename_collides,
    has_progress,
)
from resume_tailor_harness.tracking.tables import Job, JobStatus

_ANALYSIS_FIELDS = {
    "title",
    "company",
    "jd_text",
    "locations",
    "salary_bands",
    "remote_policy",
    "remote_restrictions",
    "attendance",
    "employment_type",
}
_CANONICAL_FIELDS = {"company", "title", "locations", "jd_text", "posted_at"}


def set_job_override(
    session: Session, job_id: int, field: FieldName, patch: OverridePatch
) -> int:
    """Save a correction and project only that field onto its canonical job."""
    if patch.field != field:
        raise ValueError("Field does not match request path")
    try:
        row, job_key = _latest_job_observation(session, job_id)
        store = ScrapeStore(session)
        revision = store.set_override(job_key, patch)
        _sync_job_source_fact(session, job_id, row, store, field)
        session.commit()
        return revision
    except Exception:
        session.rollback()
        raise


def clear_job_override(
    session: Session, job_id: int, field: FieldName, expected_revision: int
) -> int:
    """Remove a correction and restore only that source field on its job."""
    try:
        row, job_key = _latest_job_observation(session, job_id)
        store = ScrapeStore(session)
        revision = store.remove_override(job_key, field, expected_revision)
        _sync_job_source_fact(session, job_id, row, store, field)
        session.commit()
        return revision
    except Exception:
        session.rollback()
        raise


def _latest_job_observation(
    session: Session, job_id: int
) -> tuple[ScrapeObservationRow, str]:
    row = session.exec(
        select(ScrapeObservationRow)
        .where(ScrapeObservationRow.job_id == job_id)
        .order_by(col(ScrapeObservationRow.observed_at).desc())
    ).first()
    if row is None or row.job_key is None:
        raise KeyError(job_id)
    return row, row.job_key


def _sync_job_source_fact(
    session: Session,
    job_id: int,
    row: ScrapeObservationRow,
    store: ScrapeStore,
    field: FieldName,
) -> None:
    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(job_id)
    observation = Observation.model_validate_json(row.payload)
    facts = store.effective_facts(observation)
    progressed = job.id is not None and has_progress(session, job.id)
    incoming = IncomingJob.clean(
        source=job.source,
        url=job.url,
        company=facts.company if field == "company" else job.company,
        title=facts.title if field == "title" else job.title,
        location=(
            "; ".join(facts.locations) if facts.locations else None
        )
        if field == "locations"
        else job.location,
        jd_text=(facts.jd_text or "") if field == "jd_text" else job.jd_text,
        posted_at=(
            parse_iso_datetime(facts.posted_at)
            if field == "posted_at"
            else job.posted_at
        ),
    )
    if (
        incoming.dedup_key != job.dedup_key
        and company_rename_collides(
            session, existing=job, dedup_key=incoming.dedup_key
        )
    ):
        raise ValueError("Corrected title and company conflict with another active job")

    if field in _CANONICAL_FIELDS:
        job.company = incoming.company
        job.title = incoming.title
        job.location = incoming.location
        job.jd_text = incoming.jd_text
        job.posted_at = incoming.posted_at
        job.dedup_key = incoming.dedup_key
        job.content_fingerprint = incoming.content_fingerprint
    if field in _ANALYSIS_FIELDS:
        job.criteria_json = None
        job.analysis_meta_json = None
        job.fit_score = None
        job.fit_rationale = None
        job.reject_reason = None
        job.reject_category = None
        job.industry_pending = False
    if not progressed:
        job.status = JobStatus.raw.value
        row.applied = True
        session.add(row)
    session.add(job)
    session.flush()
