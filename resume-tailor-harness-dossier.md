---
repo_url: https://github.com/awbjcj/resume-tailor-harness
repo_name: resume-agent
role: sole author
generated_at: 2026-11-04
---

# Project: Résumé Tailor Harness

A job-search application for candidates who want their materials grounded in their own evidence.

## Summary

Résumé Tailor Harness combines job discovery, résumé and cover-letter tailoring, coaching, and application tracking (`src/resume_tailor_harness/discovery/`, `src/resume_tailor_harness/tailor/`, `src/resume_tailor_harness/tracking/`). It provides browser and command-line interfaces and an SDK for application agents (`web/src/`, `src/resume_tailor_harness/cli.py`, `sdk/python/`). Review gates check résumé claims against profile facts; mailbox integrations propose recruiting-status updates for review (`src/resume_tailor_harness/tailor/verdict.py`, `src/resume_tailor_harness/services/mailboxes.py`). The sole human author maintains the project; this snapshot is dated 2026-11-04.

Role: sole author (2,443 of 2,643 commits across three owner identities; 200 bot-authored, `git shortlog -sne 3056b869`, `git rev-list --count 3056b869`)
Repository: https://github.com/awbjcj/resume-tailor-harness
Timeline: 2026-06 – present (first commit 2026-06-08, `git log --reverse --format=%as 3056b869`)
Project context: unknown

Evidence revision: `3056b8692e51f419419837aa85ff3fb47ec4537c`. Snapshot counts use this revision.

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
- Preserved application progress by updating duplicate jobs in place when a higher-priority source arrives (`src/resume_tailor_harness/discovery/ingest.py:save_or_upgrade`, `tests/test_discovery_ingest.py:test_upgrade_preserves_application_and_status`).
- Bound agents to root-confined, hash-verified skills and recorded their identity in run metadata (`src/resume_tailor_harness/career_skills/registry.py:CareerSkillRegistry`, `src/resume_tailor_harness/profile/project_extractor.py:build_project_extractor_agent`).
- Preserved selected application documents through handoff and surfaced missing or ineligible files (`src/resume_tailor_harness/services/application_materials.py:application_materials`, `src/resume_tailor_harness/services/agent_applications.py:application_handoff`; commit `aaf59c62`).
- Isolated hosted users with request-scoped workspaces and an encrypted, owner-checked vault (`src/resume_tailor_harness/tenancy/context.py:use_context`, `src/resume_tailor_harness/services/application_accounts.py:AccountVault`).
- Built resumable recruiting-mail analysis across Gmail API, Microsoft Graph, and IMAP with saved cursors and cached classifications (`src/resume_tailor_harness/gmail/scan.py:MailboxScanner`, `src/resume_tailor_harness/gmail/processing.py:MessageProcessor`, `src/resume_tailor_harness/services/mailboxes.py`).
- Preserved cited dossier applications as skill-linked project facts through caching and cross-project merges (`src/resume_tailor_harness/profile/dossier.py:retain_dossier_evidence`, `tests/test_profile_dossier.py:test_evidence_links_survive_cache_and_cross_project_skill_merge`; commit `dd98ccf9`).
- Built reviewed workspace actions with revision checks and receipts; agent previews stay read-only (`src/resume_tailor_harness/workspace_agent/runtime.py:WorkspaceTools.functions`, `src/resume_tailor_harness/workspace_agent/actions.py:resolve_plan`; commits `9e18b568`, `8ea111d7`).
- Ranked résumé evidence by job requirements and importance without changing claims or provenance (`src/resume_tailor_harness/profile/importance.py:score_profile`, `src/resume_tailor_harness/tailor/evidence_portfolio.py:_owner_rank`; commit `db29eb82`).
- Built opt-in OpenAI API classification with guarded funding, confidence checks, and standard-classifier fallback (`src/resume_tailor_harness/decisions.py:DecisionClient.choose`, `src/resume_tailor_harness/decisions.py:_answers`; commit `cb7d32ec`).
- Exposed document selection to external application clients (`sdk/python/src/resume_harness_sdk/_applications.py:ApplicationAPI.select_resume`; commit `2e33d860`).
- Preserved native PDF preview filenames with named inline responses for résumés and cover letters (`src/resume_tailor_harness/api/routers/resumes.py:preview_pdf`, `src/resume_tailor_harness/api/routers/cover_letters.py:preview_cover_letter_pdf`; commit `580baab2`).

## Quantified outcomes

