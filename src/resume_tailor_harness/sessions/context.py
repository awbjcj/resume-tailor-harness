"""Deterministic, explicitly lossy projections; durable sources stay untouched.

Budgets are application character/byte guards, not provider token estimates.
Never prefix-slice a serialized object or a complete assembled prompt.
"""

from __future__ import annotations

import json


class ContextBudgetExceeded(ValueError):
    code = "CONTEXT_BUDGET_EXCEEDED"


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def excerpt(text: str, limit: int, *, tail: bool = False) -> str:
    if len(text) <= limit:
        return text
    marker = "[… elided …]"
    if limit < len(marker):
        return ""  # caller supplies the section's omission metadata
    size = limit - len(marker)
    return marker + text[-size:] if tail and size else text[:size] + marker


def bounded_json(value: object, limit: int) -> str:
    """Allocate recursively: each key/list item survives or fails explicitly.

    Small fields retain their type and value. Oversized leaves become labelled
    excerpts, not apparently complete values. No selected source silently vanishes.
    """

    def fit(item: object, budget: int, depth: int = 0) -> object:
        raw = encode(item)
        if len(raw) <= budget:
            return item
        if isinstance(item, (dict, list)) and item:
            keys = list(item) if isinstance(item, dict) else list(range(len(item)))
            blank = (
                dict.fromkeys(keys) if isinstance(item, dict) else [None] * len(keys)
            )
            overhead = len(encode(blank)) - 4 * len(keys)
            available = budget - overhead
            values = {}
            # Small fields consume only their actual size; large siblings share
            # what remains. Stable output order still follows the source.
            ordered = sorted(keys, key=lambda k: len(encode(item[k])))
            try:
                for n, key in enumerate(ordered):
                    allowance = available // (len(keys) - n)
                    values[key] = fit(item[key], allowance, depth + 1)
                    available -= len(encode(values[key]))
                result = (
                    {k: values[k] for k in keys}
                    if isinstance(item, dict)
                    else [values[k] for k in keys]
                )
                if len(encode(result)) <= budget:
                    return result
            except ContextBudgetExceeded:
                if depth == 0:
                    raise
                # A large nested collection is one explicitly omitted source,
                # not a reason to silently discard its selected siblings.
        result = {
            "omitted": True,
            "reason": "context budget",
            "original_chars": len(raw),
        }
        if len(encode(result)) > budget:
            raise ContextBudgetExceeded(
                "Too many context sources to represent safely; select fewer sources."
            )
        # JSON escaping means the excerpt's length is not its encoded length.
        text = item if isinstance(item, str) else raw
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if len(encode({**result, "excerpt": text[:mid]})) <= budget:
                low = mid
            else:
                high = mid - 1
        if low:
            result["excerpt"] = text[:low]
        return result

    return encode(fit(value, limit))


def recent_transcript(
    prefix: str, summaries: list[str], turns: list[str], limit: int
) -> str:
    """Reserve marker space and recent exchanges before completed summaries."""
    if limit <= len(prefix):
        return prefix[: max(0, limit)]
    summary_budget = min(len("\n".join(summaries)), (limit - len(prefix)) // 3)
    summary = excerpt("\n".join(summaries), summary_budget)
    head = prefix + (summary + "\n" if summary else "")
    budget = limit - len(head)
    body = "\n".join(turns)
    return head + excerpt(body, budget, tail=True)


def bounded_sections(
    sections: list[str], *, limit: int = 48_000, required: tuple[int, ...] = ()
) -> str:
    """Bound a complete application prompt, retaining required sections intact."""
    if len("\n\n".join(sections)) <= limit:
        return "\n\n".join(sections)
    available = (
        limit - 2 * (len(sections) - 1) - sum(len(sections[i]) for i in required)
    )
    optional = [i for i in range(len(sections)) if i not in required]
    if available < len(optional) * 64:
        raise ContextBudgetExceeded(
            "The current request and required evidence exceed the context budget; shorten the request."
        )
    result = sections.copy()
    for n, i in enumerate(sorted(optional, key=lambda i: len(sections[i]))):
        allowance = available // (len(optional) - n)
        result[i] = excerpt(sections[i], allowance)
        available -= len(result[i])
    return "\n\n".join(result)
