# Agno 3.1.3 upgrade

Checked on October 15, 2026: [PyPI](https://pypi.org/project/agno/3.1.3/)
lists 3.1.3 as the latest stable release. The project previously locked 3.1.1.
The requirement is now `agno[mcp]>=3.1.3,<4`, with an exact resolution in
`uv.lock`. Provider SDKs retain their existing constraints.

## Improvements adopted

The [3.1.2 release](https://github.com/agno-agi/agno/releases/tag/v3.1.2)
includes improvements that apply directly to the existing native agents:

| Improvement | Project integration |
| --- | --- |
| GPT-6 recognition in OpenAI Responses | `build_model` and `build_search_equipped` inherit encrypted reasoning requests and replay from Agno. Read-only tool follow-ups retain reasoning context while `store=False` keeps provider response storage disabled. |
| Responses cache-write metrics | Agno now populates `cache_write_tokens` when the provider reports it. Existing usage settlement and agent traces consume this field, including totals across tool-loop requests. Absence of provider data remains zero. |
| `Annotated` tool argument schemas | Agno unwraps annotated types when generating JSON schemas. Read-only Python tools retain their argument types without project-specific schema rewriting. |

The existing schema normalization, DeepSeek reasoning handling, Gemini schema
compatibility, retry budget, and deterministic fact-lock gates remain necessary.
These releases do not replace those application contracts.

## Features assessed but not enabled

| Feature | Fit with this project |
| --- | --- |
| Native conversation compaction and searchable archives | Agno compacts its managed session history. This application stores sessions itself and supplies an explicit per-turn prompt snapshot; toggling `compaction=True` would not compact that snapshot. Career Lab also requires complete committed history. Adoption needs a deliberate session design with tenant ownership, preserved source facts, and user controls. |
| Configurable follow-up generation | The coach, interview, and Career Lab formatters already own validated next-turn actions. A separate follow-up model call would add cost and create suggestions outside those contracts. |
| HyDE query transformation | Requires an Agno Knowledge retrieval pipeline. Current discovery, sponsorship evidence, and profile retrieval use application-owned connectors and evidence rules. |
| External Claude/Codex agent sessions, replay, cancellation, metrics, media and structured output | Most of the [3.1.3 release](https://github.com/agno-agi/agno/releases/tag/v3.1.3) targets these separate SDK adapters. The project uses native Agno agents behind its provider, spend, tenant, session, and read-only tool boundaries. Replacing that execution model requires explicit permission and lifecycle integration. |
| AgentOS browser policy, database fixes, new providers and toolkits | The application owns its FastAPI/auth layer and storage. It does not use the affected AgentOS, MongoDB or JsonDb components, and no new external service is required for this upgrade. |

## Regression coverage

`tests/test_agno_integration.py` runs the actual Agno agent loop and OpenAI SDK
against `httpx.MockTransport`, using the project's model builder and runner:

- GPT-5 and GPT-6, synchronous, asynchronous, and streamed execution.
- An annotated read-only tool, followed by a validated `ResumeContent` result.
- Encrypted reasoning replay before the tool call, with no response-id chaining.
- Cache-read, cache-write, and reasoning token aggregation across both requests.
- Operational traces that retain usage counts without recording opaque reasoning.

The existing provider transport matrix additionally covers direct and subscription
routes, native and callable search, all catalogued Responses models, and the
project's resume schema. The full offline suite covers application behavior;
offline checks do not establish live provider availability or measure model quality.

## Verification results

Verified locally on October 15, 2026:

| Check | Result |
| --- | --- |
| Existing focused compatibility tests on Agno 3.1.1 | 298 passed |
| New integration cases on Agno 3.1.1 | All 6 failed at the expected missing GPT-6 encrypted-content request or cache-write metric assertion |
| Focused compatibility tests on Agno 3.1.3 | 304 passed, including all 6 new integration cases |
| Full Python suite (`python -m pytest tests -o addopts='' -q`) | 4,219 passed, 5 skipped |
| Python lint (`ruff check src tests evals sdk/python/src`) | Passed |
| Repository-wide Pyright with the project virtualenv | 972 files; 0 errors, 0 warnings, 0 information diagnostics |
| Focused tests after narrowing the optional streamed response | 201 passed |
| Lock consistency and installed dependencies (`uv lock --check`, `uv pip check`) | Passed; only Agno changed version |
| Frontend lint and unit tests | Passed; 905 tests in 207 files |
| Production build, including TypeScript and translation catalog checks | Passed |
| Playwright shortlist smoke (`e2e/smoke.spec.ts`) | 2 passed |

The browser smoke initially exposed two missing fixture routes:
`/api/run-completions?surface=notifications` and `/api/board-views?board=shortlist`.
Their requests escaped to an absent local backend and produced 502 console
errors. The smoke fixture now supplies empty results for both; production
frontend behavior is unchanged.

Live checks also passed for `claude-haiku-5-5`, `openai:gpt-6.1-sol`,
`gemini:gemini-3.8-flash`, and `deepseek:deepseek-flash`, using the configured
provider routes. Each ran the project's model builder and runner, called one
read-only synthetic fixture tool exactly once, and returned a validated Pydantic
object containing its exact result. No resume or profile data was sent.
These are bounded connectivity/tool/schema checks, not a comparative model-quality
evaluation or a claim that every external service was exercised live.

Non-failing output included Pydantic/SQLite warnings in Python tests, jsdom canvas
notices in frontend tests, and Vite configuration/chunk-size warnings.
