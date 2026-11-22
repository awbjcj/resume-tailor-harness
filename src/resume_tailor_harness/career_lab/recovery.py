"""Explicit retry of completed, read/draft-only stages in an existing session.

No arbitrary callable replay. The session owns the operation and its final
commit receipt atomically; persisted input never bypasses current validation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Literal
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from resume_tailor_harness.sessions.context import ContextBudgetExceeded

POLICY = "career-lab-draft-recovery-v1"
MAX_ATTEMPTS = 3
MAX_AGE_SECONDS = 3_600


class DraftRecovery(BaseModel):
    operation_id: str
    policy: str = POLICY
    base_turn_count: int
    fingerprint: str
    request: dict
    created_at: str
    attempts: int = Field(default=0, ge=0, le=MAX_ATTEMPTS)
    selected_skill: str = ""
    stage: Literal["prepared", "drafted", "committed"] = "prepared"
    prose: str = Field(default="", max_length=100_000)
    notes: str = Field(default="", max_length=100_000)
    agent_meta: dict = Field(default_factory=dict)
    has_workspace_previews: bool | None = None
    continuation: dict | None = None


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def begin(root, session: dict, request: dict, source_version: str) -> DraftRecovery:
    from resume_tailor_harness.career_lab.store import store

    selected = None

    def apply(current):
        nonlocal selected
        if current["status"] != "active" or len(current["turns"]) != len(
            session["turns"]
        ):
            raise ValueError(
                "The conversation changed during this reply. Please try again."
            )
        old = current.get("recovery")
        if old and old["stage"] != "committed" and old["request"] == request:
            selected = DraftRecovery.model_validate(old)
            if selected.policy != POLICY or selected.fingerprint != source_version:
                raise ContextBudgetExceeded(
                    "Recovery inputs or policy changed. Send a new request to prepare a fresh draft."
                )
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(selected.created_at)
            ).total_seconds()
            if age > MAX_AGE_SECONDS or selected.attempts >= MAX_ATTEMPTS:
                raise ContextBudgetExceeded(
                    "Recovery budget exhausted (three attempts or one hour). Send a new request; saved work remains available."
                )
        else:
            selected = DraftRecovery(
                operation_id=uuid.uuid4().hex,
                base_turn_count=len(current["turns"]),
                fingerprint=source_version,
                request=request,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        selected.attempts += 1
        current["recovery"] = selected.model_dump(mode="json")

    store.mutate(root, session["session_id"], apply)
    assert selected is not None
    return selected


def save_draft(root, session_id: str, receipt: DraftRecovery) -> None:
    from resume_tailor_harness.career_lab.store import store

    def apply(current):
        saved = current.get("recovery") or {}
        if (
            current["status"] != "active"
            or len(current["turns"]) != receipt.base_turn_count
            or saved.get("operation_id") != receipt.operation_id
            or saved.get("attempts") != receipt.attempts
        ):
            raise ValueError(
                "The conversation changed during this reply. Please try again."
            )
        current["recovery"] = receipt.model_dump(mode="json")

    store.mutate(root, session_id, apply)
