"""Conservative recovery of complete JSON, followed by the original schema.

Only presentation and trailing commas are normalized. Missing values, closing
brackets, duplicate keys and concatenated documents are never guessed/merged.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError


class StructuredOutputError(ValueError):
    """Bounded diagnostic without echoing model output or validation inputs."""


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StructuredOutputError("JSON contains duplicate object keys")
        result[key] = value
    return result


def _nonfinite(_value: str) -> Any:
    raise StructuredOutputError("JSON contains a non-finite number")


def _without_trailing_commas(text: str) -> str:
    # Operate outside quoted strings only: code, punctuation and escaped quotes
    # inside evidence must remain byte-for-byte intact.
    pieces: list[str] = []
    quoted = escaped = False
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == ",":
            following = index + 1
            while following < len(text) and text[following].isspace():
                following += 1
            if following < len(text) and text[following] in "}]":
                continue
        pieces.append(char)
    return "".join(pieces)


def parse_structured_content(content: Any, schema: type[BaseModel]) -> BaseModel:
    if isinstance(content, schema):
        return content
    if isinstance(content, str):
        text = content.strip().lstrip("\ufeff").strip()
        if text.startswith("<think>") and "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        fenced = re.fullmatch(
            r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text, re.IGNORECASE
        )
        if fenced is not None:
            text = fenced.group(1).strip()
        if not text:
            raise StructuredOutputError("response is empty")
        if text[0] not in "{[":
            raise StructuredOutputError(
                "response does not start with a JSON object or array"
            )
        text = _without_trailing_commas(text)
        try:
            # json.loads rejects extra documents; the hooks reject values that
            # the standard decoder would silently overwrite or accept as NaN.
            json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_nonfinite)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(
                f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        try:
            return schema.model_validate_json(text)
        except ValidationError as exc:
            raise _validation_error(exc) from exc
    try:
        return schema.model_validate(content)
    except ValidationError as exc:
        raise _validation_error(exc) from exc


def _validation_error(exc: ValidationError) -> StructuredOutputError:
    details = []
    for error in exc.errors(
        include_input=False, include_context=False, include_url=False
    )[:5]:
        # Keep field paths bounded and never include the rejected value.
        location = ".".join(str(part) for part in error["loc"])[:100] or "root"
        details.append(f"{location}: {error['type']}")
    return StructuredOutputError("schema validation failed: " + "; ".join(details))


def retry_prompt(prompt: str, schema_name: str, reason: str) -> str:
    return (
        f"{prompt}\n\n"
        f"OUTPUT CORRECTION: The previous attempt did not produce valid {schema_name} JSON. "
        f"Validation: {reason[:700]}. "
        "Return exactly one complete JSON document matching the required schema. "
        "Include every required field. Use proper JSON types and escaping. "
        "Do not add markdown fences, explanations, duplicate documents or tool markup. "
        "Keep the response concise enough to finish; preserve the supplied evidence and do not invent missing facts."
    )
