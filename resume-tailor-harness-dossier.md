---
repo_url: https://github.com/awbjcj/resume-tailor-harness
repo_name: resume-agent
role: sole author
generated_at: 2026-10-02
source_revision: c102d6acd497cb9ed39073d5635e7f1f2435b445
---

# Project: Résumé Tailor Harness — Fact-Locked Job-Search Application

## Summary

A job-search application for candidates who need generated résumés and cover letters grounded in source evidence. Closed profile schemas and deterministic provenance, skill-name, and numeric-evidence gates constrain drafting before paid review. The application combines job acquisition, fit scoring, reviewer-panel tailoring, profile coaching, interviews, employer research, and application tracking through a browser interface and command-line surface. Recent implementation adds browser-free posting acquisition with verified recovery, source cooldowns, and provider Responses-transport regression coverage. The repository is actively maintained by its sole human author.

Role: sole author (2,182 of 2,285 repository commits across the owner’s Git identities, `git shortlog -sne c102d6acd497cb9ed39073d5635e7f1f2435b445`; preserved upstream/contributor and automation history is excluded from the owner count)
Repository: https://github.com/awbjcj/resume-tailor-harness
Timeline: 2026-06 – present (`git log --reverse --format=%as`)

## Tech stack (evidence-backed)

- Python — backend under `src/resume_tailor_harness/`.
- TypeScript — browser application and API contracts in `web/src/` and `contracts/ts/`.
- FastAPI — routers and schemas under `src/resume_tailor_harness/api/`.
- Pydantic — closed extraction and output schemas under `src/resume_tailor_harness/models/` and `src/resume_tailor_harness/profile/`.
- SQLModel — tracking and tenancy tables under `src/resume_tailor_harness/`.
- SQLite — workspace and system databases in `src/resume_tailor_harness/db.py` and `src/resume_tailor_harness/tenancy/system_db.py`.
- Agno — agent runner in `src/resume_tailor_harness/llm_runner.py`.
- OpenAI API — provider routing and transport in `src/resume_tailor_harness/llm_runner.py`.
- Anthropic API — provider models in `src/resume_tailor_harness/llm_routing.py`.
- Google Gemini — provider models in `src/resume_tailor_harness/llm_routing.py`.
- DeepSeek — provider models in `src/resume_tailor_harness/llm_routing.py`.
- React — browser components under `web/src/`.
- TanStack Query — browser API caching under `web/src/features/`.
- i18next — localization in `web/src/i18n/`.
- Typer — CLI in `src/resume_tailor_harness/cli.py`.
- Typst — PDF templates and renderer in `templates/` and `src/resume_tailor_harness/render/`.
- httpx — guarded HTTP transport in `src/resume_tailor_harness/security/outbound.py`.
- pytest — backend tests under `tests/` and `evals/`.
- Vitest — browser tests configured in `web/package.json`.
- Playwright — browser connectors and E2E checks under `web/e2e/` and `src/resume_tailor_harness/discovery/`.

## Architecture highlights

- Enforced source-grounded résumé generation through closed extraction schemas and deterministic review gates before paid reviewer calls (`src/resume_tailor_harness/profile/project_extractor.py`, `src/resume_tailor_harness/tailor/verdict.py`, `src/resume_tailor_harness/tailor/workflow.py`).
- Bound task agents to root-confined, hash-verified skill procedures and persisted the resolved skill identity with artifacts (`src/resume_tailor_harness/career_skills/registry.py`, `skills-lock.json`).
- Added browser-free job acquisition and verified recovery with retained posting provenance (`src/resume_tailor_harness/discovery/url_ingest/public_readers.py`, `src/resume_tailor_harness/discovery/url_ingest/recovery.py`, `tests/url_ingest/test_recovery.py`; `d7c4d0ee`).
- Applied source cooldowns to repeated acquisition failures through `src/resume_tailor_harness/security/source_cooldown.py` and `tests/test_source_cooldown.py`.
- Isolated hosted users through request-scoped workspace contexts, separate databases, and tenant-confined artifacts (`src/resume_tailor_harness/tenancy/context.py`, `src/resume_tailor_harness/tenancy/storage.py`, `src/resume_tailor_harness/tenancy/system_db.py`).
- Centralized provider model construction and guarded Responses transport compatibility in `src/resume_tailor_harness/llm_runner.py` and `tests/test_responses_transport.py` (`dc29f9b4`).
- Validated outbound addresses and redirects through one guarded HTTP gateway (`src/resume_tailor_harness/security/outbound.py`).
- Persisted resumable conversational events and application timelines for browser and CLI workflows (`src/resume_tailor_harness/sessions/stream.py`, `src/resume_tailor_harness/tracking/timeline_pivot.py`).

## Quantified outcomes

- Counted 3,611 declared Python test functions in 479 tracked files with test definitions; this is a static count, not a test-pass or coverage result (`git grep -E '^\s*(async\s+)?def\s+test_' c102d6acd497cb9ed39073d5635e7f1f2435b445 -- .`, restricted to `test_*.py` / `*_test.py` paths).
- Counted 464 tracked Python source modules under `src/resume_tailor_harness/` (`git ls-tree -r --name-only c102d6acd497cb9ed39073d5635e7f1f2435b445 -- src/resume_tailor_harness`, filtered to `.py`).
- Recorded 2,285 repository commits at source revision `c102d6ac` (`git rev-list --count c102d6acd497cb9ed39073d5635e7f1f2435b445`).
- None evidenced for production latency, uptime, business impact, or benchmarked model quality; no such outcome is claimed.

## Skills demonstrated

Languages: Python, TypeScript
Frameworks: FastAPI, Pydantic, SQLModel, Agno, React, TanStack Query, i18next, Typer
Databases: SQLite
AI and APIs: OpenAI API, Anthropic API, Google Gemini, DeepSeek
Testing: pytest, Vitest, Playwright
Tooling: Typst, httpx
