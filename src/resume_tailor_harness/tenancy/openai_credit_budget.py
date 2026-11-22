"""Atomic reservations for optional OpenAI work in a real credit period."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from resume_tailor_harness.config import Settings
from resume_tailor_harness.tenancy.context import require_context, use_context
from resume_tailor_harness.tenancy.costs import (
    OPENAI_DECISIONS_RATE_MODEL,
    MeteredUsage,
    calculate_cost,
)
from resume_tailor_harness.tenancy.system_db import (
    OpenAICreditCycle,
    OpenAICreditReconciliation,
    OpenAICreditReservation,
    UsageEvent,
    User,
)


class CreditBudgetError(RuntimeError):
    """Optional work cannot be safely admitted under the credit policy."""


@dataclass(frozen=True)
class CreditBudgetSnapshot:
    cap_micros: int
    spent_micros: int
    held_micros: int
    remaining_micros: int
    warning: bool
    optional_work_paused: bool


@dataclass(frozen=True)
class Reservation:
    id: str
    replay_text: str | None = None
    billing_pending: bool = False


def _period(settings: Settings, now: datetime) -> tuple[datetime, datetime]:
    if not settings.openai_credit_budget_enabled:
        raise CreditBudgetError("OpenAI credit accounting is not enabled.")
    if not settings.openai_credit_project_isolated:
        raise CreditBudgetError("The OpenAI credit project must be isolated for accounting.")
    official_keys = {
        key.strip() for key in (settings.official_audio_api_key, settings.openai_decisions_api_key)
        if key.strip()
    }
    other_keys = {
        key.strip() for key in (settings.openai_api_key, settings.sub2api_openai_key)
        if key.strip()
    }
    if official_keys & other_keys:
        raise CreditBudgetError("Credit project credentials must not be used for general model routing.")
    try:
        start = datetime.fromisoformat(settings.openai_credit_cycle_start.replace("Z", "+00:00"))
        end = datetime.fromisoformat(settings.openai_credit_cycle_end.replace("Z", "+00:00"))
        if start.utcoffset() is None or end.utcoffset() is None:
            raise ValueError("Credit period requires timezone offsets")
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        if not start <= now < end:
            raise ValueError("The credit period is not active")
    except (ValueError, TypeError, OverflowError):
        raise CreditBudgetError("Configure the active timezone-aware OpenAI credit period.") from None
    return start, end


def cycle_identity(settings: Settings) -> str:
    start, end = _period(settings, datetime.now(timezone.utc))
    return hashlib.sha256(f"{start.isoformat()}:{end.isoformat()}".encode()).hexdigest()


def _cycle(session: Session, settings: Settings, now: datetime) -> OpenAICreditCycle:
    start, end = _period(settings, now)
    identity = hashlib.sha256(f"{start.isoformat()}:{end.isoformat()}".encode()).hexdigest()
    cycle = session.get(OpenAICreditCycle, identity)
    if cycle is None:
        overlapping = session.execute(
            select(OpenAICreditCycle).where(
                OpenAICreditCycle.starts_at < end,
                OpenAICreditCycle.ends_at > start,
            )
        ).first()
        if overlapping:
            raise CreditBudgetError("The configured credit period overlaps a recorded period.")
        cycle = OpenAICreditCycle(
            id=identity, starts_at=start, ends_at=end,
            cap_micros=settings.openai_credit_project_cap_micros,
        )
        session.add(cycle)
        session.flush()
    else:
        # A running credit period may be made stricter, never expanded by a
        # configuration change or by starting another worker.
        cycle.cap_micros = min(cycle.cap_micros, settings.openai_credit_project_cap_micros)
    return cycle


def _snapshot(session: Session, cycle: OpenAICreditCycle) -> CreditBudgetSnapshot:
    conditions = (
        UsageEvent.own_key.is_(False),
        UsageEvent.provider == "openai",
        UsageEvent.ts >= cycle.starts_at,
        UsageEvent.ts < cycle.ends_at,
    )
    unknown = session.scalar(
        select(func.count()).select_from(UsageEvent).where(*conditions, UsageEvent.cost_micros.is_(None))
    ) or 0
    if unknown:
        raise CreditBudgetError("Shared OpenAI usage in this credit period has an unknown cost.")
    spent = int(session.scalar(select(func.sum(UsageEvent.cost_micros)).where(*conditions)) or 0)
    held = int(session.scalar(
        select(func.sum(OpenAICreditReservation.reserved_micros)).where(
            OpenAICreditReservation.cycle_id == cycle.id,
            OpenAICreditReservation.status.in_(("reserved", "submitted")),
        )
    ) or 0)
    used = spent + held
    return CreditBudgetSnapshot(
        cap_micros=cycle.cap_micros, spent_micros=spent, held_micros=held,
        remaining_micros=max(0, cycle.cap_micros - used),
        warning=used * 100 >= cycle.cap_micros * 80,
        optional_work_paused=used * 100 >= cycle.cap_micros * 95,
    )


def snapshot() -> CreditBudgetSnapshot:
    context = require_context()
    if context.system_engine is None:
        raise CreditBudgetError("Durable credit accounting is unavailable.")
    with Session(context.system_engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        cycle = _cycle(session, context.settings, datetime.now(timezone.utc))
        result = _snapshot(session, cycle)
        session.commit()
        return result


def reserve(*, request_id: str, operation: str, model: str, fingerprint: str, amount_micros: int) -> Reservation:
    context = require_context()
    if context.system_engine is None:
        raise CreditBudgetError("Durable credit accounting is unavailable.")
    try:
        request_id = str(UUID(request_id))
    except ValueError:
        raise CreditBudgetError("A valid request ID is required.") from None
    if amount_micros <= 0:
        raise CreditBudgetError("An exact rate is required.")
    identity = hashlib.sha256(f"{context.user_id}:{operation}:{request_id}".encode()).hexdigest()
    with Session(context.system_engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        existing = session.get(OpenAICreditReservation, identity)
        if existing is not None:
            if existing.fingerprint != fingerprint or existing.model != model:
                raise CreditBudgetError("This request ID belongs to different input.")
            if existing.result_text is not None:
                return Reservation(identity, existing.result_text, existing.status != "settled")
            if existing.status != "released":
                raise CreditBudgetError("This request is already processing or needs reconciliation.")
        now = datetime.now(timezone.utc)
        cycle = _cycle(session, context.settings, now)
        state = _snapshot(session, cycle)
        if (state.spent_micros + state.held_micros + amount_micros) * 100 > cycle.cap_micros * 95:
            raise CreditBudgetError("Optional OpenAI work is paused to protect the remaining credit.")
        if existing is None:
            existing = OpenAICreditReservation(
                id=identity, user_id=context.user_id, cycle_id=cycle.id,
                operation=operation, model=model, fingerprint=fingerprint,
                status="reserved", reserved_micros=amount_micros, created_at=now,
            )
            session.add(existing)
        else:
            existing.cycle_id = cycle.id
            existing.reserved_micros = amount_micros
            existing.created_at = now
            existing.submitted_at = None
            existing.status = "reserved"
        session.commit()
        return Reservation(identity)


def mark_submitted(reservation_id: str, maximum_usage: MeteredUsage) -> None:
    context = require_context()
    if context.system_engine is None:
        raise CreditBudgetError("Durable credit accounting is unavailable.")
    with Session(context.system_engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(OpenAICreditReservation, reservation_id)
        if row is None or row.user_id != context.user_id or row.status != "reserved":
            raise CreditBudgetError("Credit reservation is no longer available.")
        now = datetime.now(timezone.utc)
        cycle = _cycle(session, context.settings, now)
        if row.cycle_id != cycle.id:
            raise CreditBudgetError("The credit period changed before submission.")
        state = _snapshot(session, cycle)
        if (state.spent_micros + state.held_micros) * 100 > cycle.cap_micros * 95:
            raise CreditBudgetError("Optional OpenAI work is paused to protect the remaining credit.")
        expected_model = (
            OPENAI_DECISIONS_RATE_MODEL
            if maximum_usage.reasoning_mode == "decisions"
            else maximum_usage.model
        )
        priced = calculate_cost(context.system_engine, maximum_usage, now=now)
        if (
            maximum_usage.provider != "openai"
            or row.model != expected_model
            or priced.total_micros is None
            or priced.total_micros > row.reserved_micros
        ):
            raise CreditBudgetError("The current rate exceeds the reserved amount.")
        row.status = "submitted"
        row.submitted_at = now
        session.commit()


def release_unsubmitted(reservation_id: str) -> None:
    context = require_context()
    if context.system_engine is None:
        return
    with Session(context.system_engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(OpenAICreditReservation, reservation_id)
        if row is not None and row.user_id == context.user_id and row.status == "reserved":
            row.status = "released"
        session.commit()


def retain_result(reservation_id: str, transcript: str) -> None:
    """Allow safe replay of text while retaining a hold with uncertain usage."""
    context = require_context()
    if context.system_engine is None:
        raise CreditBudgetError("Durable credit accounting is unavailable.")
    with Session(context.system_engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(OpenAICreditReservation, reservation_id)
        if row is None or row.user_id != context.user_id or row.status != "submitted":
            raise CreditBudgetError("Credit reservation is no longer available.")
        row.result_text = transcript
        session.commit()


def reconcile(
    reservation_id: str,
    *,
    unbilled: bool,
    reason: str,
    audio_input_microseconds: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    audio_output_tokens: int = 0,
) -> None:
    """Apply administrator-verified provider evidence with an audit record."""
    actor = require_context()
    if not actor.is_admin or actor.system_engine is None:
        raise CreditBudgetError("An administrator with durable accounting is required.")
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise CreditBudgetError("A short provider evidence reference is required.")
    values = (
        audio_input_microseconds, input_tokens, output_tokens,
        cache_read_tokens, cache_write_tokens, audio_output_tokens,
    )
    if any(type(value) is not int or value < 0 for value in values):
        raise CreditBudgetError("Usage values must be non-negative integers.")

    with Session(actor.system_engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        row = session.get(OpenAICreditReservation, reservation_id)
        if row is None or row.status not in {"reserved", "submitted"}:
            raise CreditBudgetError("The reservation is not awaiting reconciliation.")
        if unbilled:
            if any(values):
                raise CreditBudgetError("An unbilled request cannot include usage.")
            row.status = "released"
            session.add(OpenAICreditReconciliation(
                id=uuid.uuid4().hex, reservation_id=row.id,
                actor_user_id=actor.user_id, outcome="unbilled", reason=reason,
            ))
            session.commit()
            return
        if row.status != "submitted" or row.submitted_at is None:
            raise CreditBudgetError("Only submitted requests can have provider usage.")
        owner = session.get(User, row.user_id)
        if owner is None:
            raise CreditBudgetError("The reservation owner no longer exists.")
        operation, model, owner_id, owner_role = row.operation, row.model, owner.id, owner.role

    if operation == "transcribe":
        if audio_input_microseconds <= 0 or any(values[1:]):
            raise CreditBudgetError("Transcription requires only billed audio duration.")
        usage = MeteredUsage(provider="openai", model=model, audio_input_microseconds=audio_input_microseconds)
    elif operation == "speech":
        if (audio_input_microseconds or cache_write_tokens or audio_output_tokens > output_tokens
                or cache_read_tokens > input_tokens or not input_tokens + output_tokens):
            raise CreditBudgetError("Speech usage is inconsistent.")
        usage = MeteredUsage(
            provider="openai", model=model, input_tokens=input_tokens, output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens, audio_output_tokens=audio_output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
    elif operation == "decisions":
        if (model != OPENAI_DECISIONS_RATE_MODEL or audio_input_microseconds or output_tokens
                or audio_output_tokens or not input_tokens
                or cache_read_tokens + cache_write_tokens > input_tokens):
            raise CreditBudgetError("Decisions usage is inconsistent.")
        usage = MeteredUsage(
            provider="openai", model="gpt-6-luna", input_tokens=input_tokens,
            cache_read_tokens=cache_read_tokens, cache_write_tokens=cache_write_tokens,
            total_tokens=input_tokens, reasoning_mode="decisions",
        )
    else:
        raise CreditBudgetError("Unknown reservation operation.")

    from resume_tailor_harness.tenancy.usage import record_direct_usage

    owner_context = replace(actor, user_id=owner_id, role=owner_role)
    with use_context(owner_context):
        record_direct_usage(
            usage, own_key=False, request_id=f"official-credit:{reservation_id}",
            credit_reservation_id=reservation_id,
            credit_reconcile_actor=actor.user_id, credit_reconcile_reason=reason,
        )
