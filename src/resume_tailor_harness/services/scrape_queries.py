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
from resume_tailor_harness.discovery.scraper.store import (
    CORRECTION_REVISION_MARKER,
    SAVED_CORRECTION_CONFLICT,
    ScrapeStore,
)
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
        effective = store.effective_facts(item)
        issues = []
        for issue in item.issues:
            if issue.kind != "conflict" or not issue.field:
                issues.append(issue)
                continue
            prefix, marker, revision = issue.message.partition(CORRECTION_REVISION_MARKER)
            if prefix != SAVED_CORRECTION_CONFLICT:
                issues.append(issue)
                continue
            if marker and revision.endswith("]") and revision[:-1].isdigit():
                current = session.get(ScrapeOverrideRow, (item.job_key, issue.field)) if item.job_key else None
                if current is not None and not current.removed and current.revision == int(revision[:-1]):
                    issues.append(issue.model_copy(update={"message": prefix}))
            elif issue.message == SAVED_CORRECTION_CONFLICT:
                # Legacy observations have no revision provenance. Preserve
                # their previous conservative comparison behavior.
                if getattr(item.facts, issue.field) != getattr(effective, issue.field):
                    issues.append(issue)
            else:
                issues.append(issue)
        result.append(
            SourceObservationView(
                id=item.id,
                job_key=item.job_key,
                source_id=item.source_id,
                revision=item.revision,
                facts=item.facts,
                effective_facts=effective,
                evidence=item.evidence,
                issues=issues,
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
