---
repo_url: https://github.com/awbjcj/resume-tailor-harness
repo_name: resume-agent
role: sole author
generated_at: 2026-10-25
---

# Project: Résumé Tailor Harness — Fact-Locked Job-Search Application

## Summary

A job-search application for candidates who need generated résumés and cover letters grounded in source evidence (`src/resume_tailor_harness/tailor/`, `src/resume_tailor_harness/cover_letter/`). Closed profile schemas and deterministic provenance, skill-name, and numeric-evidence gates constrain drafting before paid review (`src/resume_tailor_harness/profile/project_extractor.py`, `src/resume_tailor_harness/tailor/workflow.py`). The application combines job acquisition, fit scoring, reviewer-panel tailoring, coaching, interviews, employer research, and application tracking through browser, command-line, and external-agent interfaces (`src/resume_tailor_harness/api/app.py`, `src/resume_tailor_harness/cli.py`, `sdk/python/`). Recent work adds revision-checked application preparation, reusable professional screening answers, bounded taxonomy recovery, reversible non-skill cleanup, and Chinese localization (`src/resume_tailor_harness/services/agent_applications.py`, `src/resume_tailor_harness/services/application_prompt.py`, `src/resume_tailor_harness/services/match_gap.py`, `src/resume_tailor_harness/services/taxonomy.py`, `web/src/i18n/`). The repository is actively maintained by its sole human author (`git shortlog -sne 9fa44306`).

