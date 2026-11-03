# Cost quota operations

LLM quota enforcement uses integer USD micro-units (`$1 = 1_000_000`) to keep
accounting deterministic. Token counts remain available for platform-key and
bring-your-own-key analytics. They stop controlling access when
`COST_QUOTA_ENFORCEMENT=enforce`.

## Rollout

1. Start in `shadow` mode. Every `AgentRunner` and direct transcription call
   records provider/model-specific token lines and an effective-dated rate-card
   snapshot. The legacy weighted-token guard remains active.
2. Resolve each rate-coverage warning and compare computed costs with
   provider/Agno telemetry. Then set `COST_QUOTA_ENFORCEMENT=enforce`. Shared
   calls with an unknown rate fail closed. BYOK calls remain available and are
   marked unpriced.

## Defaults and resets

- `FREE` receives `$1` every seven days from assignment.
- `SUBSCRIBER` receives `$20` monthly from assignment. Month-end assignments
  clamp without drifting (January 31 → February 28 → March 31).
- Shared platform keys default to a `$500` UTC calendar-month cap.
- Administrators, free members, and subscribers all use shared platform keys
  first. Administrator usage counts toward the platform cap; member usage also
  consumes the member's recurring allowance and credits.
- After the applicable shared allowance is exhausted, the provider call uses
  the member's workspace key when configured. Without a workspace key, the
  existing quota-exhausted error is returned before any provider request.
- Credits survive resets and tier changes. The recurring allowance is spent first.
- Resetting a current period forgives its spend, refunds credits consumed during
  that period, and preserves its anchor.

Administrators use `/admin/quotas` for tier, account, bulk operation, rate-card,
and audit views. Bulk operations require a frozen preview, reason, and
idempotency key. All-member scope includes disabled non-admin accounts.

## OpenAI Decisions endpoint (2026-11-03)

Verified against the [Decisions billing guide](https://developers.openai.com/api/docs/guides/decisions#pricing-and-availability),
[Luna model notes](https://developers.openai.com/api/docs/models/gpt-6-luna),
and [Standard pricing](https://developers.openai.com/api/docs/pricing).
The admin rate card lists `gpt-6-luna:decisions` separately from ordinary
`gpt-6-luna` generation. It is an internal rate identity for `POST /v1/decisions`,
not a provider model ID. The two rows are effective from GA on October 22.

USD per million tokens, global Standard processing:

| Full prompt input | Ordinary input | Cached read | 30m cache write | Output |
| --- | ---: | ---: | ---: | ---: |
| At most 272,000 | $0.10 | $0.01 | $0.125 | $0 |
| More than 272,000 | $0.20 | $0.02 | $0.25 | $0 |

Input totals include cache reads and writes; those tokens are subtracted once
before applying the ordinary input rate. The long band prices the full request.
For example, 10,000 input tokens including 2,000 cached reads and 1,000 writes
cost $0.000845 (845 USD micros), deducted once from shared funding. Decisions
usage retains the native model ID and `reasoning_mode=decisions`, with a receipt
pointing to this endpoint's rate snapshot and individual input/cache line items.
Both member allowances and the global cap include these costs; administrators
remain subject to the global cap.

The current Decisions request schema supports only the default 30m cache TTL.
The adapter uses the global endpoint, with no regional premium. Twelve-hour
Responses caching and ordinary Luna output pricing do not apply here. No paid
inference was used to refresh these rates. Existing installations receive the
rate rows at the next system-database initialization; prior receipts are retained.

## DeepSeek Search and Fetch

Verified 2026-10-18 against the [official pricing](https://api-docs.deepseek.com/quick_start/pricing/)
and [Search/Fetch billing rules](https://api-docs.deepseek.com/guides/search/).
Standalone Search and Fetch each cost $0.75 per 1,000 successful requests
(750 USD micros per request), independent of model and peak/off-peak token rates.
Only HTTP 200 responses with nonempty search results or fetched page content
record a billable tool unit. Empty results and failures cost zero; requesting
more results does not change the unit price.

The rate card uses separate `deepseek-search` and `deepseek-fetch` identities,
effective from this integration's 2026-10-18 refresh. Each request checks
SpendGate and settles through the existing usage ledger; shared funding consumes
the applicable quotas and BYOK retains analytics with zero quota deduction.
LLM tokens consumed while reading results remain on the selected model's token
rate, avoiding double counting. Existing model-token rates are unchanged.

DeepSeek separately documents a grace period for **server-side** Search/Fetch
tools used through DeepSeek Harness, Claude Code, and Codex: per-request billing
starts at 2026-11-01 00:00 Beijing time (2026-10-31 16:00 UTC). This app calls the
standalone endpoints and applies their published rate immediately.

## Standard model rate refresh (2026-10-23)

The built-in catalog includes updates from [OpenAI pricing](https://developers.openai.com/api/docs/pricing),
[Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing), and
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing):

- Sonnet 5.5 cache reads cost $0.10 per million tokens from October 7,
  down from $0.20. Input, cache writes, and output retain their prior prices.
- GPT-5.6 Sol/Terra/Luna and GPT-5.5/Pro have separate prompt bands at
  272,000 and 272,001 tokens. The long band charges twice the input/cache
  price and 1.5 times output. These corrections apply from October 23;
  historical catalog rows and recorded usage remain intact.
- Gemini 4 Argon is priced from its October 13 GA release at $2 input,
  $0.10 cached input, and $10 output per million tokens. From December 1,
  these become $4, $0.20, and $20. Explicit cache writes remain unpriced
  because Argon supports implicit caching only.
- The Gemini 3.5 Flash alias uses 3.6 Flash promotional rates from this
  refresh: $0.75 input, $0.075 cached input, $3.75 output per million.
  January 1, 2027 rates are $1.50/$0.15/$7.50. Existing 3.6/3.7/3.8 Flash
  promotional expiry rows remain in effect.

Rates are seeded idempotently during system-database initialization, so existing
installations receive the update on application restart. Recorded usage receipts
are not recalculated. This updates the rate catalog, not model selection defaults.

The catalog's single cache-write bucket represents the application's default
cache lifetime (OpenAI 30 minutes; Claude five minutes). It does not distinguish
OpenAI 12-hour writes or Claude one-hour writes. Those lifetimes, other service
tiers, regional premiums, and Gemini cache storage need separate metering before
using this catalog as an invoice estimate for such requests. Search rates exclude
account-level free allowances and are conservative estimates when those apply.
