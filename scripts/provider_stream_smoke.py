"""Opt-in paid provider smoke test; sends synthetic prompts, never profile data.

Uses the configured SpendGate route. It never replaces a gateway route with a
direct key. Output contains event counts and timing, not credentials or prose.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import time
from urllib.parse import urlsplit

from agno.agent import Agent

from resume_tailor_harness.config import get_settings
from resume_tailor_harness.llm_runner import (
    AgentRunner,
    build_search_equipped,
    resolve_route,
)
from resume_tailor_harness.sessions.stream import Failed, ToolCompleted

MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "openai:gpt-5.6-terra",
    "gemini": "gemini:gemini-3.8-flash",
    "deepseek": "deepseek:deepseek-v4-pro",
}


def probe(provider: str, timeout: float) -> dict:
    started = time.monotonic()
    settings = get_settings().model_copy(update={"llm_retries": 0})
    route = resolve_route(MODELS[provider], settings=settings)
    result: dict = {
        "provider": provider,
        "model": MODELS[provider],
        "host": urlsplit(route.base_url or "").hostname or "provider default",
    }
    if not route.api_key:
        return {**result, "status": "unconfigured"}

    def stream_probe(provider_name: str) -> str:
        """Confirm the requested provider name, without any external side effects."""
        return f"Confirmed {provider_name}."

    def checkpoint():
        if time.monotonic() - started > timeout:
            raise TimeoutError("Provider smoke test timed out")

    counts: Counter = Counter()
    completed_tools: set[str] = set()
    try:
        model, native = build_search_equipped(
            MODELS[provider], mode="native", reasoning=True, settings=settings
        )
        runner = AgentRunner(
            Agent(
                model=model, tools=[*native, stream_probe], retries=0, telemetry=False
            ),
            settings=settings,
        )
        first_event = None
        for event in runner.stream(
            f"Search the web for the official {provider} Python SDK repository. Then call stream_probe with provider_name='{provider}'. Reply with one short sentence and the repository link.",
            checkpoint=checkpoint,
        ):
            counts[event.tag] += 1
            if first_event is None:
                first_event = round(time.monotonic() - started, 2)
            if isinstance(event, Failed):
                result["errorCode"] = event.code
            if isinstance(event, ToolCompleted) and event.ok:
                completed_tools.add(event.name)
        result.update(
            status="passed"
            if counts["completed"]
            and {"web_search", "stream_probe"} <= completed_tools
            and counts["text"]
            else "failed",
            firstEventSeconds=first_event,
            events=dict(counts),
            completedTools=sorted(completed_tools),
        )
    except Exception as exc:
        result.update(status="failed", errorCode=type(exc).__name__)
    result["elapsedSeconds"] = round(time.monotonic() - started, 2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--providers", nargs="+", choices=list(MODELS), default=list(MODELS)
    )
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=len(args.providers)) as pool:
        results = list(
            pool.map(lambda provider: probe(provider, args.timeout), args.providers)
        )
    print(json.dumps(results, indent=2))
    raise SystemExit(
        0 if all(result["status"] == "passed" for result in results) else 1
    )
