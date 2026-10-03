"""Payment evidence with signed HTTP deliveries and a real file-backed ledger."""

import copy
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import stripe
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from resume_tailor_harness.api.auth import hash_password
from resume_tailor_harness.config import Settings
from resume_tailor_harness.tenancy import payments
from resume_tailor_harness.tenancy.quotas import quota_snapshot, charge_shared_cost
from resume_tailor_harness.tenancy.system_db import (
    MemberSubscription,
    QuotaLedgerEntry,
    QuotaTier,
    StripeCheckout,
    StripeReceipt,
    StripeSubscription,
    User,
    make_system_engine,
)

USER = "alice0000000"
NOW = datetime.now(UTC).replace(microsecond=0)


class FakeStripe:
    def __init__(self):
        self.prices = {
            "price_credit": {
                "id": "price_credit",
                "active": True,
                "currency": "usd",
                "unit_amount": 1000,
                "billing_scheme": "per_unit",
                "recurring": None,
            },
            "price_plan": {
                "id": "price_plan",
                "active": True,
                "currency": "usd",
                "unit_amount": 2000,
                "billing_scheme": "per_unit",
                "recurring": {
                    "interval": "month",
                    "interval_count": 1,
                    "usage_type": "licensed",
                },
            },
        }
        self.checkouts, self.subscriptions, self.invoices = {}, {}, {}
        self.checkout_calls, self.portal_calls = [], []
        self.close_calls = 0

    def close(self):
        self.close_calls += 1

    def price(self, key):
        return copy.deepcopy(self.prices[key])

    def customer(self, user_id, email):
        return {"id": f"cus_{user_id}"}

    def checkout(self, params, key):
        if params.get("managed_payments", {}).get("enabled") is not False:
            raise stripe.InvalidRequestError(
                "Managed Payments controls payment_method_types",
                param="payment_method_types",
            )
        self.checkout_calls.append((copy.deepcopy(params), key))
        sid = f"cs_{params['metadata']['checkout_id']}"
        self.checkouts.setdefault(
            sid,
            {
                **copy.deepcopy(params),
                "id": sid,
                "url": f"https://checkout.stripe.com/{sid}",
                "status": "open",
                "payment_status": "unpaid",
                "amount_total": self.prices[params["line_items"][0]["price"]][
                    "unit_amount"
                ],
                "currency": "usd",
                "payment_intent": f"pi_{sid}",
            },
        )
        return copy.deepcopy(self.checkouts[sid])

    def checkout_status(self, sid):
        return copy.deepcopy(self.checkouts[sid])

    def find_checkout(self, customer_id, order_id):
        return copy.deepcopy(
            next(
                (
                    row
                    for row in self.checkouts.values()
                    if row["customer"] == customer_id
                    and row["metadata"]["checkout_id"] == order_id
                ),
                None,
            )
        )

    def subscription(self, sid):
        return copy.deepcopy(self.subscriptions[sid])

    def invoice(self, iid):
        return copy.deepcopy(self.invoices[iid])

    def portal(self, params):
        self.portal_calls.append(params)
        return {"url": "https://billing.stripe.com/portal"}

    def payment_intent(self, iid):
        checkout = next(
            row for row in self.checkouts.values() if row["payment_intent"] == iid
        )
        return {
            "id": iid,
            "customer": checkout["customer"],
            "metadata": checkout["metadata"],
        }


@pytest.fixture
def billing(mu_app, mu_client, monkeypatch):
    settings = mu_app.state.settings.model_copy(
        update={
            "stripe_enabled": True,
            "stripe_secret_key": "sk_test_fake",
            "stripe_webhook_secret": "whsec_fake",
            "app_base_url": "https://testserver",
            "stripe_credit_prices": {"price_credit": 10_000_000},
            "stripe_subscription_prices": {"price_plan": "SUBSCRIBER"},
        }
    )
    mu_app.state.settings = settings
    fake = FakeStripe()
    monkeypatch.setattr(payments, "StripeGateway", lambda _: fake)
    with Session(mu_app.state.system_engine) as session:
        session.add(
            User(
                id=USER,
                username="alice",
                role="user",
                password_hash=hash_password("member-password", iterations=1000),
            )
        )
        session.commit()
    assert (
        mu_client.post(
            "/api/auth/login",
            json={"identifier": "alice", "password": "member-password"},
        ).status_code
        == 200
    )
    return mu_app.state.system_engine, settings, fake


def checkout(client, price="price_credit", key="purchase-12345"):
    response = client.post(
        "/api/account/billing/checkout", json={"priceId": price, "idempotencyKey": key}
    )
    assert response.status_code == 200, response.text
    return response.json()["checkoutId"]


def event(kind, obj, eid="evt_test", created=1):
    return {
        "id": eid,
        "type": kind,
        "created": created,
        "livemode": False,
        "data": {"object": obj},
    }


