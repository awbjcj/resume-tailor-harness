"""One sync pass: fetch inbox → propose status changes.

Shared by the manual POST /api/gmail/sync run and the scheduler tick, so
the two can never drift. Never auto-applies a status change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resume_tailor_harness.config import get_settings
from resume_tailor_harness.db import get_session
from resume_tailor_harness.gmail.auth import build_service
from resume_tailor_harness.gmail.classify import (
    build_classifier_llm,
    hydrating_classifier,
)
from resume_tailor_harness.gmail.client import fetch_recent_messages
from resume_tailor_harness.llm_runner import Runner
from resume_tailor_harness.services.notifications import sync_notifications


class _Unset:
    __slots__ = ()


_UNSET = _Unset()


def run_gmail_sync(
    engine: Any,
    reporter: Any,
    *,
    service: Any | None = None,
    llm: Runner | None | _Unset = _UNSET,
    data_dir: Path | None = None,
) -> dict:
    reporter.begin(2, "Scanning Gmail")
    if service is None:
        service = build_service(data_dir)
    warnings: list[str] = []

    def warn(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    def fetch_progress(current: int, total: int) -> None:
        reporter.checkpoint()
        reporter.step(current, label="Scanning Gmail", total=total)

    reporter.begin(get_settings().gmail_max_messages, "Scanning Gmail")
    emails = fetch_recent_messages(
        service,
        max_results=get_settings().gmail_max_messages,
        on_progress=fetch_progress,
    )
    classify_message = hydrating_classifier(
        service,
        None if isinstance(llm, _Unset) else llm,
        llm_factory=build_classifier_llm if isinstance(llm, _Unset) else None,
        on_warning=warn,
    )

    def classify(email):
        reporter.checkpoint()
        return classify_message(email)

    reporter.begin(1, "Classifying")
    with get_session(engine) as session:
        pending = sync_notifications(session, emails, classify=classify)
    for warning in warnings:
        reporter.step(1, label=warning)
    reporter.step(1, label="Done with warnings" if warnings else "Done")
    return {"pending": len(pending), **({"warnings": warnings} if warnings else {})}
