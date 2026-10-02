from datetime import datetime
from typing import Literal

from pydantic import Field

from resume_tailor_harness.api.schemas.base import CamelModel


class BillingOffer(CamelModel):
    price_id: str
    name: str
    mode: Literal["payment", "subscription"]
    amount_cents: int
    currency: Literal["usd"]
    credit_micros: int | None = None
    tier_id: str | None = None
    allowance_micros: int | None = None
    interval: Literal["week", "month"] | None = None
    interval_count: int | None = None


class BillingSubscription(CamelModel):
    status: str
    cancel_at_period_end: bool
    paid_through: datetime | None = None


class BillingCatalog(CamelModel):
    enabled: bool
    offers: list[BillingOffer] = Field(default_factory=list)
    portal_available: bool = False
    subscription: BillingSubscription | None = None


class BillingCheckoutRequest(CamelModel):
    price_id: str = Field(min_length=1, max_length=255, pattern=r"^price_[a-zA-Z0-9]+$")
    idempotency_key: str = Field(
        min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$"
    )


class BillingCheckoutResponse(CamelModel):
    url: str
    checkout_id: str


class BillingPortalResponse(CamelModel):
    url: str


class BillingCheckoutState(CamelModel):
    status: Literal["pending", "open", "fulfilled", "expired"]


class BillingWebhookResponse(CamelModel):
    received: bool = True