def deliver(client, ev, secret="whsec_fake"):
    body = json.dumps(ev, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signature = hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return client.post(
        "/api/billing/stripe/webhook",
        content=body,
        headers={
            "stripe-signature": f"t={timestamp},v1={signature}",
            "content-type": "application/json",
        },
    )


def paid_subscription(
    fake,
    sid,
    start=NOW - timedelta(days=1),
    end=NOW + timedelta(days=29),
    iid="in_first",
):
    order = fake.checkouts[sid]
    fake.subscriptions["sub_test"] = {
        "id": "sub_test",
        "status": "active",
        "customer": order["customer"],
        "metadata": order["metadata"],
        "cancel_at_period_end": False,
        "items": {"data": [{"price": {"id": "price_plan"}, "quantity": 1}]},
    }
    fake.invoices[iid] = {
        "id": iid,
        "status": "paid",
        "billing_reason": "subscription_create"
        if iid == "in_first"
        else "subscription_cycle",
        "customer": order["customer"],
        "parent": {"subscription_details": {"subscription": "sub_test"}},
        "lines": {
            "has_more": False,
            "data": [
                {
                    "pricing": {"price_details": {"price": "price_plan"}},
                    "parent": {"subscription_item_details": {"proration": False}},
                    "quantity": 1,
                    "period": {
                        "start": int(start.timestamp()),
                        "end": int(end.timestamp()),
                    },
                }
            ],
        },
    }
    return event("invoice.paid", {"id": iid}, eid=f"evt_{iid}")


def test_catalog_prices_and_hosted_gate(billing, mu_app, mu_client):
    response = mu_client.get("/api/account/billing")
    assert response.status_code == 200
    offers = response.json()["offers"]
    assert offers[0]["amountCents"] == 1000
    assert offers[0]["creditMicros"] == 10_000_000
    assert offers[1]["allowanceMicros"] == 20_000_000
    mu_app.state.app_mode = "local"
    assert mu_client.get("/api/account/billing").json()["enabled"] is False
    assert (
        mu_client.post(
            "/api/account/billing/checkout",
            json={"priceId": "price_credit", "idempotencyKey": "purchase-12345"},
        ).status_code
        == 404
    )
    assert deliver(mu_client, event("unhandled", {})).status_code == 404


def test_retry_does_not_return_expired_checkout_url(billing, mu_client):
    _, _, fake = billing
    sid = checkout(mu_client)
    fake.checkouts[sid]["status"] = "expired"
    fake.checkouts[sid]["url"] = None
    response = mu_client.post(
        "/api/account/billing/checkout",
        json={"priceId": "price_credit", "idempotencyKey": "purchase-12345"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BILLING_CHECKOUT_ENDED"


@pytest.mark.parametrize("state", ["incomplete_expired", "canceled"])
def test_closed_unpaid_subscription_releases_checkout(billing, mu_client, state):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    paid_subscription(fake, sid)
    fake.checkouts[sid]["status"] = "complete"
    fake.checkouts[sid]["url"] = None
    fake.subscriptions["sub_test"]["status"] = state
    assert (
        deliver(
            mu_client, event("customer.subscription.updated", {"id": "sub_test"})
        ).status_code
        == 200
    )
    assert checkout(mu_client, "price_plan", "new-purchase") != sid
    assert quota_snapshot(engine, USER).tier_id == "FREE"


@pytest.mark.parametrize("paid", [False, True])
@pytest.mark.parametrize("action", ["delete", "promote"])
def test_account_deletion_cannot_orphan_pending_or_active_billing(
    billing, mu_client, paid, action
):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    if paid:
        payments.process_event(engine, paid_subscription(fake, sid), fake, now=NOW)
    assert (
        mu_client.post(
            "/api/auth/login",
            json={"identifier": "owner", "password": "owner-password"},
        ).status_code
        == 200
    )
    response = (
        mu_client.delete(f"/api/admin/users/{USER}?confirm=DELETE")
        if action == "delete"
        else mu_client.patch(f"/api/admin/users/{USER}", json={"role": "admin"})
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BILLING_ACTIVE"
    with Session(engine) as session:
        user = session.get(User, USER)
        assert user is not None
        assert user.role == "user"
    if paid:
        fake.subscriptions["sub_test"]["status"] = "canceled"
        assert (
            deliver(
                mu_client,
                event(
                    "customer.subscription.deleted", {"id": "sub_test"}, "evt_cancel", 2
                ),
            ).status_code
            == 200
        )
    else:
        fake.checkouts[sid]["status"] = "expired"
        assert (
            deliver(
                mu_client, event("checkout.session.expired", {"id": sid})
            ).status_code
            == 200
        )
    if action == "delete":
        assert (
            mu_client.delete(f"/api/admin/users/{USER}?confirm=DELETE").status_code
            == 200
        )
    else:
        assert (
            mu_client.patch(
                f"/api/admin/users/{USER}", json={"role": "admin"}
            ).status_code
            == 200
        )


def test_unavailable_offer_does_not_hide_existing_billing_portal(billing, mu_client):
    _, _, fake = billing
    checkout(mu_client)
    fake.prices["price_plan"]["active"] = False
    response = mu_client.get("/api/account/billing")
    assert response.status_code == 200
    assert response.json()["portalAvailable"] is True
    assert [offer["priceId"] for offer in response.json()["offers"]] == ["price_credit"]


def test_gateway_is_closed_after_success_and_provider_failure(
    billing, mu_client, monkeypatch
):
    _, _, fake = billing
    assert mu_client.get("/api/account/billing").status_code == 200
    assert fake.close_calls == 1
    monkeypatch.setattr(
        fake,
        "portal",
        lambda _: (_ for _ in ()).throw(stripe.APIConnectionError("timeout")),
    )
    checkout(mu_client)
    assert mu_client.post("/api/account/billing/portal").status_code == 502
    assert fake.close_calls == 3
    assert deliver(mu_client, event("unhandled", {}), secret="wrong").status_code == 400
    assert fake.close_calls == 4
    assert deliver(mu_client, event("unhandled", {})).status_code == 200
    assert fake.close_calls == 5


def test_checkout_pinned_owner_amount_return_urls_and_idempotency(billing, mu_client):
    engine, settings, fake = billing
    sid = checkout(mu_client)
    assert checkout(mu_client) == sid
    assert len(fake.checkout_calls) == 1
    params, key = fake.checkout_calls[0]
    assert params["customer"] == f"cus_{USER}"
    assert params["line_items"] == [{"price": "price_credit", "quantity": 1}]
    assert params["currency"] == "usd"
    assert params["adaptive_pricing"] == {"enabled": False}
    assert params["success_url"].startswith("https://testserver/account?")
    assert params["payment_intent_data"]["metadata"]["user_id"] == USER
    assert quota_snapshot(engine, USER).credit_balance_micros == 0
    conflict = mu_client.post(
        "/api/account/billing/checkout",
        json={"priceId": "price_plan", "idempotencyKey": "purchase-12345"},
    )
    assert conflict.status_code == 409
    assert key.startswith("resume-checkout-")


@pytest.mark.parametrize(
    "change",
    [
        {"active": False},
        {"currency": "eur"},
        {"unit_amount": None},
        {"unit_amount": 0},
        {"billing_scheme": "tiered"},
        {"transform_quantity": {"divide_by": 5, "round": "down"}},
        {"recurring": {"interval": "month"}},
    ],
)
def test_invalid_credit_price_never_starts_checkout(billing, mu_client, change):
    _, _, fake = billing
    fake.prices["price_credit"].update(change)
    assert (
        mu_client.post(
            "/api/account/billing/checkout",
            json={"priceId": "price_credit", "idempotencyKey": "purchase-12345"},
        ).status_code
        == 503
    )
    assert not fake.checkout_calls


def test_price_allowlist_cycle_and_missing_config(billing, mu_app, mu_client):
    engine, _, fake = billing
    assert (
        mu_client.post(
            "/api/account/billing/checkout",
            json={"priceId": "price_unknown", "idempotencyKey": "purchase-12345"},
        ).status_code
        == 400
    )
    fake.prices["price_plan"]["recurring"]["interval"] = "year"
    assert [
        offer["priceId"]
        for offer in mu_client.get("/api/account/billing").json()["offers"]
    ] == ["price_credit"]
    fake.prices["price_plan"]["recurring"]["interval"] = "month"
    with Session(engine) as session:
        tier = session.get(QuotaTier, "SUBSCRIBER")
        assert tier is not None
        tier.archived_at = NOW
        session.commit()
    assert [
        offer["priceId"]
        for offer in mu_client.get("/api/account/billing").json()["offers"]
    ] == ["price_credit"]
    mu_app.state.settings.app_base_url = ""
    assert mu_client.get("/api/account/billing").status_code == 503


def test_origin_admin_auth_and_tenant_isolation(billing, mu_client):
    sid = checkout(mu_client)
    assert (
        mu_client.post(
            "/api/account/billing/portal",
            headers={"origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    assert (
        mu_client.post(
            "/api/auth/login",
            json={"identifier": "owner", "password": "owner-password"},
        ).status_code
        == 200
    )
    assert mu_client.get(f"/api/account/billing/checkout/{sid}").status_code == 404
    assert mu_client.post("/api/account/billing/portal").status_code == 403
    mu_client.cookies.clear()
    assert mu_client.get("/api/account/billing").status_code == 401
    assert (
        mu_client.post(
            "/api/account/billing/checkout",
            json={"priceId": "price_credit", "idempotencyKey": "purchase-12345"},
        ).status_code
        == 401
    )


def test_webhook_raw_signature_and_live_mode(billing, mu_client):
    assert deliver(mu_client, event("unhandled", {}), secret="wrong").status_code == 400
    ev = event("unhandled", {})
    ev["livemode"] = True
    assert deliver(mu_client, ev).status_code == 400
    assert (
        mu_client.post(
            "/api/billing/stripe/webhook", content=b"x" * 1_048_577
        ).status_code
        == 413
    )
    mu_client.cookies.clear()
    assert deliver(mu_client, event("unhandled", {})).status_code == 200


def test_unpaid_then_async_paid_duplicate_events_grant_once(billing, mu_client):
    engine, settings, fake = billing
    sid = checkout(mu_client)
    assert (
        deliver(mu_client, event("checkout.session.completed", {"id": sid})).status_code
        == 200
    )
    assert quota_snapshot(engine, USER).credit_balance_micros == 0
    fake.checkouts[sid].update(payment_status="paid", status="complete")
    settings.stripe_credit_prices["price_credit"] = (
        999_000_000  # Existing order is frozen.
    )
    ev = event("checkout.session.async_payment_succeeded", {"id": sid}, "evt_paid")
    assert deliver(mu_client, ev).status_code == 200
    assert deliver(mu_client, ev).status_code == 200
    assert deliver(mu_client, {**ev, "id": "evt_also_paid"}).status_code == 200
    assert quota_snapshot(engine, USER).credit_balance_micros == 10_000_000
    assert (
        mu_client.get(f"/api/account/billing/checkout/{sid}").json()["status"]
        == "fulfilled"
    )
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuotaLedgerEntry)
                .where(QuotaLedgerEntry.kind == "CREDIT_PURCHASE")
            )
            == 1
        )


def test_mismatched_paid_amount_rolls_back_receipt_then_retry(billing, mu_client):
    engine, _, fake = billing
    sid = checkout(mu_client)
    fake.checkouts[sid].update(payment_status="paid", amount_total=1)
    ev = event("checkout.session.completed", {"id": sid})
    assert deliver(mu_client, ev).status_code == 409
    assert quota_snapshot(engine, USER).credit_balance_micros == 0
    with Session(engine) as session:
        assert session.get(StripeReceipt, "event:evt_test") is None
    fake.checkouts[sid]["amount_total"] = 1000
    assert deliver(mu_client, ev).status_code == 200
    assert quota_snapshot(engine, USER).credit_balance_micros == 10_000_000


def test_database_failure_rolls_back_grant_and_receipts(
    billing, mu_client, monkeypatch
):
    engine, _, fake = billing
    sid = checkout(mu_client)
    fake.checkouts[sid]["payment_status"] = "paid"
    original = payments._ledger
    monkeypatch.setattr(
        payments,
        "_ledger",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk failure")),
    )
    ev = event("checkout.session.completed", {"id": sid})
    with pytest.raises(RuntimeError, match="disk failure"):
        payments.process_event(engine, ev, fake)
    monkeypatch.setattr(payments, "_ledger", original)
    assert quota_snapshot(engine, USER).credit_balance_micros == 0
    payments.process_event(engine, ev, fake)
    assert quota_snapshot(engine, USER).credit_balance_micros == 10_000_000


def test_concurrent_duplicate_webhooks_and_restart(billing, mu_client, mu_app):
    engine, _, fake = billing
    sid = checkout(mu_client)
    fake.checkouts[sid]["payment_status"] = "paid"
    ev = event("checkout.session.completed", {"id": sid})
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: payments.process_event(engine, ev, fake), range(8)))
    restarted = make_system_engine(mu_app.state.data_dir)
    try:
        payments.process_event(restarted, {**ev, "id": "evt_after_restart"}, fake)
        assert quota_snapshot(restarted, USER).credit_balance_micros == 10_000_000
    finally:
        restarted.dispose()


def test_subscription_invoice_before_checkout_renewal_preserves_usage(
    billing, mu_client
):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    ev = paid_subscription(fake, sid)
    payments.process_event(engine, ev, fake, now=NOW)
    first = quota_snapshot(engine, USER, now=NOW)
    assert first.tier_id == "SUBSCRIBER"
    assert first.subscription_expires_at == NOW + timedelta(days=29)
    charge_shared_cost(engine, USER, 2_000_000, now=NOW)
    # Payment receipt for a future extension must not reset this cycle's usage.
    invoice = fake.invoices["in_first"]
    fake.invoices["in_renew"] = {
        **copy.deepcopy(invoice),
        "id": "in_renew",
        "billing_reason": "subscription_cycle",
    }
    fake.invoices["in_renew"]["lines"]["data"][0]["period"] = {
        "start": int((NOW + timedelta(days=29)).timestamp()),
        "end": int((NOW + timedelta(days=59)).timestamp()),
    }
    # A Stripe period cannot start in the future; simulate its actual renewal date.
    payments.process_event(
        engine,
        event("invoice.paid", {"id": "in_renew"}, "evt_renew"),
        fake,
        now=NOW + timedelta(days=29),
    )
    renewed = quota_snapshot(engine, USER, now=NOW + timedelta(days=29))
    assert renewed.tier_id == "SUBSCRIBER"
    assert renewed.subscription_expires_at == NOW + timedelta(days=59)
    payments.process_event(
        engine, {**ev, "id": "evt_old_invoice"}, fake, now=NOW + timedelta(days=30)
    )
    assert quota_snapshot(
        engine, USER, now=NOW + timedelta(days=30)
    ).subscription_expires_at == NOW + timedelta(days=59)
    with Session(engine) as session:
        binding = session.get(StripeSubscription, "sub_test")
        member = session.get(MemberSubscription, USER)
        assert binding is not None
        assert member is not None
        assert binding.paid_through is not None
        assert member.status == "ACTIVE"


def test_subscription_checkout_alone_never_grants_and_blocks_duplicate(
    billing, mu_client
):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    fake.checkouts[sid].update(payment_status="paid", status="complete")
    assert (
        deliver(mu_client, event("checkout.session.completed", {"id": sid})).status_code
        == 200
    )
    assert quota_snapshot(engine, USER).tier_id == "FREE"
    assert (
        mu_client.post(
            "/api/account/billing/checkout",
            json={"priceId": "price_plan", "idempotencyKey": "different-key"},
        ).status_code
        == 409
    )


def test_subscription_cancellation_preserves_credit_and_stale_invoice_cannot_reactivate(
    billing, mu_client
):
    engine, _, fake = billing
    topup = checkout(mu_client)
    fake.checkouts[topup]["payment_status"] = "paid"
    payments.process_event(
        engine, event("checkout.session.completed", {"id": topup}), fake, now=NOW
    )
    sid = checkout(mu_client, "price_plan", "plan-purchase")
    ev = paid_subscription(fake, sid)
    payments.process_event(engine, ev, fake, now=NOW)
    fake.subscriptions["sub_test"]["cancel_at_period_end"] = True
    payments.process_event(
        engine,
        event("customer.subscription.updated", {"id": "sub_test"}, "evt_scheduled", 5),
        fake,
        now=NOW,
    )
    assert quota_snapshot(engine, USER, now=NOW).tier_id == "SUBSCRIBER"
    fake.subscriptions["sub_test"]["status"] = "canceled"
    payments.process_event(
        engine,
        event("customer.subscription.deleted", {"id": "sub_test"}, "evt_deleted", 10),
        fake,
        now=NOW,
    )
    assert quota_snapshot(engine, USER, now=NOW).tier_id == "FREE"
    assert quota_snapshot(engine, USER, now=NOW).credit_balance_micros == 10_000_000
    fake.subscriptions["sub_test"]["status"] = (
        "active"  # Simulate stale concurrent retrieval.
    )
    fake.invoices["in_first"]["lines"]["data"][0]["period"]["end"] += 10000000
    payments.process_event(
        engine, event("invoice.paid", {"id": "in_first"}, "evt_stale"), fake, now=NOW
    )
    assert quota_snapshot(engine, USER, now=NOW).tier_id == "FREE"


def test_failed_invoice_and_term_expiry(billing, mu_client):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    ev = paid_subscription(fake, sid)
    fake.invoices["in_first"]["status"] = "open"
    with pytest.raises(payments.BillingError, match="state is not ready"):
        payments.process_event(engine, ev, fake, now=NOW)
    assert quota_snapshot(engine, USER, now=NOW).tier_id == "FREE"
    fake.invoices["in_first"]["status"] = "paid"
    payments.process_event(engine, {**ev, "id": "evt_actual_paid"}, fake, now=NOW)
    payments.process_event(
        engine,
        event("invoice.payment_failed", {"id": "in_failed"}, "evt_failed"),
        fake,
        now=NOW,
    )
    assert quota_snapshot(engine, USER, now=NOW + timedelta(days=30)).tier_id == "FREE"


def test_historical_invoice_does_not_grant_now(billing, mu_client):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    ev = paid_subscription(
        fake, sid, start=NOW - timedelta(days=60), end=NOW - timedelta(days=30)
    )
    payments.process_event(engine, ev, fake, now=NOW)
    assert quota_snapshot(engine, USER, now=NOW).tier_id == "FREE"


def test_expired_checkout_allows_new_subscription_and_portal_uses_owner(
    billing, mu_client
):
    _, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    fake.checkouts[sid]["status"] = "expired"
    assert checkout(mu_client, "price_plan", "new-purchase") != sid
    assert (
        mu_client.post(
            "/api/account/billing/portal", json={"customerId": "cus_attacker"}
        ).status_code
        == 200
    )
    assert fake.portal_calls[-1]["customer"] == f"cus_{USER}"


def test_cumulative_refund_and_dispute_suspend_consumed_credit(billing, mu_client):
    engine, _, fake = billing
    sid = checkout(mu_client)
    fake.checkouts[sid]["payment_status"] = "paid"
    payments.process_event(
        engine, event("checkout.session.completed", {"id": sid}), fake, now=NOW
    )
    charge = {
        "id": "ch_test",
        "currency": "usd",
        "amount": 1000,
        "amount_refunded": 500,
        "payment_intent": f"pi_{sid}",
    }
    payments.process_event(
        engine, event("charge.refunded", charge, "evt_refund"), fake, now=NOW
    )
    payments.process_event(
        engine, event("charge.refunded", charge, "evt_refund_duplicate"), fake, now=NOW
    )
    assert quota_snapshot(engine, USER, now=NOW).credit_balance_micros == 5_000_000
    charge_shared_cost(engine, USER, 5_000_000, now=NOW)
    charge["amount_refunded"] = 1000
    payments.process_event(
        engine, event("charge.refunded", charge, "evt_full_refund"), fake, now=NOW
    )
    with Session(engine) as session:
        user = session.get(User, USER)
        assert user is not None
        assert user.shared_key_access is False
    assert quota_snapshot(engine, USER, now=NOW).credit_balance_micros == 0


def test_stripe_provider_errors_are_sanitized(billing, mu_client, monkeypatch):
    _, _, fake = billing
    monkeypatch.setattr(
        fake,
        "price",
        lambda _: (_ for _ in ()).throw(
            stripe.APIConnectionError("sk_secret_do_not_show")
        ),
    )
    response = mu_client.post(
        "/api/account/billing/checkout",
        json={"priceId": "price_credit", "idempotencyKey": "purchase-12345"},
    )
    assert response.status_code == 502
    assert "sk_secret" not in response.text


@pytest.mark.parametrize("expanded_intent", [False, True])
def test_dispute_object_is_applied_once_even_with_distinct_event_ids(
    billing, mu_client, expanded_intent
):
    engine, _, fake = billing
    sid = checkout(mu_client)
    fake.checkouts[sid]["payment_status"] = "paid"
    payments.process_event(
        engine, event("checkout.session.completed", {"id": sid}), fake
    )
    intent_id = f"pi_{sid}"
    dispute = {
        "id": "dp_test",
        "payment_intent": {"id": intent_id} if expanded_intent else intent_id,
    }
    payments.process_event(
        engine, event("charge.dispute.created", dispute, "evt_dispute"), fake
    )
    with Session(engine) as session:
        user = session.get(User, USER)
        assert user is not None
        assert user.shared_key_access is False
        user.shared_key_access = True  # operator reconciliation
        session.commit()
    payments.process_event(
        engine, event("charge.dispute.created", dispute, "evt_duplicate"), fake
    )
    with Session(engine) as session:
        user = session.get(User, USER)
        assert user is not None
        assert user.shared_key_access is True
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuotaLedgerEntry)
                .where(QuotaLedgerEntry.kind == "PAYMENT_DISPUTED")
            )
            == 1
        )


