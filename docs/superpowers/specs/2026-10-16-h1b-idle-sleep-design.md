# H-1B idle sleep with SQLite retained

Date: 2026-10-16 (America/New_York)

Status: Written design awaiting user review. The user approved the direction
"Keep SQLite and let H-1B sleep when idle." This document does not record an
implementation, deployment, or measured saving.

## Intent and scope

Reduce the total hosting bill for the resume app and its H-1B data service.
The user explicitly chose the lowest total bill over moving storage to a new
provider. Preserve existing data, tenant isolation, H-1B evidence semantics,
and the resume app's scheduled work. A slower first H-1B lookup after inactivity
is the accepted trade-off.

Keep both SQLite stores and their Railway volumes. Enable Railway Serverless
only for `h1b-job-search-mcp`, after making wake-up reliable. Keep
`resume-tailor-harness` continuously available because its Gmail sync and
reminder loops run inside the application process. No Supabase project,
PostgreSQL migration, object-storage layer, new worker, or recurring wake-up
request is part of this design.

Success means the H-1B service demonstrably sleeps without requests, wakes
through its existing private connection, and returns the same results from
the same cached data. Savings must be measured after rollout; they are not an
acceptance claim based only on a configuration toggle.

## Current evidence

Read-only inspection found the following production resources:

| Resource | Identity or location |
| --- | --- |
| Railway project | `resume-tailor-harness`, `121b62b6-b581-4478-9c92-54b3fa993059` |
| Environment | `production`, `94880fae-d0fa-4c7c-8bc5-9b781bc7f855` |
| Resume service | `d6581b90-64d0-4794-a701-337602bde104` |
| H-1B service | `abc99b4c-63a1-46cf-9788-e1fe9a5b0d72` |
| H-1B volume | `8ef1ef82-4e5a-4e92-b0a6-fd445f09b6ae`, mounted at `/app/data_cache` |
| Resume volume | `/app/data` |
| Existing H-1B connection | `http://h1b-job-search-mcp.railway.internal:8080/mcp` |

The connection was verified through a filtered CLI read: H-1B is enabled,
uses `streamable-http`, and has no deployment timeout override. The current
code default is 30 seconds. Credentials were not printed or saved. Both
services have one replica and deploy from their respective `main` branches.
The H-1B service has no public domain; adding one is unnecessary.

Seven-day Railway metrics gathered during discovery give these monthly
projections at published RAM, CPU, and volume rates:

| Service | Average RAM | Average CPU | Average disk | Compute/month | Disk/month |
| --- | ---: | ---: | ---: | ---: | ---: |
| Resume app | 0.3028 GB | 0.001709 vCPU | 0.4270 GB | $3.06 | $0.06 |
| H-1B | 0.0813 GB | 0.001829 vCPU | 2.2113 GB | $0.85 | $0.33 |

These are sampled resource projections, not invoices. They exclude egress,
backups, account minimums, and other projects. The H-1B compute estimate is
the approximate maximum avoidable cost at this workload; actual savings will
be lower because requests and startup still consume compute. Volume charges
continue while sleeping. Account minimums may prevent a lower invoice.
Zero public HTTP metrics for H-1B do not establish zero usage: its caller uses
private networking.

The code already uses disk-backed SQLite queries with bounded caches. The
remaining wake-up issues are specific:

- `h1b/mcp.py::h1b_tools` attempts connection once. A transient startup failure
  becomes unavailable evidence through the existing service failure path.
- `server_lifespan` starts `cache_recent_data` in the background. It checks DOL
  before activating a cached dataset, although the volume survives a restart.
- `/health` reports process liveness immediately, with `status=degraded` until
  a dataset is loaded. HTTP 200 alone does not prove data readiness.

## Alternatives considered

1. Keep both services continuously running. This has the least complexity and
   remains the rollback state, but retains idle H-1B compute charges.
2. Keep SQLite and let H-1B sleep. Selected because it targets compute without
   introducing a paid storage service or changing data ownership.
3. Migrate to an external managed database. Rejected for this cost objective:
   it requires SQLite and tenancy changes while the current combined disk
   projection is only about $0.40/month. Free-tier limits and paid service
   costs would become additional operating constraints.

## Design

### 1. Railway owns sleeping and waking

