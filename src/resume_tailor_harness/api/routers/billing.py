"""Authenticated purchase adapters and a separately signature-guarded webhook."""

import asyncio
from collections.abc import Callable
from contextlib import closing
from typing import TypeVar

import stripe
from fastapi import APIRouter, Request

from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.schemas.billing import (
    BillingCatalog,
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    BillingCheckoutState,
    BillingPortalResponse,
    BillingWebhookResponse,
)
from resume_tailor_harness.tenancy.context import require_context
from resume_tailor_harness.tenancy import payments

router = APIRouter(prefix="/account/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/billing", tags=["billing"])
T = TypeVar("T")


def _call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except payments.BillingError as exc:
        raise ApiException(exc.status, exc.code, str(exc)) from exc
    except stripe.StripeError as exc:
        raise ApiException(
            502,
            "BILLING_PROVIDER_UNAVAILABLE",
            "Stripe is temporarily unavailable. Please try again.",
        ) from exc


def _gateway(request: Request) -> closing[payments.StripeGateway]:
    # Always use process settings; tenant-owned secrets cannot configure billing.
    settings = request.app.state.settings
    if not payments.billing_enabled(settings, request.app.state.app_mode):
        raise ApiException(404, "BILLING_DISABLED", "Payments are not enabled")
    return closing(_call(lambda: payments.StripeGateway(settings)))


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") != payments.billing_origin(
        request.app.state.settings
    ):
        raise ApiException(
            403, "BILLING_ORIGIN_INVALID", "Use the application to start a purchase"
        )


@router.get("")
def catalog(request: Request) -> BillingCatalog:
    if not payments.billing_enabled(
        request.app.state.settings, request.app.state.app_mode
    ):
        return BillingCatalog(enabled=False)
    with _gateway(request) as gateway:
        return BillingCatalog.model_validate(
            _call(
                lambda: payments.billing_catalog(
                    request.app.state.system_engine,
                    request.app.state.settings,
                    require_context().user_id,
                    gateway,
                )
            )
        )


@router.post("/checkout")
def checkout(body: BillingCheckoutRequest, request: Request) -> BillingCheckoutResponse:
    def create():
        with _gateway(request) as gateway:
            _check_origin(request)
            return payments.create_checkout(
                request.app.state.system_engine,
                request.app.state.settings,
                require_context().user_id,
                body.price_id,
                body.idempotency_key,
                gateway,
            )

    return BillingCheckoutResponse.model_validate(_call(create))


@router.get("/checkout/{session_id}")
def checkout_status(session_id: str, request: Request) -> BillingCheckoutState:
    def read():
        with _gateway(request):
            return payments.checkout_state(
                request.app.state.system_engine, require_context().user_id, session_id
            )

    return BillingCheckoutState.model_validate(_call(read))


@router.post("/portal")
def portal(request: Request) -> BillingPortalResponse:
    def create():
        with _gateway(request) as gateway:
            _check_origin(request)
            return payments.create_portal(
                request.app.state.system_engine,
                request.app.state.settings,
                require_context().user_id,
                gateway,
            )

    return BillingPortalResponse.model_validate(_call(create))


@webhook_router.post("/stripe/webhook")
async def webhook(request: Request) -> BillingWebhookResponse:
    with _gateway(request) as gateway:
        return await _receive_webhook(request, gateway)


async def _receive_webhook(
    request: Request, gateway: payments.StripeGateway
) -> BillingWebhookResponse:
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 1_048_576:
            raise ApiException(413, "WEBHOOK_TOO_LARGE", "Webhook body is too large")
    settings = request.app.state.settings
    try:
        event = stripe.Webhook.construct_event(
            bytes(payload),
            request.headers.get("stripe-signature", ""),
            settings.stripe_webhook_secret,
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise ApiException(
            400, "WEBHOOK_SIGNATURE_INVALID", "Invalid Stripe webhook signature"
        ) from exc
    if bool(event.get("livemode")) != settings.stripe_secret_key.startswith(
        ("sk_live_", "rk_live_")
    ):
        raise ApiException(
            400,
            "WEBHOOK_MODE_INVALID",
            "Stripe event mode does not match this deployment",
        )
    await asyncio.to_thread(
        _call,
        lambda: payments.process_event(request.app.state.system_engine, event, gateway),
    )
    return BillingWebhookResponse()