- Reduced the full Python suite's measured runtime on one Windows machine from 836.79 seconds to 294.21 seconds (64.8%) with four pytest-xdist workers; both runs reported 4,698 passed and 5 skipped (`docs/test-performance.md`; commit `edbe85b3`).
- Reduced the full Vitest suite's measured runtime on the same machine from 186.39 seconds to 79.10 seconds (57.6%) using four isolated VM workers; both runs reported 215 files and 965 tests passed (`docs/test-performance.md`; commit `edbe85b3`).
- Registered 37 pinned skill procedures across seven agent families (`skills-lock.json` at `3056b869`; reproduce with `git show 3056b869:skills-lock.json | python -c "import json,sys; s=json.load(sys.stdin)['skills']; print(len(s), len({v['family'] for v in s.values()}))"`).

## Skills demonstrated

### Languages

- Name: Python
  - Context: Built backend extraction and concurrency services.
  - Evidence:
    - Built ordered fan-out with isolated failures — `src/resume_tailor_harness/concurrency.py:gather_isolated` (commit `861e7309`).
    - Projected project facts into a source-aware profile fragment — `src/resume_tailor_harness/profile/project_extractor.py:project_facts_to_profile`.
    - Staged mailbox history pages and saved their cursors — `src/resume_tailor_harness/gmail/scan.py:MailboxScanner._stage_page`.
    - Projected cited project applications into skill-linked facts — `src/resume_tailor_harness/profile/dossier.py:retain_dossier_evidence` (commit `dd98ccf9`).
- Name: TypeScript
  - Context: Built typed clients for run events and coach sessions.
  - Evidence:
    - Mapped server run states and watched event streams — `web/src/lib/runs/sse.ts:watchRun` (commit `09cd425a`).
    - Typed coach responses and mutations against API schemas — `web/src/features/coach/use-coach.ts:useCoachSessions`.
    - Parsed conversation streams into browser events — `web/src/lib/chat/agui.ts:parseAguiEvent` (commit `846dbb38`).
    - Sent reviewed action IDs and proposal digest from a card — `web/src/components/chat/workspace-review/WorkspaceProposalCard.tsx:WorkspaceProposalCard` (commit `f510a676`).

### Frameworks

- Name: FastAPI
  - Context: Exposed services through an API factory and typed routes.
  - Evidence:
    - Composed routers and lifecycle in the server factory — `src/resume_tailor_harness/api/app.py:create_app` (commit `af4d0134`).
    - Added a route to resolve profile proposals — `src/resume_tailor_harness/api/routers/coach.py:resolve_profile_changes` (commit `865c9897`).
    - Accepted coach messages through a session-scoped route — `src/resume_tailor_harness/api/routers/coach.py:send_message`.
    - Rejected authorization-header access to in-app proposal review — `src/resume_tailor_harness/api/routers/workspace_agent.py:review_proposal` (commit `9e18b568`).
- Name: Pydantic
  - Context: Defined and validated extracted project facts.
  - Evidence:
    - Forbade extra fields in project extraction — `src/resume_tailor_harness/profile/project_extractor.py:ProjectDocFacts` (commit `aa8d09ee`).
    - Tested rejection of unrelated top-level sections — `tests/test_profile_project_extractor.py:test_project_doc_schema_forbids_foreign_top_level_sections` (commit `aa8d09ee`).
    - Normalized a skill-category label before validation — `src/resume_tailor_harness/profile/project_extractor.py:ProjectDocFacts._normalize_tooling_skill_category`.
    - Rejected extra fields in model-facing workspace commands — `src/resume_tailor_harness/workspace_agent/models.py:WorkspaceChange` (commit `9e18b568`).
- Name: SQLModel
  - Context: Modeled jobs and preserved them during source upgrades.
  - Evidence:
    - Defined persisted job and application tables — `src/resume_tailor_harness/tracking/tables.py:Job`, `src/resume_tailor_harness/tracking/tables.py:Application` (commit `dac8594d` for `Job`).
    - Updated an existing job when a stronger source arrives — `src/resume_tailor_harness/discovery/ingest.py:save_or_upgrade`.
    - Stored mailbox receipts as database records — `src/resume_tailor_harness/gmail/tables.py:GmailReceipt`.
    - Stored proposals and action receipts separately — `src/resume_tailor_harness/workspace_agent/tables.py:12-35` (commit `9e18b568`).
