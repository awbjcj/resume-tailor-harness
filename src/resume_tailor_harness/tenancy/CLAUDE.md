# Tenancy developer reference

Migrated from the project root `CLAUDE.md` (2026-08-15, CLAUDE.md split) — loads only when working under `src/resume_tailor_harness/tenancy/`.

### Tenancy context (ADR-0003)

Multi-user state rides a `contextvars.ContextVar` holding the active
`UserContext` (`tenancy/context.py`). Its set-points are the API dependency,
`RunManager.submit` (which copies the caller context into its worker), and the
CLI callback (`--user`). The Workspace layout is named once: the relative-path
constants (`FACTS_PATH`, `SEARCH_PATH`, `CONNECTORS_PATH`, `REVIEW_PATH`,
`REVIEW_DEEP_PATH`, `TELEMETRY_PATH`, `SKILL_ALIASES_PATH`) live in
`tenancy/paths.py`, and `resolve_tenant_path` rebases them into the active
Workspace at the leaves — so callers pass defaults, not hand-threaded absolute paths. `get_settings()` returns effective request settings or
environment settings and must never be cached across requests. System tables
use separate SQLAlchemy metadata and never appear in workspace databases.
Session cookies and PATs resolve only to that context. Short-lived query tokens
are purpose-bound to SSE or selected downloads and are never accepted as
general API authorization. Limits use `NULL = system default` and `0 =
unlimited`; admins and calls made with a user's own provider key are exempt from
shared-key budget enforcement. Admin user deletion evicts open workspace
engines before a staged, rollback-safe removal.

---

### Registration modes and platform spend governance (ADR-0009)

`Settings.registration_mode` (`closed` / `invite` / `open`) is a business
decision independent of shared-key eligibility. `User.shared_key_access`
(`auth_register.py`, `auth_google.py`) defaults to `True` for every new
account, invited or self-registered — there is no `open_signup_shared_keys`
setting; ADR-0009's Consequences section records that the original
per-signup-path default was superseded once the signup-rate limit
(`Settings.global_daily_signup_limit`), per-member allowance, and the
platform-wide monthly cap (below) became the actual Sybil-multiplication
controls. An admin can still flip `shared_key_access` off per user through the
admin-users API.

- `api/attempts.py::consume_global_signup` is an atomic (`BEGIN IMMEDIATE`),
  rolling-24h counter independent of per-email/per-IP attempt budgets, capping
  total verification emails sent per day (`Settings.global_daily_signup_limit`)
  regardless of how many distinct emails/IPs originate them.
- **Spend policy has one seam.** `tenancy/spend.py` owns key and endpoint
  selection plus shared-funding eligibility. In `enforce` mode it rechecks
  database eligibility per call so concurrent consumption, subscription expiry,
  revocation and top-ups are visible across requests. The phase-local TTL cache
  is retained only in `shadow` mode. `AgentRunner.arun` runs blocking gate and
  settlement work through `asyncio.to_thread`. Key changes still wait for a
  shared model's in-flight calls to finish.
- **Subscription terms are finite.** `tenancy/subscriptions.py` applies audited,
  idempotent activation, renewal and revocation under `BEGIN IMMEDIATE`.
  Active renewals extend expiry without resetting usage; expired terms restart
  now. `quotas.py` expires terms before reads/charges, restores FREE, and keeps
  durable credits. Legacy manually assigned tiers remain recurring until
  explicitly migrated. New periods record `ALLOWANCE_GRANT` ledger entries.
- **Usage is accounting, not best-effort telemetry.** `usage.record_call` writes
  the response receipt, all per-model usage/line items, and deductions in one
  transaction. Stable response run IDs are tenant-scoped and repeat-safe;
  conflicting payloads fail. Persistence failures roll back and surface an
  error. `charge_in_session` owns allowance-first, then credit, then overage
  allocation. Gateway credentials belong to the platform and are billable;
  genuine BYOK remains exempt. Hosted mode defaults to `enforce`, while an
  explicit `shadow` setting remains available for migration.
- `tenancy/limits.py::enforce_agent_budget` runs before every LLM call
  (`llm_runner.py`'s `AgentRunner.run`/`arun` and direct transcription), and
  delegates to `SpendGate`. A
  non-admin account without `shared_key_access` is rejected when its resolved
  provider has no per-user key. In `shadow` mode, the legacy rolling token
  guard remains active while calls dual-record exact token metrics and USD
  micro-cost. In `enforce` mode, an exact active rate is required before a
  shared-key call, user cost allowance and credit balances are checked, and a
  platform-wide UTC calendar-month shared-key cost is checked against
  `Settings.global_monthly_cost_quota_micros`. **Administrators are exempt
  from the per-user allowance and remain bound by the platform-wide cap.**
  That asymmetry is the design, not an oversight: the per-user allowance
  protects the platform's budget _allocation_, the platform cap protects its
  _absolute_ spend, and an operator with unbounded absolute spend is exactly
  the failure the cap exists to prevent. `global_monthly_cost` and
  `global_weekly_usage` therefore sum **every** shared-key `UsageEvent`, admin
  rows included — neither joins `User`. ADR-0009's Amendment 2 and ADR-0010
  record this; ADR-0009's first amendment describes the superseded exemption
  and is marked as such. Pinned by
  `tests/tenancy/test_cost_quotas.py::test_admin_usage_counts_toward_global_cost_quota_for_other_users`.
  BYOK calls retain token and estimated-cost analytics but have zero quota
  charge.
- Open self-registration additionally seeds lower active-job and concurrency
  ceilings (`open_signup_max_active_jobs`,
  `open_signup_max_concurrent_runs`). Its legacy token override is retained
  only for stage-one rollback and stops controlling access after cost
  enforcement is enabled.
