---
repo_url: https://github.com/awbjcj/resume-tailor-harness
repo_name: resume-tailor-harness
role: sole author
generated_at: 2026-08-30
---

# Résumé Tailor Harness

Résumé Tailor Harness is a job-search application that keeps generated documents tied to a candidate's evidence and leaves irreversible decisions with the user.

## Summary

Models can draft, reframe, and critique. They cannot be the final authority for content that reaches a document. The harness enforces that rule in three ways:

- Fact-lock turns a candidate's history into a closed-schema evidence profile. It checks every generated claim within the application and rejects claims that cannot cite a fact ID before an LLM reviewer is ever paid.
- Skill-concentrated tailoring gives each task agent one SHA-256-verified local `SKILL.md` procedure. A root-confined registry resolves that procedure to an identified, persisted, tamper-evident artifact.
- Tool loops are read-only. Deterministic services make changes only after user approval.

The application supports multi-source job discovery, fit scoring, a reviewer-panel tailoring loop, fact-locked cover letters, Typst PDF rendering, mock interviews, profile coaching, cited employer research, H-1B sponsorship evidence, and an application-event timeline with analytics and calendar export. It is available as a Typer CLI, a FastAPI and React web application, and a hosted multi-user service with per-user workspaces. The repository is under active development and maintained by its sole human author.

Role: sole author (2,059 of 2,117 commits across two author identities; 58 bot commits, `git shortlog -sne HEAD`)
Repository: https://github.com/awbjcj/resume-tailor-harness
Timeline: 2026-06 to present (`git log --reverse --format=%as`; `git log -1 --format=%as`)

## Tech stack and evidence

