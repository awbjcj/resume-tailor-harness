"""Portable URL-bound rules exclude jobs, evidence, credentials and approval."""

from pydantic import BaseModel, Field
from sqlmodel import Session, delete
from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    CrawlLimits,
    Draft,
)
from resume_tailor_harness.discovery.scraper.identity import (
    board_key,
    normalize_board_url,
)
from resume_tailor_harness.discovery.scraper.store import ScrapeStore
from resume_tailor_harness.discovery.scraper.tables import (
    ScrapeSourceRow,
    ScrapeRevisionRow,
    ScrapeDraftRow,
    ScrapeApprovalRow,
    ScrapeCacheRow,
)


class PortableSource(BaseModel):
    url: str = Field(max_length=8192)
    plan: BoardPlan | None = None
    limits: CrawlLimits = Field(default_factory=CrawlLimits)


class SourceBundle(BaseModel):
    sources: list[PortableSource] = Field(default_factory=list, max_length=1000)


def export_sources(session: Session) -> str:
    sources = []
    for row in ScrapeStore(session).list_sources():
        draft = Draft.model_validate_json(row.payload)
        if draft.state != "approved":
            continue
        sources.append(
            PortableSource(url=draft.url, plan=draft.plan, limits=draft.limits)
        )
    return SourceBundle(sources=sources).model_dump_json()


def reset_sources(session: Session) -> None:
    for table in (
        ScrapeApprovalRow,
        ScrapeDraftRow,
        ScrapeCacheRow,
        ScrapeRevisionRow,
        ScrapeSourceRow,
    ):
        session.exec(delete(table))


def import_sources(session: Session, payload: str) -> None:
    bundle = SourceBundle.model_validate_json(payload)
    drafts = [
        Draft(
            source_id=board_key(item.url),
            url=normalize_board_url(item.url),
            plan=item.plan,
            limits=item.limits,
            state="unverified",
        )
        for item in bundle.sources
    ]
    reset_sources(session)
    for draft in {item.source_id: item for item in drafts}.values():
        session.add(
            ScrapeSourceRow(
                id=draft.source_id,
                url=draft.url,
                revision=0,
                enabled=False,
                payload=draft.model_dump_json(),
            )
        )
    session.flush()
