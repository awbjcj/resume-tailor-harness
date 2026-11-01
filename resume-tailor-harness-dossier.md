---
repo_url: https://github.com/awbjcj/resume-tailor-harness
repo_name: resume-agent
role: sole author
generated_at: 2026-11-01
---

# Project: Résumé Tailor Harness

A job-search application for candidates who want application materials grounded in their own evidence.

## Summary

Résumé Tailor Harness brings job discovery, résumé and cover-letter tailoring, coaching, and application tracking into one system (`src/resume_tailor_harness/discovery/`, `src/resume_tailor_harness/tailor/`, `src/resume_tailor_harness/tracking/`). It provides a browser interface, command-line interface, and an SDK for external application agents (`web/src/`, `src/resume_tailor_harness/cli.py`, `sdk/python/`). Review gates check whether generated résumé claims trace back to profile facts, and mailbox integrations propose recruiting-status updates for review (`src/resume_tailor_harness/tailor/verdict.py`, `src/resume_tailor_harness/services/mailboxes.py`). The sole human author continues to maintain the project; the latest commit in the evidence snapshot is dated 2026-11-01.

Role: sole author (2,394 of 2,590 reachable commits across the owner's three Git identities; the remaining 196 are bot-authored, `git shortlog -sne 16a243a9`, `git rev-list --count 16a243a9`)
Repository: https://github.com/awbjcj/resume-tailor-harness
Timeline: 2026-06 – present (first commit 2026-06-08, `git log --reverse --format=%as 16a243a9`)

Evidence revision: `16a243a9c6a158d6fe8f6cf8454e90129d7fece2`. Counts tied to the snapshot use this revision.

## Tech stack (evidence-backed)

- Python — backend services and concurrent calls in `src/resume_tailor_harness/concurrency.py`.
- TypeScript — browser run tracking in `web/src/lib/runs/sse.ts`.
- FastAPI — application factory and coach routes in `src/resume_tailor_harness/api/app.py`, `src/resume_tailor_harness/api/routers/coach.py`.
- Pydantic — closed project extraction schema in `src/resume_tailor_harness/profile/project_extractor.py`.
- SQLModel — job and application tables in `src/resume_tailor_harness/tracking/tables.py`.
- SQLAlchemy — engine configuration and system tables in `src/resume_tailor_harness/db.py`, `src/resume_tailor_harness/tenancy/system_db.py`.
- SQLite — workspace engine and concurrency settings in `src/resume_tailor_harness/db.py`.
- Agno — project extraction agent and runner in `src/resume_tailor_harness/profile/project_extractor.py`, `src/resume_tailor_harness/llm_runner.py`.
- React — coach interface in `web/src/features/coach/CoachPage.tsx`.
- TanStack Query — coach queries and mutations in `web/src/features/coach/use-coach.ts`.
- i18next — language initialization and switching in `web/src/i18n/index.ts`.
- Typer — profile commands in `src/resume_tailor_harness/cli.py`.
- Docker — multi-stage application image in `Dockerfile`.
- GitHub Actions — quality and security workflows in `.github/workflows/_reusable-ci.yml`.
- pytest — backend regression tests in `tests/test_profile_project_extractor.py`.
- pytest-xdist — worker scheduling in `pyproject.toml`.
- Vitest — browser unit tests and worker configuration in `web/src/`, `web/vitest.config.ts`.
- Playwright — browser automation and interface checks in `src/resume_tailor_harness/discovery/connectors/tesla.py`, `web/e2e/`.
- OpenAI API — model construction in `src/resume_tailor_harness/llm_runner.py`.
- Anthropic API — model construction and search-tool selection in `src/resume_tailor_harness/llm_runner.py`.
- Google Gemini — model adapter and construction in `src/resume_tailor_harness/llm_runner.py`.
- DeepSeek — model adapter and construction in `src/resume_tailor_harness/llm_runner.py`.
- AG-UI — conversation event projection in `src/resume_tailor_harness/api/runs/agui.py`.
- Stripe — checkout and payment-event handling in `src/resume_tailor_harness/tenancy/payments.py`.
- Gmail API — history and message reads in `src/resume_tailor_harness/gmail/scan.py`, `src/resume_tailor_harness/gmail/client.py`.
- Microsoft Graph — mailbox delta reads in `src/resume_tailor_harness/mailboxes/microsoft.py`.
- IMAP — read-only mailbox access in `src/resume_tailor_harness/mailboxes/imap.py`.
- Typst — résumé template and PDF compilation in `templates/resume-base.typ`, `src/resume_tailor_harness/render/renderer.py`.
- httpx — bounded public requests in `src/resume_tailor_harness/security/outbound.py`.
- Git — version and release history in `scripts/release.py`.

## Architecture highlights

- Enforced provenance, skill-naming, and numeric-evidence gates in résumé review; the fact-check reviewer blocks by default and can be configured as advisory (`src/resume_tailor_harness/tailor/verdict.py:aggregate`, `src/resume_tailor_harness/tailor/review_config.py:ReviewerSpec`).
- Preserved application progress when a higher-priority source replaces a duplicate job by updating the existing record in place (`src/resume_tailor_harness/discovery/ingest.py:save_or_upgrade`, `tests/test_discovery_ingest.py:test_upgrade_preserves_application_and_status`).
- Bound task agents to root-confined, hash-verified skill procedures and recorded the selected skill identity with run metadata (`src/resume_tailor_harness/career_skills/registry.py:CareerSkillRegistry`, `src/resume_tailor_harness/profile/project_extractor.py:build_project_extractor_agent`).
- Built application-agent context around an approved-job queue and fact-checked attachments, with instructions to obtain confirmation before final submission (`src/resume_tailor_harness/services/agent_applications.py:application_context`).
- Isolated hosted users with request-scoped workspace contexts and an encrypted account vault that checks its owner on read (`src/resume_tailor_harness/tenancy/context.py:use_context`, `src/resume_tailor_harness/services/application_accounts.py:AccountVault`).
- Built resumable recruiting-mail analysis across Gmail API, Microsoft Graph, and IMAP using saved cursors and cached classifications (`src/resume_tailor_harness/gmail/scan.py:MailboxScanner`, `src/resume_tailor_harness/gmail/processing.py:MessageProcessor`, `src/resume_tailor_harness/services/mailboxes.py`).
- Added visual résumé review using the export renderer and bounded page previews, with overflow reported as a layout failure (`src/resume_tailor_harness/render/layout_review.py:render_layout_preview`, `tests/test_visual_layout_review.py:test_overflow_is_diagnostic_and_bounded_and_temp_pdf_is_removed`).
- Built profile-change approval into coach conversations, with a follow-up build tracked in the browser (`src/resume_tailor_harness/api/routers/coach.py:resolve_profile_changes`, `web/src/features/coach/use-coach.ts:useEndCoachSession`; commits `865c9897`, `16a243a9`).

## Quantified outcomes

- Reduced the full Python suite's measured runtime on one Windows machine from 836.79 seconds to 294.21 seconds (64.8%) with four pytest-xdist workers; both runs reported 4,698 passed and 5 skipped (`docs/test-performance.md`; commit `edbe85b3`).
- Reduced the full Vitest suite's measured runtime on the same machine from 186.39 seconds to 79.10 seconds (57.6%) using four isolated VM workers; both runs reported 215 files and 965 tests passed (`docs/test-performance.md`; commit `edbe85b3`).
- Registered 36 pinned skill procedures across seven agent families (`skills-lock.json` at `16a243a9`; reproduce with `git show 16a243a9:skills-lock.json | python -c "import json,sys; s=json.load(sys.stdin)['skills']; print(len(s), len({v['family'] for v in s.values()}))"`).

## Skills demonstrated

### Languages

- Name: Python
  - Context: Built backend services for structured extraction and concurrent work.
  - Evidence:
    - Created an ordered fan-out that isolates individual failures — `src/resume_tailor_harness/concurrency.py:gather_isolated` (commit `861e7309`).
    - Projected extracted project facts into a source-aware profile fragment — `src/resume_tailor_harness/profile/project_extractor.py:project_facts_to_profile`.
    - Staged mailbox history pages and saved their cursors for later processing — `src/resume_tailor_harness/gmail/scan.py:MailboxScanner._stage_page`.
- Name: TypeScript
  - Context: Built typed browser clients for run events and coach sessions.
  - Evidence:
    - Mapped server run states and watched event streams — `web/src/lib/runs/sse.ts:watchRun` (commit `09cd425a`).
    - Typed coach response records and mutations against generated API schemas — `web/src/features/coach/use-coach.ts:useCoachSessions`.
    - Parsed streamed conversation events into browser event records — `web/src/lib/chat/agui.ts:parseAguiEvent` (commit `846dbb38`).

### Frameworks

- Name: FastAPI
  - Context: Exposed application services through an API factory and typed routes.
  - Evidence:
    - Composed routers and application lifecycle in the server factory — `src/resume_tailor_harness/api/app.py:create_app` (commit `af4d0134`).
    - Added a route to resolve proposed profile changes — `src/resume_tailor_harness/api/routers/coach.py:resolve_profile_changes` (commit `865c9897`).
    - Accepted coach messages through a session-scoped route — `src/resume_tailor_harness/api/routers/coach.py:send_message`.
- Name: Pydantic
  - Context: Defined and validated the shape of extracted project facts.
  - Evidence:
    - Forbade extra fields on the project extraction record — `src/resume_tailor_harness/profile/project_extractor.py:ProjectDocFacts` (commit `aa8d09ee`).
    - Tested rejection of unrelated top-level sections — `tests/test_profile_project_extractor.py:test_project_doc_schema_forbids_foreign_top_level_sections` (commit `aa8d09ee`).
    - Normalized a known skill-category label before validation — `src/resume_tailor_harness/profile/project_extractor.py:ProjectDocFacts._normalize_tooling_skill_category`.
- Name: SQLModel
  - Context: Modeled tracked jobs and used sessions to preserve them during source upgrades.
  - Evidence:
    - Defined persisted job and application tables — `src/resume_tailor_harness/tracking/tables.py:Job`, `src/resume_tailor_harness/tracking/tables.py:Application` (commit `dac8594d` for `Job`).
    - Updated an existing job when a stronger source arrives — `src/resume_tailor_harness/discovery/ingest.py:save_or_upgrade`.
    - Stored mailbox message receipts as database records — `src/resume_tailor_harness/gmail/tables.py:GmailReceipt`.
- Name: SQLAlchemy
  - Context: Configured database engines and mapped account records.
  - Evidence:
    - Created pooled engines for concurrent in-memory sessions — `src/resume_tailor_harness/db.py:make_engine` (commit `33932273`).
    - Defined user and account tables on a declarative base — `src/resume_tailor_harness/tenancy/system_db.py:SystemBase`, `src/resume_tailor_harness/tenancy/system_db.py:User` (commit `b18d45ff`).
- Name: Agno
  - Context: Constructed task agents with structured outputs and wrapped their execution.
  - Evidence:
    - Built a project extraction agent with a closed output schema and selected skill — `src/resume_tailor_harness/profile/project_extractor.py:build_project_extractor_agent` (commit `01a10110`).
    - Added a runner for synchronous, asynchronous, and streamed agent calls — `src/resume_tailor_harness/llm_runner.py:AgentRunner`.
- Name: React
  - Context: Built the coach interface and its session interactions.
  - Evidence:
    - Rendered the coach page and its localized interface — `web/src/features/coach/CoachPage.tsx:CoachPage` (commit `68571e6a`).
    - Tested the coach hook after a follow-up profile build — `web/src/features/coach/use-coach.test.tsx:42` (commit `992ce80d`).
    - Rendered apply and discard controls for a proposed profile change — `web/src/features/coach/ProfileChangeCard.tsx:ProfileChangeCard`.
- Name: TanStack Query
  - Aliases: React Query
  - Context: Managed coach data and refreshed affected views after mutations.
  - Evidence:
    - Loaded coach sessions with a query hook — `web/src/features/coach/use-coach.ts:useCoachSessions` (commit `bccb2437`).
    - Invalidated session and profile queries after a follow-up build — `web/src/features/coach/use-coach.ts:useEndCoachSession`.
    - Invalidated session lists after archive and delete mutations — `web/src/features/coach/use-coach.ts:useCoachSessionMutation`.
- Name: i18next
  - Context: Added language selection and translated interface copy.
  - Evidence:
    - Initialized supported languages and persisted changes — `web/src/i18n/index.ts:initializeI18n`, `web/src/i18n/index.ts:changeLanguage` (commit `fc2a4bbb` for initialization).
    - Tested locale selection and document-language updates — `web/src/i18n/index.test.ts:30-44`.
- Name: Typer
  - Context: Exposed profile-source workflows as command-line commands.
  - Evidence:
    - Registered a command to add a profile source — `src/resume_tailor_harness/cli.py:profile_add` (commit `b20ec959`).
    - Added a command that synchronizes sources from a repository account — `src/resume_tailor_harness/cli.py:profile_sync_github` (commit `6b0d2be6`).

### Databases

- Name: SQLite
  - Aliases: SQLite3
  - Context: Configured workspace databases for concurrent application and test access.
  - Evidence:
    - Enabled write-ahead logging and a busy timeout for file-backed databases — `src/resume_tailor_harness/db.py:_enable_sqlite_write_concurrency`.
    - Created a uniquely named shared in-memory database per engine — `src/resume_tailor_harness/db.py:make_engine` (commit `33932273`).
    - Created a separate system database engine for account state — `src/resume_tailor_harness/tenancy/system_db.py:make_system_engine`.

### Cloud & Infra

- Name: Docker
  - Context: Packaged the web and backend application into a deployable image.
  - Evidence:
    - Built the web assets in a separate image stage and copied them into the runtime — `Dockerfile:1-13`, `Dockerfile:42` (commit `750ce069` for the build stage).
    - Configured an optional companion service with a health check — `compose.h1b.yaml:4-35`.
- Name: GitHub Actions
  - Context: Automated quality checks and branch promotion safeguards.
  - Evidence:
    - Ran backend and browser checks in reusable jobs — `.github/workflows/_reusable-ci.yml:20-58` (commit `bc1e2f33` for the offline test step).
    - Restricted promotion into the production branch by checking its source branch — `.github/workflows/require-dev-base.yml:8-25`.

### Testing

- Name: pytest
  - Context: Wrote regression tests for extraction, concurrency, and skill integrity.
  - Evidence:
    - Checked that project extraction rejects unrelated sections — `tests/test_profile_project_extractor.py:test_project_doc_schema_forbids_foreign_top_level_sections` (commit `aa8d09ee`).
    - Tested that fan-out keeps results ordered and isolates errors — `tests/test_concurrency.py:test_gather_isolated_preserves_order_and_isolates_errors`.
    - Parameterized invalid skill-manifest cases to check that failures remain confined to their capability — `tests/test_career_skill_registry.py:test_invalid_manifest_entry_fails_only_its_capability`.
- Name: pytest-xdist
  - Context: Distributed the complete backend suite across isolated workers while retaining its tests.
  - Evidence:
    - Configured work-stealing with at most four workers — `pyproject.toml:67-73` (commit `edbe85b3`).
    - Compared serial and parallel runs with matching test identities and statuses — `docs/test-performance.md:12-51` (commit `edbe85b3`).
- Name: Vitest
  - Context: Tested browser logic and configured isolated web-test workers.
  - Evidence:
    - Tested that coach session data refreshes after a build — `web/src/features/coach/use-coach.test.tsx:42` (commit `992ce80d`).
    - Configured isolated VM workers and a memory recycling limit — `web/vitest.config.ts:7-23` (commit `edbe85b3`).
    - Checked that malformed stream events do not consume the replay cursor — `web/src/lib/chat/agui.test.ts:8-12`.
- Name: Playwright
  - Context: Used browser automation for a job connector and interface checks.
  - Evidence:
    - Opened a browser-backed portal to capture job listings — `src/resume_tailor_harness/discovery/connectors/tesla.py:open_portal` (commit `2f9ff1fe`).
    - Tested localized profile-change approval at different widths — `web/e2e/profile-conversation.spec.ts:6` (commit `865c9897`).
    - Tested authentication-page reflow across languages, viewport widths, and enlarged text — `web/e2e/auth-layout.spec.ts:18-51`.

### Architecture

- Name: API design
  - Context: Designed separate interfaces for profile changes and external application agents.
  - Evidence:
    - Added a route for accepting or dismissing proposed profile changes — `src/resume_tailor_harness/api/routers/coach.py:resolve_profile_changes` (commit `865c9897`).
    - Returned approved-job context with eligible attachments and scoped questions — `src/resume_tailor_harness/services/agent_applications.py:application_context`.
    - Exposed coach-session messages through a dedicated route — `src/resume_tailor_harness/api/routers/coach.py:send_message`.
- Name: Concurrency
  - Context: Coordinated independent calls without letting one failure discard sibling results.
  - Evidence:
    - Collected concurrent results in input order with per-item errors — `src/resume_tailor_harness/concurrency.py:gather_isolated` (commit `861e7309`).
    - Tested cancellation of in-flight tasks when a checkpoint fails — `tests/test_concurrency.py:test_gather_isolated_cancels_in_flight_tasks_when_checkpoint_raises`.
    - Tested that asynchronous funding waiters leave executor capacity for settlement — `tests/test_llm_runner_concurrency.py:test_async_funding_waiters_leave_executor_capacity_for_settlement`.
- Name: Application security
  - Context: Restricted untrusted network access and protected saved employer credentials.
  - Evidence:
    - Resolved public addresses before pinning outbound requests and bounded response size — `src/resume_tailor_harness/security/outbound.py:fetch_public_bytes` (commit `df3cdf04`).
    - Encrypted the account vault and rejected data belonging to another owner — `src/resume_tailor_harness/services/application_accounts.py:AccountVault._read`, `src/resume_tailor_harness/services/application_accounts.py:AccountVault._write` (commit `ec5bce45`).
    - Tested rejection of unsafe skill-manifest entries, including path traversal and hash mismatches — `tests/test_career_skill_registry.py:test_invalid_manifest_entry_fails_only_its_capability`.
- Name: Agent orchestration
  - Context: Bound agent tasks to verified procedures and retained their selected identities.
  - Evidence:
    - Checked skill paths and hashes before making a capability available — `src/resume_tailor_harness/career_skills/registry.py:CareerSkillRegistry` (commit `08c42dc3`).
    - Saved the selected skill reference with project-extractor run metadata — `src/resume_tailor_harness/profile/project_extractor.py:build_project_extractor_agent`.
    - Tested that a changed skill file is revalidated before reuse — `tests/test_career_skill_registry.py:test_registry_revalidates_a_skill_after_the_file_changes`.
- Name: Internationalization
  - Aliases: i18n
  - Context: Supported English and Chinese interface language selection without changing underlying values.
  - Evidence:
    - Selected and persisted a supported language — `web/src/i18n/index.ts:resolveInitialLanguage`, `web/src/i18n/index.ts:changeLanguage` (commit `fc2a4bbb` for initialization).
    - Tested language switching while preserving unsaved settings — `web/e2e/i18n-review.spec.ts:80` (commit `570191d4`).
    - Translated dynamic run error labels for display — `web/src/i18n/dynamic-labels.ts:localizeRunError` (commit `1df8e042`).

### Tooling

- Name: OpenAI API
  - Context: Adapted model construction and request settings for agent calls.
  - Evidence:
    - Built Responses requests with explicit reasoning and output settings — `src/resume_tailor_harness/llm_runner.py:_build_openai_responses` (commit `75605133`).
    - Tested that agents use the Responses endpoint — `tests/test_llm_runner_build_model.py:test_openai_agents_are_built_on_the_responses_endpoint`.
    - Tested that provider-managed response state is disabled — `tests/test_llm_runner_build_model.py:test_openai_never_uses_provider_managed_response_state`.
- Name: Anthropic API
  - Context: Configured model-specific reasoning and search options.
  - Evidence:
    - Selected a search-tool variant for the model generation — `src/resume_tailor_harness/llm_runner.py:anthropic_web_search_tool` (commit `a160f498`).
    - Tested forwarding of the prompt-cache option — `tests/test_llm_runner_build_model.py:test_anthropic_cache_flag_is_forwarded`.
- Name: Google Gemini
  - Aliases: Gemini
  - Context: Adapted model requests and structured output for different model generations.
  - Evidence:
    - Preserved dictionary and referenced item types in the model adapter — `src/resume_tailor_harness/llm_runner.py:_compatible_gemini_class` (commit `4aa14a61`).
    - Selected generation-specific thinking settings during model construction — `src/resume_tailor_harness/llm_runner.py:_build_model_from_route`.
- Name: DeepSeek
  - Context: Adapted the model's response and reasoning events to the agent runner.
  - Evidence:
    - Added a provider-specific response adapter — `src/resume_tailor_harness/llm_runner.py:_compatible_deepseek_responses_class` (commit `cdbe5c1d`).
    - Tested that streamed reasoning deltas are mapped — `tests/test_llm_runner_build_model.py:test_deepseek_maps_its_streamed_reasoning_deltas`.
- Name: AG-UI
  - Context: Projected durable conversation events into a browser-consumable stream.
  - Evidence:
    - Mapped text, tool, reasoning, and terminal events while retaining replay cursors — `src/resume_tailor_harness/api/runs/agui.py:project_event` (commit `846dbb38`).
    - Parsed projected events on the browser side — `web/src/lib/chat/agui.ts:parseAguiEvent`.
    - Tested that malformed events do not advance the browser replay cursor — `web/src/lib/chat/agui.test.ts:8-12`.
- Name: Stripe
  - Context: Integrated checkout and reconciled payment events with account records.
  - Evidence:
    - Created checkout sessions through a gateway — `src/resume_tailor_harness/tenancy/payments.py:StripeGateway.checkout` (commit `b0f186c0`).
    - Retrieved current payment state and recorded event receipts before updating the ledger — `src/resume_tailor_harness/tenancy/payments.py:process_event`.
- Name: Gmail API
  - Context: Read mailbox history and message metadata for resumable recruiting-mail analysis.
  - Evidence:
    - Staged history and message-list pages with saved cursors — `src/resume_tailor_harness/gmail/scan.py:MailboxScanner._stage_page` (commit `5d7a7670`).
    - Batched message reads and tested retry of failed parts — `src/resume_tailor_harness/gmail/client.py:batch_read_messages`, `tests/test_gmail_client.py:test_batch_retries_only_failed_parts`.
    - Tested that listing pages and a deleted message do not abort a scan — `tests/test_gmail_client.py:test_listing_pages_and_deleted_message_do_not_abort_scan`.
- Name: Microsoft Graph
  - Context: Read mailbox delta pages while restricting continuation URLs.
  - Evidence:
    - Fetched and normalized mailbox pages — `src/resume_tailor_harness/mailboxes/microsoft.py:read_page` (commit `d4b8a43a`).
    - Validated continuation URLs before requests — `src/resume_tailor_harness/mailboxes/microsoft.py:_validate_graph_url` (commit `779e327a`).
- Name: IMAP
  - Context: Connected to mailboxes securely and resumed message reads.
  - Evidence:
    - Established TLS before login and selected the folder read-only — `src/resume_tailor_harness/mailboxes/imap.py:open_mailbox` (commit `779e327a`).
    - Tested backfill, new arrivals, and mailbox identity changes — `tests/test_mailboxes.py:test_imap_backfill_new_arrivals_and_uidvalidity`.
- Name: Typst
  - Context: Built résumé templates and compiled them into page-bounded PDFs.
  - Evidence:
    - Defined a shared résumé template with adjustable density and section blocks — `templates/resume-base.typ:2-28`, `templates/resume-base.typ:145-225` (commit `8c7acdf2`).
    - Compiled and checked rendered pages — `src/resume_tailor_harness/render/renderer.py:render_pdf`.
    - Tested page-fit overflow and cleanup during layout review — `tests/test_visual_layout_review.py:test_overflow_is_diagnostic_and_bounded_and_temp_pdf_is_removed`.
- Name: httpx
  - Context: Made bounded network requests with explicit transport controls.
  - Evidence:
    - Streamed a pinned public response with size and content-type checks — `src/resume_tailor_harness/security/outbound.py:fetch_public_bytes` (commit `df3cdf04`).
    - Disabled redirects and environment-derived proxy settings for mailbox reads — `src/resume_tailor_harness/mailboxes/microsoft.py:open_mailbox`.
- Name: Git
  - Context: Used repository history and tags to prepare releases.
  - Evidence:
    - Read commits since a prior version to determine a release bump — `scripts/release.py:Repository.commits`, `scripts/release.py:infer_bump` (commit `f714f38f` for bump inference).
    - Created version tags against a selected commit — `scripts/release.py:GitHub.create_tag`.
