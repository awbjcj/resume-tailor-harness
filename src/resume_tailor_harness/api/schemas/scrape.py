from typing import Literal

from pydantic import Field, JsonValue

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    CrawlLimits,
    Evidence,
    FieldIssue,
    JobFacts,
    FieldName,
    NavigationOutcome,
    ValidationResult,
)


class OverrideOut(CamelModel):
    field: FieldName
    revision: int
    value: JsonValue
    removed: bool


class OverridePatchIn(CamelModel):
    field: FieldName
    value: JsonValue
    expected_revision: int = Field(ge=0)


class OverrideRevisionOut(CamelModel):
    revision: int


class ObservationOut(CamelModel):
    id: str
    job_key: str | None = None
    source_id: str
    revision: int
    facts: JobFacts
    effective_facts: JobFacts | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    issues: list[FieldIssue] = Field(default_factory=list)
    accepted: bool = False


class DraftOut(CamelModel):
    id: str
    source_id: str
    url: str
    enabled: bool
    page_kind: Literal[
        "posting", "listing", "empty_listing", "blocked", "unrelated"
    ]
    revision: int
    base_revision: int
    corrections: dict[str, dict[FieldName, JsonValue]]
    correction_revisions: dict[str, dict[FieldName, int]]
    plan: BoardPlan | None = None
    limits: CrawlLimits
    samples: list[ObservationOut]
    validation: ValidationResult
    navigation: NavigationOutcome | None = None
    state: Literal["draft", "validated", "approved", "unverified"]


class ApprovalResultOut(CamelModel):
    source_id: str
    approved_revision: int
    job_ids: list[int] = Field(default_factory=list)


class AnalyzeIn(CamelModel):
    url: str = Field(min_length=1, max_length=8192)
    limits: CrawlLimits = Field(default_factory=CrawlLimits)


class RevisionIn(CamelModel):
    expected_revision: int = Field(ge=0)


class ApproveIn(RevisionIn):
    selected_keys: list[str] = Field(default_factory=list, max_length=3)


class DraftPatchIn(RevisionIn):
    plan: BoardPlan | None = None
    limits: CrawlLimits | None = None
    samples: dict[str, JobFacts] | None = None


class RollbackIn(RevisionIn):
    revision: int = Field(ge=1)


class SnapshotElement(CamelModel):
    selector: str
    text: str


class SourceStateIn(RevisionIn):
    enabled: bool