- Python: 437 backend modules under `src/resume_tailor_harness/`; the project requires Python 3.13 or newer in `pyproject.toml`.
- TypeScript: the React application and generated API client under `web/src/` and `contracts/ts/`.
- SQL: grouped, filtered, and paged persistence queries in `src/resume_tailor_harness/tracking/board_query.py`, `src/resume_tailor_harness/tracking/timeline_pivot.py`, and `src/resume_tailor_harness/tenancy/`.
- FastAPI: 48 router modules under `src/resume_tailor_harness/api/routers/` expose the web and integration APIs.
- Pydantic: closed extraction schemas, agent output contracts, API contracts, and settings validation under `src/resume_tailor_harness/models/`, `src/resume_tailor_harness/api/schemas/`, and `src/resume_tailor_harness/config.py`.
- SQLModel: domain tables and session-backed services in `src/resume_tailor_harness/tracking/tables.py`, `src/resume_tailor_harness/tenancy/`, and `src/resume_tailor_harness/services/`.
- SQLite: WAL-mode workspace databases and a separate hosted system database configured by `src/resume_tailor_harness/db.py` and `src/resume_tailor_harness/tenancy/system_db.py`.
- Agno: model-agent execution is isolated behind `src/resume_tailor_harness/llm_runner.py::AgentRunner` and task-specific `agents.py` modules.
- Agent harness design: the skill registry, agent-family boundary, deterministic gate set, verdict constructor, and read-only tool-loop rule live in `src/resume_tailor_harness/career_skills/registry.py`, `src/resume_tailor_harness/tailor/verdict.py`, `src/resume_tailor_harness/tailor/workflow.py`, and `CONTEXT.md`.
- Prompt engineering: least-privilege reviewer inputs, untrusted-content delimiting, and reviewer-identity validation are implemented in `src/resume_tailor_harness/tailor/panel.py` and `src/resume_tailor_harness/tailor/prompt_blocks.py`.
- LLM evaluation: a judge, calibration set, metrics, and reporting for tailoring and cover-letter quality live under `evals/`.
- Anthropic API: bare model identifiers route through the provider seam in `src/resume_tailor_harness/llm_routing.py` and `src/resume_tailor_harness/llm_runner.py`.
- OpenAI API: `openai:` models, embeddings, transcription, and speech route through `src/resume_tailor_harness/llm_routing.py` and `src/resume_tailor_harness/llm_runner.py`.
- Google Gemini API: `gemini:` models route through `src/resume_tailor_harness/llm_routing.py` and `src/resume_tailor_harness/llm_runner.py`.
- DeepSeek API: `deepseek:` models route through `src/resume_tailor_harness/llm_routing.py` and `src/resume_tailor_harness/llm_runner.py`.
- Model Context Protocol: a prefixed read-only H-1B toolset is confined to `src/resume_tailor_harness/h1b/mcp.py` and the sponsorship agents in `src/resume_tailor_harness/h1b/service.py`, as recorded by ADR 0011.
- Server-Sent Events: resumable run and conversational streams are implemented in `src/resume_tailor_harness/api/routers/runs.py` and `src/resume_tailor_harness/sessions/stream.py`.
- React: 406 `.tsx` modules under `web/src/` implement the browser application.
- Vite: frontend development and production builds are defined in `web/package.json` and `web/vite.config.ts`.
- TanStack Query: API cache and mutation orchestration throughout `web/src/features/`.
- i18next: English and Simplified Chinese runtime localization in `web/src/i18n/`.
- Tailwind CSS: design tokens and utility styling configured by `web/src/index.css` and the Vite plugin.
- Typer: the command-line surface begins in `src/resume_tailor_harness/cli.py`.
- Typst: resume and cover-letter PDF rendering uses `templates/*.typ` and `src/resume_tailor_harness/render/`.
- Playwright: browser-backed connectors and browser regression coverage live in `src/resume_tailor_harness/discovery/scraper/`, `src/resume_tailor_harness/discovery/connectors/tesla.py`, and `web/e2e/`.
- httpx: connector HTTP, provider-adjacent calls, and the guarded outbound gateway use `httpx` under `src/resume_tailor_harness/discovery/connectors/` and `src/resume_tailor_harness/security/outbound.py`.
- Gmail API: per-user inbox reads and draft creation are implemented under `src/resume_tailor_harness/gmail/` and `src/resume_tailor_harness/api/routers/gmail.py`.
- OpenAPI: the committed backend contract and generated TypeScript client live in `contracts/openapi.json` and `contracts/ts/api.ts`.
- API design: typed REST resources and a generated client share the contract in `src/resume_tailor_harness/api/schemas/`, `src/resume_tailor_harness/api/routers/`, and `contracts/`.
- Multi-tenant architecture: hosted requests, runs, storage, databases, and settings are scoped through `src/resume_tailor_harness/tenancy/`.
- asyncio: LLM and connector fan-out is bounded in `src/resume_tailor_harness/concurrency.py`, `src/resume_tailor_harness/llm_runner.py`, and `src/resume_tailor_harness/discovery/connectors/runner.py`.
- Schema design: closed profile facts, application events, API envelopes, and agent outputs use explicit models under `src/resume_tailor_harness/models/` and `src/resume_tailor_harness/api/schemas/`.
- Security engineering: the threat model, guarded egress, archive validation, authentication, and tenant storage controls live in `docs/resume-tailor-harness-threat-model.md`, `src/resume_tailor_harness/security/`, and `src/resume_tailor_harness/tenancy/storage.py`.
- pytest: Python tests live under `tests/` and `evals/`.
- Vitest: React unit and integration tests are configured in `web/package.json` and colocated under `web/src/`.
- Ruff: the Python lint contract is declared in `pyproject.toml`.
- GitHub Actions: CI workflows are checked in under `.github/workflows/`.
- Railway: the single-service deployment, persistent-volume custody, and production settings are documented in `Dockerfile`, `railway.json`, and `docs/deploy-railway.md`.

## Architecture