Role: sole author (2,309 of 2,477 repository commits across the owner's three Git identities, `git shortlog -sne 9fa44306`; automation excluded from the owner count)
Repository: https://github.com/awbjcj/resume-tailor-harness
Timeline: 2026-06 – present (`git log --reverse --format=%as`)

Evidence revision: `9fa44306ca47246824e4c6afdfcbeab63b454fb3`. Counts below refer to this snapshot; the first commit date is 2026-06-08.

## Tech stack (evidence-backed)

- Python — backend under `src/resume_tailor_harness/`.
- TypeScript — browser application and API contracts in `web/src/` and `contracts/ts/`.
- FastAPI — routers and schemas under `src/resume_tailor_harness/api/`.
- Pydantic — closed extraction and output schemas under `src/resume_tailor_harness/models/` and `src/resume_tailor_harness/profile/`.
- SQLModel — tracking and tenancy tables under `src/resume_tailor_harness/`.
- SQLAlchemy — engine pooling in `src/resume_tailor_harness/db.py` and conditional updates in `src/resume_tailor_harness/services/agent_applications.py`.
- SQLite — workspace and system databases in `src/resume_tailor_harness/db.py` and `src/resume_tailor_harness/tenancy/system_db.py`.
- Agno — agent runner in `src/resume_tailor_harness/llm_runner.py`.
- OpenAI API — provider routing and transport in `src/resume_tailor_harness/llm_runner.py`.
- Anthropic API — provider models in `src/resume_tailor_harness/llm_routing.py`.
- Google Gemini — provider models in `src/resume_tailor_harness/llm_routing.py`.
- DeepSeek — provider models in `src/resume_tailor_harness/llm_routing.py`.
- AG-UI — authenticated run-event projection in `src/resume_tailor_harness/api/runs/agui.py` and typed browser events in `web/src/`.
- Stripe — hosted checkout, signed webhooks, credits, and subscription ledger integration in `src/resume_tailor_harness/tenancy/payments.py`.
- React — browser components under `web/src/`.
- TanStack Query — browser API caching under `web/src/features/`.
- i18next — localization in `web/src/i18n/`.
- Typer — CLI in `src/resume_tailor_harness/cli.py`.
- Typst — PDF templates and renderer in `templates/` and `src/resume_tailor_harness/render/`.
- httpx — guarded HTTP transport in `src/resume_tailor_harness/security/outbound.py`.
- pytest — backend tests under `tests/` and `evals/`.
- Vitest — browser tests configured in `web/package.json`.
- Playwright — browser connectors and E2E checks under `web/e2e/` and `src/resume_tailor_harness/discovery/`.
- Docker — frontend/backend image in `Dockerfile` and optional companion service in `compose.h1b.yaml`.
- GitHub Actions — quality, security audit, and branch-promotion workflows in `.github/workflows/`.

## Architecture highlights

- Enforced evidence-based résumé acceptance with closed project extraction, three deterministic gates, and blocking unscored fact verification, including external drafts (`src/resume_tailor_harness/tailor/review_config.py`, `src/resume_tailor_harness/tailor/verdict.py`, `src/resume_tailor_harness/services/external_tailoring.py`; `9d35d9cf`).
- Bound task agents to root-confined, hash-verified skill procedures and persisted the resolved skill identity with artifacts (`src/resume_tailor_harness/career_skills/registry.py`, `skills-lock.json`).
- Built external-agent application preparation with an approved-job queue, scoped questions, revision-checked answers, verified attachments, and a stop-before-submit handoff (`src/resume_tailor_harness/services/agent_applications.py`, `sdk/python/`; `40f1e0d1`).
- Bounded skill-classification recovery with a shared call/prompt budget and durable retry history while retaining successful siblings and visibly provisional placements (`src/resume_tailor_harness/services/match_gap.py`, `src/resume_tailor_harness/taxonomy/classification.py`, `src/resume_tailor_harness/taxonomy/state.py`; `6d563d5c`).
- Isolated hosted users through request-scoped workspace contexts, separate databases, and tenant-confined artifacts (`src/resume_tailor_harness/tenancy/context.py`, `src/resume_tailor_harness/tenancy/storage.py`, `src/resume_tailor_harness/tenancy/system_db.py`).
- Implemented reversible non-skill cleanup through canonical retirement records, shared effective-taxonomy reads, and locked revision-checked writes without rewriting source evidence (`src/resume_tailor_harness/taxonomy/non_skills.py`, `src/resume_tailor_harness/taxonomy/snapshot.py`, `src/resume_tailor_harness/taxonomy/custody.py`; `4279b131`).
- Localized browser copy and account communication through English/Chinese catalogs, backend-progress labels, and saved language preferences (`web/src/i18n/`, `web/scripts/i18n-catalog.mjs`, `src/resume_tailor_harness/mail/account_notifications.py`; `469eb2b9`, `9e46f732`).
- Preserved recoverable chat workspaces through AG-UI projections of authenticated run events and shared Career Lab session context (`src/resume_tailor_harness/api/runs/agui.py`, `src/resume_tailor_harness/sessions/stream.py`, `src/resume_tailor_harness/career_lab/`; `846dbb38`, `9b502d1a`).

## Quantified outcomes

- Counted 3,859 declared Python test functions in 499 tracked files; this is a static declaration count, not a test-pass or coverage result (`git grep -n -E '^\s*(async\s+)?def\s+test_' 9fa44306 -- ':(glob)**/test_*.py' ':(glob)**/*_test.py'`; count output lines and distinct file paths).
- Counted 492 tracked backend Python modules (`git ls-tree -r --name-only 9fa44306 -- src/resume_tailor_harness`, filtered to `.py`).
- Registered 35 pinned skill procedures across seven populated families; the enum also defines sponsorship research (`skills-lock.json`, `src/resume_tailor_harness/career_skills/models.py`; count `skills` entries and distinct `family` values at `9fa44306`).
- Recorded 2,477 repository commits (`git rev-list --count 9fa44306`).
- None evidenced for production latency, uptime, business impact, or benchmarked model quality; no such outcome is claimed.

## Skills demonstrated

Languages: Python, TypeScript
Frameworks: FastAPI, Pydantic, SQLModel, SQLAlchemy, Agno, React, TanStack Query, i18next, Typer
Databases: SQLite (aliases: SQLite3)
AI and APIs: OpenAI API, Anthropic API, Google Gemini, DeepSeek, AG-UI, Stripe
Testing: pytest, Vitest, Playwright
Cloud & Infra: Docker, GitHub Actions
Tooling: Typst, httpx
