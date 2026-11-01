---
repo_url: https://github.com/awbjcj/resume-tailor-harness
repo_name: resume-agent
role: sole author
generated_at: 2026-10-31
---

# Project: Résumé Tailor Harness

## Summary

Résumé Tailor Harness is a job-search application for candidates who want résumés and cover letters grounded in profile evidence (`src/resume_tailor_harness/tailor/`, `src/resume_tailor_harness/cover_letter/`). It brings job discovery, fit analysis, reviewer-panel tailoring, coaching, interviews, and application tracking together in a browser interface, command-line interface, and external-agent SDK (`src/resume_tailor_harness/api/app.py`, `src/resume_tailor_harness/cli.py`, `sdk/python/`). It also analyzes recruiting email and reviews rendered résumé layouts (`src/resume_tailor_harness/services/gmail_sync.py`, `src/resume_tailor_harness/services/mailboxes.py`, `src/resume_tailor_harness/render/layout_review.py`). The project is actively maintained by its sole human author (`git shortlog -sne 429106b8`).

Role: sole author (2,382 of 2,577 reachable commits across the owner's three Git identities; automation excluded from the author count, `git shortlog -sne 429106b8`, `git rev-list --count 429106b8`)
Repository: https://github.com/awbjcj/resume-tailor-harness
Timeline: 2026-06 – present (first commit 2026-06-08, `git log --reverse --format=%as 429106b8`)

Evidence revision: `429106b88587059c97ecedf097fb1338fba07a31`. Repository counts below refer to this snapshot.

## Tech stack (evidence-backed)

- Python — backend under `src/resume_tailor_harness/`.
- TypeScript — browser application and API contracts in `web/src/` and `contracts/ts/`.
- FastAPI — routers and schemas under `src/resume_tailor_harness/api/`.
- Pydantic — extraction and output schemas under `src/resume_tailor_harness/models/` and `src/resume_tailor_harness/profile/`.
- SQLModel — tracking and tenancy tables under `src/resume_tailor_harness/`.
- SQLAlchemy — database engine pooling in `src/resume_tailor_harness/db.py` and conditional writes in `src/resume_tailor_harness/services/agent_applications.py`.
- SQLite — workspace and system databases in `src/resume_tailor_harness/db.py` and `src/resume_tailor_harness/tenancy/system_db.py`.
- Agno — agent runner in `src/resume_tailor_harness/llm_runner.py`.
- OpenAI API — provider routing and transport in `src/resume_tailor_harness/llm_runner.py`.
- Anthropic API — provider models in `src/resume_tailor_harness/llm_routing.py`.
- Google Gemini — provider models in `src/resume_tailor_harness/llm_routing.py`.
- DeepSeek — provider models in `src/resume_tailor_harness/llm_routing.py`.
- AG-UI — authenticated run-event projection in `src/resume_tailor_harness/api/runs/agui.py` and browser events in `web/src/`.
- Stripe — checkout, signed webhooks, credits, and subscription ledger integration in `src/resume_tailor_harness/tenancy/payments.py`.
- Gmail API — mailbox history and backfill reads in `src/resume_tailor_harness/gmail/scan.py`.
- Microsoft Graph — mailbox reads in `src/resume_tailor_harness/mailboxes/microsoft.py`.
- IMAP — mailbox reads in `src/resume_tailor_harness/mailboxes/imap.py`.
- React — browser components under `web/src/`.
- TanStack Query — browser API caching under `web/src/features/`.
- i18next — localization in `web/src/i18n/`.
- Typer — command-line interface in `src/resume_tailor_harness/cli.py`.
- Typst — PDF templates and renderer in `templates/` and `src/resume_tailor_harness/render/`.
- httpx — guarded HTTP transport in `src/resume_tailor_harness/security/outbound.py`.
- pytest — backend tests under `tests/` and `evals/`.
- pytest-xdist — parallel backend test workers configured in `pyproject.toml`.
- Vitest — browser tests configured in `web/package.json` and `web/vitest.config.ts`.
- Playwright — browser connectors and end-to-end checks under `src/resume_tailor_harness/discovery/` and `web/e2e/`.
- Docker — application image in `Dockerfile` and optional companion service in `compose.h1b.yaml`.
- GitHub Actions — quality, security audit, and branch-promotion workflows in `.github/workflows/`.
- Git — repository history and release automation in `scripts/release.py`.

## Architecture highlights

- Enforced provenance, skill-naming, numeric-evidence, and layout-fit gates in résumé review; the fact-check reviewer is a blocking gate by default and can be configured as advisory (`src/resume_tailor_harness/tailor/review_config.py`, `src/resume_tailor_harness/tailor/verdict.py`, `config/review.yaml.example`).
- Preserved application progress when a higher-priority source replaces a duplicate job, using source-aware merge decisions and in-place updates (`src/resume_tailor_harness/discovery/merge.py`, `src/resume_tailor_harness/discovery/ingest.py`).
- Added evidence-backed optional résumé sections and visual layout review, using the export renderer to produce bounded page previews and a page-fit verdict (`src/resume_tailor_harness/models/resume.py`, `src/resume_tailor_harness/tailor/provenance.py`, `src/resume_tailor_harness/render/layout_review.py`).
- Bound task agents to root-confined, hash-verified skill procedures and recorded the selected skill identity with agent run metadata (`src/resume_tailor_harness/career_skills/registry.py`, `src/resume_tailor_harness/profile/project_extractor.py`).
- Built external-agent application context with an approved-job queue, revision-checked answers, and verified attachments; the handoff instructs the agent to stop for confirmation before submission (`src/resume_tailor_harness/services/agent_applications.py`, `sdk/python/`; `40f1e0d1`).
- Isolated hosted users through request-scoped workspace contexts, separate databases, and tenant-confined artifacts (`src/resume_tailor_harness/tenancy/context.py`, `src/resume_tailor_harness/tenancy/storage.py`, `src/resume_tailor_harness/tenancy/system_db.py`).
- Secured employer account storage with an encrypted, tenant-bound vault and exact HTTPS-origin and employer matching for credential access (`src/resume_tailor_harness/services/application_accounts.py`, `src/resume_tailor_harness/api/routers/application_accounts.py`).
- Built resumable recruiting-mail analysis across Gmail API, Microsoft Graph, and IMAP, with durable cursors and reuse of cached message classifications (`src/resume_tailor_harness/gmail/scan.py`, `src/resume_tailor_harness/gmail/processing.py`, `src/resume_tailor_harness/services/mailboxes.py`).

## Quantified outcomes

- Reduced the full Python suite's measured runtime on one Windows machine from 836.79 seconds to 294.21 seconds (64.8%) with four pytest-xdist workers; both runs reported 4,698 passed and 5 skipped (`docs/test-performance.md`, `edbe85b3`).
- Reduced the full Vitest suite's measured runtime on the same machine from 186.39 seconds to 79.10 seconds (57.6%) using four isolated VM workers; both runs reported 215 files and 965 tests passed (`docs/test-performance.md`, `edbe85b3`).
- Counted 4,115 declared Python test functions in 522 tracked test files at the evidence revision; these are declarations, not a test-pass or coverage result (`git grep -n -E '^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+test_' 429106b8 -- ':(glob)**/test_*.py' ':(glob)**/*_test.py'`; count output lines and distinct file paths).
- Counted 514 tracked backend Python modules (`git ls-tree -r --name-only 429106b8 -- src/resume_tailor_harness | grep -c '\.py$'`).
- Registered 35 pinned skill procedures across seven agent families (`skills-lock.json` at `429106b8`; count entries under `skills` and their distinct `family` values).
- Recorded 2,577 reachable repository commits (`git rev-list --count 429106b8`).

## Skills demonstrated

Languages: Python, TypeScript
Frameworks: FastAPI, Pydantic, SQLModel, SQLAlchemy, Agno, React, TanStack Query, i18next, Typer
Databases: SQLite (aliases: SQLite3)
AI and APIs: OpenAI API, Anthropic API, Google Gemini, DeepSeek, AG-UI, Stripe, Gmail API, Microsoft Graph, IMAP
Testing: pytest, pytest-xdist, Vitest, Playwright
Cloud & Infra: Docker, GitHub Actions
Tooling: Typst, httpx, Git
