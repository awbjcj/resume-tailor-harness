"""Operator-managed subscription terms, inspired by Sub2API's renewal semantics."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from resume_tailor_harness.tenancy.quotas import (
    IdempotencyConflictError,
    _aware,
    _ensure_in_session,
    _new_period,
    _period_end,
)
from resume_tailor_harness.tenancy.system_db import (
    MemberSubscription,
    QuotaLedgerEntry,
    QuotaTier,
    SubscriptionOperation,
    User,
)


def apply_subscription(
    engine: Engine,
    user_id: str,
    *,
    actor_user_id: str,
    action: str,
    tier_id: str | None,
    cycles: int,
    reason: str,
    idempotency_key: str,
    now: datetime | None = None,
) -> dict:
    """Grant, renew or revoke exactly once, including its allowance ledger.

    Active renewal extends expiry only. Expired terms start a new allowance
    period now; unused recurring allowance expires, durable credits survive.
    """
    if action not in {"ACTIVATE", "RENEW", "REVOKE"}:
        raise ValueError("unknown subscription action")
    if (
        not 1 <= cycles <= 52
        or not reason.strip()
        or not 8 <= len(idempotency_key) <= 64
    ):
        raise ValueError("cycles, reason and idempotency key are required")
    moment = now or datetime.now(UTC)
    fingerprint = json.dumps([user_id, actor_user_id, action, tier_id, cycles, reason])
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        previous = session.get(SubscriptionOperation, idempotency_key)
        if previous is not None:
            if previous.fingerprint != fingerprint:
                raise IdempotencyConflictError(
                    "subscription operation key was already used"
                )
            return json.loads(previous.result_json)
        user = session.get(User, user_id)
        if user is None or user.role == "admin":
            raise LookupError("No such member")
        account, period, _ = _ensure_in_session(session, user_id, moment)
        subscription = session.get(MemberSubscription, user_id)
        active = subscription is not None and subscription.status == "ACTIVE"
        if action == "REVOKE":
            if not active:
                raise ValueError("there is no active subscription to revoke")
            assert subscription is not None
            subscription.status = "REVOKED"
            tier = session.get(QuotaTier, "FREE")
            assert tier is not None
        else:
            if action == "ACTIVATE" and active:
                raise ValueError("renew or revoke the active subscription first")
            if action == "RENEW" and subscription is None:
                raise ValueError("there is no subscription to renew")
            selected_tier = tier_id or (subscription.tier_id if subscription else None)
            tier = session.get(QuotaTier, selected_tier) if selected_tier else None
            if tier is None or tier.is_default or tier.archived_at is not None:
                raise ValueError("select an available paid tier")
            if active and subscription is not None and tier.id != subscription.tier_id:
                raise ValueError("renewal cannot change the active tier")
            start = (
                _aware(subscription.expires_at) if active and subscription else moment
            )
            anchor = (
                _aware(subscription.starts_at) if active and subscription else moment
            )
            expiry = start
            for _ in range(cycles):
                expiry = _period_end(expiry, tier, anchor=anchor)
            if subscription is None:
                subscription = MemberSubscription(user_id=user_id)
                session.add(subscription)
            subscription.tier_id = tier.id
            subscription.starts_at = anchor
            subscription.expires_at = expiry
            subscription.status = "ACTIVE"
        if not active or action == "REVOKE":
            period.closed_at = moment
            account.tier_id = tier.id
            account.anchor_at = moment
            account.quota_override_micros = None
            period = _new_period(session, account, tier, moment)
        assert subscription is not None
        result = {
            "user_id": user_id,
            "tier_id": subscription.tier_id,
            "status": subscription.status,
            "starts_at": _aware(subscription.starts_at).isoformat(),
            "expires_at": _aware(subscription.expires_at).isoformat(),
        }
        session.add(
            QuotaLedgerEntry(
                user_id=user_id,
                period_id=period.id,
                kind={
                    "ACTIVATE": "SUBSCRIPTION_ACTIVATED",
                    "RENEW": "SUBSCRIPTION_RENEWED",
                    "REVOKE": "SUBSCRIPTION_REVOKED",
                }[action],
                amount_micros=0,
                actor_user_id=actor_user_id,
                reason=reason,
                snapshot_json=json.dumps(result),
            )
        )
        session.add(
            SubscriptionOperation(
                idempotency_key=idempotency_key,
                user_id=user_id,
                fingerprint=fingerprint,
                result_json=json.dumps(result),
            )
        )
        session.commit()
        return result
