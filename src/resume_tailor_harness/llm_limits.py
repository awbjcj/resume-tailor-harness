"""Process-wide admission for every provider invocation, across users and runs.

Use one gate rather than per-agent semaphores: separate keys can fund the same
gateway account. Sync threads and async loops share the same FIFO and slots.
Streaming owns its slot until the underlying iterator is closed.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from resume_tailor_harness.config import Settings, env_settings


class LLMQueueTimeout(TimeoutError):
    """The shared provider queue did not admit this call in time."""


def retry_after_seconds(error: Any) -> float | None:
    """Read Retry-After from SDK wrappers, including Agno's exception cause."""
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        response = getattr(error, "response", None) or error
        headers = getattr(response, "headers", None)
        raw = headers.get("retry-after") if headers is not None else None
        if raw is not None:
            try:
                delay = float(raw)
            except (ValueError, TypeError):
                try:
                    date = parsedate_to_datetime(str(raw))
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                    delay = (date - datetime.now(timezone.utc)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    delay = -1
            if math.isfinite(delay) and delay >= 0:
                return delay
        error = getattr(error, "__cause__", None) or getattr(error, "__context__", None)
    return None


def _rate_limited(error: Any) -> bool:
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        response = getattr(error, "response", None)
        if (
            getattr(error, "status_code", None) == 429
            or getattr(response, "status_code", None) == 429
        ):
            return True
        error = getattr(error, "__cause__", None) or getattr(error, "__context__", None)
    return False


@dataclass(eq=False)
class _Waiter:
    loop: asyncio.AbstractEventLoop | None = None
    event: asyncio.Event | None = None


class CallLimiter:
    """One queue, safe across threads and event loops without executor waiters."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._waiters: deque[_Waiter] = deque()
        self._starts: deque[float] = deque()
        self._active = 0
        self._cooldown_until = 0.0

    def _notify(self) -> None:
        self._condition.notify_all()
        # Wake only the head: later callers cannot overtake it anyway.
        while self._waiters:
            head = self._waiters[0]
            if head.loop is not None and head.event is not None:
                try:
                    head.loop.call_soon_threadsafe(head.event.set)
                except RuntimeError:
                    if not head.loop.is_closed():
                        raise
                    # A discarded loop cannot resume its waiter. Do not let
                    # it strand the queue or leak an already admitted slot.
                    self._waiters.popleft()
                    continue
            break

    def _try_acquire(
        self, waiter: _Waiter, settings: Settings
    ) -> tuple[bool, float | None]:
        now = time.monotonic()
        while self._starts and self._starts[0] <= now - 60:
            self._starts.popleft()
        if (
            self._waiters[0] is not waiter
            or self._active >= settings.llm_global_concurrency
        ):
            return False, None
        delay = self._cooldown_until - now
        rpm = settings.llm_global_requests_per_minute
        if rpm and len(self._starts) >= rpm:
            delay = max(delay, self._starts[-rpm] + 60 - now)
        if delay > 0:
            return False, delay
        self._waiters.popleft()
        self._active += 1
        self._starts.append(now)
        self._notify()
        return True, None

    def _remove(self, waiter: _Waiter) -> None:
        with self._condition:
            if waiter in self._waiters:
                self._waiters.remove(waiter)
                self._notify()

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LLMQueueTimeout(
                "Timed out waiting for shared LLM capacity; try again later."
            )
        return remaining

    def acquire(self, settings: Settings) -> None:
        waiter = _Waiter()
        deadline = time.monotonic() + settings.llm_queue_timeout_seconds
        with self._condition:
            self._waiters.append(waiter)
            try:
                while True:
                    remaining = self._remaining(deadline)
                    acquired, delay = self._try_acquire(waiter, settings)
                    if acquired:
                        return
                    self._condition.wait(
                        min(remaining, delay) if delay is not None else remaining
                    )
            except BaseException:
                self._remove(waiter)
                raise

    async def acquire_async(self, settings: Settings) -> None:
        waiter = _Waiter(asyncio.get_running_loop(), asyncio.Event())
        deadline = time.monotonic() + settings.llm_queue_timeout_seconds
        with self._condition:
            self._waiters.append(waiter)
        try:
            while True:
                with self._condition:
                    remaining = self._remaining(deadline)
                    assert waiter.event is not None
                    waiter.event.clear()
                    acquired, delay = self._try_acquire(waiter, settings)
                    if acquired:
                        return
                try:
                    await asyncio.wait_for(
                        waiter.event.wait(),
                        timeout=min(remaining, delay)
                        if delay is not None
                        else remaining,
                    )
                except TimeoutError:
                    pass
        except BaseException:
            self._remove(waiter)
            raise

    def release(self) -> None:
        with self._condition:
            self._active -= 1
            self._notify()

    def defer(self, error: Any = None) -> None:
        settings = env_settings()
        delay = max(
            settings.llm_rate_limit_cooldown_seconds, retry_after_seconds(error) or 0
        )
        with self._condition:
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + delay)
            self._notify()


_limiter = CallLimiter()


def defer_rate_limited_calls(error: Any = None) -> None:
    """Share provider rate-limit cooldown with all queued calls, not one run."""
    _limiter.defer(error)


@contextmanager
def llm_call():
    # Deployment settings deliberately bypass the per-tenant settings overlay.
    _limiter.acquire(env_settings())
    try:
        yield
    except BaseException as exc:
        if _rate_limited(exc):
            _limiter.defer(exc)
        raise
    finally:
        _limiter.release()


@asynccontextmanager
async def async_llm_call():
    await _limiter.acquire_async(env_settings())
    try:
        yield
    except BaseException as exc:
        if _rate_limited(exc):
            _limiter.defer(exc)
        raise
    finally:
        _limiter.release()