- Name: SQLAlchemy
  - Context: Configured database engines and mapped account records.
  - Evidence:
    - Created pooled engines for concurrent in-memory sessions — `src/resume_tailor_harness/db.py:make_engine` (commit `33932273`).
    - Defined user and account tables on a declarative base — `src/resume_tailor_harness/tenancy/system_db.py:SystemBase`, `src/resume_tailor_harness/tenancy/system_db.py:User` (commit `b18d45ff`).
    - Committed database effects and approval receipts in one transaction — `src/resume_tailor_harness/workspace_agent/actions.py:resolve_plan` (commit `9e18b568`).
- Name: Agno
  - Context: Built task agents with structured outputs and an execution wrapper.
  - Evidence:
    - Built a project extraction agent with a closed output schema and selected skill — `src/resume_tailor_harness/profile/project_extractor.py:build_project_extractor_agent` (commit `01a10110`).
    - Added a runner for sync, async, and streamed calls — `src/resume_tailor_harness/llm_runner.py:AgentRunner`.
    - Bound workspace read and preview tools to a conversational persona — `src/resume_tailor_harness/career_lab/agents.py:build_persona_agent` (commit `9e18b568`).
- Name: React
  - Context: Built the coach interface and session interactions.
  - Evidence:
    - Rendered the localized coach page — `web/src/features/coach/CoachPage.tsx:CoachPage` (commit `68571e6a`).
    - Tested the coach hook after a follow-up profile build — `web/src/features/coach/use-coach.test.tsx:42` (commit `992ce80d`).
    - Rendered apply and discard controls for profile proposals — `web/src/features/coach/ProfileChangeCard.tsx:ProfileChangeCard`.
    - Rendered a card for applying or discarding selected actions — `web/src/components/chat/workspace-review/WorkspaceProposalCard.tsx:WorkspaceProposalCard`.
- Name: TanStack Query
  - Aliases: React Query
  - Context: Managed coach data and refreshed views after mutations.
  - Evidence:
    - Loaded coach sessions with a query — `web/src/features/coach/use-coach.ts:useCoachSessions` (commit `bccb2437`).
    - Invalidated session and profile queries after a follow-up build — `web/src/features/coach/use-coach.ts:useEndCoachSession`.
    - Invalidated session lists after archive and delete mutations — `web/src/features/coach/use-coach.ts:useCoachSessionMutation`.
    - Loaded review proposals and refreshed them after a turn — `web/src/components/chat/workspace-review/WorkspaceReviewPanel.tsx:WorkspaceReviewPanel`.
- Name: i18next
  - Context: Added language selection and translated interface copy.
  - Evidence:
    - Initialized languages and persisted changes — `web/src/i18n/index.ts:initializeI18n`, `web/src/i18n/index.ts:changeLanguage` (commit `fc2a4bbb` for initialization).
    - Tested locale selection and document-language updates — `web/src/i18n/index.test.ts:30-44`.
- Name: Typer
  - Context: Exposed profile-source workflows as commands.
  - Evidence:
    - Added a profile-source command — `src/resume_tailor_harness/cli.py:profile_add` (commit `b20ec959`).
    - Added repository-account source synchronization — `src/resume_tailor_harness/cli.py:profile_sync_github` (commit `6b0d2be6`).

### Databases

- Name: SQLite
  - Aliases: SQLite3
  - Context: Configured workspace databases for concurrent access.
  - Evidence:
    - Enabled write-ahead logging and a busy timeout for file-backed databases — `src/resume_tailor_harness/db.py:_enable_sqlite_write_concurrency`.
    - Created a unique shared in-memory database per engine — `src/resume_tailor_harness/db.py:make_engine` (commit `33932273`).
    - Created a separate database engine for account state — `src/resume_tailor_harness/tenancy/system_db.py:make_system_engine`.

### Cloud & Infra

- Name: Docker
  - Context: Packaged the web app and backend into an image.
  - Evidence:
    - Built web assets in a separate stage and copied them into the runtime — `Dockerfile:1-13`, `Dockerfile:42` (commit `750ce069` for the build stage).
    - Configured an optional companion service with a health check — `compose.h1b.yaml:4-35`.
- Name: GitHub Actions
  - Context: Automated quality checks and branch promotion safeguards.
  - Evidence:
    - Ran backend and browser checks in reusable jobs — `.github/workflows/_reusable-ci.yml:20-58` (commit `bc1e2f33` for the offline test step).
    - Restricted production promotion by source branch — `.github/workflows/require-dev-base.yml:8-25`.

