"""One bounded, resumable pass: discover changes → cache evidence → propose updates.

Shared by the manual POST /api/gmail/sync run and the scheduler tick, so
the two can never drift. Never auto-applies a status change.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any
from weakref import WeakValueDictionary

from filelock import FileLock, Timeout
from sqlalchemy import func
from sqlmodel import select

from resume_tailor_harness.config import get_settings
from resume_tailor_harness.db import get_session
from resume_tailor_harness.gmail.auth import build_service
from resume_tailor_harness.gmail.classify import (
    build_classifier_llm,
    classifier_available,
    SyncClassifier,
)
from resume_tailor_harness.gmail.errors import GmailApiError
from resume_tailor_harness.gmail.processing import MessageProcessor
from resume_tailor_harness.gmail.scan import LANES, MailboxScanner
from resume_tailor_harness.llm_runner import Runner
from resume_tailor_harness.tracking.tables import Notification


class _Unset:
    __slots__ = ()


_UNSET = _Unset()
_SYNC_LOCKS: WeakValueDictionary[str, Lock] = WeakValueDictionary()
_LOCK_GUARD = Lock()


@contextmanager
def _sync_lock(engine):
    """Serialize manual/scheduled work, including different server processes."""
    database = engine.url.database or ""
    with _LOCK_GUARD:
        key = str(engine.url)
        lock = _SYNC_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _SYNC_LOCKS[key] = lock
    if not lock.acquire(blocking=False):
        raise GmailApiError("A Gmail sync is already running for this workspace.")
    try:
        if (
            engine.url.get_backend_name() == "sqlite"
            and database
            and engine.url.query.get("mode") != "memory"
        ):
            try:
                with FileLock(
                    str(Path(database).resolve()) + ".gmail-sync.lock", timeout=0
                ):
                    yield
            except Timeout as exc:
                raise GmailApiError(
                    "A Gmail sync is already running for this workspace."
                ) from exc
        else:
            yield
    finally:
        lock.release()


def run_gmail_sync(
    engine: Any,
    reporter: Any,
    *,
    service: Any | None = None,
    llm: Runner | None | _Unset = _UNSET,
    data_dir: Path | None = None,
    review_cleared: bool = False,
) -> dict:
    reporter.checkpoint()
    reporter.begin(1, "Scanning Gmail")
    if service is None:
        service = build_service(data_dir)
    with _sync_lock(engine):
        return _run_sync(engine, reporter, service, llm, review_cleared=review_cleared)


def _run_sync(engine, reporter, service, llm, *, review_cleared: bool = False) -> dict:
    warnings: list[str] = []

    def warn(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    settings = get_settings()
    page_size = min(settings.gmail_max_messages, 500)
    ai_available = llm is not None and not isinstance(llm, _Unset)
    if isinstance(llm, _Unset) and settings.gmail_max_ai_calls > 0:
        try:
            ai_available = classifier_available()
        except Exception:  # noqa: BLE001 — optional AI configuration cannot block rules
            warn("AI classification is unavailable. Synced using email rules only.")
            # Keep the enabled fingerprint. If uncertain mail reaches the lazy
            # factory, its existing failure handler leaves it retryable.
            ai_available = True
    classifier = SyncClassifier(
        None if isinstance(llm, _Unset) else llm,
        build_classifier_llm if isinstance(llm, _Unset) else None,
        settings.gmail_max_ai_calls,
        warn,
        ai_available=ai_available,
    )
    reporter.begin(settings.gmail_sync_max_pages, "Syncing Gmail")
    with get_session(engine) as session:
        scanner = MailboxScanner(service, session, warn)
        processor = MessageProcessor(
            service, session, scanner.account, classifier, reporter.checkpoint
        )
        # Snapshot stale work once: deferred AI/errors must not spin within this
        # run. Oldest attempts first keep one failing message from starving others.
        stale = processor.stale_ids(page_size)
        for page in range(settings.gmail_sync_max_pages):
            reporter.checkpoint()
            if page == 0 and stale:
                processor.process(stale, recruiting=False)
                session.commit()
            else:
                active = [lane for lane in LANES if scanner.has_work(lane)]
                if not active:
                    break
                lane = active[page % len(active)]
                ids = scanner.take(lane, page_size)
                processor.process(
                    ids, recruiting=lane != "inbox", refresh=lane == "history"
                )
                scanner.complete(lane, len(ids))
                session.commit()
            reporter.step(
                page + 1,
                label=f"Processed {processor.stats['processed']} emails; reused {processor.stats['cached']} cached results",
            )
        if review_cleared:
            reporter.checkpoint()
            processor.restore_cleared_proposals()
            session.commit()
        has_more = any(scanner.has_work(lane) for lane in LANES) or bool(
            processor.stale_ids(1)
        )
        pending = session.exec(
            select(func.count())
            .select_from(Notification)
            .where(Notification.state == "pending")
        ).one()
        stats = {**processor.stats, "ai_calls": classifier.calls}
    if has_more:
        warn(
            "More emails remain. Progress is saved; the next sync continues where this one stopped."
        )
    for warning in warnings:
        reporter.step(1, label=warning)
    reporter.step(1, label="Done with warnings" if warnings else "Done")
    return {
        "pending": pending,
        "has_more": has_more,
        "stats": stats,
        **({"warnings": warnings} if warnings else {}),
    }
