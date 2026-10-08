"""Stripe collection over the existing allowance and durable-credit ledger.

Remote calls happen outside SQLite writer transactions. Event receipts, object
receipts, entitlements and balance changes commit in the same transaction.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict, cast
from urllib.parse import urlsplit

import stripe
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from stripe.params import CustomerCreateParams
from stripe.params.billing_portal import (
    SessionCreateParams as PortalSessionCreateParams,
)
from stripe.params.checkout import SessionCreateParams as CheckoutSessionCreateParams

from resume_tailor_harness.config import Settings
from resume_tailor_harness.tenancy.quotas import _aware, _ensure_in_session, _new_period
from resume_tailor_harness.tenancy.system_db import (
    MemberSubscription,
    QuotaLedgerEntry,
    QuotaTier,
    StripeCheckout,
    StripeCustomer,
    StripeReceipt,
    StripeSubscription,
    User,
)

STRIPE_API_VERSION = "2026-02-25.clover"
TERMINAL = {"canceled", "unpaid", "incomplete_expired", "paused"}
CLOSED = {"canceled", "incomplete_expired"}
logger = logging.getLogger(__name__)


class _ManagedPaymentsParams(TypedDict):
    enabled: bool


class _CheckoutCreateParams(CheckoutSessionCreateParams):
    # The pinned Stripe SDK does not yet declare this supported API parameter.
    managed_payments: _ManagedPaymentsParams


class BillingError(RuntimeError):
    def __init__(
        self, message: str, *, status: int = 409, code: str = "BILLING_CONFLICT"
    ):
        super().__init__(message)
        self.status, self.code = status, code


def billing_enabled(settings: Settings, app_mode: str) -> bool:
    return app_mode == "hosted" and settings.stripe_enabled


def billing_service_available(settings: Settings, app_mode: str) -> bool:
    return app_mode == "hosted" and bool(
        settings.stripe_secret_key and settings.stripe_webhook_secret
    )


def billing_origin(settings: Settings) -> str:
    base = settings.app_base_url.strip().rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise BillingError(
            "Billing requires an HTTPS APP_BASE_URL",
            status=503,
            code="BILLING_UNAVAILABLE",
        )
    return base


def stripe_data(value: Any) -> Any:
    """Keep provider resource objects outside the dictionary-based ledger."""
    if isinstance(value, stripe.StripeObject):
        # Stripe 15+ resources are no longer dicts; to_dict now recurses.
        # Retain the recursive converter for the supported Stripe 14 range.
        legacy_converter = getattr(value, "to_dict_recursive", None)
        return legacy_converter() if callable(legacy_converter) else value.to_dict()
    return value


class StripeGateway:
    def __init__(self, settings: Settings):
        if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
            raise BillingError(
                "Payments are not configured", status=503, code="BILLING_UNAVAILABLE"
            )
        self.http_client = stripe.HTTPXClient(timeout=15, allow_sync_methods=True)
        self.client = stripe.StripeClient(
            settings.stripe_secret_key,
            stripe_version=STRIPE_API_VERSION,
            max_network_retries=2,
            http_client=self.http_client,
        )

    def close(self) -> None:
        self.http_client.close()

    def price(self, price_id: str) -> Any:
        return stripe_data(self.client.v1.prices.retrieve(price_id))

    def customer(self, user_id: str, email: str | None) -> Any:
        params: CustomerCreateParams = {"metadata": {"user_id": user_id}}
        if email:
            params["email"] = email
        return stripe_data(
            self.client.v1.customers.create(
                params, options={"idempotency_key": f"resume-customer-{user_id}"}
            )
        )

    def checkout(self, params: CheckoutSessionCreateParams, key: str) -> Any:
        return stripe_data(
            self.client.v1.checkout.sessions.create(
                params, options={"idempotency_key": key}
            )
        )

    def checkout_status(self, session_id: str) -> Any:
        return stripe_data(self.client.v1.checkout.sessions.retrieve(session_id))

    def find_checkout(self, customer_id: str, order_id: str) -> Any:
        sessions = self.client.v1.checkout.sessions.list(
            {"customer": customer_id, "limit": 100}
        )
        for item in sessions.auto_paging_iter():
            checkout = stripe_data(item)
            if (checkout.get("metadata") or {}).get("checkout_id") == order_id:
                return checkout
        return None

    def subscription(self, subscription_id: str) -> Any:
        return stripe_data(self.client.v1.subscriptions.retrieve(subscription_id))

    def invoice(self, invoice_id: str) -> Any:
        return stripe_data(self.client.v1.invoices.retrieve(invoice_id))

    def payment_intent(self, intent_id: str) -> Any:
        return stripe_data(self.client.v1.payment_intents.retrieve(intent_id))

    def portal(self, params: PortalSessionCreateParams) -> Any:
        return stripe_data(self.client.v1.billing_portal.sessions.create(params))


def _member(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None or user.disabled_at is not None or user.role == "admin":
        raise BillingError(
            "Payments are available to active member accounts",
            status=403,
            code="BILLING_MEMBER_REQUIRED",
        )
    return user


def _offer(
    session: Session, settings: Settings, gateway: StripeGateway, price_id: str
) -> dict:
    credit = settings.stripe_credit_prices.get(price_id)
    tier_id = settings.stripe_subscription_prices.get(price_id)
    if (credit is None) == (tier_id is None):
        raise BillingError(
            "Select an available purchase", status=400, code="BILLING_PRICE_INVALID"
        )
    price = gateway.price(price_id)
    if (
        not price.get("active")
        or price.get("currency") != "usd"
        or not isinstance(price.get("unit_amount"), int)
        or price["unit_amount"] <= 0
        or price.get("billing_scheme") != "per_unit"
        or price.get("transform_quantity")
        # Managed Payments calculates tax. Inclusive prices preserve the gross
        # USD purchase/refund amount recorded by the existing credit ledger.
        or (
            settings.stripe_managed_payments_enabled
            and price.get("tax_behavior") != "inclusive"
        )
    ):
        raise BillingError(
            "The selected price is unavailable", status=503, code="BILLING_UNAVAILABLE"
        )
    offer = {
        "price_id": price_id,
        "amount_cents": price["unit_amount"],
        "currency": "usd",
        "credit_micros": credit,
        "tier_id": tier_id,
    }
    if credit is not None:
        if (
            type(credit) is not int
            or not 0 < credit <= 1_000_000_000_000
            or price.get("recurring")
        ):
            raise BillingError(
                "Invalid credit price configuration",
                status=503,
                code="BILLING_UNAVAILABLE",
            )
        return {
            **offer,
            "name": "Credit top-up",
            "mode": "payment",
            "allowance_micros": None,
            "interval": None,
            "interval_count": None,
        }
    tier = session.get(QuotaTier, tier_id)
    recurring = price.get("recurring") or {}
    if (
        tier is None
        or tier.is_default
        or tier.archived_at is not None
        or recurring.get("interval")
        != {"MONTH": "month", "WEEK": "week"}.get(tier.cycle_unit)
        or recurring.get("interval_count") != tier.cycle_count
        or recurring.get("usage_type") != "licensed"
    ):
        raise BillingError(
            "Plan and Stripe billing cycles must match",
            status=503,
            code="BILLING_UNAVAILABLE",
        )
    return {
        **offer,
        "name": tier.name,
        "mode": "subscription",
        "allowance_micros": tier.allowance_micros,
        "interval": recurring["interval"],
        "interval_count": recurring["interval_count"],
    }


def billing_catalog(
    engine: Engine, settings: Settings, user_id: str, gateway: StripeGateway
) -> dict:
    billing_origin(settings)
    with Session(engine) as session:
        _member(session, user_id)
        offers = []
        price_ids = (
            (*settings.stripe_credit_prices, *settings.stripe_subscription_prices)
            if settings.stripe_enabled
            else ()
        )
        for key in price_ids:
            try:
                offers.append(_offer(session, settings, gateway, key))
            except (BillingError, stripe.StripeError):
                # Existing customers must retain their portal even when a price
                # is archived or Stripe cannot load the purchase catalog.
                logger.warning("Stripe offer %s is unavailable", key)
        customer = session.get(StripeCustomer, user_id)
        subscription = session.scalars(
            select(StripeSubscription)
            .where(StripeSubscription.user_id == user_id)
            .order_by(StripeSubscription.created_at.desc())
        ).first()
        return {
            "enabled": True,
            "offers": offers,
            "portal_available": customer is not None,
            "subscription": None
            if subscription is None
            else {
                "status": subscription.status,
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "paid_through": subscription.paid_through,
            },
        }


def _customer_id(engine: Engine, user_id: str, gateway: StripeGateway) -> str:
    with Session(engine) as session:
        user = _member(session, user_id)
        row = session.get(StripeCustomer, user_id)
        if row:
            return row.customer_id
        email = user.email
    customer_id = gateway.customer(user_id, email)["id"]
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        _member(session, user_id)
        row = session.get(StripeCustomer, user_id)
        if row is None:
            row = StripeCustomer(user_id=user_id, customer_id=customer_id)
            session.add(row)
        session.commit()
        return row.customer_id


def _recover_checkout(engine: Engine, order_id: str, gateway: StripeGateway) -> None:
    """Recover a lost response before retrying a time-sensitive creation."""
    with Session(engine) as session:
        order = session.get(StripeCheckout, order_id)
        if order is None or order.status not in {"pending", "open"}:
            return
        session_id, customer_id = order.session_id, order.customer_id
        if not session_id and _aware(order.expires_at) >= datetime.now(UTC) + timedelta(
            minutes=30
        ):
            return
    # Stripe rejects expires_at less than 30 minutes from a new creation. A
    # previous successful creation must be found rather than changing its
    # idempotent parameters, which could create a second subscription.
    remote = (
        gateway.checkout_status(session_id)
        if session_id
        else gateway.find_checkout(customer_id, order_id)
    )
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        order = session.get(StripeCheckout, order_id)
        assert order is not None
        if order.status not in {"pending", "open"}:
            return
        if remote is not None:
            if _order(session, remote) is not order or remote.get("mode") != order.mode:
                raise BillingError("Checkout identity does not match")
            order.session_id = remote["id"]
            order.checkout_url = (
                remote.get("url") if remote.get("status") == "open" else None
            )
            order.status = "expired" if remote.get("status") == "expired" else "open"
        elif order.session_id is None:
            # A concurrent creator that later returns may no longer hand out
            # this closed reservation. Its original expiry parameters are fixed.
            order.status = "expired"
        session.commit()


def create_checkout(
    engine: Engine,
    settings: Settings,
    user_id: str,
    price_id: str,
    key: str,
    gateway: StripeGateway,
) -> dict:
    base = billing_origin(settings)
    order_id = hashlib.sha256(f"{user_id}:{key}".encode()).hexdigest()[:32]
    with Session(engine) as session:
        _member(session, user_id)
        offer = _offer(session, settings, gateway, price_id)
    customer_id = _customer_id(engine, user_id, gateway)
    _recover_checkout(engine, order_id, gateway)
    # Expire a preceding session only after Stripe confirms it has expired.
    # A completed session awaiting its webhook still blocks another subscription.
    if offer["mode"] == "subscription":
        with Session(engine) as session:
            previous = session.scalars(
                select(StripeCheckout).where(
                    StripeCheckout.user_id == user_id,
                    StripeCheckout.mode == "subscription",
                    StripeCheckout.status.in_(["pending", "open"]),
                    StripeCheckout.id != order_id,
                )
            ).first()
            previous_id, session_id, previous_price = (
                (previous.id, previous.session_id, previous.price_id)
                if previous
                else (None, None, None)
            )
        if previous_id:
            _recover_checkout(engine, previous_id, gateway)
            with Session(engine) as session:
                previous = session.get(StripeCheckout, previous_id)
                assert previous is not None
                session_id = previous.session_id
                previous_expired = previous.status == "expired"
            state = "pending"
            if previous_expired:
                state = "expired"
            elif session_id:
                state = gateway.checkout_status(session_id).get("status")
            if state in {"open", "pending"} and previous_price == price_id:
                # Reopening the app after a lost response resumes the original
                # purchase and Stripe idempotency key, even with a new UI key.
                order_id = previous_id
            elif state != "expired":
                raise BillingError("A subscription checkout is already in progress")
            else:
                with Session(engine) as session:
                    session.execute(text("BEGIN IMMEDIATE"))
                    previous = session.get(StripeCheckout, previous_id)
                    if previous and previous.status != "fulfilled":
                        previous.status = "expired"
                    session.commit()
    with Session(engine, expire_on_commit=False) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        _member(session, user_id)
        order = session.get(StripeCheckout, order_id)
        if order:
            if order.price_id != price_id:
                raise BillingError("This checkout key was used for another purchase")
            if order.status in {"fulfilled", "expired"}:
                raise BillingError(
                    "This checkout has ended; start a new purchase",
                    code="BILLING_CHECKOUT_ENDED",
                )
            if order.checkout_url:
                return {"url": order.checkout_url, "checkout_id": order.session_id}
            if order.session_id:
                raise BillingError("Payment confirmation is pending")
        else:
            if offer["mode"] == "subscription":
                pending = session.scalars(
                    select(StripeCheckout).where(
                        StripeCheckout.user_id == user_id,
                        StripeCheckout.mode == "subscription",
                        StripeCheckout.status.in_(["pending", "open"]),
                    )
                ).first()
                linked = session.scalars(
                    select(StripeSubscription).where(
                        StripeSubscription.user_id == user_id,
                        StripeSubscription.status.not_in(CLOSED),
                    )
                ).first()
                member = session.get(MemberSubscription, user_id)
                if (
                    pending
                    or linked
                    or (
                        member
                        and member.status == "ACTIVE"
                        and _aware(member.expires_at) > datetime.now(UTC)
                    )
                ):
                    raise BillingError(
                        "Manage the current subscription before starting another"
                    )
            order = StripeCheckout(
                id=order_id,
                user_id=user_id,
                customer_id=customer_id,
                price_id=price_id,
                mode=offer["mode"],
                managed_payments=settings.stripe_managed_payments_enabled,
                amount_cents=offer["amount_cents"],
                credit_micros=offer["credit_micros"] or 0,
                tier_id=offer["tier_id"],
                expires_at=datetime.now(UTC) + timedelta(minutes=31),
            )
            session.add(order)
            session.commit()
    metadata = {"checkout_id": order.id, "user_id": user_id}
    params: _CheckoutCreateParams = {
        "mode": cast(Literal["payment", "subscription"], order.mode),
        "customer": customer_id,
        "client_reference_id": user_id,
        "metadata": metadata,
        "line_items": [{"price": order.price_id, "quantity": 1}],
        "currency": "usd",
        "managed_payments": {"enabled": order.managed_payments},
        "expires_at": int(_aware(order.expires_at).timestamp()),
        "success_url": f"{base}/account?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/account?billing=canceled",
    }
    if not order.managed_payments:
        # Standard Checkout keeps the USD/card policy even when Managed Payments
        # is the account default. Managed Payments owns these parameters.
        params["adaptive_pricing"] = {"enabled": False}
        params["payment_method_types"] = ["card"]
    if order.mode == "subscription":
        params["subscription_data"] = {"metadata": metadata}
    else:
        params["payment_intent_data"] = {"metadata": metadata}
    checkout = gateway.checkout(params, f"resume-checkout-{order_id}")
    if not checkout.get("url"):
        raise BillingError(
            "Unable to open checkout", status=502, code="BILLING_PROVIDER_UNAVAILABLE"
        )
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        saved = session.get(StripeCheckout, order_id)
        assert saved is not None
        if saved.status == "expired":
            raise BillingError(
                "This checkout has ended; start a new purchase",
                code="BILLING_CHECKOUT_ENDED",
            )
        if saved.session_id and saved.session_id != checkout["id"]:
            raise BillingError("Checkout identity changed")
        saved.session_id, saved.checkout_url = checkout["id"], checkout["url"]
        if saved.status == "pending":
            saved.status = "open"
        session.commit()
    return {"url": checkout["url"], "checkout_id": checkout["id"]}


def create_portal(
    engine: Engine, settings: Settings, user_id: str, gateway: StripeGateway
) -> dict:
    base = billing_origin(settings)
    with Session(engine) as session:
        _member(session, user_id)
        customer = session.get(StripeCustomer, user_id)
        if customer is None:
            raise BillingError("No billing account exists yet")
        params: PortalSessionCreateParams = {
            "customer": customer.customer_id,
            "return_url": f"{base}/account",
        }
    if settings.stripe_portal_configuration_id:
        params["configuration"] = settings.stripe_portal_configuration_id
    return {"url": gateway.portal(params)["url"]}


def require_closed_billing(session: Session, user_id: str) -> None:
    """Guard account removal or promotion in its existing writer transaction."""
    active = session.scalars(
        select(StripeSubscription.id).where(
            StripeSubscription.user_id == user_id,
            StripeSubscription.status.not_in(CLOSED),
        )
    ).first()
    pending = session.scalars(
        select(StripeCheckout.id).where(
            StripeCheckout.user_id == user_id,
            StripeCheckout.status.in_(["pending", "open"]),
        )
    ).first()
    if active or pending:
        raise BillingError(
            "Cancel Stripe subscriptions and resolve pending checkouts before deleting or promoting this account",
            code="BILLING_ACTIVE",
        )


def checkout_state(engine: Engine, user_id: str, session_id: str) -> dict:
    with Session(engine) as session:
        order = session.scalars(
            select(StripeCheckout).where(
                StripeCheckout.user_id == user_id,
                StripeCheckout.session_id == session_id,
            )
        ).first()
        if order is None:
            raise BillingError("No such checkout", status=404, code="NOT_FOUND")
        return {"status": order.status}


def _id(value: Any) -> str | None:
    return value.get("id") if isinstance(value, dict) else value


def _receipt(session: Session, key: str) -> bool:
    if session.get(StripeReceipt, key):
        return False
    session.add(StripeReceipt(id=key))
    return True


def _order(session: Session, obj: Any) -> StripeCheckout | None:
    order = session.get(
        StripeCheckout, (obj.get("metadata") or {}).get("checkout_id", "")
    )
    if order is None:
        return None  # Another app can share the same Stripe account.
    if order.customer_id != _id(obj.get("customer")) or order.user_id != (
        obj.get("metadata") or {}
    ).get("user_id"):
        raise BillingError("Payment ownership does not match")
    return order


def _ledger(
    session: Session,
    order: StripeCheckout,
    period_id: str,
    kind: str,
    amount: int = 0,
    credit: int = 0,
    source: str = "",
) -> None:
    session.add(
        QuotaLedgerEntry(
            user_id=order.user_id,
            period_id=period_id,
            kind=kind,
            amount_micros=amount,
            credit_micros=credit,
            reason=f"Stripe {source}",
            snapshot_json=json.dumps({"checkout_id": order.id, "source": source}),
        )
    )


def _revoke(
    session: Session,
    binding: StripeSubscription,
    order: StripeCheckout,
    now: datetime,
    source: str,
) -> None:
    member = session.get(MemberSubscription, order.user_id)
    if member is None or member.status != "ACTIVE" or member.tier_id != binding.tier_id:
        return
    account, period, _ = _ensure_in_session(session, order.user_id, now)
    if member.status != "ACTIVE":
        return  # Expiry already closed the term and granted a free period.
    member.status = "REVOKED"
    period.closed_at = now
    tier = session.get(QuotaTier, "FREE")
    assert tier is not None
    account.tier_id, account.anchor_at, account.quota_override_micros = (
        "FREE",
        now,
        None,
    )
    period = _new_period(session, account, tier, now)
    _ledger(session, order, period.id, "SUBSCRIPTION_REVOKED", source=source)


def _bind(session: Session, obj: Any, order: StripeCheckout) -> StripeSubscription:
    binding = session.get(StripeSubscription, obj["id"])
    if order.mode != "subscription" or not order.tier_id:
        raise BillingError("Unexpected subscription purchase")
    items = obj.get("items", {}).get("data", [])
    if (
        len(items) != 1
        or _id(items[0].get("price")) != order.price_id
        or items[0].get("quantity") != 1
    ):
        raise BillingError(
            "Subscription plan changed; operator reconciliation is required"
        )
    if binding is None:
        binding = StripeSubscription(
            id=obj["id"],
            user_id=order.user_id,
            checkout_id=order.id,
            tier_id=order.tier_id,
            status=obj["status"],
            created_at=datetime.fromtimestamp(
                obj.get("created", int(datetime.now(UTC).timestamp())), UTC
            ),
        )
        session.add(binding)
        session.flush()
    if binding.checkout_id != order.id:
        raise BillingError("Subscription ownership changed")
    return binding


def _grant_invoice(
    session: Session, invoice: Any, sub: Any, now: datetime, event_created: int
) -> None:
    order = _order(session, sub)
    if order is None or _id(invoice.get("customer")) != order.customer_id:
        return
    binding = _bind(session, sub, order)
    if session.get(StripeReceipt, f"invoice:{invoice['id']}") is not None:
        return
    if (
        binding.status == "canceled"
        or (binding.status in TERMINAL and binding.state_event_created > event_created)
        or sub.get("status") in TERMINAL
        or invoice.get("billing_reason")
        not in {"subscription_create", "subscription_cycle"}
    ):
        return
    if invoice.get("status") != "paid" or sub.get("status") != "active":
        # Roll back both receipts so Stripe can retry the same event after its
        # invoice/subscription reads converge. A 200 would discard that retry.
        raise BillingError(
            "Paid invoice state is not ready; retry delivery",
            status=503,
            code="BILLING_STATE_PENDING",
        )
    lines = invoice.get("lines", {})
    if lines.get("has_more"):
        raise BillingError("Subscription invoice needs reconciliation")
    matches = [
        line
        for line in lines.get("data", [])
        if _id(
            line.get("price")
            or line.get("pricing", {}).get("price_details", {}).get("price")
        )
        == order.price_id
        and not (
            line.get("proration")
            or line.get("parent", {})
            .get("subscription_item_details", {})
            .get("proration")
        )
    ]
    if len(matches) != 1 or matches[0].get("quantity") != 1:
        raise BillingError("Subscription invoice does not match its purchase")
    start, end = (
        datetime.fromtimestamp(matches[0]["period"][key], UTC)
        for key in ("start", "end")
    )
    if end <= start or start > now:
        raise BillingError("Invalid paid invoice period")
    if binding.paid_through and end <= _aware(binding.paid_through):
        return
    _receipt(session, f"invoice:{invoice['id']}")
    binding.paid_through = end
    binding.status = sub["status"]
    binding.cancel_at_period_end = bool(sub.get("cancel_at_period_end"))
    order.status = "fulfilled"
    if end <= now:
        return  # Late historical payment never grants a fresh cycle today.
    member = session.get(MemberSubscription, order.user_id)
    active = (
        member is not None
        and member.status == "ACTIVE"
        and member.tier_id == order.tier_id
        and _aware(member.expires_at) >= start
    )
    if active:
        assert member is not None
        member.expires_at = end
    account, period, _ = _ensure_in_session(session, order.user_id, now)
    tier = session.get(QuotaTier, order.tier_id)
    if tier is None:
        raise BillingError("Paid tier is missing")
    if not active:
        if member is None:
            member = MemberSubscription(user_id=order.user_id)
            session.add(member)
        member.tier_id, member.starts_at, member.expires_at, member.status = (
            tier.id,
            start,
            end,
            "ACTIVE",
        )
        session.info.setdefault("subscription_terms", {})[order.user_id] = member
        period.closed_at = now
        account.tier_id, account.anchor_at, account.quota_override_micros = (
            tier.id,
            start,
            None,
        )
        period = _new_period(session, account, tier, start)
    period.ends_at = end
    _ledger(
        session,
        order,
        period.id,
        "SUBSCRIPTION_RENEWED" if active else "SUBSCRIPTION_ACTIVATED",
        source=invoice["id"],
    )


def _apply_subscription_event(
    session: Session, event: Any, sub: Any, invoice: Any, moment: datetime
) -> None:
    kind = event["type"]
    order = _order(session, sub)
    if order is not None and session.get(User, order.user_id) is not None:
        binding = _bind(session, sub, order)
        if kind.startswith("customer.subscription."):
            if (
                event["created"] >= binding.state_event_created
                and binding.status != "canceled"
            ):
                binding.status = sub["status"]
                binding.cancel_at_period_end = bool(sub.get("cancel_at_period_end"))
                binding.state_event_created = event["created"]
                if binding.status in TERMINAL:
                    _revoke(session, binding, order, moment, event["id"])
            if binding.status in CLOSED and order.status != "fulfilled":
                order.status = "expired"
                order.checkout_url = None
        elif invoice is not None:
            _grant_invoice(session, invoice, sub, moment, event["created"])


def _apply_checkout_event(session: Session, obj: Any, moment: datetime) -> None:
    order = _order(session, obj)
    if order is not None and session.get(User, order.user_id) is not None:
        if order.session_id not in {None, obj["id"]} or obj.get("mode") != order.mode:
            raise BillingError("Checkout identity does not match")
        order.session_id = obj["id"]
        if obj.get("status") == "expired" and order.status != "fulfilled":
            order.status = "expired"
        if (
            order.mode == "payment"
            and obj.get("payment_status") == "paid"
            and _receipt(session, f"checkout:{obj['id']}")
        ):
            if (
                obj.get("currency") != "usd"
                or obj.get("amount_total") != order.amount_cents
            ):
                raise BillingError("Paid amount does not match the purchase")
            account, period, _ = _ensure_in_session(session, order.user_id, moment)
            account.credit_balance_micros += order.credit_micros
            order.status, order.payment_intent_id = (
                "fulfilled",
                _id(obj.get("payment_intent")),
            )
            _ledger(
                session,
                order,
                period.id,
                "CREDIT_PURCHASE",
                order.credit_micros,
                order.credit_micros,
                obj["id"],
            )


def _apply_charge_event(
    session: Session, event: Any, obj: Any, intent: Any, moment: datetime
) -> None:
    kind = event["type"]
    # Refunds are cumulative. If purchased funds were already consumed,
    # suspend shared-key access for operator review instead of creating
    # a negative credit balance (which the allowance ledger forbids).
    order = _order(session, intent) if intent else None
    if order is not None and order.status != "fulfilled":
        raise BillingError("Payment fulfillment is pending; retry this adjustment")
    if order and order.status == "fulfilled":
        user = session.get(User, order.user_id)
        if user:
            account, period, _ = _ensure_in_session(session, order.user_id, moment)
            if kind == "charge.dispute.created" and _receipt(
                session, f"dispute:{obj['id']}"
            ):
                user.shared_key_access = False
                _ledger(
                    session,
                    order,
                    period.id,
                    "PAYMENT_DISPUTED",
                    source=obj["id"],
                )
            elif kind == "charge.refunded":
                if (
                    obj.get("currency") != "usd"
                    or obj.get("amount") != order.amount_cents
                ):
                    raise BillingError("Refund amount does not match its purchase")
                total = (
                    order.credit_micros * obj["amount_refunded"] // order.amount_cents
                )
                delta = max(0, total - order.refunded_micros)
                removed = min(delta, account.credit_balance_micros)
                account.credit_balance_micros -= removed
                order.refunded_micros = max(order.refunded_micros, total)
                if removed < delta:
                    user.shared_key_access = False
                if delta:
                    _ledger(
                        session,
                        order,
                        period.id,
                        "CREDIT_REFUND",
                        -delta,
                        -removed,
                        obj["id"],
                    )


def process_event(
    engine: Engine, event: Any, gateway: StripeGateway, *, now: datetime | None = None
) -> None:
    moment = now or datetime.now(UTC)
    kind, obj = event["type"], event["data"]["object"]
    # Retrieve current state rather than trusting event delivery order.
    invoice, sub, intent = None, None, None
    if kind == "invoice.paid":
        invoice = gateway.invoice(obj["id"])
        subscription_id = _id(
            invoice.get("subscription")
            or (invoice.get("parent") or {})
            .get("subscription_details", {})
            .get("subscription")
        )
        if subscription_id:
            sub = gateway.subscription(subscription_id)
    elif kind in {
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.created",
    }:
        sub = gateway.subscription(obj["id"])
    elif kind in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.expired",
    }:
        obj = gateway.checkout_status(obj["id"])
    elif kind in {"charge.refunded", "charge.dispute.created"} and obj.get(
        "payment_intent"
    ):
        intent_id = _id(obj["payment_intent"])
        if intent_id is None:
            raise BillingError("Payment intent identity is missing")
        intent = gateway.payment_intent(intent_id)
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        if not _receipt(session, f"event:{event['id']}"):
            return
        if sub is not None:
            _apply_subscription_event(session, event, sub, invoice, moment)
        elif kind.startswith("checkout.session."):
            _apply_checkout_event(session, obj, moment)
        elif kind in {"charge.refunded", "charge.dispute.created"}:
            _apply_charge_event(session, event, obj, intent, moment)
        session.commit()
