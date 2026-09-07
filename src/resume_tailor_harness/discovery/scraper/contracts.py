"""Versioned declarations exchanged by public-page extraction and review."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from pydantic.alias_generators import to_camel


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class CrawlLimits(Contract):
    listing_pages: int = Field(default=10, ge=1, le=50)
    detail_pages: int = Field(default=50, ge=1, le=200)
    elapsed_seconds: int = Field(default=300, ge=1, le=900)


class SalaryBand(Contract):
    minimum: Decimal | None = Field(default=None, ge=0)
    maximum: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    period: str | None = None
    locations: list[str] = Field(default_factory=list)
    raw_text: str

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("salary minimum exceeds maximum")
        return self


class JobFacts(Contract):
    title: str | None = None
    company: str | None = None
    jd_text: str | None = None
    locations: list[str] | None = None
    salary_bands: list[SalaryBand] | None = None
    remote_policy: Literal["remote", "hybrid", "onsite"] | None = None
    remote_restrictions: str | None = None
    attendance: str | None = None
    employment_type: str | None = None
    posted_at: str | None = None
    closes_at: str | None = None
    source_url: str
    application_url: str | None = None
    posting_id: str | None = None


FieldName = Literal[
    "title",
    "company",
    "jd_text",
    "locations",
    "salary_bands",
    "remote_policy",
    "remote_restrictions",
    "attendance",
    "employment_type",
    "posted_at",
    "closes_at",
    "source_url",
    "application_url",
    "posting_id",
]


class Evidence(Contract):
    field: FieldName
    snapshot_id: str
    quote: str = Field(min_length=1)
    selector: str | None = None
    json_path: str | None = None


class FieldIssue(Contract):
    field: FieldName | None = None
    kind: Literal["not_stated", "extraction_failed", "conflict", "invalid_evidence"]
    message: str = ""


class Snapshot(Contract):
    etag: str | None = None
    last_modified: str | None = None
    dynamic: bool = True
    id: str
    requested_url: str
    final_url: str
    html: str
    visible_text: str
    json_ld: list[JsonValue] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Observation(Contract):
    id: str = Field(default_factory=lambda: uuid4().hex)
    job_key: str | None = None
    source_id: str
    revision: int = Field(ge=0)
    facts: JobFacts
    evidence: list[Evidence] = Field(default_factory=list)
    issues: list[FieldIssue] = Field(default_factory=list)
    accepted: bool = False


class FieldRule(Contract):
    field: FieldName
    selector: str = Field(min_length=1, max_length=500)
    attribute: Literal["href", "content", "datetime", "data-job-id", "id"] | None = None


class BoardPlan(Contract):
    card_selector: str = Field(min_length=1, max_length=500)
    field_rules: list[FieldRule] = Field(default_factory=list, max_length=30)
    detail_mode: Literal["link", "inline", "panel"] = "link"
    link_selector: str | None = Field(default=None, max_length=500)
    open_selector: str | None = Field(default=None, max_length=500)
    close_selector: str | None = Field(default=None, max_length=500)
    detail_selector: str | None = Field(default=None, max_length=500)
    pagination: Literal["none", "numbered", "next", "load_more", "infinite"] = "none"
    control_selector: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def usable_controls(self) -> Self:
        if self.detail_mode == "link" and not self.link_selector:
            raise ValueError("link details require link_selector")
        if self.detail_mode == "panel" and not (
            self.open_selector and self.close_selector and self.detail_selector
        ):
            raise ValueError("panels require open, close and detail selectors")
        if self.pagination not in {"none", "infinite"} and not self.control_selector:
            raise ValueError("pagination requires control_selector")
        return self


class PageUnderstanding(Contract):
    kind: Literal["posting", "listing", "empty_listing", "blocked", "unrelated"]
    plan: BoardPlan | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class ValidationResult(Contract):
    valid: bool = False
    issues: list[FieldIssue] = Field(default_factory=list)


TerminalReason = Literal[
    "complete",
    "empty",
    "partial_limit",
    "throttled",
    "blocked",
    "review_required",
    "failed",
    "cancelled",
    "capability_unavailable",
]


class NavigationOutcome(Contract):
    terminal_reason: TerminalReason = "complete"
    discovered: int = 0
    inspected: int = 0
    messages: list[str] = Field(default_factory=list)


class Draft(Contract):
    id: str = Field(default_factory=lambda: uuid4().hex)
    source_id: str
    url: str
    enabled: bool = True
    page_kind: Literal[
        "posting", "listing", "empty_listing", "blocked", "unrelated"
    ] = "listing"
    revision: int = Field(default=0, ge=0)
    base_revision: int = Field(default=0, ge=0)
    corrections: dict[str, dict[FieldName, JsonValue]] = Field(default_factory=dict)
    correction_revisions: dict[str, dict[FieldName, int]] = Field(default_factory=dict)
    plan: BoardPlan | None = None
    limits: CrawlLimits = Field(default_factory=CrawlLimits)
    samples: list[Observation] = Field(default_factory=list)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    navigation: NavigationOutcome | None = None
    state: Literal["draft", "validated", "approved", "unverified"] = "draft"


class ApprovalResult(Contract):
    source_id: str
    approved_revision: int
    job_ids: list[int] = Field(default_factory=list)


class OverridePatch(Contract):
    field: FieldName
    value: JsonValue
    expected_revision: int = Field(ge=0)


class PullReport(Contract):
    repair_draft_id: str | None = None
    terminal_reason: TerminalReason = "complete"
    discovered: int = 0
    inspected: int = 0
    imported: int = 0
    duplicate: int = 0
    filtered: int = 0
    review_needed: int = 0
    failed: int = 0
    observations: list[Observation] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class BrowserAction(Contract):
    kind: Literal[
        "navigate",
        "open_detail",
        "expand_description",
        "next",
        "load_more",
        "scroll",
        "close_detail",
    ]
    selector: str | None = Field(default=None, max_length=500)
    url: str | None = None


class BrowserCapability(Contract):
    available: bool
    reason: str | None = None
