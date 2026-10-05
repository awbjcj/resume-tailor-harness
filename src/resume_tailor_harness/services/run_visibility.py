"""Presentation policy; quiet chat runs still complete and persist normally."""

from sqlalchemy import or_
from sqlmodel import col

from resume_tailor_harness.tracking.tables import RunCompletion

# Keep the browser policy in sync (checked by test_run_visibility_contract).
CHAT_RUN_KINDS = frozenset(
    {
        "career-lab-turn",
        "career-lab-end",
        "profile-coach-open",
        "profile-coach-turn",
        "profile-coach-end",
        "mock-interview-open",
        "mock-interview-turn",
        "mock-interview-end",
        "scout-start",
        "scout-turn",
        "scout-end",
    }
)


def visible_run_completion(kind: str, status: str) -> bool:
    return kind not in CHAT_RUN_KINDS or status == "failed"


def visible_run_completions_clause():
    """Filter before ordering/limits so quiet runs cannot bury failures."""
    return or_(
        col(RunCompletion.kind).not_in(CHAT_RUN_KINDS),
        RunCompletion.status == "failed",
    )