Use the supported service-instance Serverless setting for H-1B only. Railway
documents outbound-traffic-based inactivity, normally sleeping after roughly
5-10 minutes, and wake-up on requests from the same project's private network.
There is no application timer that stops the process, and no keep-alive cron.
Local cache cleanup may continue while the process is awake; it makes no
network requests.

The setting takes effect on a newly deployed container. Read back both the
setting and the live deployment after applying it. Do not add an undocumented
`sleepApplication` property to `railway.json`; use Railway's supported
service settings/API. Inspect pending environment changes immediately before
rollout so unrelated changes are not included.

Keep the existing private endpoint, port, volume, region, and replica count.
The normal private route must pass a real sleep/wake test before release is
considered successful. Failure of that route triggers rollback rather than
creating a public endpoint as an implicit workaround.

### 2. Serve valid cached data before refreshing DOL

Add a focused startup operation in the H-1B data manager that examines local
quarterly `.sqlite` files newest first and activates the newest valid store
using the existing schema and metadata validation. It performs no HTTP calls,
pickle conversion, pruning, or full-dataset materialization. Invalid files
are skipped and reported without deleting or replacing them. A failed
candidate must not replace a valid selected store.

Default queries must use that validated cached selection until refresh
establishes a newer usable period. They must not immediately select a corrupt
newer file again solely because its filename sorts last. This fallback does
not claim the selected cache is the latest period published by DOL.

Run this operation off the event loop as the first step of startup warmup.
Then run the existing best-effort six-quarter refresh. Preserve the existing
period-selection and per-period locks, importer subprocess, atomic database
replacement, bounded query caches, and six-quarter retention policy.

With a usable local store, health can become ready without waiting for DOL.
This means "a validated cached dataset is available," not "DOL freshness has
been confirmed." Keep returned fiscal periods and source provenance accurate.
Do not mark a cached period as newly confirmed from DOL. During startup
refresh, `get_available_data` must return its known local metadata promptly
instead of starting a duplicate synchronous discovery request; an unknown
published latest period remains unknown until discovery succeeds.

With no valid local store, retain the existing degraded startup and download
behavior. Do not represent missing data or an incomplete import as zero
filings. Keep explicit data refresh and force-download behavior available.
No new recurring refresh loop is introduced.

This first change does not redesign the import locking scheme. A new-quarter
refresh can still delay queries. Test that cached wake-up stays within the
caller budget with the normal populated cache. If lock contention or refresh
time makes that fail, leave Serverless disabled and revise this design before
adding a larger import-concurrency change.

### 3. Retry connection establishment within a fixed budget

Keep transport handling in `src/resume_tailor_harness/h1b/mcp.py`, before the
agent and any billable research work begin. For `streamable-http`, allow at
most three connection attempts, with waits of 1 and 2 seconds between them.
The existing `h1b_mcp_timeout_seconds` bounds the entire connection sequence,
including attempts and waits, rather than being multiplied by retries. Each
attempt receives at most 10 seconds and at most the remaining total budget.
Use monotonic time and interruptible async waits.

Retry only identifiable transient connection failures: connection refusal or
reset, connection/read timeout during initialization, and HTTP 502, 503, or
504. For exception groups, retry only when every underlying failure is in
that transient set. Authentication, invalid configuration, unsupported
protocol, invalid payload, and unknown exceptions fail immediately.
Cancellation always propagates immediately.

Construct a fresh toolkit for each attempt. Preserve the existing lifecycle
contract: a toolkit whose `connect` failed owns its partial cleanup; the
application closes successfully connected toolkits exactly once on the same
event loop. Verify that behavior against the installed Agno transport in
tests so retries do not leak connections or mask the original failure.

Do not retry the research agent, replay completed tool calls, or change LLM
retry policy. Local `stdio` keeps its existing single-attempt behavior. After
exhaustion, retain the existing unavailable-evidence path and its short TTL;
do not turn startup failure into a successful "no filings" result. Logs record
attempt number and failure category without URLs containing secrets or raw
provider payloads.

After successful initialization, normal tool calls continue to use the full
configured operation timeout. Failed connection attempts must not reduce the
timeout on the connected toolkit's later tool calls.

### 4. Preserve the resume application's existing behavior

The resume service stays awake. Gmail sync, reminders, user databases,
authentication, billing, and run recovery are outside the change. Existing
cached H-1B evidence remains the display source, with the same freshness and
tenant isolation rules. No new frontend flow or setting is needed; the
deployment-owned timeout already expresses the operator's wait budget.