### Testing

- Name: pytest
  - Context: Wrote regression tests for extraction, concurrency, and skill integrity.
  - Evidence:
    - Checked that project extraction rejects unrelated sections — `tests/test_profile_project_extractor.py:test_project_doc_schema_forbids_foreign_top_level_sections` (commit `aa8d09ee`).
    - Tested that fan-out keeps results ordered and isolates errors — `tests/test_concurrency.py:test_gather_isolated_preserves_order_and_isolates_errors`.
    - Tested invalid skill manifests for per-capability failure isolation — `tests/test_career_skill_registry.py:test_invalid_manifest_entry_fails_only_its_capability`.
    - Checked retention of every dossier skill and cited example — `tests/test_profile_dossier.py:test_repository_dossier_retains_every_labeled_skill_and_usage_example` (commit `dd98ccf9`).
- Name: pytest-xdist
  - Context: Distributed the backend suite across isolated workers.
  - Evidence:
    - Configured work-stealing with at most four workers — `pyproject.toml:67-73` (commit `edbe85b3`).
    - Compared serial and parallel runs with matching test identities and statuses — `docs/test-performance.md:12-51` (commit `edbe85b3`).
- Name: Vitest
  - Context: Tested browser logic and configured isolated web-test workers.
  - Evidence:
    - Tested coach-session refresh after a build — `web/src/features/coach/use-coach.test.tsx:42` (commit `992ce80d`).
    - Configured isolated VM workers and a memory recycling limit — `web/vitest.config.ts:7-23` (commit `edbe85b3`).
    - Checked malformed events do not consume the replay cursor — `web/src/lib/chat/agui.test.ts:8-12`.
- Name: Playwright
  - Context: Used browser automation for a job connector and interface checks.
  - Evidence:
    - Opened a browser-backed portal to capture job listings — `src/resume_tailor_harness/discovery/connectors/tesla.py:open_portal` (commit `2f9ff1fe`).
    - Tested localized profile-change approval at different widths — `web/e2e/profile-conversation.spec.ts:6` (commit `865c9897`).
    - Tested authentication-page reflow across languages, viewport widths, and enlarged text — `web/e2e/auth-layout.spec.ts:18-51`.

### Architecture

- Name: API design
  - Context: Designed interfaces for profile changes and external agents.
  - Evidence:
    - Added a route to accept or dismiss profile proposals — `src/resume_tailor_harness/api/routers/coach.py:resolve_profile_changes` (commit `865c9897`).
    - Returned approved-job context with eligible attachments and scoped questions — `src/resume_tailor_harness/services/agent_applications.py:application_context`.
    - Exposed coach messages through a dedicated route — `src/resume_tailor_harness/api/routers/coach.py:send_message`.
    - Exposed durable run completion lookup to application clients — `sdk/python/src/resume_harness_sdk/_operations.py:OperationAPI.get_run_completion` (commit `2e33d860`).
- Name: Concurrency
  - Context: Isolated failures across concurrent calls.
  - Evidence:
    - Collected concurrent results in order with per-item errors — `src/resume_tailor_harness/concurrency.py:gather_isolated` (commit `861e7309`).
    - Tested in-flight cancellation when a checkpoint fails — `tests/test_concurrency.py:test_gather_isolated_cancels_in_flight_tasks_when_checkpoint_raises`.
    - Tested that asynchronous funding waiters leave executor capacity for settlement — `tests/test_llm_runner_concurrency.py:test_async_funding_waiters_leave_executor_capacity_for_settlement`.
    - Tested concurrent approvals create one effect — `tests/test_workspace_agent.py:test_concurrent_approvals_apply_once` (commit `9e18b568`).
- Name: Application security
  - Context: Restricted network access and protected employer credentials.
  - Evidence:
    - Pinned outbound requests to public addresses and bounded response size — `src/resume_tailor_harness/security/outbound.py:fetch_public_bytes` (commit `df3cdf04`).
    - Encrypted the account vault and rejected another owner's data — `src/resume_tailor_harness/services/application_accounts.py:AccountVault._read`, `src/resume_tailor_harness/services/application_accounts.py:AccountVault._write` (commit `ec5bce45`).
    - Tested rejection of traversal and hash-mismatched skill entries — `tests/test_career_skill_registry.py:test_invalid_manifest_entry_fails_only_its_capability`.
    - Rejected altered digests and stale revisions before applying changes — `src/resume_tailor_harness/workspace_agent/actions.py:resolve_plan` (commit `8ea111d7`).
