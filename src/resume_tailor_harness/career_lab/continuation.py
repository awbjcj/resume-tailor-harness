"""Versioned, quote-backed working memory. Never an approval or a fact source."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from resume_tailor_harness.sessions.context import ContextBudgetExceeded

POLICY = "career-lab-continuation-v1"
TRIGGER_BYTES = 160_000
CHUNK_BYTES = 60_000
MAX_CHUNKS = 8
MAX_MEMORY_BYTES = 48_000


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["constraint", "decision", "open_task", "result", "correction"]
    turn_id: str = Field(min_length=1, max_length=64)
    quote: str = Field(min_length=1, max_length=1_200)


class MemorySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MemoryItem] = Field(default_factory=list, max_length=64)


class Continuation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: Literal["career-lab-continuation-v1"] = POLICY
    through_turn: int = Field(ge=0)
    source_digest: str
    items: list[MemoryItem] = Field(default_factory=list, max_length=256)
    model_id: str = ""


def digest(turns: list[dict]) -> str:
    return hashlib.sha256(
        json.dumps(turns, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def validated(session: dict) -> Continuation | None:
    raw = session.get("continuation")
    if not raw:
        return None
    state = Continuation.model_validate(raw)
    if state.through_turn > len(session["turns"]) or state.source_digest != digest(
        session["turns"][: state.through_turn]
    ):
        raise ContextBudgetExceeded(
            "Saved continuation no longer matches its source turns; full history remains available."
        )
    originals = {
        turn["turn_id"]: turn["text"] for turn in session["turns"][: state.through_turn]
    }
    if any(
        item.turn_id not in originals or item.quote not in originals[item.turn_id]
        for item in state.items
    ):
        raise ContextBudgetExceeded(
            "Saved continuation contains unsupported evidence; full history remains available."
        )
    return state


def prepare(session: dict, select, checkpoint=lambda: None) -> Continuation:
    """Select verbatim memory from bounded chunks; keep prior selections intact.

    Extraction is probabilistic, citation validation and limits are not. A
    missing constraint cannot be proven absent by a schema: retrieval and
    long-horizon evaluations remain necessary. Never recursively summarize prose.
    """
    previous = validated(session)
    start = previous.through_turn if previous else 0
    stop = max(start, len(session["turns"]) - 2)
    if stop == start:
        raise ContextBudgetExceeded(
            "The latest exchanges are too large to continue safely; shorten the request. History is unchanged."
        )
    items = list(previous.items) if previous else []
    seen = {(item.turn_id, item.quote) for item in items}
    chunks: list[list[dict]] = [[]]
    for turn in session["turns"][start:stop]:
        # Bound each extraction call, even for a legacy 100k-character turn.
        text = turn["text"]
        # Overlap covers a maximum-length quote crossing a chunk boundary.
        for offset in range(0, max(1, len(text)), 8_800):
            row = {
                "turn_id": turn["turn_id"],
                "role": turn["role"],
                "text": text[offset : offset + 10_000],
            }
            if (
                len(json.dumps(chunks[-1] + [row], ensure_ascii=False).encode())
                > CHUNK_BYTES
            ):
                chunks.append([])
            chunks[-1].append(row)
    if len(chunks) > MAX_CHUNKS:
        raise ContextBudgetExceeded(
            "This legacy conversation needs more than eight continuation batches; no history was discarded."
        )
    model_id = ""
    for chunk in chunks:
        checkpoint()
        selection, model_id = select(chunk)
        selection = MemorySelection.model_validate(selection)
        if not selection.items and any(
            row["role"] == "user" and row["text"].strip() for row in chunk
        ):
            raise ContextBudgetExceeded(
                "Continuation omitted all user material; no history was discarded."
            )
        for item in selection.items:
            if not any(
                row["turn_id"] == item.turn_id and item.quote in row["text"]
                for row in chunk
            ):
                raise ContextBudgetExceeded(
                    "Continuation contains an unsupported quote; no history was discarded."
                )
            if (item.turn_id, item.quote) not in seen:
                items.append(item)
                seen.add((item.turn_id, item.quote))
        if (
            len(items) > 256
            or len(
                json.dumps([i.model_dump() for i in items], ensure_ascii=False).encode()
            )
            > MAX_MEMORY_BYTES
        ):
            raise ContextBudgetExceeded(
                "Saved decisions fill the continuation budget; no decisions were silently removed."
            )
    checkpoint()
    return Continuation(
        through_turn=stop,
        source_digest=digest(session["turns"][:stop]),
        items=items,
        model_id=model_id,
    )