def test_adjustment_with_missing_expanded_intent_id_leaves_no_receipt(billing):
    engine, _, fake = billing
    ev = event(
        "charge.dispute.created",
        {"id": "dp_test", "payment_intent": {"object": "payment_intent"}},
    )
    with pytest.raises(
        payments.BillingError, match="Payment intent identity is missing"
    ):
        payments.process_event(engine, ev, fake)
    with Session(engine) as session:
        assert session.get(StripeReceipt, "event:" + ev["id"]) is None


def test_refund_delivered_before_fulfillment_retries_without_losing_adjustment(
    billing, mu_client
):
    engine, _, fake = billing
    sid = checkout(mu_client)
    charge = {
        "id": "ch_test",
        "currency": "usd",
        "amount": 1000,
        "amount_refunded": 1000,
        "payment_intent": f"pi_{sid}",
    }
    refund = event("charge.refunded", charge, "evt_early_refund")
    assert deliver(mu_client, refund).status_code == 409
    fake.checkouts[sid]["payment_status"] = "paid"
    assert (
        deliver(mu_client, event("checkout.session.completed", {"id": sid})).status_code
        == 200
    )
    assert deliver(mu_client, refund).status_code == 200
    assert quota_snapshot(engine, USER).credit_balance_micros == 0


def test_cancellation_at_expired_term_does_not_double_grant_free_allowance(
    billing, mu_client
):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    end = NOW + timedelta(days=29)
    payments.process_event(engine, paid_subscription(fake, sid, end=end), fake, now=NOW)
    fake.subscriptions["sub_test"]["status"] = "canceled"
    payments.process_event(
        engine,
        event("customer.subscription.deleted", {"id": "sub_test"}, "evt_end", 10),
        fake,
        now=end,
    )
    with Session(engine) as session:
        grants = session.scalars(
            select(QuotaLedgerEntry).where(QuotaLedgerEntry.kind == "ALLOWANCE_GRANT")
        ).all()
        assert len(grants) == 3  # initial free, first paid, expired free