- Name: Agent orchestration
  - Context: Bound agent tasks to verified procedures and recorded their identities.
  - Evidence:
    - Checked skill paths and hashes before enabling capabilities — `src/resume_tailor_harness/career_skills/registry.py:CareerSkillRegistry` (commit `08c42dc3`).
    - Saved the skill reference with extraction run metadata — `src/resume_tailor_harness/profile/project_extractor.py:build_project_extractor_agent`.
    - Tested revalidation of a changed skill before reuse — `tests/test_career_skill_registry.py:test_registry_revalidates_a_skill_after_the_file_changes`.
    - Exposed workspace reads and previews without an approval tool — `src/resume_tailor_harness/workspace_agent/runtime.py:WorkspaceTools.functions` (commit `9e18b568`).
- Name: Internationalization
  - Aliases: i18n
  - Context: Supported English and Chinese without changing stored values.
  - Evidence:
    - Selected and persisted the language — `web/src/i18n/index.ts:resolveInitialLanguage`, `web/src/i18n/index.ts:changeLanguage` (commit `fc2a4bbb` for initialization).
    - Tested language switching while preserving unsaved settings — `web/e2e/i18n-review.spec.ts:80` (commit `570191d4`).
    - Translated dynamic run error labels for display — `web/src/i18n/dynamic-labels.ts:localizeRunError` (commit `1df8e042`).

- Name: Data provenance
  - Context: Preserved cited evidence through extraction, merging, and publication.
  - Evidence:
    - Parsed skill contexts and citations while excluding fenced examples — `src/resume_tailor_harness/profile/dossier.py:parse_dossier` (commit `dd98ccf9`).
    - Linked retained applications to their source skills as project facts — `src/resume_tailor_harness/profile/dossier.py:retain_dossier_evidence`.
    - Tested evidence links across cached extraction and cross-project skill merges — `tests/test_profile_dossier.py:test_evidence_links_survive_cache_and_cross_project_skill_merge`.
    - Compared source fingerprints with the last publication to report changes — `src/resume_tailor_harness/profile/publication.py:publication_status` (commit `aaf59c62`).
    - Cleared stale assessments and evidence links after approved claim edits — `src/resume_tailor_harness/profile/conversation.py:apply_change` (commit `3056b869`).
- Name: Human-in-the-loop
  - Aliases: HITL
  - Context: Required review before applying workspace changes.
  - Evidence:
    - Tested previews neither apply changes nor expose approval — `tests/test_workspace_agent.py:test_tools_and_publishing_do_not_apply_changes` (commit `9e18b568`).
    - Rechecked digests and revisions, then saved an action receipt — `src/resume_tailor_harness/workspace_agent/actions.py:resolve_plan` (commit `8ea111d7`).
    - Tested receipt failure rolls back the domain effect — `tests/test_workspace_agent.py:test_effects_roll_back_if_receipt_transaction_fails`.

### Tooling

- Name: OpenAI API
  - Context: Adapted model construction and request settings.
  - Evidence:
    - Built Responses requests with explicit reasoning and output settings — `src/resume_tailor_harness/llm_runner.py:_build_openai_responses` (commit `75605133`).
    - Tested agents use the Responses endpoint — `tests/test_llm_runner_build_model.py:test_openai_agents_are_built_on_the_responses_endpoint`.
    - Tested provider-managed response state is disabled — `tests/test_llm_runner_build_model.py:test_openai_never_uses_provider_managed_response_state`.
    - Validated choice confidence and settled classification usage — `src/resume_tailor_harness/decisions.py:DecisionClient.choose` (commit `cb7d32ec`).
    - Priced classification input and cache at endpoint-specific rates — `src/resume_tailor_harness/tenancy/costs.py:calculate_cost` (commit `1be33451`).
- Name: Anthropic API
  - Context: Configured model-specific reasoning and search options.
  - Evidence:
    - Selected search tools by model generation — `src/resume_tailor_harness/llm_runner.py:anthropic_web_search_tool` (commit `a160f498`).
    - Tested forwarding of the prompt-cache option — `tests/test_llm_runner_build_model.py:test_anthropic_cache_flag_is_forwarded`.
- Name: Google Gemini
  - Aliases: Gemini
  - Context: Adapted requests and structured output across model generations.
  - Evidence:
    - Preserved dictionary and referenced item types in the adapter — `src/resume_tailor_harness/llm_runner.py:_compatible_gemini_class` (commit `4aa14a61`).
    - Selected generation-specific thinking settings — `src/resume_tailor_harness/llm_runner.py:_build_model_from_route`.
