"""Additive fact-ranking metadata; none of these fields establish a claim."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


FactContext = Literal[
    "professional",
    "personal_project",
    "academic_project",
    "research",
    "education",
    "volunteer",
    "unknown",
]


class FactImportanceSignals(BaseModel):
    """Source-grounded ordinal assessments, each on a closed 0..4 scale."""

    model_config = ConfigDict(extra="forbid")

    context: FactContext = "unknown"
    significance: int = Field(default=2, ge=0, le=4)
    essentiality: int = Field(default=2, ge=0, le=4)
    impact: int = Field(default=0, ge=0, le=4)
    ownership: int = Field(default=0, ge=0, le=4)


class FactImportanceScore(BaseModel):
    """Application-computed score and weighted contributions, never model authority."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    score: float = Field(ge=0, le=100)
    context: FactContext = "unknown"
    method: Literal["assessed", "fallback"] = "fallback"
    components: dict[str, float] = Field(default_factory=dict)
