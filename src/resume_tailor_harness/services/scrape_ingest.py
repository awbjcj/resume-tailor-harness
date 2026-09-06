"""Observation persistence is independent of canonical-source ingest no-ops."""

from sqlmodel import Session, col, select

from resume_tailor_harness.discovery.connectors.dates import parse_iso_datetime
from resume_tailor_harness.services.discovery import _save_with_active_job_limit
from resume_tailor_harness.discovery.scraper.contracts import Observation
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.discovery.scraper.tables import ScrapeObservationRow
from resume_tailor_harness.models.job import EmploymentType, JobCriteria, SalaryRange
from resume_tailor_harness.tracking.tables import Job


def ingest_observation(
    session: Session,
    observation: Observation,
    store: ScrapeStore,
    *,
    inline: bool = False,
) -> int | None:
    store.save_observation(observation)
    if not observation.accepted:
        return None
    facts = store.effective_facts(observation)
    if not facts.title or not facts.jd_text:
        return None
    existing = find_observed_job(session, observation, store, inline=inline)
    if existing is not None and existing.status != "raw":
        row = session.get(ScrapeObservationRow, observation.id)
        if row is None:
            raise RuntimeError("saved observation is missing")
        row.job_id = existing.id
        session.add(row)
        session.flush()
        return existing.id
    job = _save_with_active_job_limit(
        session,
        source="scrape",
        url=facts.source_url,
        title=facts.title,
        company=facts.company,
        location="; ".join(facts.locations) if facts.locations else None,
        jd_text=facts.jd_text,
        posted_at=parse_iso_datetime(facts.posted_at),
        commit=False,
        source_identity=observation.job_key if inline else None,
    )
    if job is None:
        job = existing
    if job is None:
        return None
    row = session.get(ScrapeObservationRow, observation.id)
    if row is None:
        raise RuntimeError("saved observation is missing")
    row.job_id = job.id
    row.applied = job.status == "raw" and job.source == "scrape"
    session.add(row)
    session.flush()
    return job.id


def project_source_facts(
    session: Session, job_id: int, criteria: JobCriteria
) -> JobCriteria:
    row = session.exec(
        select(ScrapeObservationRow)
        .where(
            col(ScrapeObservationRow.job_id) == job_id,
            col(ScrapeObservationRow.applied).is_(True),
        )
        .order_by(col(ScrapeObservationRow.observed_at).desc())
    ).first()
    if row is None:
        return criteria
    observation = Observation.model_validate_json(row.payload)
    facts = ScrapeStore(session).effective_facts(observation)
    result = criteria.model_copy(deep=True)
    result.remote_policy = facts.remote_policy
    result.location = "; ".join(facts.locations) if facts.locations else None
    result.employment_type = (
        EmploymentType(facts.employment_type)
        if facts.employment_type in {item.value for item in EmploymentType}
        else None
    )
    result.salary_range = None
    if facts.salary_bands and len(facts.salary_bands) == 1:
        salary = facts.salary_bands[0]
        if salary.currency and salary.period:
            result.salary_range = SalaryRange(
                minimum=float(salary.minimum) if salary.minimum is not None else None,
                maximum=float(salary.maximum) if salary.maximum is not None else None,
                currency=salary.currency,
                period=salary.period.lower(),
            )
    return JobCriteria.model_validate(
        {
            **result.model_dump(mode="json"),
            "source_facts": facts.model_dump(mode="json"),
        }
    )


def find_observed_job(
    session: Session,
    observation: Observation,
    store: ScrapeStore,
    *,
    inline: bool = False,
) -> Job | None:
    if inline:
        return session.exec(
            select(Job).where(col(Job.source_identity) == observation.job_key)
        ).first()
    from resume_tailor_harness.discovery.merge import IncomingJob
    from resume_tailor_harness.tracking.repository import find_existing

    facts = store.effective_facts(observation)
    incoming = IncomingJob.clean(
        source="scrape",
        jd_text=facts.jd_text or "",
        url=facts.source_url,
        title=facts.title,
        company=facts.company,
        location="; ".join(facts.locations) if facts.locations else None,
    )
    return find_existing(
        session,
        incoming.url,
        incoming.jd_text,
        incoming.dedup_key,
        incoming.content_fingerprint,
        incoming.location,
    )
