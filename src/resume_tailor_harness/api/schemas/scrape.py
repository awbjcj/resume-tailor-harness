from pydantic import Field, JsonValue

from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.discovery.scraper.contracts import (
    BoardPlan,
    CrawlLimits,
    JobFacts,
    FieldName,
)


class OverrideOut(CamelModel):
    field: FieldName
    revision: int
    value: JsonValue
    removed: bool


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