## Verification and release requirements

Offline tests must demonstrate:

- Transient HTTP initialization failures followed by success yield one
  connected toolkit, bounded delays, and one successful close.
- Permanent errors, unknown errors, cancellation, and exhausted time budgets
  do not spin or retry indefinitely. Exception groups retain classification.
- `stdio` lifecycle behavior, tool allowlist, and result-size limits remain
  unchanged. No failed attempt invokes an agent or tool.
- The operation timeout after successful connection remains the configured
  value; connection-budget enforcement does not leak into research execution.
- Valid cached SQLite becomes available while DOL requests are delayed or
  failing. Startup skips a corrupt newer file safely and handles an empty
  cache as degraded. A default query after skipping a corrupt newer file
  still succeeds against the validated cache. Health and period metadata
  remain truthful.
- Cached search, company statistics, six-quarter trends, and result ordering
  match the pre-change behavior for identical fixture data.
- Existing import interruption tests continue to prove that a committed store
  survives and incomplete `.building` files are never served.

Use the focused H-1B suites in both repositories, then their required Python
checks. Run the H-1B service's full suite for its startup changes. There is no
frontend or API-schema change that justifies regenerating web contracts.

Before enabling Serverless, complete any initial dataset build with sleeping
disabled and verify the expected production cache is usable. A local query or
import that emits no network traffic is not guaranteed protection from the
platform's inactivity detector merely because it consumes CPU. Keep sleep
disabled for maintenance imports known to exceed the idle window; never add
network keep-alives just to work around this.

Deployment order:

1. Deliver tested caller connection handling through this repository's
   required feature branch -> `dev` -> `main` path.
2. Deliver tested H-1B startup handling through that repository's verified
   branch/PR workflow. Resolve its rules before implementation; do not assume
   this repository's `dev` branch exists there.
3. Verify both live versions and cached query parity while H-1B is awake.
4. Enable H-1B Serverless and deploy that setting. Verify the existing volume
   is still attached and the resume service's sleep setting is unchanged.
5. Let traffic settle without polling the service endpoint. Observe sleeping
   through Railway's control-plane status, allowing at least 15 quiet minutes
   as a validation window rather than claiming a strict platform deadline.
6. From the resume deployment, make a direct allowlisted MCP query to the
   existing private endpoint. This avoids an unnecessary paid LLM call. Record
   wake duration, connection attempts, successful result, and fiscal period.
   Require completion inside the configured connection budget and operation
   timeout, and compare with the awake baseline.
7. Verify it can return to sleep and the resume app's scheduled work remains
   enabled. Record deployment IDs, setting state, and test evidence.

Compare an equivalent post-change usage window with the seven-day baseline,
including restart compute and network usage. Distinguish projected resource
savings from actual invoice changes. Do not claim savings until measured.
This design does not create a recurring monitor or authorize automatic
future messages.

## Rollback

Disable H-1B Serverless and deploy the setting if private wake-up fails,
requests regularly exceed the wait budget, refresh interruption becomes a
problem, or startup overhead negates savings. Confirm the service is awake
and a cached query succeeds. Leave SQLite and the mounted volume intact.
The caller retries and cached-startup changes can remain if healthy; revert
their source changes through the normal release process if they are the
cause. No database restore or schema rollback is required.

## Sources and implementation locations

Platform documentation checked during design:

- [Railway Serverless](https://docs.railway.com/deployments/serverless)
- [Railway service API](https://docs.railway.com/integrations/api/manage-services)
- [Railway volumes](https://docs.railway.com/volumes/reference)
- [Railway pricing](https://docs.railway.com/pricing/plans)

Repository evidence and expected change boundaries:

- Resume app: `src/resume_tailor_harness/h1b/mcp.py`,
  `tests/test_h1b_mcp.py`, `tests/test_h1b_service.py`, and
  `docs/deploy-railway.md`.
- H-1B service in `D:/Fun/h1b-job-search-mcp`: `src/server.py`,
  `src/disclosure_store.py` for existing validation semantics,
  `tests/test_server.py`, and `docs/memory-architecture.md`.
- Existing resume app scheduling: `src/resume_tailor_harness/api/app.py`,
  `gmail/scheduler.py`, and `services/reminder_scheduler.py`.

The next stage is user review of this written spec, followed by a separate
implementation plan and execution-method selection under the invoked
brainstorming workflow.
