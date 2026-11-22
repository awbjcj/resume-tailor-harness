from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import asdict
from collections.abc import Iterable, Mapping
from datetime import timezone
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.orm import Session

from resume_tailor_harness.tenancy.context import current_context
from resume_tailor_harness.tenancy.costs import (
    OPENAI_DECISIONS_RATE_MODEL,
    MeteredUsage,
    calculate_cost,
    normalize_provider,
)
from resume_tailor_harness.tenancy.quotas import charge_in_session
from resume_tailor_harness.tenancy.system_db import (
    OpenAICreditReservation,
    OpenAICreditReconciliation,
    UsageEvent,
    UsageLineItem,
    UsageReceipt,
)

logger = logging.getLogger(__name__)

# Deprecated analytics weights. They remain populated for one compatibility
# release, but are never consulted by cost-quota enforcement.
WEIGHT_INPUT = 1.0
WEIGHT_OUTPUT = 3.0
WEIGHT_CACHE_READ = 0.1
WEIGHT_CACHE_CREATION = 1.25


def _value(obj: object, name: str, default: object = None) -> object:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _metric(metrics: object, name: str) -> int:
    value = _value(metrics, name, 0) or 0
    if isinstance(value, (list, tuple)):
        value = sum(item or 0 for item in value)
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _provider_cost_micros(metrics: object) -> int | None:
    value = _value(metrics, "cost")
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return round(float(value) * 1_000_000)
    except (TypeError, ValueError):
        return None


def _fallback_identity(agent: object, response: object) -> tuple[str, str]:
    model = getattr(agent, "model", None)
    model_id = (
        getattr(response, "model", None)
        or getattr(model, "id", None)
        or getattr(agent, "model_id", None)
        or ""
    )
    provider = getattr(response, "model_provider", None)
    if not provider and model is not None:
        get_provider = getattr(model, "get_provider", None)
        if callable(get_provider):
            provider = get_provider()
        provider = provider or getattr(model, "provider", None)
    if not provider and model_id:
        from resume_tailor_harness.llm_runner import split_provider

        provider, model_id = split_provider(str(model_id))
    return normalize_provider(str(provider or "")), str(model_id)


def _detail_entries(metrics: object) -> Iterable[tuple[str, str, str, object]]:
    details = _value(metrics, "details")
    if not isinstance(details, Mapping):
        return ()
    entries: list[tuple[str, str, str, object]] = []
    for model_type, model_metrics in details.items():
        if isinstance(model_metrics, (list, tuple)):
            for detail in model_metrics:
                entries.append(
                    (
                        normalize_provider(str(_value(detail, "provider") or "")),
                        str(_value(detail, "id") or ""),
                        str(model_type).upper(),
                        detail,
                    )
                )
        elif isinstance(model_metrics, Mapping):
            # Compatibility with older Agno dict serializations.
            for model, detail in model_metrics.items():
                entries.append(
                    (
                        normalize_provider(
                            str(_value(detail, "provider") or model_type)
                        ),
                        str(_value(detail, "id") or model),
                        str(model_type).upper(),
                        detail,
                    )
                )
    return entries


def _nested_units(value: object) -> int:
    names = {
        "tool_units",
        "web_search_count",
        "web_search_requests",
        "web_search_queries",
        "search_queries",
    }
    if not isinstance(value, Mapping):
        return 0
    total = 0
    for key, item in value.items():
        if str(key).casefold() in names:
            try:
                total += int(item or 0)
            except (TypeError, ValueError):
                pass
        elif isinstance(item, Mapping):
            total += _nested_units(item)
    return total


def _metered(
    provider: str, model: str, metrics: object, *, model_type: str | None = None
) -> MeteredUsage:
    input_tokens = _metric(metrics, "input_tokens")
    output_tokens = _metric(metrics, "output_tokens")
    cache_write = _metric(metrics, "cache_write_tokens") or _metric(
        metrics, "cache_creation_tokens"
    )
    total = _metric(metrics, "total_tokens")
    audio_input = _metric(metrics, "audio_input_tokens")
    audio_output = _metric(metrics, "audio_output_tokens")
    return MeteredUsage(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=_metric(metrics, "cache_read_tokens"),
        cache_write_tokens=cache_write,
        reasoning_tokens=_metric(metrics, "reasoning_tokens"),
        audio_input_tokens=audio_input,
        audio_output_tokens=audio_output,
        audio_input_microseconds=_metric(metrics, "audio_input_microseconds"),
        total_tokens=total or input_tokens + output_tokens,
        tool_units=(
            _metric(metrics, "tool_units")
            or _metric(metrics, "web_search_requests")
            or _metric(metrics, "search_queries")
            or _nested_units(_value(metrics, "provider_metrics"))
        ),
        provider_cost_micros=_provider_cost_micros(metrics),
        reasoning_effort=str(_value(metrics, "reasoning_effort") or "") or None,
        reasoning_mode=(
            str(_value(metrics, "reasoning_mode") or "") or model_type or None
        ),
    )


