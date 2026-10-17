# Provider conversation streaming

The conversation path shares one event contract for Profile Coach, Interview,
Discovery Scout, Career Lab, and the job assistant. `llm_runner.py` remains the
only model construction and invocation boundary. SpendGate continues to select
the key and endpoint together; streaming does not bypass routing or quotas.

## Endpoints and search

| Provider | Sub2API endpoint | Search in `auto` mode |
| --- | --- | --- |
| Anthropic | `/v1/messages` | Native Messages web search |
| OpenAI | `/v1/responses` | Native Responses web search |
| Gemini | `/v1beta/models/{model}:streamGenerateContent` | Native Google Search |
| DeepSeek Pro | `/v1/responses` | Native Responses web search |
| DeepSeek Flash | `/v1/responses` | Application search function |

Direct routes use the respective provider SDK defaults (DeepSeek's Responses
base is `https://api.deepseek.com`). The current sibling Sub2API router supports
these protocols; it does not expose Gemini `/interactions`. Gemini search now
uses GenerateContent, including function declarations, server tool invocations,
thought signatures, and function IDs on replay. Combining native search and
application functions requires Gemini 3 or later; older custom model IDs receive
an actionable error to select tool search mode.

DeepSeek Flash silently ignores `web_search`. The capability gate follows
[DeepSeek's Responses documentation](https://api-docs.deepseek.com/guides/responses_api/):
only `deepseek-v4-pro` selects native search. Explicit `native` on Flash fails;
`auto` uses the application's existing callable search and its existing budget.

## Lifecycle

- `provider_stream.py` preserves SDK facts that Agno otherwise drops: partial
  function arguments, hosted search activity, citations, failure/stop reasons,
  and missing terminal markers. State is scoped to one HTTP request.
- Concurrent Responses function calls are assembled by item ID. Stateless
  follow-up requests replay hosted search items alongside function calls.
  Gemini replays original content parts, including opaque thought signatures.
  Opaque replay payloads never enter browser events.
- `stream_execution.py` drives Agno's async stream from the synchronous worker.
  A bounded queue and one producer task preserve context and backpressure.
  Checkpoints run while network I/O is silent, allowing Stop before the first
  token; cancellation joins the producer and closes clients before releasing
  the spend gate. Synchronous application tools still depend on their own
  checkpoint/timeout behavior while executing. They stay on the run thread,
  preserving database Session ownership and per-turn search budgets.
- Automatic retries happen only for transient failures before any visible
  output. Mid-response failures retain the partial reply and require an explicit
  retry. Truncation and empty output cannot become a saved successful turn.
  Failed or cancelled streams settle any usage the SDK exposed before
  closure; unreported tokens are not estimated. Successful runs retain the
  existing aggregate usage settlement.
- Tool previews update a single card by call ID. Sources use validated HTTP(S)
  URLs. Terminal events settle unfinished tool cards. Reasoning is displayed
  only when the provider exposes it; enabled thinking does not guarantee a
  visible summary on every response.
  Gemini hosted calls without optional provider IDs receive display IDs;
  anonymous results match pending calls of the same type in arrival order.
- Stop waits for server confirmation while preserving output. A completion that
  wins the race is accepted. Cancellation failures remain observable and can be
  retried without losing settlement received while Stop was pending.
  SSE reconnect preserves the contiguous cursor, ignores duplicates,
  repairs gaps, and backs off from 500 ms to 8 seconds.

## Verification

`tests/test_provider_conversation_stream.py` exercises real Agno and provider
SDKs against HTTP fixtures for every route, in synchronous and cancellable
modes. Coverage includes reasoning, native search, function replay, interleaved
arguments, truncation/EOF, pre-output HTTP retries, and cancellation during
silent I/O. Browser tests cover source validation/rendering, tool snapshots,
Stop races, cancellation failure, replay, and gap recovery.

`scripts/provider_stream_smoke.py` is an opt-in paid check using synthetic
prompts and the configured SpendGate route. It requires successful web search,
a local `stream_probe` function, streamed text, and terminal completion, and
prints only event counts/timings. Run with:

```powershell
.venv/Scripts/python.exe scripts/provider_stream_smoke.py --timeout 75
```

Live direct smoke checks passed on 2026-10-16 for Claude Sonnet 5, GPT-5.6 Terra,
Gemini 3.8 Flash, and DeepSeek V4 Pro. DeepSeek Flash was separately observed to
ignore native search. No live Sub2API gateway was configured for this check;
gateway coverage is through the real SDKs with HTTP fixtures and inspection of
the current Sub2API router, not a live gateway inference claim.

Repository validation:

- Full Python suite after review fixes: 4,251 passed, 5 skipped.
- Full frontend suite after review fixes: 207 files / 913 tests passed.
- Ruff and ESLint passed; TypeScript, translation checks, and the production
  build passed. No API schema regeneration was needed: source citations extend
  the hand-written SSE contract, whose backend/frontend parity is tested.