def test_reopening_pending_subscription_resumes_same_stripe_purchase(
    billing, mu_client, monkeypatch
):
    _, _, fake = billing
    original = fake.checkout
    monkeypatch.setattr(
        fake,
        "checkout",
        lambda *_: (_ for _ in ()).throw(stripe.APIConnectionError("timeout")),
    )
    response = mu_client.post(
        "/api/account/billing/checkout",
        json={"priceId": "price_plan", "idempotencyKey": "lost-response"},
    )
    assert response.status_code == 502
    monkeypatch.setattr(fake, "checkout", original)
    sid = checkout(mu_client, "price_plan", "new-ui-key")
    assert checkout(mu_client, "price_plan", "yet-another-key") == sid
    assert len(fake.checkout_calls) == 1


def test_non_subscription_invoice_from_same_stripe_account_is_ignored(
    billing, mu_client
):
    engine, _, fake = billing
    fake.invoices["in_other"] = {"id": "in_other", "parent": None, "status": "paid"}
    assert (
        deliver(mu_client, event("invoice.paid", {"id": "in_other"})).status_code == 200
    )
    assert quota_snapshot(engine, USER).tier_id == "FREE"


@pytest.mark.parametrize("remote_state", [None, "open", "expired", "complete"])
def test_delayed_retry_recovers_lost_checkout_without_second_subscription(
    billing, mu_client, monkeypatch, remote_state
):
    engine, _, fake = billing
    original = fake.checkout

    def lose_response(params, key):
        if remote_state:
            remote = original(params, key)
            fake.checkouts[remote["id"]]["status"] = remote_state
            if remote_state != "open":
                fake.checkouts[remote["id"]]["url"] = None
        raise stripe.APIConnectionError("lost response")

    monkeypatch.setattr(fake, "checkout", lose_response)
    assert (
        mu_client.post(
            "/api/account/billing/checkout",
            json={"priceId": "price_plan", "idempotencyKey": "lost-response"},
        ).status_code
        == 502
    )
    with Session(engine) as session:
        pending = session.scalars(select(StripeCheckout)).one()
        old_id = pending.id
        pending.expires_at = datetime.now(UTC) + timedelta(minutes=10)
        session.commit()
    monkeypatch.setattr(fake, "checkout", original)
    response = mu_client.post(
        "/api/account/billing/checkout",
        json={"priceId": "price_plan", "idempotencyKey": "new-ui-key"},
    )
    if remote_state == "complete":
        assert response.status_code == 409
        assert len(fake.checkout_calls) == 1
    else:
        assert response.status_code == 200, response.text
        resumed = response.json()["checkoutId"] == f"cs_{old_id}"
        assert resumed is (remote_state == "open")
        assert len(fake.checkout_calls) == (2 if remote_state == "expired" else 1)
    assert quota_snapshot(engine, USER).tier_id == "FREE"


