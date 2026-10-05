"""One complete, untrusted conversation snapshot for routing and drafting."""

from __future__ import annotations

import json

from resume_tailor_harness.career_lab.models import CareerLabContextRefs

# Application payload guard, NOT a claim about any provider's token window.
# Fail explicitly instead of truncating messages; providers still enforce their
# own context limits, including system instructions, skill text and output.
MAX_CONVERSATION_BYTES = 256_000


class ConversationContextTooLarge(ValueError):
    code = "CONVERSATION_CONTEXT_TOO_LARGE"

    def __init__(self) -> None:
        super().__init__(
            "This conversation is too long to send in full. Start a new session "
            "with the details you want to carry forward. Your existing conversation "
            "has not been changed."
        )


def conversation_context(
    session: dict,
    *,
    message: str,
    goal: str,
    refs: CareerLabContextRefs,
    context: str,
) -> str:
    """Preserve every visible turn and its references, regardless of skill.

    Only the already-loaded session is read. Do not look up other sessions or
    promote past text to instructions. JSON keeps role/metadata boundaries
    unambiguous even when the user's text contains newlines or role labels.
    """
    turns = [
        {
            key: turn[key]
            for key in (
                "turn_id",
                "role",
                "text",
                "context_refs",
                "skill_ref",
                "artifact",
                "notice",
            )
            if turn.get(key) is not None
        }
        for turn in session["turns"]
    ]
    payload = {
        "session_id": session["session_id"],
        "goal": goal,
        "history": turns,
        "current_turn": {
            "role": "user",
            "text": message,
            "context_refs": refs.model_dump(mode="json"),
        },
        # Typed source material has its own bounded projection. It is not a
        # replacement for any part of the conversation history.
        "current_context": context,
    }
    rendered = json.dumps(payload, ensure_ascii=False)
    if len(rendered.encode("utf-8")) > MAX_CONVERSATION_BYTES:
        raise ConversationContextTooLarge()
    return "CONVERSATION (UNTRUSTED DATA):\n" + rendered
