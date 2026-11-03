"""Portable contracts for preparation, evidence inspection, and run recovery."""

from typing import Literal

from pydantic import TypeAdapter
from typing_extensions import NotRequired, TypedDict

RedoStage = Literal["pull", "extract", "tailor", "render"]


class RunCompletion(TypedDict):
    id: int
    runId: str
    kind: str
    label: str
    status: Literal["succeeded", "failed", "cancelled"]
    completedAt: str
    error: NotRequired[str | None]
    readAt: NotRequired[str | None]
    resultHref: NotRequired[str | None]
    resultAvailable: NotRequired[bool]


class OperationLog(TypedDict):
    message: str
    timestamp: NotRequired[str]
    state: NotRequired[str]


class ProfileStatus(TypedDict):
    documentCount: int
    hasResume: bool
    canRebuild: NotRequired[bool]
    factsBuiltAt: NotRequired[str | None]
    freshness: NotRequired[Literal["missing", "current", "refresh-needed", "unknown"]]
    publishedAt: NotRequired[str | None]
    pendingSourceCount: NotRequired[int]
    githubUsername: NotRequired[str | None]


class SecretsStatus(TypedDict):
    anthropicKey: bool
    anyLlmKey: bool


class SearchStatus(TypedDict):
    configured: bool


class SourcesStatus(TypedDict):
    enabledCount: int


class CareerSkillsCapability(TypedDict):
    available: int
    unavailable: int


class H1BCapability(TypedDict):
    capability: Literal["disabled", "available", "unavailable"]


class SetupCapabilities(TypedDict):
    careerSkills: CareerSkillsCapability
    h1b: NotRequired[H1BCapability | None]


class SetupStatus(TypedDict):
    secrets: SecretsStatus
    profile: ProfileStatus
    search: SearchStatus
    sources: SourcesStatus
    capabilities: NotRequired[SetupCapabilities | None]
    complete: bool


class JobTextInput(TypedDict):
    jdText: str
    url: NotRequired[str | None]
    company: NotRequired[str | None]
    title: NotRequired[str | None]
    location: NotRequired[str | None]
    postedAt: NotRequired[str | None]
    details: NotRequired[dict]


class PortfolioRequirement(TypedDict):
    text: str
    kind: Literal["skill", "responsibility", "seniority"]
    priority: int
    coverage: Literal["covered", "adjacent", "gap"]
    supportingFactIds: list[str]
    approvedTerms: list[str]
    core: bool
    rationale: str


class PortfolioSelection(TypedDict):
    ownerId: str
    ownerKind: Literal["experience", "project"]
    selectedFactIds: list[str]
    requirementTexts: list[str]
    rank: int
    bulletBudget: int
    bridge: bool
    rationale: str


class PortfolioOmission(TypedDict):
    ownerId: str
    ownerKind: Literal["experience", "project"]
    rationale: str


class EvidenceExcerpt(TypedDict):
    factId: str
    ownerId: str
    ownerKind: Literal["experience", "project"]
    text: str


class EvidencePortfolio(TypedDict):
    status: Literal["planned", "deterministic_fallback", "inherited"]
    warning: NotRequired[str | None]
    requirements: list[PortfolioRequirement]
    selections: list[PortfolioSelection]
    selectedSkillFactIds: list[str]
    highlightTerms: list[str]
    sectionOrder: list[str]
    omissions: list[PortfolioOmission]
    evidenceExcerpts: list[EvidenceExcerpt]
    realizedOutsideFactIds: list[str]


COMPLETION = TypeAdapter(RunCompletion)
COMPLETIONS = TypeAdapter(list[RunCompletion])
LOGS = TypeAdapter(list[OperationLog])
SETUP = TypeAdapter(SetupStatus)
PORTFOLIO = TypeAdapter(EvidencePortfolio)
