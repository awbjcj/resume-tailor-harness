"""Shared origin scheduling and explicit crawl resource accounting."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import cast
from urllib.robotparser import RobotFileParser

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.schema import Table

from resume_tailor_harness.tenancy.system_db import CrawlHostLease

from .contracts import CrawlLimits

CRAWLER_AGENT = "ResumeTailorBot"
LEASE_SECONDS = 60.0


@dataclass(frozen=True)
class HostLease:
    host: str
    owner: str
    token: int
    expires_at: float


class HostScheduler:
    def __init__(self, engine: Engine, clock: Callable[[], float] = time.time):
        self.engine = engine
        self.clock = clock
        cast(Table, CrawlHostLease.__table__).create(engine, checkfirst=True)

    def acquire(self, host: str, owner: str, deadline: float) -> HostLease | None:
        now = self.clock()
        if now >= deadline:
            return None
        table = cast(Table, CrawlHostLease.__table__)
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert(table).values(
                        host=host, owner="", token=0, expires_at=0, available_at=0
                    )
                )
        except IntegrityError:
            pass  # The host already has a shared schedule.
        with self.engine.begin() as conn:
            result = conn.execute(
                update(table)
                .where(
                    table.c.host == host,
                    table.c.expires_at <= now,
                    table.c.available_at <= now,
                )
                .values(
                    owner=owner, token=table.c.token + 1, expires_at=now + LEASE_SECONDS
                )
            )
            if result.rowcount != 1:
                return None
            row = (
                conn.execute(select(table).where(table.c.host == host)).mappings().one()
            )
            return HostLease(host, owner, row["token"], row["expires_at"])

    def renew(self, lease: HostLease) -> bool:
        table = cast(Table, CrawlHostLease.__table__)
        now = self.clock()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(table)
                .where(
                    table.c.host == lease.host,
                    table.c.owner == lease.owner,
                    table.c.token == lease.token,
                    table.c.expires_at > now,
                )
                .values(expires_at=now + LEASE_SECONDS)
            )
            return result.rowcount == 1

    def release(self, lease: HostLease, delay: float) -> None:
        table = cast(Table, CrawlHostLease.__table__)
        with self.engine.begin() as conn:
            conn.execute(
                update(table)
                .where(
                    table.c.host == lease.host,
                    table.c.owner == lease.owner,
                    table.c.token == lease.token,
                )
                .values(
                    owner="", expires_at=0, available_at=self.clock() + max(3, delay)
                )
            )


class BudgetExceeded(RuntimeError):
    pass


class CrawlBudget:
    def __init__(
        self,
        limits: CrawlLimits,
        clock: Callable[[], float] = time.monotonic,
        cancelled: Callable[[], bool] = lambda: False,
    ):
        self.limits = limits
        self.clock = clock
        self.cancelled = cancelled
        self.deadline = clock() + limits.elapsed_seconds
        self.listings = 0
        self.details = 0
        self.requests = 0
        self.bytes = 0

    def check_deadline(self) -> None:
        if self.cancelled():
            raise BudgetExceeded("cancelled")
        if self.clock() >= self.deadline:
            raise BudgetExceeded("elapsed time limit")

    def charge_listing(self) -> None:
        self.check_deadline()
        if self.listings >= self.limits.listing_pages:
            raise BudgetExceeded("listing page limit")
        self.listings += 1

    def charge_detail(self) -> None:
        self.check_deadline()
        if self.details >= self.limits.detail_pages:
            raise BudgetExceeded("detail page limit")
        self.details += 1

    def begin_page(self) -> None:
        self.check_deadline()
        self.requests = 0
        self.bytes = 0

    def charge_request(self, byte_count: int = 0) -> None:
        self.check_deadline()
        if self.requests >= 200:
            raise BudgetExceeded("page request limit")
        self.requests += 1
        self.charge_bytes(byte_count)

    def charge_bytes(self, byte_count: int) -> None:
        self.check_deadline()
        if byte_count < 0:
            raise ValueError("byte count must be nonnegative")
        if self.bytes + byte_count > 20 * 1024 * 1024:
            raise BudgetExceeded("page bytes limit")
        self.bytes += byte_count


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    delay_seconds: float = 3
    reason: str = ""


def robots_decision(url: str, status: int, text: str) -> RobotsDecision:
    if status in {404, 410}:
        return RobotsDecision(True)
    if status != 200:
        return RobotsDecision(False, reason=f"robots.txt unavailable (HTTP {status})")
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    delay = parser.crawl_delay(CRAWLER_AGENT) or parser.crawl_delay("*") or 3
    delay_seconds = max(3.0, float(delay))
    allowed = parser.can_fetch(CRAWLER_AGENT, url)
    return RobotsDecision(
        allowed, delay_seconds, "" if allowed else "robots.txt disallows this path"
    )


def retry_delay(value: str | None, attempt: int, *, now: float | None = None) -> float:
    if value:
        try:
            return max(0, float(value))
        except ValueError:
            try:
                return max(
                    0,
                    parsedate_to_datetime(value).timestamp()
                    - (time.time() if now is None else now),
                )
            except (ValueError, TypeError, OverflowError):
                pass
    return 30.0 * (attempt + 1)