- Fact-locked generation combines closed Pydantic extraction schemas with three in-process deterministic gates: provenance, skill naming, and numeric evidence. Their names are reserved so a user-configured reviewer cannot shadow a gate. A single verdict constructor handles every gate and reviewer critique: `src/resume_tailor_harness/tailor/verdict.py`, `src/resume_tailor_harness/tailor/review_config.py`, `src/resume_tailor_harness/tailor/provenance.py`, and `src/resume_tailor_harness/profile/project_extractor.py`.
- A root-confined, SHA-256-verified registry assigns each skilled task agent one approved procedure. Models do not choose a path. A symlinked or altered entry disables that capability, and the resolved `SkillRef` is persisted with each affected artifact and turn: `src/resume_tailor_harness/career_skills/registry.py`, `src/resume_tailor_harness/career_skills/models.py`, and `skills-lock.json`.
- The review loop manages cost in code. Deterministic gates run before the paid reviewer panel, so issues reach the reviser in the same round. A provenance-only failure receives a free retry outside the `max_rounds` quality budget. Revisions start from the best gate-clean round, and a scored regression ends the loop early: `src/resume_tailor_harness/tailor/workflow.py`.
- Gate reviewers receive only the profile facts cited by a draft. Advisory reviewers receive no raw profile. The system marks every third-party job description as untrusted content, validates the claimed reviewer identity, and requires a merged advisory panel to cover its configured roster: `src/resume_tailor_harness/tailor/panel.py` and `src/resume_tailor_harness/tailor/prompt_blocks.py`.
- Source Scout, Profile Coach, sponsorship research, and Career Lab use read-only tool loops. Their proposals, draft notes, and candidate sources are re-verified outside the loop. Deterministic services write approved changes, and Career Lab output remains draft-only: `src/resume_tailor_harness/career_lab/`, `src/resume_tailor_harness/discovery/`, `src/resume_tailor_harness/h1b/service.py`, and ADR 0011.
- A provider-neutral Agno substrate turns provider-prefixed IDs into models with lazily imported SDKs. Three cost tiers can mix providers. A durable event log supports resumable Server-Sent Events, cooperative cancellation, idempotent terminal run history, and shared React chat primitives: `src/resume_tailor_harness/llm_routing.py`, `src/resume_tailor_harness/llm_runner.py`, `src/resume_tailor_harness/sessions/stream.py`, and `src/resume_tailor_harness/services/run_completions.py`.
- Hosted users receive a request-scoped workspace context, separate SQLite databases, and tenant-confined artifact resolution. Requests, background runs, and CLI paths use one custody model. A DNS-rebinding-resistant httpx gateway validates every redirect and pins the validated address: `src/resume_tailor_harness/tenancy/context.py`, `src/resume_tailor_harness/tenancy/storage.py`, `src/resume_tailor_harness/security/outbound.py`, ADR 0003, and ADR 0008.
- Thirteen ATS-specific company adapters use table-driven detection and per-URL failure isolation. A canonical SQLModel application-event dataset powers the cross-job grid, wide and lossless CSV exports, calendar downloads, funnel analytics, and offer comparisons: `src/resume_tailor_harness/discovery/connectors/companies.py`, `src/resume_tailor_harness/discovery/connectors/registry.py`, `src/resume_tailor_harness/tracking/timeline_pivot.py`, and `src/resume_tailor_harness/api/routers/analytics.py`.

## Measured repository facts

- 3,411 Python test functions across 454 files (`grep -rhE '^\s*(async )?def test_' tests evals`; `grep -rlE '^\s*(async )?def test_' tests evals`).
- 76,403 physical lines of Python across 437 modules under `src/resume_tailor_harness/` (`find src/resume_tailor_harness -name '*.py'`).
- 35 hash-verified career skills across 8 agent families. Each is pinned to a reviewed upstream ref and SHA-256 digest (`skills-lock.json`; `src/resume_tailor_harness/career_skills/models.py::AgentFamily`).
- 48 FastAPI router modules and 406 React `.tsx` modules (`ls src/resume_tailor_harness/api/routers/*.py`, excluding `__init__.py`; `find web/src -name '*.tsx'`).
- 2,117 commits from 2026-06-08 through 2026-08-30. Of those, 2,059 are attributed to the same human across two identities and 58 to bots (`git rev-list --count HEAD`; `git shortlog -sne HEAD`).
- 18 connector kinds, including 13 ATS-specific adapters plus company-URL, recipe-scrape, Adzuna, RemoteOK, and LinkedIn source families (`src/resume_tailor_harness/discovery/connectors/companies.py` and `src/resume_tailor_harness/discovery/connectors/registry.py`).
- 13 accepted architecture decisions covering deduplication, custody, tenancy, agent write boundaries, filtering, security, quotas, MCP isolation, and application-status invariants (`docs/adr/README.md`).

## Skills demonstrated

Languages: Python, TypeScript, SQL
Frameworks: FastAPI, Pydantic, SQLModel, Agno, React, Vite, Typer
Databases: SQLite
AI and APIs: Agent harness design, prompt engineering, LLM evaluation, Anthropic API, OpenAI API, Google Gemini API, DeepSeek API, Model Context Protocol, Gmail API
Frontend: TanStack Query, i18next, Tailwind CSS, Server-Sent Events
Testing: pytest, Vitest, Playwright
Architecture: API design, multi-tenant architecture, asyncio, schema design, security engineering
Tooling: httpx, OpenAPI, Typst, Ruff, GitHub Actions, Railway
