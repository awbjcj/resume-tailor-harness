# Hosted subscription and credit lifecycle

The quota console manages finite member subscriptions using the existing tier
catalog. This is an operator-managed entitlement system: it does not collect
payments or claim that an invoice was paid. Record the external invoice or
business reason when granting access.

## Operator workflow

1. In **Admin → Cost quotas**, configure the paid tier's cycle and USD allowance.
2. Open **Manage** for the member, choose **Activate subscription**, select the
   plan and number of cycles, and enter the reason. Activation clears any old
   allowance override and grants the first cycle's allowance.
3. Use **Renew subscription** after the next payment. An active renewal extends
   expiry from the existing end, without resetting usage or granting the same
   cycle twice. Renewal of an expired or revoked term starts a new term now.
4. Use the existing **Member balance operation → Grant credit** preview and
   commit flow for durable top-ups. Those credits survive cycle and term expiry.
5. **Revoke subscription** ends the entitlement immediately, clears its override
   and starts a free-tier period. Top-ups remain. The same transition happens
   lazily at expiry before the next balance read or billed call; no scheduler is
   required, and restarting the service does not renew a term.

Month-end renewals retain their original anchor (August 31 → September 30 →
October 31). Cycle grants, activation, renewal, expiry, revocation, usage and
operator adjustments appear in the member's admin ledger. Members see the
subscription state and term end alongside spend and remaining credit.

Existing manually assigned tiers retain their recurring behavior until an
operator activates a finite subscription. The older **Assign tier** action is
an explicit administrative override: it revokes an active finite term and
starts an indefinitely recurring tier. It is not a payment renewal action.

## Funding and settlement

Deployment-owned Sub2API credentials consume the member's allowance and then
durable credits, just like other platform credentials. The upstream gateway's
flat-rate subscription is separate from the member's entitlement. Direct BYOK
calls remain exempt; administrator calls remain exempt from member quotas and
count toward the platform cap. Subscription routing still selects the gateway
key and endpoint together and never falls back to a direct API key.

All amounts use integer USD micro-units and the existing effective rate cards.
These are application quota charges, not a reconciliation of upstream invoices.
Usage, component prices, receipt and balance deduction commit in one SQLite
writer transaction. Agno response run IDs deduplicate settlement per tenant;
conflicting metrics under the same ID fail visibly. Responses without an ID
(including current direct audio adapters) are distinct invocations and cannot
be deduplicated across replays. A settlement write failure rolls back the whole
transaction and raises an operator-visible failure; it is not silently treated
as successful telemetry. There is no external payment webhook or billing retry
queue in this implementation.

Enforced calls re-read authoritative eligibility so another request's top-up,
revocation or consumption is visible immediately. Already admitted concurrent
calls can still overshoot the remaining allowance; the full overage is recorded
and later calls are blocked, as in ADR-0010. This does not reserve an estimated
maximum cost before generation.

A shared agent holds its selected credential through usage settlement. A
funding change waits until preceding calls settle and rechecks eligibility
before applying the new key, preventing shared calls from being mislabeled as
BYOK while a sibling changes credentials.

## Rollout

Back up the deployed data volume first. Startup creates three additive tables
(`member_subscriptions`, `subscription_operations`, `usage_receipts`); existing
quota accounts, pricing and history are retained. Historical gateway calls are
not retroactively billed. Previously created periods do not receive fabricated
historical grant entries; subsequent cycle grants are recorded.

Hosted mode now defaults to `COST_QUOTA_ENFORCEMENT=enforce`. An explicit
`shadow` environment value still wins, including after a settings refresh;
operators upgrading a shadow deployment must set it to `enforce` to enable
credit-based access control. Check exact rate coverage for the configured
models before that switch. Local mode retains its existing default.

Changes must land on `dev`, then be promoted through the normal `dev` → `main`
PR before Railway deploys them. Verify activation, one priced gateway call,
the resulting allowance/credit ledger split, duplicate grant retry and exhausted
balance rejection using a dedicated test member after deployment.

## Reference

The implementation was compared with the local `D:/Fun/sub2api` checkout
at commit `2bfd93a6b`:
`backend/internal/service/subscription_service.go` (finite terms, active renewal
and expired-term restart) and `backend/internal/repository/usage_billing_repo.go`
(transactional effects and request deduplication). It adapts those invariants to
this project's SQLite ownership and recurring-allowance model.
