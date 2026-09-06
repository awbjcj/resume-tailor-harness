from typing import Any, Literal

from pydantic import Field

from resume_tailor_harness.models.base import ExtensibleModel


CoverageState = Literal["covered", "adjacent", "gap"]
OwnerKind = Literal["experience", "project"]
PortfolioStatus = Literal["planned", "deterministic_fallback", "inherited"]
RequirementKind = Literal["skill", "responsibility", "seniority"]


class EvidenceFactCandidate(ExtensibleModel):
    fact_id: str
    text: str
    source_order: int = 0
    metric_count: int = 0
    direct_must_requirements: list[str] = Field(default_factory=list)
    direct_requirements: list[str] = Field(default_factory=list)
    adjacent_requirements: list[str] = Field(default_factory=list)


class EvidenceOwnerCandidate(ExtensibleModel):
    owner_id: str
    owner_kind: OwnerKind
    label: str
    start: str | None = None
    end: str | None = None
    current: bool = False
    source_order: int = 0
    strength: float = 0.0
    suggested_bullet_count: int = 1
    direct_must_requirements: list[str] = Field(default_factory=list)
    direct_requirements: list[str] = Field(default_factory=list)
    adjacent_requirements: list[str] = Field(default_factory=list)
    facts: list[EvidenceFactCandidate] = Field(default_factory=list)


class EvidenceCatalog(ExtensibleModel):
    owners: list[EvidenceOwnerCandidate] = Field(default_factory=list)


class PortfolioRequirement(ExtensibleModel):
    text: str
    kind: RequirementKind = "skill"
    priority: int = Field(default=100, ge=1)
    coverage: CoverageState = "gap"
    supporting_fact_ids: list[str] = Field(default_factory=list)
    approved_terms: list[str] = Field(default_factory=list)
    core: bool = False
    rationale: str = ""


class PortfolioSelection(ExtensibleModel):
    owner_id: str
    owner_kind: OwnerKind
    selected_fact_ids: list[str] = Field(default_factory=list)
    requirement_texts: list[str] = Field(default_factory=list)
    rank: int = Field(default=100, ge=1)
    bullet_budget: int = Field(default=1, ge=0)
    bridge: bool = False
    rationale: str = ""

    def __init__(
        self,
        *,
        owner_id: str,
        owner_kind: OwnerKind,
        selected_fact_ids: list[str] | None = None,
        requirement_texts: list[str] | None = None,
        rank: int = 100,
        bullet_budget: int = 1,
        bridge: bool = False,
        rationale: str = "",
        schema_version: int = 1,
        **extra_data: Any,
    ) -> None:
        """Expose Pydantic's generated keyword interface to static analyzers."""
        values: dict[str, Any] = {
            "owner_id": owner_id,
            "owner_kind": owner_kind,
            "rank": rank,
            "bullet_budget": bullet_budget,
            "bridge": bridge,
            "rationale": rationale,
            "schema_version": schema_version,
        }
        if selected_fact_ids is not None:
            values["selected_fact_ids"] = selected_fact_ids
        if requirement_texts is not None:
            values["requirement_texts"] = requirement_texts
        super().__init__(**values, **extra_data)


class PortfolioOmission(ExtensibleModel):
    owner_id: str
    owner_kind: OwnerKind
    rationale: str


class EvidenceExcerpt(ExtensibleModel):
    fact_id: str
    owner_id: str
    owner_kind: OwnerKind
    text: str


class EvidencePortfolio(ExtensibleModel):
    """Frozen, validated strategy for one tailoring attempt.

    The portfolio is strategy data, never a source of candidate truth. Every
    written claim still has to cite and pass checks against ``ProfileFacts``.
    """

    status: PortfolioStatus = "planned"
    warning: str | None = None
    requirements: list[PortfolioRequirement] = Field(default_factory=list)
    selections: list[PortfolioSelection] = Field(default_factory=list)
    selected_skill_fact_ids: list[str] = Field(default_factory=list)
    highlight_terms: list[str] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)
    omissions: list[PortfolioOmission] = Field(default_factory=list)
    evidence_excerpts: list[EvidenceExcerpt] = Field(default_factory=list)

    def __init__(
        self,
        *,
        status: PortfolioStatus = "planned",
        warning: str | None = None,
        requirements: list[PortfolioRequirement] | None = None,
        selections: list[PortfolioSelection] | None = None,
        selected_skill_fact_ids: list[str] | None = None,
        highlight_terms: list[str] | None = None,
        section_order: list[str] | None = None,
        omissions: list[PortfolioOmission] | None = None,
        evidence_excerpts: list[EvidenceExcerpt] | None = None,
        schema_version: int = 1,
        **extra_data: Any,
    ) -> None:
        """Expose Pydantic's generated keyword interface to static analyzers."""
        values: dict[str, Any] = {
            "status": status,
            "warning": warning,
            "schema_version": schema_version,
        }
        for name, value in (
            ("requirements", requirements),
            ("selections", selections),
            ("selected_skill_fact_ids", selected_skill_fact_ids),
            ("highlight_terms", highlight_terms),
            ("section_order", section_order),
            ("omissions", omissions),
            ("evidence_excerpts", evidence_excerpts),
        ):
            if value is not None:
                values[name] = value
        super().__init__(**values, **extra_data)