def test_closed_reservation_returns_new_purchase_signal(
    billing, mu_client, monkeypatch
):
    engine, _, fake = billing
    original = fake.checkout
    monkeypatch.setattr(
        fake,
        "checkout",
        lambda *_: (_ for _ in ()).throw(stripe.APIConnectionError("timeout")),
    )
    body = {"priceId": "price_credit", "idempotencyKey": "lost-response"}
    assert mu_client.post("/api/account/billing/checkout", json=body).status_code == 502
    with Session(engine) as session:
        pending = session.scalars(select(StripeCheckout)).one()
        pending.expires_at = datetime.now(UTC) + timedelta(minutes=10)
        session.commit()
    monkeypatch.setattr(fake, "checkout", original)
    response = mu_client.post("/api/account/billing/checkout", json=body)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BILLING_CHECKOUT_ENDED"
    assert len(fake.checkout_calls) == 0
    checkout(mu_client, key="new-purchase-key")


def test_overlapping_renewal_does_not_reset_spent_allowance(billing, mu_client):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    payments.process_event(engine, paid_subscription(fake, sid), fake, now=NOW)
    before = charge_shared_cost(engine, USER, 2_000_000, now=NOW)
    invoice = fake.invoices["in_first"]
    fake.invoices["in_extension"] = {
        **copy.deepcopy(invoice),
        "id": "in_extension",
        "billing_reason": "subscription_cycle",
    }
    fake.invoices["in_extension"]["lines"]["data"][0]["period"]["end"] += 86400
    payments.process_event(
        engine,
        event("invoice.paid", {"id": "in_extension"}, "evt_extension"),
        fake,
        now=NOW,
    )
    after = quota_snapshot(engine, USER, now=NOW)
    assert after.spent_micros == before.spent_micros == 2_000_000
    assert after.period_start == before.period_start


