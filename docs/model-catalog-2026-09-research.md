# Model catalog refresh research — 2026-09-09

## Scope and decision

This note records the user-requested provider refresh against first-party API
documentation and a first-party DeepSeek customer pricing notice. The latter
arrived after the initial public-doc review and changes the V4 Pro route's
effective price, but it does not publish a new API slug or a new configuration
surface.

| Requested name | Verified provider API identifier | Catalog identifier | Recommendation |
| --- | --- | --- | --- |
| GPT Astra | `gpt-6-astra` | `openai:gpt-6-astra` | Add. The official name is **GPT-6 Astra**, not `gpt-astra` or `gpt-6-astra-pro`. |
| Gemini 3.8 | `gemini-3.8-flash` | `gemini:gemini-3.8-flash` | Add. It is GA; Google lists its release date as 2026-09-02. |
| DeepSeek V4.1 Flash | `deepseek-v4-pro` (temporary V4.1 Flash route) | `deepseek:deepseek-v4-pro` | Retain the documented API ID, label it as the V4.1 Flash route, and effective-date the announced price. Do not add an invented `deepseek-v4.1-*` ID. |

OpenAI documents GPT-6 Astra as API-available and directs Responses callers to
set `model` to `gpt-6-astra`. [Model page](https://developers.openai.com/api/docs/models/gpt-6-astra) · [model guidance](https://developers.openai.com/api/docs/guides/latest-model)

Google documents `gemini-3.8-flash` as GA, and its release/deprecation table
records 2026-09-02 as its release date. [Gemini 3.8 model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) · [release table](https://ai.google.dev/gemini-api/docs/deprecations)

DeepSeek's public model list still documents `deepseek-v4-pro` as an API model
identifier, and its changelog says clients obtain the latest V4 Pro version by
setting `model='deepseek-v4-pro'`. The newer customer notice says requests to
that Pro model are temporarily routed to V4.1 Flash, so the supported ID—not a
new guessed V4.1 slug—is the catalog route to update. [List Models](https://api-docs.deepseek.com/api/list-models/) · [DeepSeek change log](https://api-docs.deepseek.com/updates/)[^v41-pricing-notice]

## Published standard API rates

All prices below are USD per million tokens. They are the published Standard
rates appropriate to this project's shared-key accounting; Batch, Flex, Fast,
data-residency uplifts, storage, and other modality-specific prices should not
silently replace them.

### OpenAI: GPT-6 Astra

| Input-context band | Input | Cached input | Cache write | Output |
| --- | ---: | ---: | ---: | ---: |
| At most 272,000 input tokens | $10.00 | $1.00 | $12.50 | $50.00 |
| More than 272,000 input tokens | $20.00 | $2.00 | $25.00 | $75.00 |

The long-context band applies to the full request. Standard Web Search is
$10 per 1,000 calls, with search-content tokens billed at the selected model's
rates. [OpenAI pricing](https://developers.openai.com/api/docs/pricing) · [Astra model specification](https://developers.openai.com/api/docs/models/gpt-6-astra)

For an exact ledger, seed two effective-dated/context-band rows for the model
instead of treating its long-context premium as a flat rate. The existing
`LlmRate` shape can represent the split with a zero-to-272,000 row and a
272,001-and-up row.

### Google: Gemini 3.8 Flash

| Effective period | Input | Cached input | Output, including thinking |
| --- | ---: | ---: | ---: |
| 2026-09-02 through 2026-12-31 | $0.75 | $0.075 | $3.75 |
| From 2027-01-01 | $1.50 | $0.15 | $7.50 |

The paid tier also lists Google Search grounding at 5,000 included requests per
month shared by Gemini 3.x, then $14 per 1,000 requests. The project cannot
infer the account-level included allowance from an individual request, so the
existing $14-per-unit metering convention remains the conservative choice.
[Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)

### DeepSeek: published V4 family

DeepSeek's official model-and-pricing page currently names exactly these public
V4 API identifiers: `deepseek-v4-flash`, `deepseek-v4-pro`, and
`deepseek-v4-flash-vision-exp`. The latter is explicitly experimental, but it
has the same published text rates as V4 Flash.

| Model | Period | Input cache miss | Input cache hit | Output |
| --- | --- | ---: | ---: | ---: |
| `deepseek-v4-flash` | Off-peak | $0.22 | $0.007 | $0.66 |
| `deepseek-v4-flash` | Peak | $0.44 | $0.014 | $1.32 |
| `deepseek-v4-pro` | Off-peak | $0.66 | $0.022 | $1.98 |
| `deepseek-v4-pro` | Peak | $1.32 | $0.044 | $3.96 |
| `deepseek-v4-flash-vision-exp` | Off-peak | $0.22 | $0.007 | $0.66 |
| `deepseek-v4-flash-vision-exp` | Peak | $0.44 | $0.014 | $1.32 |

DeepSeek defines peak as 01:00–04:00 and 06:00–10:00 UTC, Monday through
Friday, and off-peak for all other times. [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing/)

### DeepSeek V4.1 Flash via `deepseek-v4-pro`

From **2026-09-10T04:00:00Z**, the first-party customer notice supersedes the
then-published V4 Pro price for requests made through `deepseek-v4-pro`: until
V4.1 Pro launches, DeepSeek will route those requests to V4.1 Flash and bill
them at the V4.1 Flash rate. The existing public pricing page still shows the
older V4 Pro values, so it is evidence of the supported ID and peak schedule,
not the post-cutover price.[^v41-pricing-notice]

| Catalog/API ID | Period | Input cache miss | Input cache hit | Output |
| --- | --- | ---: | ---: | ---: |
| `deepseek-v4-pro` — V4.1 Flash route | Off-peak | $0.15 | $0.003 | $0.60 |
| `deepseek-v4-pro` — V4.1 Flash route | Peak | $0.30 | $0.006 | $1.20 |

No first-party source currently publishes `deepseek-v4.1-flash`,
`deepseek-v4.1-pro`, or another V4.1-specific API identifier. Do not create a
separate catalog entry or rate key for one. The documented `GET /models`
endpoint defines returned `id` values as the strings used in API endpoints; its
current example includes `deepseek-v4-pro`. [List Models](https://api-docs.deepseek.com/api/list-models/)[^v41-pricing-notice]

## Thinking and Responses compatibility

| Model | Verified control | Valid curated choices | Important integration fact |
| --- | --- | --- | --- |
| GPT-6 Astra | Responses `reasoning: {"effort": ...}` | `low`, `medium`, `high`, `xhigh`, `max` | Do **not** expose `none` or `minimal`: `none` returns HTTP 400. Astra supports prompt caching and native Web Search in the Responses API. |
| Gemini 3.8 Flash | `thinking_level` / `thinkingLevel` | `low`, `medium`, `high` | `medium` is the default. `minimal` is an error, so do not inherit that value from Gemini 3.5/3.6. |
| DeepSeek V4 Flash and V4 Pro (including the temporary V4.1 Flash route) | Responses `reasoning: {"effort": ...}` | `none`, `low`, `high`, `max` | `none` disables thinking. The provider maps `medium` and `xhigh` to `high`; the customer notice names no V4.1-specific control change, so retain the documented V4 Pro behavior. |

Sources: [OpenAI Astra model specification](https://developers.openai.com/api/docs/models/gpt-6-astra) · [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) · [OpenAI Astra migration guidance](https://developers.openai.com/api/docs/guides/latest-model) · [Gemini thinking controls](https://ai.google.dev/gemini-api/docs/generate-content/thinking) · [DeepSeek thinking controls](https://api-docs.deepseek.com/guides/thinking_mode/)

The project already routes OpenAI through Responses and uses provider-native
Web Search. Astra's official model page marks Web Search as supported under
Responses, and its migration guide states that prompt caching is supported.
No special provider branch is therefore indicated for the model catalog entry.

## DeepSeek V4.1 Flash: customer-announced routing window

The customer notice is a release/pricing announcement, not a new public API
specification. It establishes three facts: V4.1 Flash is planned for release
around 2026-09-10 Beijing time; V4 Pro requests are routed to it until V4.1 Pro
is available; and the preceding V4.1 Flash rate card takes effect at
2026-09-10T04:00:00Z.[^v41-pricing-notice] It does **not** provide a V4.1 API
identifier, context/output limit, modality, concurrency value, or thinking
control. Those facts must not be inferred from a name or copied from a future
version without a later DeepSeek API-doc update.

The evidence-backed catalog action is consequently precise: retain
`deepseek:deepseek-v4-pro` as the selectable API ID, relabel it **DeepSeek
V4.1 Flash (via V4 Pro API)** for the routing window, keep the documented
DeepSeek V4 response/thinking integration unchanged, and add only the two
effective-dated rate rows above. Do not add `deepseek:deepseek-v4.1-flash` or
any other direct V4.1 identifier.

## Repository mapping for the implementation owner

- `src/resume_tailor_harness/llm_runner.py` owns `MODEL_CATALOG`; provider
  prefixes belong there, and its lowest declared OpenAI effort becomes the
  non-reasoning floor. Astra therefore needs `low` as its floor, while Gemini
  3.8 needs no `minimal` entry.
- `src/resume_tailor_harness/tenancy/costs.py` owns effective-dated `LlmRate`
  seed data. Add Astra's short/long Standard rows at its release date and
  Gemini's promotional and scheduled 2027 reversion rows at its release date.
- Keep `deepseek-v4-pro` as the API ID, but present it as **DeepSeek V4.1 Flash
  (via V4 Pro API)** during the vendor-announced route. Close its older V4 Pro
  rate rows at 2026-09-10T04:00:00Z and seed the announced V4.1 Flash
  peak/off-peak rows at that instant. Do not create a `deepseek-v4.1-*` model
  key until DeepSeek publishes one.
- The settings UI consumes the API catalog, so adding entries and rates at the
  backend seam is the relevant project update; tests should cover exact IDs,
  reasoning vocabularies, model construction, and priced rate lookup.

[^v41-pricing-notice]: DeepSeek, “Announcement on DeepSeek V4.1 Flash API Pricing,” first-party customer notice received 2026-09-09. Private correspondence; no public URL. It states the temporary V4 Pro-to-V4.1-Flash routing, the 2026-09-10T04:00:00Z effective time, and the V4.1 Flash rates.