- Name: DeepSeek
  - Context: Adapted model responses and reasoning events to the runner.
  - Evidence:
    - Added a provider-specific response adapter — `src/resume_tailor_harness/llm_runner.py:_compatible_deepseek_responses_class` (commit `cdbe5c1d`).
    - Tested that streamed reasoning deltas are mapped — `tests/test_llm_runner_build_model.py:test_deepseek_maps_its_streamed_reasoning_deltas`.
- Name: AG-UI
  - Context: Streamed durable conversation events to the browser.
  - Evidence:
    - Mapped text, tool, reasoning, and terminal events while retaining replay cursors — `src/resume_tailor_harness/api/runs/agui.py:project_event` (commit `846dbb38`).
    - Parsed projected events on the browser side — `web/src/lib/chat/agui.ts:parseAguiEvent`.
    - Tested malformed events do not advance the replay cursor — `web/src/lib/chat/agui.test.ts:8-12`.
- Name: Stripe
  - Context: Integrated checkout and reconciled payment events.
  - Evidence:
    - Created checkout sessions through a gateway — `src/resume_tailor_harness/tenancy/payments.py:StripeGateway.checkout` (commit `b0f186c0`).
    - Read payment state and saved event receipts before ledger updates — `src/resume_tailor_harness/tenancy/payments.py:process_event`.
- Name: Gmail API
  - Context: Read mailbox history for resumable recruiting-mail analysis.
  - Evidence:
    - Staged history and message pages with saved cursors — `src/resume_tailor_harness/gmail/scan.py:MailboxScanner._stage_page` (commit `5d7a7670`).
    - Batched message reads and retried failed parts — `src/resume_tailor_harness/gmail/client.py:batch_read_messages`, `tests/test_gmail_client.py:test_batch_retries_only_failed_parts`.
    - Tested listing pages and deleted messages do not abort scans — `tests/test_gmail_client.py:test_listing_pages_and_deleted_message_do_not_abort_scan`.
- Name: Microsoft Graph
  - Context: Read mailbox delta pages while restricting continuation URLs.
  - Evidence:
    - Fetched and normalized mailbox pages — `src/resume_tailor_harness/mailboxes/microsoft.py:read_page` (commit `d4b8a43a`).
    - Validated continuation URLs before requests — `src/resume_tailor_harness/mailboxes/microsoft.py:_validate_graph_url` (commit `779e327a`).
- Name: IMAP
  - Context: Connected to mailboxes securely and resumed message reads.
  - Evidence:
    - Established TLS before login and selected folders read-only — `src/resume_tailor_harness/mailboxes/imap.py:open_mailbox` (commit `779e327a`).
    - Tested backfill, new arrivals, and mailbox identity changes — `tests/test_mailboxes.py:test_imap_backfill_new_arrivals_and_uidvalidity`.
- Name: Typst
  - Context: Built résumé templates and compiled page-bounded PDFs.
  - Evidence:
    - Defined a shared résumé template with density and section blocks — `templates/resume-base.typ:2-28`, `templates/resume-base.typ:145-225` (commit `8c7acdf2`).
    - Compiled and checked rendered pages — `src/resume_tailor_harness/render/renderer.py:render_pdf`.
    - Tested page-fit overflow and layout cleanup — `tests/test_visual_layout_review.py:test_overflow_is_diagnostic_and_bounded_and_temp_pdf_is_removed`.
    - Tested readable gaps across templates and densities — `tests/test_render_typography.py:test_readable_gaps_survive_every_template_and_density` (commit `580baab2`).
- Name: httpx
  - Context: Made bounded requests with explicit transport controls.
  - Evidence:
    - Streamed a pinned response with size and content-type checks — `src/resume_tailor_harness/security/outbound.py:fetch_public_bytes` (commit `df3cdf04`).
    - Disabled redirects and ambient proxies for mailbox reads — `src/resume_tailor_harness/mailboxes/microsoft.py:open_mailbox`.
- Name: Git
  - Context: Used history and tags to prepare releases.
  - Evidence:
    - Read commits since the prior version to determine a bump — `scripts/release.py:Repository.commits`, `scripts/release.py:infer_bump` (commit `f714f38f` for bump inference).
    - Created version tags for a selected commit — `scripts/release.py:GitHub.create_tag`.
