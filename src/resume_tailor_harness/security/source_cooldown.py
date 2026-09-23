"""Durable, bounded circuit breakers for public job sources."""

import hashlib
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.schema import Table

from resume_tailor_harness.db import make_engine
from resume_tailor_harness.tenancy.context import current_context
from resume_tailor_harness.tenancy.system_db import CrawlCooldown


class SourceCooldown(ValueError):
    def __init__(self, reason: str, retry_at: float):
        self.reason = reason
        self.retry_at = retry_at
        retry = datetime.fromtimestamp(retry_at, timezone.utc).isoformat(
            timespec="seconds"
        )
        super().__init__(f"Source paused: {reason}; retry after {retry}")


def _key(url: str, origin_only: bool = False) -> str:
    parsed = urlsplit(url)
    origin = f"{parsed.scheme.lower()}://{parsed.hostname}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"
    # Queries can contain personal search terms; they are never persisted.
    value = origin if origin_only else origin + (parsed.path or "/")
    return hashlib.sha256(value.encode()).hexdigest()


class CooldownStore:
    def __init__(self, engine, *, clock=time.time):
        self.engine, self.clock = engine, clock
        self.table = cast(Table, CrawlCooldown.__table__)
        self.table.create(engine, checkfirst=True)

    def check(self, url: str) -> None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(self.table)
                    .where(
                        self.table.c.key.in_([_key(url), _key(url, True)]),
                        self.table.c.retry_at > self.clock(),
                    )
                    .order_by(self.table.c.retry_at.desc())
                )
                .mappings()
                .first()
            )
        if row:
            raise SourceCooldown(row["reason"], row["retry_at"])

    def block(
        self, url: str, reason: str, *, seconds: float = 3600, origin_only: bool = False
    ) -> SourceCooldown:
        # Never store response bodies, URLs, credentials, or caller-provided error text.
        if reason not in {
            "HTTP 401",
            "HTTP 403",
            "HTTP 429",
            "HTTP 503",
            "robots policy",
            "access challenge",
        }:
            raise ValueError("Unsupported source cooldown reason")
        retry_at = self.clock() + min(86400, max(60, seconds))
        key = _key(url, origin_only)
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    delete(self.table).where(self.table.c.retry_at <= self.clock())
                )
                conn.execute(
                    insert(self.table).values(key=key, reason=reason, retry_at=retry_at)
                )
        except IntegrityError:
            with self.engine.begin() as conn:
                conn.execute(
                    update(self.table)
                    .where(self.table.c.key == key, self.table.c.retry_at < retry_at)
                    .values(reason=reason, retry_at=retry_at)
                )
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(self.table).where(self.table.c.key == key))
                .mappings()
                .one()
            )
        return SourceCooldown(row["reason"], row["retry_at"])


@lru_cache(maxsize=8)
def _local_engine(path: str):
    return make_engine(f"sqlite:///{path}")


def default_store() -> CooldownStore:
    context = current_context()
    engine = context.system_engine if context else None
    if engine is None:
        engine = _local_engine((Path("data") / "crawl-system.db").absolute().as_posix())
    return CooldownStore(engine)
