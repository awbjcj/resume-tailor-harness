# Stripe billing for hosted deployments

Members can buy durable credits and subscribe from **Account → Plans and
credits**. Stripe hosts Checkout and the customer portal; card details never
reach this application. The backend is Python/FastAPI on Railway, so the Vercel
payments skill is adapted to this deployment rather than installing a second
Next.js backend. Billing is disabled by default and always unavailable in local
mode. Administrator accounts are quota exempt and cannot buy member plans.

## Configure the deployed service

1. In **Admin → Cost quotas**, configure a paid tier's allowance and cycle.
   The existing `SUBSCRIBER` tier has a monthly $20 shared-cost allowance by
   default; its selling price is your independent business choice.
2. Create active **USD**, fixed, per-unit Stripe prices. Credit prices must be
   one-time. Plan prices must recur weekly or monthly with an interval count
   matching the application's tier. Usage-based, yearly, tiered, transformed
   quantity and zero-price offers are rejected. This integration uses quantity
   one and card payments, and disables Adaptive Pricing to keep checkout in USD.
3. Configure the following service environment variables (JSON values without
   surrounding shell quotes when entered in Railway's variable editor):

   ```dotenv
   STRIPE_ENABLED=true
   STRIPE_SECRET_KEY=<Stripe secret key>
   STRIPE_WEBHOOK_SECRET=<endpoint signing secret>
   APP_BASE_URL=https://your-app.example
   STRIPE_CREDIT_PRICES={"price_yourCreditPrice":10000000}
   STRIPE_SUBSCRIPTION_PRICES={"price_yourMonthlyPrice":"SUBSCRIBER"}
   STRIPE_PORTAL_CONFIGURATION_ID=<optional portal configuration ID>
   COST_QUOTA_ENFORCEMENT=enforce
   ```

   `STRIPE_CREDIT_PRICES` maps allowed Stripe price IDs to integer USD micro-units
   of credit: `10000000` grants $10 in durable credits. Stripe owns the selling
   price displayed in the UI. `STRIPE_SUBSCRIPTION_PRICES` maps recurring price
   IDs to existing application tier IDs. An ID must appear in exactly one map.
   These settings are deployment-owned and never read from tenant overlays.
   Hosted Checkout requires no publishable key or browser Stripe SDK.

4. Create a Stripe webhook endpoint at
   `https://your-app.example/api/billing/stripe/webhook`. Set its event API
   version to **2026-02-25.clover**, matching the pinned Python SDK integration.
   Subscribe to:

   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `checkout.session.expired`
   - `invoice.paid`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `charge.refunded`
   - `charge.dispute.created`

   Copy this endpoint's signing secret into `STRIPE_WEBHOOK_SECRET`. Test and
   live keys, prices, endpoint secrets and events must belong to the same mode.

5. Enable the Stripe customer portal for card updates, invoice history and
   cancellation **at the end of the billing period**. Disable subscription
   switching, quantity edits, trials, promotion codes and prorations. Those
   changes need a separate application entitlement policy; an unexpected
   subscription price change is rejected for operator reconciliation. If using
   a custom portal configuration, set its ID above. Confirm the dashboard's
   default portal configuration when the optional ID is omitted.
6. Back up the data volume. Land the changes on `dev` and promote `dev` to
   `main` through the existing PR workflow; Railway deploys `main`. Startup
   creates four additive system tables (`stripe_customers`, `stripe_checkouts`,
   `stripe_subscriptions`, `stripe_receipts`) while retaining existing balances
   and subscription history.

## Accounting and delivery

Checkout accepts only a configured price ID and a purchase retry key; user,
customer, quantity, credit amount, plan and return URLs are resolved server-side.
The customer portal is likewise bound to the authenticated member. Pending
subscription checkout and active subscriptions block a second subscription.
Credit and tier snapshots are persisted before starting Checkout. In-flight
credit purchases retain their promised credit even if deployment mappings change.
After a lost response, retries reuse the original purchase. If its creation
window has closed, the backend first looks up the customer's matching Stripe
session: an open session resumes, a completed session waits for fulfillment,
and an expired or never-created session releases the reservation for a new
purchase. Changing a retry key alone cannot create a second subscription.

Only a signed webhook can fulfill a payment. The success URL merely polls the
member's persisted checkout state and refreshes usage after fulfillment; visiting
or editing it grants nothing. Unpaid checkout sessions grant no credit.
`invoice.paid` retrieves the latest invoice and subscription, and grants only
the invoice's actual paid period for an active subscription. Initial and renewal
invoices are handled independently of Checkout event delivery order. Old paid
invoices cannot shorten a later term or reactivate a canceled subscription. A
failed renewal adds no allowance: access expires at the previously paid end.
Scheduled cancellation keeps access until that date; immediate termination
returns the member to FREE while preserving durable credits.

Event and payment-object receipts commit in the same SQLite `BEGIN IMMEDIATE`
transaction as the financial effect. Duplicate deliveries, separate event IDs
for one purchase, concurrent handlers and service restarts do not grant twice.
Failures roll back receipts too, allowing Stripe's delivery retry to recover.
Operationally, inspect failed endpoint deliveries in Stripe and replay them
after correcting configuration or database availability. Do not acknowledge a
failed delivery manually before reconciling its entitlement.

Credit refunds remove the cumulative proportional credit once, using the
original purchase snapshot. If refunded credit has already been spent, or a
credit purchase is disputed, shared-key access is suspended for operator review;
BYOK continues under its existing policy. The ledger records the adjustment,
and a consumed-credit refund may require recovering a shortfall before an
administrator restores access. Dispute resolution and refunds of subscription
invoices require operator reconciliation; these do not automatically restore
credits or infer a new subscription term. Cancel the Stripe subscription and
revoke or adjust the application term as appropriate. Do not use manual
subscription grants as a substitute for collecting a Stripe invoice.

## Verification before enabling live purchases

Use Stripe test mode and a dedicated member:

1. Purchase a top-up, then verify one `CREDIT_PURCHASE` ledger entry and the
   expected credit. Replay its webhook and verify the balance stays unchanged.
2. Subscribe and verify the tier, first allowance grant and paid-through date.
   A Checkout return before invoice processing must show payment pending.
3. Generate a renewal through Stripe's subscription testing tools; verify the
   next paid term, then fail a renewal and verify expiry without a new allowance.
4. Update a card and schedule cancellation through the portal; verify the paid
   term remains available until expiry and purchased credits survive.
5. Test a credit refund and webhook retry. Review failures in Stripe's endpoint
   delivery log, and confirm a service restart preserves payment deduplication.

Offline tests cover these ledger and authentication boundaries with a fake
Stripe transport, signed HTTP webhook requests, a file-backed SQLite database,
concurrent deliveries and database reopening. A separate offline check exercises
the real Python SDK's synchronous requests, serialization and session pagination.
They do not verify your Stripe
account, portal configuration, tax policy or live charge processing. Configure
those and complete the test-mode checkout above before enabling live keys.

Official references: [Checkout fulfillment](https://docs.stripe.com/payments/checkout/fulfill-orders),
[subscription webhooks](https://docs.stripe.com/billing/subscriptions/webhooks),
[Stripe Python SDK](https://github.com/stripe/stripe-python).
