"""Read models for public scrape review and correction surfaces."""

import json
from dataclasses import dataclass
from typing import cast

from pydantic import JsonValue
from sqlmodel import Session, col, select

from resume_tailor_harness.discovery.scraper.contracts import (
    Draft,
    CrawlLimits,
    Evidence,
    FieldIssue,
    FieldName,
    JobFacts,
    Observation,
)
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.discovery.scraper.tables import (
    ScrapeObservationRow,
    ScrapeOverrideRow,
    ScrapeRevisionRow,
    ScrapeSourceRow,
)


@dataclass(frozen=True)
class SourceObservationView:
    id: str
    job_key: str | None
    source_id: str
    revision: int
    facts: JobFacts
    effective_facts: JobFacts
    evidence: list[Evidence]
    issues: list[FieldIssue]
    accepted: bool


@dataclass(frozen=True)
class OverrideView:
    field: FieldName
    revision: int
    value: JsonValue
    removed: bool


def get_draft(session: Session, draft_id: str) -> Draft:
    return ScrapeStore(session).get_draft(draft_id)


def source_revisions(session: Session, source_id: str) -> list[Draft]:
    rows = session.exec(
        select(ScrapeRevisionRow).where(ScrapeRevisionRow.source_id == source_id)
    ).all()
    return [Draft.model_validate_json(row.payload) for row in rows]


def source_analysis_request(
    session: Session, source_id: str
) -> tuple[str, CrawlLimits]:
    row = session.get(ScrapeSourceRow, source_id)
    if row is None:
        raise KeyError(source_id)
    draft = Draft.model_validate_json(row.payload)
    return draft.url, draft.limits


def job_observations(session: Session, job_id: int) -> list[SourceObservationView]:
    rows = session.exec(
        select(ScrapeObservationRow)
        .where(ScrapeObservationRow.job_id == job_id)
        .order_by(col(ScrapeObservationRow.observed_at))
    ).all()
    store = ScrapeStore(session)
    result = []
    for row in rows:
        item = Observation.model_validate_json(row.payload)
        result.append(
            SourceObservationView(
                id=item.id,
                job_key=item.job_key,
                source_id=item.source_id,
                revision=item.revision,
                facts=item.facts,
                effective_facts=store.effective_facts(item),
                evidence=item.evidence,
                issues=item.issues,
                accepted=item.accepted,
            )
        )
    return result


def _job_key(session: Session, job_id: int) -> str:
    row = session.exec(
        select(ScrapeObservationRow)
        .where(ScrapeObservationRow.job_id == job_id)
        .order_by(col(ScrapeObservationRow.observed_at).desc())
    ).first()
    if row is None or row.job_key is None:
        raise KeyError(job_id)
    return row.job_key


def job_overrides(session: Session, job_id: int) -> list[OverrideView]:
    key = _job_key(session, job_id)
    rows = session.exec(
        select(ScrapeOverrideRow).where(ScrapeOverrideRow.job_key == key)
    ).all()
    return [
        OverrideView(
            field=cast(FieldName, row.field),
            revision=row.revision,
            value=json.loads(row.value),
            removed=row.removed,
        )
        for row in rows
    ]