def test_real_stripe_sdk_serializes_sync_requests_and_recovers_across_pages(
    monkeypatch,
):
    requests = []

    def request(client, method, url, **kwargs):
        sent = httpx.Request(
            method, url, headers=kwargs["headers"], content=kwargs.get("data") or b""
        )
        requests.append(sent)
        path, query = (
            urlsplit(str(sent.url)).path,
            parse_qs(urlsplit(str(sent.url)).query),
        )
        if method.lower() == "get" and path == "/v1/checkout/sessions":
            second_page = "starting_after" in query
            response = {
                "object": "list",
                "url": path,
                "has_more": not second_page,
                "data": [
                    {
                        "object": "checkout.session",
                        "id": "cs_found" if second_page else "cs_other",
                        "metadata": {
                            "checkout_id": "order_test" if second_page else "other"
                        },
                    }
                ],
            }
        else:
            kind = (
                "checkout.session"
                if "/checkout/" in path
                else "billing_portal.session"
                if "/billing_portal/" in path
                else path.split("/")[2].rstrip("s")
            )
            response = {
                "object": kind,
                "id": path.split("/")[-1],
                "url": "https://checkout.stripe.com/test",
            }
        return httpx.Response(200, json=response, request=sent)

    monkeypatch.setattr(httpx.Client, "request", request)
    # BaseSettings accepts runtime options outside its generated field signature.
    settings_options: dict[str, Any] = {"_env_file": None}
    gateway = payments.StripeGateway(
        Settings(
            stripe_secret_key="sk_test_offline",
            stripe_webhook_secret="whsec_offline",
            **settings_options,
        )
    )
    assert gateway.price("price_test")["id"] == "price_test"
    gateway.customer(USER, "alice@example.com")
    checkout_params: payments._CheckoutCreateParams = {
        "mode": "payment",
        "metadata": {"checkout_id": "order_test"},
        "managed_payments": {"enabled": False},
    }
    gateway.checkout(checkout_params, "retry_test")
    gateway.checkout_status("cs_test")
    gateway.subscription("sub_test")
    gateway.invoice("in_test")
    gateway.payment_intent("pi_test")
    gateway.portal({"customer": "cus_test", "return_url": "https://testserver/account"})
    assert gateway.find_checkout("cus_test", "order_test")["id"] == "cs_found"
    assert len(requests) == 10
    assert all(
        sent.headers["Stripe-Version"] == payments.STRIPE_API_VERSION
        for sent in requests
    )
    assert requests[1].headers["Idempotency-Key"] == f"resume-customer-{USER}"
    assert requests[2].headers["Idempotency-Key"] == "retry_test"
    assert parse_qs(requests[2].content.decode())["managed_payments[enabled]"] == [
        "false"
    ]
    assert parse_qs(requests[2].content.decode())["metadata[checkout_id]"] == [
        "order_test"
    ]
    assert parse_qs(urlsplit(str(requests[-1].url)).query)["starting_after"] == [
        "cs_other"
    ]
    gateway.close()
    http_client = gateway.http_client._client
    assert http_client is not None
    assert http_client.is_closed


