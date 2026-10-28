# GPT-6.1 Terra and Gemini 4 Argon

Verified October 28, 2026 using Context7 and live official documentation.

| Contract | GPT-6.1 Terra | Gemini 4 Argon |
| --- | --- | --- |
| Project ID | `openai:gpt-6.1-terra` | `gemini:gemini-4-argon` |
| Release / GA | October 26, 2026 | October 13, 2026 |
| Provider effort vocabulary | `none`, `low`, `medium`, `high`, `xhigh`, `max` | `low`, `medium`, `high` |
| Provider default effort | `medium` | `medium` |
| Project reasoning fallback | `high` | `high` |
| Project non-reasoning effort | `none` | `low`, which still permits thinking |
| Project endpoint | Responses | Generate Content |
| Context | 1,050,000 tokens | 1,048,576 shared input/thinking/output tokens |

Terra is the default mid-tier model. Explicit environment or workspace model
selections remain in effect. The Settings catalog exposes both models and their
effort choices through the existing API; no frontend-specific model list is
needed. OpenAI access is now required for the default mid tier, through a direct
key or the existing subscription route.

Terra's provider maximum output is 128,000 tokens. The project retains its
32,000/64,000 output ceilings for ordinary/reasoning OpenAI agents and stateless
encrypted reasoning replay. Function tools use Responses. No sampling overrides
are sent.

Argon uses named thinking levels without a numeric budget. The adapter sets a
32,768-token total output ceiling and a 15-minute HTTP timeout for direct and
gateway routes. It sends no sampling settings or explicit cache references.
This stays within one non-streaming Generate Content hop. Generate Content
allows 65,536 tokens per streaming hop; longer output needs continuation support.
Interactions instead allows 65,536 synchronous tokens and requires background
execution beyond that. This integration does not add long-decode continuation.

## Standard token prices

USD per million tokens, excluding tools, tax, service-tier and regional changes:

| Model / period or context | Input | Cached input | 30m cache write | Output |
| --- | ---: | ---: | ---: | ---: |
| Terra, at most 272,000 input tokens | 1.00 | 0.05 | 1.25 | 5.00 |
| Terra, more than 272,000 input tokens | 2.00 | 0.10 | 2.50 | 7.50 |
| Argon, through November 30, 2026 | 2.00 | 0.10 | Not applicable | 10.00 |
| Argon, from December 1, 2026 | 4.00 | 0.20 | Not applicable | 20.00 |

The rate seed starts Terra at release and Argon at GA, keeps historical rows,
and schedules Argon's December transition. Terra's long-context band prices
the entire request. Seed dates use UTC calendar boundaries. Argon uses implicit
caching only. Its grounding rate uses
the existing $14/1,000-query accounting convention; the shared monthly free
allowance is not separately metered here.

Generate Content's candidate and thinking token counters are separate. The
adapter normalizes their sum into billable output while retaining the thinking
detail for analytics; downstream accounting does not add it again. This also
includes separately reported tool-use prompt tokens in input. It corrects future
usage accounting for existing Gemini models. Stored usage is not repriced.

The single cache-write bucket estimates Terra's default 30-minute retention;
12-hour writes cost 2.50/M (short) or 5.00/M (long) and need lifetime-aware
metering before invoice-grade accounting. Subscription/gateway billing and
actual account model availability require separate verification.

Google also changed new paid Generate Content projects to default storage on
October 26. Existing projects retain their setting. The installed
`google-genai` 2.28.0 config has no typed `store` field; configure AI Studio
logging according to the deployment's retention policy. This change does not
claim a new SDK-level storage opt-out.

## Sources and validation

- [Terra model](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
- [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- [OpenAI release notes](https://developers.openai.com/api/docs/changelog)
- [GPT-6 migration](https://developers.openai.com/api/docs/guides/latest-model)
- [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models)
- [Argon migration](https://ai.google.dev/gemini-api/docs/latest-model)
- [Generate Content thinking and limits](https://ai.google.dev/gemini-api/docs/generate-content/thinking)
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini release notes and storage change](https://ai.google.dev/gemini-api/docs/changelog)

Validation uses offline model construction, serialized request checks, mocked
SDK transports, API catalog checks, and rate boundary/idempotency tests. It does
not establish successful paid inference, gateway forwarding, or tenant access.

Final local results:

- `pytest --ignore=tests/api`: 3,826 passed, 5 skipped.
- `pytest tests/api/test_secrets_router.py tests/api/test_admin_cost_quotas.py`:
  16 passed.
- Repository-wide Ruff and Pyright passed.
- Frontend production build and i18n catalog checks passed; generated OpenAPI
  and TypeScript schemas include the Terra default.
