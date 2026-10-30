from collections.abc import Iterable, Mapping, Sequence
from enum import Enum

from pydantic import Field

from resume_tailor_harness.models.base import ExtensibleModel

FACT_CHECK_REVIEWER = "fact-check"


def has_failed_fact_check(
    critiques: Sequence[Mapping[str, object]] | None,
    gate_names: Iterable[str] | None = None,
) -> bool:
    """Reject a contradictory passing flag only when fact-check was a gate.

    Unknown legacy rosters fall back to the shipped fact-check gate.
    """
    if gate_names is not None and FACT_CHECK_REVIEWER not in gate_names:
        return False
    return any(
        critique.get("reviewer") == FACT_CHECK_REVIEWER
        and critique.get("passed") is not True
        for critique in critiques or ()
    )


class Severity(str, Enum):
    blocking = "blocking"  # blocks the round when this reviewer is a gate
    major = "major"
    minor = "minor"


class ReviewIssue(ExtensibleModel):
    severity: Severity
    message: str
    suggestion: str | None = None
    location: str | None = None  # which section/bullet the issue refers to


class ReviewCritique(ExtensibleModel):
    """One reviewer agent's structured verdict on a ResumeContent draft."""

    reviewer: str  # the reviewing agent's name
    score: int = Field(ge=0, le=100)
    passed: bool  # blocks the round when this reviewer is a gate
    issues: list[ReviewIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    summary: str | None = None


class MergedPanelReview(ExtensibleModel):
    """One combined advisory call's critique for every configured dimension."""

    critiques: list[ReviewCritique] = Field(default_factory=list)