class UsageSettlementError(RuntimeError):
    """A hosted call must not silently escape the billing ledger."""


def record_call(
    agent: object,
    response: object,
    *,
    own_key: bool | None = None,
    credit_reservation_id: str | None = None,
    credit_result_text: str | None = None,
    credit_reconcile_actor: str | None = None,
    credit_reconcile_reason: str | None = None,
) -> None:
    """Settle a response once: receipt, exact usage, line items and balances.

    The provider run id is scoped to the tenant. A retry of the same response
    is harmless; conflicting metrics under that id fail visibly. Responses
    without an id represent distinct invocations and cannot be replay-deduplicated.
    """
    context = current_context()
    if context is None or context.system_engine is None:
        if credit_reservation_id:
            raise UsageSettlementError("Credit accounting context is unavailable")
        return
    try:
        if bool(credit_reconcile_actor) != bool(credit_reconcile_reason):
            raise UsageSettlementError("Reconciliation requires an actor and reason")
        pricing_moment = None
        if credit_reservation_id:
            with Session(context.system_engine) as session:
                held = session.get(OpenAICreditReservation, credit_reservation_id)
                if held is None or held.user_id != context.user_id or held.submitted_at is None:
                    raise UsageSettlementError("Credit reservation has no submission time")
                pricing_moment = held.submitted_at
                if pricing_moment.tzinfo is None:
                    pricing_moment = pricing_moment.replace(tzinfo=timezone.utc)
        metrics = getattr(response, "metrics", None)
        fallback_provider, fallback_model = _fallback_identity(agent, response)
        entries = list(_detail_entries(metrics))
        if not entries:
            entries = [(fallback_provider, fallback_model, "MODEL", metrics)]
        from resume_tailor_harness.tenancy.limits import selected_key_is_own
        from resume_tailor_harness.tenancy.spend import SpendGate

        charges = []
        for provider, model, model_type, detail in entries:
            usage = _metered(
                provider or fallback_provider,
                model or fallback_model,
                detail,
                model_type=model_type,
            )
            funded_by_owner = (
                selected_key_is_own(usage.provider, agent)
                if own_key is None
                else own_key
            )
            priced = calculate_cost(context.system_engine, usage, now=pricing_moment)
            if (
                not funded_by_owner
                and priced.total_micros is None
                and context.settings.cost_quota_enforcement == "enforce"
            ):
                raise UsageSettlementError(
                    "Shared usage has no exact price; settlement failed"
                )
            charges.append((usage, funded_by_owner, priced))
        request_id = getattr(response, "run_id", None)
        receipt_id = hashlib.sha256(
            f"{context.user_id}:{request_id}".encode()
        ).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(
                [(asdict(usage), own_key) for usage, own_key, _ in charges],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        settlements = []
        with Session(context.system_engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            receipt = session.get(UsageReceipt, receipt_id) if request_id else None
            if receipt is not None:
                if receipt.fingerprint != fingerprint:
                    raise UsageSettlementError(
                        "Response id reused with different usage"
                    )
                return
            reservation = None
            if credit_reservation_id:
                reservation = session.get(OpenAICreditReservation, credit_reservation_id)
                if (
                    reservation is None
                    or reservation.user_id != context.user_id
                    or reservation.status != "submitted"
                    or reservation.submitted_at is None
                    or len(charges) != 1
                    or charges[0][1]
                    or charges[0][0].provider != "openai"
                    or reservation.model != (
                        OPENAI_DECISIONS_RATE_MODEL
                        if charges[0][0].reasoning_mode == "decisions"
                        else charges[0][0].model
                    )
                    or not request_id
                    or charges[0][2].total_micros is None
                    or (
                        charges[0][2].total_micros > reservation.reserved_micros
                        and not credit_reconcile_actor
                    )
                ):
                    raise UsageSettlementError("Credit reservation cannot be settled")
            if request_id:
                session.add(
                    UsageReceipt(
                        id=receipt_id, user_id=context.user_id, fingerprint=fingerprint
                    )
                )
            for usage, own_key, priced in charges:
                event = UsageEvent(
                    user_id=context.user_id,
                    provider=usage.provider or None,
                    model=usage.model or None,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_creation_tokens=usage.cache_write_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                    reasoning_tokens=usage.reasoning_tokens,
                    audio_input_tokens=usage.audio_input_tokens,
                    audio_output_tokens=usage.audio_output_tokens,
                    audio_input_microseconds=usage.audio_input_microseconds,
                    total_tokens=usage.total_tokens,
                    weighted_total=(
                        usage.input_tokens * WEIGHT_INPUT
                        + usage.output_tokens * WEIGHT_OUTPUT
                        + usage.cache_read_tokens * WEIGHT_CACHE_READ
                        + usage.cache_write_tokens * WEIGHT_CACHE_CREATION
                    ),
                    own_key=own_key,
                    cost_micros=priced.total_micros,
                    quota_cost_micros=0 if own_key else priced.total_micros or 0,
                    tool_cost_micros=priced.tool_micros,
                    provider_cost_micros=usage.provider_cost_micros,
                    rate_id=priced.rate_id,
                    pricing_status=priced.pricing_status,
                    reasoning_effort=usage.reasoning_effort,
                    reasoning_mode=usage.reasoning_mode,
                )
                if reservation is not None:
                    # Associate delayed settlement with the period in which
                    # the provider request was admitted, even across rollover.
                    assert reservation.submitted_at is not None
                    event.ts = reservation.submitted_at
                session.add(event)
                session.flush()
                if priced.rate_id:
                    session.add_all(
                        UsageLineItem(
                            usage_event_id=event.id,
                            kind=line.kind,
                            units=line.units,
                            rate_micros=line.rate_micros,
                            cost_micros=line.cost_micros,
                            rate_id=line.rate_id or priced.rate_id,
                        )
                        for line in priced.lines
                    )
                snapshot = None
                if (
                    not own_key
                    and not context.is_admin
                    and priced.total_micros is not None
                ):
                    snapshot = charge_in_session(
                        session,
                        context.user_id,
                        priced.total_micros,
                        usage_event_id=event.id,
                        new_event=True,
                    )
                if not own_key:
                    settlements.append(
                        (
                            snapshot,
                            float(event.weighted_total or 0),
                            int(priced.total_micros or 0),
                        )
                    )
            if reservation is not None:
                reservation.status = "settled"
                if credit_result_text is not None:
                    reservation.result_text = credit_result_text
                if credit_reconcile_actor and credit_reconcile_reason:
                    session.add(OpenAICreditReconciliation(
                        id=uuid.uuid4().hex, reservation_id=reservation.id,
                        actor_user_id=credit_reconcile_actor, outcome="settled",
                        reason=credit_reconcile_reason,
                    ))
            session.commit()
        for snapshot, weighted, cost in settlements:
            SpendGate().settle(snapshot, weighted=weighted, cost_micros=cost)
    except Exception as exc:
        context.spend_decisions.clear()
        logger.error("usage settlement failed", exc_info=True)
        raise UsageSettlementError(
            "Usage could not be settled; operator attention is required"
        ) from exc


def record_direct_usage(
    usage: MeteredUsage,
    *,
    own_key: bool | None = None,
    request_id: str | None = None,
    credit_reservation_id: str | None = None,
    credit_result_text: str | None = None,
    credit_reconcile_actor: str | None = None,
    credit_reconcile_reason: str | None = None,
) -> None:
    """Send non-Agno provider calls through the same immutable recorder."""

    metrics = SimpleNamespace(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        audio_input_tokens=usage.audio_input_tokens,
        audio_output_tokens=usage.audio_output_tokens,
        audio_input_microseconds=usage.audio_input_microseconds,
        total_tokens=usage.total_tokens,
        tool_units=usage.tool_units,
        cost=(
            usage.provider_cost_micros / 1_000_000
            if usage.provider_cost_micros is not None
            else None
        ),
        reasoning_effort=usage.reasoning_effort,
        reasoning_mode=usage.reasoning_mode,
    )
    record_call(
        SimpleNamespace(model=SimpleNamespace(id=usage.model, provider=usage.provider)),
        SimpleNamespace(
            model=usage.model,
            model_provider=usage.provider,
            metrics=metrics,
            run_id=request_id,
        ),
        own_key=own_key,
        credit_reservation_id=credit_reservation_id,
        credit_result_text=credit_result_text,
        credit_reconcile_actor=credit_reconcile_actor,
        credit_reconcile_reason=credit_reconcile_reason,
    )
