"""Tenant-owned scraping state; callers own transaction boundaries."""

from sqlmodel import Field, SQLModel
import time


class ScrapeDraftRow(SQLModel, table=True):
    __tablename__ = "scrape_drafts"
    id: str = Field(primary_key=True)
    revision: int
    payload: str
    approved_from: int | None = None


class ScrapeSourceRow(SQLModel, table=True):
    __tablename__ = "scrape_sources"
    id: str = Field(primary_key=True)
    url: str = Field(index=True, unique=True)
    revision: int = 0
    enabled: bool = True
    payload: str


class ScrapeRevisionRow(SQLModel, table=True):
    __tablename__ = "scrape_revisions"
    source_id: str = Field(primary_key=True)
    revision: int = Field(primary_key=True)
    payload: str


class ScrapeObservationRow(SQLModel, table=True):
    __tablename__ = "scrape_observations"
    id: str = Field(primary_key=True)
    job_key: str | None = Field(index=True)
    source_id: str = Field(index=True)
    job_id: int | None = Field(default=None, index=True)
    observed_at: float = Field(default_factory=time.time)
    applied: bool = False
    payload: str


class ScrapeSnapshotRow(SQLModel, table=True):
    __tablename__ = "scrape_snapshots"
    id: str = Field(primary_key=True)
    payload: str


class ScrapeCacheRow(SQLModel, table=True):
    __tablename__ = "scrape_cache"
    key: str = Field(primary_key=True)
    expires_at: float
    payload: str


class ScrapeOverrideRow(SQLModel, table=True):
    __tablename__ = "scrape_overrides"
    job_key: str = Field(primary_key=True)
    field: str = Field(primary_key=True)
    revision: int
    removed: bool = False
    value: str


class ScrapeOverrideHistoryRow(SQLModel, table=True):
    __tablename__ = "scrape_override_history"
    job_key: str = Field(primary_key=True)
    field: str = Field(primary_key=True)
    revision: int = Field(primary_key=True)
    removed: bool
    value: str


class ScrapeApprovalRow(SQLModel, table=True):
    __tablename__ = "scrape_approvals"
    draft_id: str = Field(primary_key=True)
    payload: str