@pytest.mark.parametrize("stale", ["invoice", "subscription"])
def test_paid_invoice_retry_after_provider_state_converges(billing, mu_client, stale):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    ev = paid_subscription(fake, sid)
    if stale == "invoice":
        fake.invoices["in_first"]["status"] = "open"
    else:
        fake.subscriptions["sub_test"]["status"] = "past_due"
    assert deliver(mu_client, ev).status_code == 503
    with Session(engine) as session:
        assert session.get(StripeReceipt, "event:" + ev["id"]) is None
        assert session.get(StripeReceipt, "invoice:in_first") is None
    assert quota_snapshot(engine, USER).tier_id == "FREE"
    fake.invoices["in_first"]["status"] = "paid"
    fake.subscriptions["sub_test"]["status"] = "active"
    assert deliver(mu_client, ev).status_code == 200
    assert deliver(mu_client, {**ev, "id": "evt_second_delivery"}).status_code == 200
    assert quota_snapshot(engine, USER).tier_id == "SUBSCRIBER"
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuotaLedgerEntry)
                .where(QuotaLedgerEntry.kind == "SUBSCRIPTION_ACTIVATED")
            )
            == 1
        )


@pytest.mark.parametrize("price", ["price_plan", "price_credit"])
def test_disabling_sales_keeps_existing_billing_service(
    billing, mu_app, mu_client, price
):
    engine, settings, fake = billing
    sid = checkout(mu_client, price)
    if price == "price_plan":
        ev = paid_subscription(fake, sid)
    else:
        fake.checkouts[sid]["payment_status"] = "paid"
        ev = event("checkout.session.completed", {"id": sid})
    settings.stripe_enabled = False
    response = mu_client.get("/api/account/billing")
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["offers"] == []
    assert response.json()["portalAvailable"] is True
    assert mu_client.post("/api/account/billing/portal").status_code == 200
    assert (
        mu_client.post(
            "/api/account/billing/checkout",
            json={"priceId": "price_credit", "idempotencyKey": "disabled-purchase"},
        ).status_code
        == 404
    )
    assert deliver(mu_client, ev, secret="wrong").status_code == 400
    assert deliver(mu_client, ev).status_code == 200
    snapshot = quota_snapshot(engine, USER)
    if price == "price_plan":
        assert snapshot.tier_id == "SUBSCRIBER"
    else:
        assert snapshot.credit_balance_micros == 10_000_000
    assert (
        mu_client.get(f"/api/account/billing/checkout/{sid}").json()["status"]
        == "fulfilled"
    )


@pytest.mark.parametrize("state", sorted(payments.TERMINAL))
def test_paid_invoice_for_terminal_subscription_is_acknowledged(
    billing, mu_client, state
):
    engine, _, fake = billing
    sid = checkout(mu_client, "price_plan")
    ev = paid_subscription(fake, sid)
    fake.subscriptions["sub_test"]["status"] = state
    assert deliver(mu_client, ev).status_code == 200
    assert deliver(mu_client, ev).status_code == 200
    assert quota_snapshot(engine, USER).tier_id == "FREE"
    with Session(engine) as session:
        assert session.get(StripeReceipt, "event:" + ev["id"]) is not None
        assert session.get(StripeReceipt, "invoice:in_first") is None
