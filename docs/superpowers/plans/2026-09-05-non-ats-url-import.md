# Public non-ATS URL Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver accurate public-page job imports and editable, approved, reusable URL-bound board extraction in local and hosted installations.

**Architecture:** Extend learn-and-replay with evidence-bearing observations, versioned review state, and an application-controlled browser executor. Store approved sources and jobs in the same tenant database transaction; use a separate shared host scheduler for courteous network access. Reuse existing Run, AgentRunner, tenancy, ingestion, and generated API contracts.

**Tech Stack:** Python, Agno, Pydantic, SQLModel/SQLAlchemy, SQLite workspace/system databases, Playwright Chromium, FastAPI, React, TypeScript, Vitest, pytest, Docker.

**Spec:** `docs/superpowers/specs/2026-09-05-non-ats-url-import-design.md` (approved).

## Global Constraints

- Accuracy takes priority over throughput.
- Missing facts are null, with “not stated” distinct from extraction failure.
- Default per-pull ceilings are 10 listing pages, 50 distinct detail inspections, and five minutes of total elapsed time, including delays.
- Initial operator caps are 50 listing pages, 200 details, and 15 minutes.
- Preview uses at most three details and shares the same host scheduling policy.
- Maintain a minimum three-second gap plus zero-to-two-second jitter between top-level page/detail acquisitions and result-changing actions; honor any longer explicit crawl delay.
- Initial page budgets are 200 requests and 20 MiB transferred; exceeding either produces a partial result rather than an unbounded retry.
- Use a 24-hour detail cache by default; explicit refresh revalidates it under the same pacing rules.
- Do not automate login, solve access challenges, submit applications, or bypass access restrictions.
- Existing known-ATS readers remain the preferred route.
- Never execute model-generated code. No direct browser egress outside the public-network gateway.
- Keep descriptions frozen beyond raw for this new automatic observation path. Preserve progress and artifacts; explicit application Redo remains separate.
- Work branches originate from dev; PRs target dev. Do not push or deploy as part of this plan without user instruction.

## Execution conventions and file map

Read root `CLAUDE.md` and nested discovery, connectors, security, tenancy, API,
services, and tracking references before their tasks. Repository facts can drift:
use the named symbols, not assumed line numbers. Run commands from the repository
root unless explicitly prefixed with `npm --prefix web` or a web working directory.

This is one connected feature with twelve independently testable tasks. Keep
unfinished entry points disabled until their dependencies pass. Do not split it
into unrelated redesigns or replace the existing Run substrate.

New production modules (all under `src/resume_tailor_harness/`):

| Module | Responsibility |
| --- | --- |
| `discovery/scraper/contracts.py` | Evidence, observations, drafts, plan and result schemas |
| `discovery/scraper/identity.py` | URL/config and observed-job identities |
| `discovery/scraper/tables.py` | Tenant SQLModel tables, no I/O |
| `discovery/scraper/store.py` | Transactional draft/revision/observation/override persistence |
| `discovery/scraper/pacing.py` | Shared leases, robots decisions, budgets, retry policy |
| `security/browser_gateway.py` | Bounded binary responses through pinned public egress |
| `discovery/scraper/browser_worker.py` | Isolated browser lifecycle and declared actions |
| `discovery/scraper/understand.py` | Page classification and plan proposals |
| `discovery/scraper/validate.py` | Evidence, identity, and selector validation |
| `discovery/scraper/extract.py` | Structured/visible fact reconciliation |
| `discovery/scraper/replay.py` | Bounded list/detail navigation and cache reuse |
| `services/scrape_review.py` | Draft analysis, approval, and correction use cases |
| `services/scrape_ingest.py` | Observation-to-existing-ingestion adapter |
| `api/schemas/scrape.py`, `api/routers/scrape.py` | CamelCase API DTOs and thin routes |

New frontend modules live in `web/src/features/sources/scrape/`: `ScrapePreview.tsx`,
`ScrapeJobEditor.tsx`, `ScrapeRuleEditor.tsx`, `ScrapeLimits.tsx`, and `use-scrape.ts`.
Job corrections live in `web/src/features/job/SourceCorrections.tsx`.

Every task below has a red/green check and a narrow commit. Test snippets express
specific regression assertions; include their imports and setup in the named
files. For each listed matrix, add parametrized cases alongside the snippet.
Never replace network-enforcement or restart tests with only mocked success.

## Task 1: Define field, evidence, plan, and identity contracts

**Files:** Create `discovery/scraper/contracts.py`, `identity.py`; modify existing
`discovery/scraper/recipe.py`, `discovery/url_ingest/models.py`; create
`tests/scraper/test_contracts.py`, `test_identity.py`.

**Interfaces:** `normalize_board_url(url: str) -> str`; `board_key(url: str) -> str`;
`observed_job_key(source_id: str, posting_id: str | None, canonical_url: str | None) -> str | None`.
Export the Pydantic models below; all schemas forbid extra fields. Use repository
Job types at adapters rather than changing their existing enums globally.

- [ ] Add models with these exact fields and meanings:

```python
class CrawlLimits(BaseModel):
    listing_pages: int = Field(default=10, ge=1, le=50)
    detail_pages: int = Field(default=50, ge=1, le=200)
    elapsed_seconds: int = Field(default=300, ge=1, le=900)

class SalaryBand(BaseModel):
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    currency: str | None = None
    period: str | None = None
    locations: list[str] = Field(default_factory=list)
    raw_text: str

class JobFacts(BaseModel):
    title: str | None = None
    company: str | None = None
    jd_text: str | None = None
    locations: list[str] | None = None
    salary_bands: list[SalaryBand] | None = None
    remote_policy: Literal['remote', 'hybrid', 'onsite'] | None = None
    remote_restrictions: str | None = None
    attendance: str | None = None
    employment_type: str | None = None
    posted_at: str | None = None
    closes_at: str | None = None
    source_url: str
    application_url: str | None = None
    posting_id: str | None = None
```

Define `FieldName` as the literal union of JobFacts fields. `Evidence` holds
`field: FieldName`, `snapshot_id`, exact `quote`, optional `selector`, optional
`json_path`. `FieldIssue` holds `field` and `kind` (not_stated, extraction_failed,
conflict, invalid_evidence). `Observation` holds `id`, optional `job_key`,
`source_id`, `revision`, `facts`, `evidence`, `issues`, and `accepted: bool`.
`Snapshot` holds `id`, requested/final URLs, HTML, visible text, JSON-LD values,
and fetched timestamp; IDs are content hashes including final URL.

Define `FieldRule(field, selector, attribute)` with text extraction when attribute
is null. `BoardPlan` has card selector, field rules, detail mode (link, inline,
panel), optional link/open/close/detail selectors, and pagination mode (none,
numbered, next, load_more, infinite) plus optional control selector. Validate
required selectors by mode. No arbitrary scripts, regex programs, or tools.
`PageUnderstanding` has kind (posting, listing, empty_listing, blocked, unrelated),
optional plan, and evidence references. `ValidationResult` has `valid` and issues.
`PullReport` has terminal reason, seven distinct counters from the spec, and
observations. `Draft` has ID, source ID, URL, integer revision, plan, limits,
samples, validation result, and state. `ApprovalResult` has source ID, approved
revision, and imported job IDs. `OverridePatch` has field/value/expected revision.

- [ ] Write tests before implementation:

```python
def test_distinct_boards_keep_query_and_spa_route():
    assert board_key('https://example.com/jobs?team=a') != board_key('https://example.com/jobs?team=b')
    assert board_key('https://example.com/#/jobs') != board_key('https://example.com/#/internships')

def test_unknown_policy_is_not_onsite():
    facts = JobFacts(source_url='https://example.com/jobs/1')
    assert facts.remote_policy is None
    assert facts.salary_bands is None
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/scraper/test_contracts.py tests/scraper/test_identity.py -q`; expect missing symbols initially.
- [ ] Implement IDNA host normalization, default-port removal, known tracking-parameter removal, SHA256 URL keys, and stable posting IDs scoped to sources. Retain query order and SPA fragments; never merge ambiguous inline jobs by title. Cover all plan modes and salary/null round trips.
- [ ] Re-run to green, then `git add` only these six files and commit `feat: define evidence-bearing scrape contracts`.

## Task 2: Persist review revisions and overrides in the tenant transaction

**Files:** Create `discovery/scraper/tables.py`, `store.py`; modify `tracking/migrate.py`,
`db.py`, `discovery/scraper/recipe_store.py`; create `tests/scraper/test_review_store.py`.

**Interfaces:** `ScrapeStore(session: Session)` with `save_draft(draft: Draft) -> Draft`,
`get_draft(draft_id: str) -> Draft`, `approve(draft_id: str, expected_revision: int) -> Draft`,
`save_observation(value: Observation) -> None`, `set_override(job_key: str, patch: OverridePatch) -> int`,
`remove_override(job_key: str, field: FieldName, expected_revision: int) -> int`,
`effective_facts(observation: Observation) -> JobFacts`. Methods flush, never commit.

- [ ] Add a file-backed database test that saves a draft and explicit-null override,
  disposes the engine, reopens the database, and asserts the override still wins.
  Add two-session stale revision tests and tenant database isolation.

```python
assert store.effective_facts(observation).remote_policy is None
with pytest.raises(RevisionConflict):
    store.approve(draft.id, expected_revision=draft.revision - 1)
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/scraper/test_review_store.py -q`; expect missing store/tables.
- [ ] Create tables for source, source revision, draft, snapshot, observation,
  job binding, override revision, and approval receipt. Store typed JSON payloads
  with schema version; use unique source URL keys, revision keys, and draft
  approval IDs. Compare-and-swap revisions in SQL; raise `RevisionConflict` on
  zero updated rows. Keep prior override revisions after removal. Snapshot and
  observation inserts are idempotent by ID. Never use process locks for DB integrity.
- [ ] Add idempotent migration from host recipe candidates without approval and
  without deleting the legacy file. Expose source state even when invalid recipes
  cannot migrate; preserve the migration reason for review.
- [ ] Run tests to green and existing `tests/scraper/test_recipe_store.py`,
  `tests/test_migrate.py`; commit `feat: persist scrape review revisions and corrections`.

## Task 3: Enforce shared pacing, robots decisions, and budgets

**Files:** Create `discovery/scraper/pacing.py`; modify `tenancy/system_db.py`,
`tenancy/migrate_system.py`; create `tests/scraper/test_pacing.py`.

**Interfaces:** `HostScheduler(engine: Engine, clock: Callable[[], float])`;
`acquire(host: str, owner: str, deadline: float) -> HostLease | None`;
`release(lease: HostLease, delay: float) -> None`; `renew(lease: HostLease) -> bool`.
`HostLease` holds host, owner, fencing token, expires_at. `CrawlBudget(limits: CrawlLimits)`
exposes `charge_listing()`, `charge_detail()`, `charge_request(byte_count: int)`,
and `check_deadline()`; raises `BudgetExceeded(reason: str)`. `RobotsDecision`
holds allowed, delay_seconds, expires_at, and reason.

- [ ] Write concurrent independent-engine tests using one file-backed shared DB:

```python
first = scheduler_a.acquire('example.com', 'a', deadline=100)
assert first is not None
assert scheduler_b.acquire('example.com', 'b', deadline=100) is None
scheduler_a.release(first, delay=3)
assert scheduler_b.acquire('example.com', 'b', deadline=100) is None
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/scraper/test_pacing.py -q` red.
- [ ] Implement system-DB host leases (local mode uses one installation scheduler
  DB, never each tenant DB). Use DB atomic acquisition, monotonic elapsed budgets,
  wall-clock lease expiry, renewal and fencing. A lost lease cancels acquisition;
  never permit an old worker to release a newer lease. Persist cooldowns.
- [ ] Add robots fetch/cache via existing public egress; 404/410 allow, unavailable
  or denied policy pauses, successful policy caches 24 hours. Apply rules per
  fetched origin/path including redirected targets. Implement seconds and HTTP-date
  Retry-After, longer crawl delays, 30/60-second fallback and two retries total.
- [ ] Test injected clocks/jitter, dead worker recovery, 50/200/900 caps, 200
  requests/20 MiB per acquisition, four asset slots, cancellation during waits,
  and no counting retries outside the elapsed budget. Re-run green and commit
  `feat: enforce shared courteous crawl budgets`.

## Task 4: Add a browser response gateway with no direct egress

**Files:** Create `security/browser_gateway.py`; modify `security/outbound.py`;
create `tests/test_browser_gateway.py`; retain `tests/test_security_outbound.py`.

**Interfaces:** `BrowserRequest(url: str, method: str, headers: dict[str, str], body: bytes | None)`;
`BrowserResponse(status: int, headers: dict[str, str], body: bytes, final_url: str)`;
`BrowserGateway.fetch(request: BrowserRequest, budget: CrawlBudget) -> BrowserResponse`.
Gateway constructor receives HostScheduler and isolated tenant cache storage.

- [ ] Add tests with injected DNS/transport recording validated and connected IPs:

```python
with pytest.raises(ValueError, match='public HTTP'):
    gateway.fetch(BrowserRequest('http://169.254.169.254/', 'GET', {}, None), budget)
assert transport.connections == []
```

Keep the existing outbound ValueError contract instead of introducing a second
trust boundary.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_browser_gateway.py -q` red.
- [ ] Extend the existing pinned transport with a bounded binary response path
  for HTML, JavaScript, CSS, fonts, and JSON; preserve existing text-only caller
  limits. Revalidate and pin every redirect. Cap compressed and decoded bytes,
  strip hop-by-hop headers, preserve content semantics, and prohibit credentials
  crossing origins. Apply robots/pacing/cache policy before outbound I/O.
- [ ] Allow GET/HEAD and bounded, observed read-only JSON search requests; reject
  forms, uploads, mutations, unclassified POSTs, and application submission.
  Read-only POST endpoints require explicit declarative request classification
  from observed search actions, restricted URL/body schema, and no credentials.
  Unsupported access patterns produce a visible partial result.
- [ ] Test rebinding, IPv4/IPv6, redirects to private hosts, oversized chunked and
  compressed bodies, incorrect MIME, 429 assets, cache revalidation, and tracking
  asset suppression. Re-run both test files green; commit
  `feat: broker browser requests through pinned public egress`.

## Task 5: Run a bounded isolated browser locally and in the image

**Files:** Create `discovery/scraper/browser_worker.py`; modify `Dockerfile`,
`container_runtime.py`, `discovery/url_ingest/browser.py`; create
`tests/scraper/test_browser_worker.py`, `tests/integration/test_scrape_browser.py`.

**Interfaces:** `BrowserWorker` is a context manager exposing
`snapshot(url: str, budget: CrawlBudget) -> Snapshot` and
`act(action: BrowserAction, budget: CrawlBudget) -> Snapshot`.
Define `BrowserAction(kind, selector=None, url=None)` in contracts; kind is the
spec's closed action set. Worker IPC transports these validated declarations,
not browser objects or executable source. `BrowserCapability` holds available/reason.

- [ ] Write lifecycle tests asserting context closure on deadline/cancellation,
  service-worker blocking, popup/frame interception, and deny-by-default routes.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/scraper/test_browser_worker.py -q` red.
- [ ] Configure fresh, sandboxed Chromium and an isolated context per run. Route
  every HTTP(S) request through Task 4 and fulfill its response. No `continue_`
  escape path. Close WebSockets; disable downloads, service workers, QUIC and
  background network features. Use a deny-all browser proxy with no loopback
  bypass as a second barrier to unhandled traffic. Verify the barrier with real
  browser probes; do not equate request routing alone with full isolation.

```python
browser = playwright.chromium.launch(chromium_sandbox=True, proxy=deny_proxy)
context = browser.new_context(service_workers='block', accept_downloads=False)
context.route('**/*', fulfill_from_gateway)
context.route_web_socket('**/*', lambda ws: ws.close())
```

The named proxy config and handler are private worker implementations, initialized
before any page. Implement explicit teardown and subprocess termination after a
bounded grace period. If the OS/container cannot enforce the sandbox and network
barrier, capability is unavailable; never silently weaken it.
- [ ] Install locked-version Chromium and system libraries in Docker; run the
  browser as non-root with needed sandbox support. Keep API startup independent
  of worker availability and cap workers at two per installation by default.
  Verify local Windows and hosted container paths use the same protocol.
- [ ] Add real-browser fixture tests for routing, blocked private subresources,
  direct egress probes, worker restart, and cancellation. Fixture transport is
  injected only in test construction, with no production private-host allow flag.
- [ ] Re-run unit tests, existing `tests/test_browser_capability.py`,
  `tests/test_container_runtime.py`, and integration tests with Chromium installed;
  commit `feat: run isolated public-page browser workers`.

## Task 6: Learn page structure and validate it against actual details

**Files:** Create `discovery/scraper/understand.py`, `validate.py`; modify
`learn.py`, `recipe_parse.py`; create `tests/scraper/test_understand.py`,
`test_plan_validation.py`, fixtures `dynamic_board.html`, `panel_board.html`,
`empty_board.html`, `blocked_board.html`, `mixed_layout_board.html`.

**Interfaces:** `understand(snapshot: Snapshot, agent: Runner) -> PageUnderstanding`;
`validate_plan(plan: BoardPlan, listing: Snapshot, details: list[Snapshot]) -> ValidationResult`;
`validate_evidence(observation: Observation, snapshots: list[Snapshot]) -> ValidationResult`.

- [ ] Add deterministic fake-runner tests for every page kind, no-pagination
  boards, unsupported actions, and description selectors absent from detail pages:

```python
result = validate_plan(plan, listing, details=[wrong_detail])
assert result.valid is False
assert any(issue.kind == 'invalid_evidence' for issue in result.issues)
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/scraper/test_understand.py tests/scraper/test_plan_validation.py -q` red.
- [ ] Use existing AgentRunner/expect_schema and prompt guidance with untrusted
  page boundaries. Preserve JSON-LD before pruning. Bound each snapshot input to
  60,000 characters with deterministic relevant-region selection and a truncation
  indicator. Do not invent off-screen selectors; ask the executor for observed
  detail snapshots first. Classify missing dynamic job content independently of
  header/footer length. Require observed evidence for empty vs blocked.
- [ ] Resolve each rule on up to three distinct details and varied layouts.
  Verify identity alignment and navigation progress; absent optional fields are
  not structural failure. Distinguish a broken selector from a field not stated.
  Reject any plan depending on inferred selector/code execution.
- [ ] Test malformed/error model responses, prompt injection, stale selectors,
  truncated evidence and one-repair ceiling. Re-run green; commit
  `feat: validate learned boards against observed details`.

## Task 7: Extract grounded structured job facts without losing prose

**Files:** Create `discovery/scraper/extract.py`; modify `url_ingest/llm.py`,
`url_ingest/ats_readers.py`, `connectors/base.py`, `discovery/extract.py`;
create `tests/scraper/test_evidence_extraction.py` and field-specific fixtures.

**Interfaces:** `extract_observation(snapshot: Snapshot, source_id: str, revision: int, agent: Runner) -> Observation`;
`reconcile_facts(structured: Observation, visible: Observation) -> Observation`.
Extend RawJob with optional `observation_id` using a default to retain caller compatibility.

- [ ] Add an exact-field test with two locations/two salary bands, remote-region
  restriction, and full description; assert unknown values stay null:

```python
assert observation.facts.salary_bands[0].period == 'hour'
assert observation.facts.salary_bands[0].minimum == Decimal('40')
assert observation.facts.remote_policy is None
assert observation.facts.jd_text == expected_full_description
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/scraper/test_evidence_extraction.py -q` red.
- [ ] Read matching JobPosting JSON-LD and visible detail/sidebar content. Scope
  multiple JobPosting objects by stable identity, never choose the first blindly.
  Use the same typed extraction path for boards and individual URLs. Preserve
  description HTML as cleaned Markdown without substituting an LLM summary.
- [ ] Verify literal quotes/JSON paths against snapshots and type-normalize only
  evidenced values. Contradictions remain issues with both evidence alternatives.
  No title/description or ambiguous identity means accepted=false. Persist
  original salary/date/location values even when downstream normalizers cannot
  represent every alternative. Cap extraction at one call per new detail plus
  existing transient retries governed by budget; reuse agents and content hashes.
- [ ] Add tests for wrong-job JSON-LD, sidebar salary loss, generic company text,
  missing optional fields, impossible ranges, and unsupported remote inference.
  Re-run with `tests/url_ingest` green; commit `feat: preserve grounded job facts from public pages`.

## Task 8: Replay approved plans with refresh and truthful outcomes

**Files:** Create `discovery/scraper/replay.py`; modify `dashboard.py`,
`url_ingest/fetch.py`, `url_ingest/service.py`; create `tests/scraper/test_replay.py`.

**Interfaces:** `replay(draft: Draft, worker: BrowserWorker, store: ScrapeStore, agent: Runner, *, preview: bool = False, refresh: bool = False) -> PullReport`.
Consume Tasks 1–7; return observations even when ingestion will be a no-op.

- [ ] Write tests for next/load-more/infinite loops with repeated IDs and budget
  termination, and changed detail layout without configuration replacement:

```python
assert report.terminal_reason == 'partial_limit'
assert report.inspected <= 50
assert approved_revision_after == approved_revision_before
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/scraper/test_replay.py -q` red.
- [ ] Execute only declared actions, close panels before continuing, count first
  page and inline inspections, resolve links against each current final URL,
  and halt repeated identities. Hold host leases across page acquisition and
  load completion; reserve action pacing before result-changing clicks.
- [ ] Cache tenant snapshots for 24 hours, conditional-refresh expired entries,
  and bypass extraction for unchanged hashes. Separate seen-job identity from
  refresh eligibility so existing jobs can produce new observations.
- [ ] Emit complete, empty, partial_limit, throttled, blocked, review_required,
  failed, cancelled, or capability_unavailable reasons with separate counters.
  At most one repair proposal; persist it as a draft. Never silently adopt it or
  mark jobs closed because a crawl stopped. Surface native unsupported read paths.
- [ ] Re-run tests plus `tests/scraper/test_dashboard.py`, `tests/url_ingest/test_fetch.py`;
  commit `feat: replay approved scrape plans with bounded refresh`.

## Task 9: Approve drafts atomically and connect observations to ingestion

**Files:** Create `services/scrape_review.py`, `services/scrape_ingest.py`;
modify `services/sources.py`, `services/discovery.py`, `discovery/ingest.py`,
`discovery/connectors/sources.py`; create `tests/test_scrape_review_service.py`.

**Interfaces:** `analyze_url(session: Session, url: str, limits: CrawlLimits) -> Draft`;
`revalidate_draft(session: Session, draft_id: str, expected_revision: int) -> Draft`;
`approve_draft(session: Session, draft_id: str, expected_revision: int, selected_keys: list[str]) -> ApprovalResult`;
`ingest_observation(session: Session, observation: Observation, store: ScrapeStore) -> int | None`.
Services own transactions; worker sessions use the existing Run launch seam.

- [ ] Add rollback tests injecting failure after the first selected job insert:

```python
with pytest.raises(InjectedFailure):
    approve_draft(session, draft.id, draft.revision, selected_keys)
assert persisted_approved_source_count == 0
assert persisted_sample_job_count == 0
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_scrape_review_service.py -q` red.
- [ ] Persist approved scrape sources in the tenant database, not YAML, so source
  approval, selected samples, bindings, and idempotency receipt share a transaction.
  Merge DB-backed scrape sources into existing list/pull services; other providers
  remain in YAML. Import legacy scrape targets transactionally as unverified DB
  sources and suppress their legacy list duplicates after successful migration.
- [ ] Use save_or_upgrade(commit=False); preserve canonical IDs and progress.
  Store every observation independently, including equal-tier no-ops. Bind
  manual corrections to resolved job identity; conflicting source facts create
  review issues. For this feature, rows beyond raw keep their description and
  derived facts until explicit user action. Never delete or rewrite artifacts.
- [ ] Resolve overrides into downstream extraction inputs so a later LLM cannot
  overwrite approved corrections. Explicit changes invalidate only dependent
  criteria/scoring under existing lifecycle rules; preserve status high-water
  marks. Reject identity collisions for manual title/company edits rather than
  transferring overrides to a different job. Permit clearing an override separately.
- [ ] Test idempotent approval, stale draft rejection, empty unverified source,
  two boards per host, raw vs progressed rows, sample deselection, canonical
  dedup binding, and persistent conflict indicators. Run existing source/ingest
  tests; commit `feat: approve reusable scrape sources atomically`.

## Task 10: Expose review APIs and include state in workspace lifecycle

**Files:** Create `api/schemas/scrape.py`, `api/routers/scrape.py`; modify
`api/app.py`, `api/routers/runs.py`, `api/schemas/sources.py`, `services/backup.py`,
`services/settings_bundle.py`, `settings_sections.py`; create
`tests/api/test_scrape_review.py`, `tests/test_scrape_transfer.py`; regenerate
`contracts/openapi.json`, `contracts/ts/api.ts`, `web/src/lib/api/schema.ts`.

**Interfaces:** Endpoints below use generated CamelModel DTOs and existing error
envelopes. No network work in request sessions.

| Route | Result |
| --- | --- |
| POST `/api/scrape/drafts` with URL/limits | 202 Run; result draftId |
| GET/PATCH `/api/scrape/drafts/{id}` | Draft; PATCH requires expectedRevision |
| POST `/api/scrape/drafts/{id}/validate` | 202 Run; result validated draftId/revision |
| POST `/api/scrape/drafts/{id}/approve` | ApprovalResult; expectedRevision/selectedKeys |
| GET `/api/scrape/sources/{id}/revisions` | approved and proposed revision summaries |
| POST `/api/scrape/sources/{id}/relearn` | 202 Run; new draft, original stays approved |
| POST `/api/scrape/sources/{id}/rollback` | new approved revision copied from validated prior revision |
| GET `/api/jobs/{id}/source-observations` | evidence, current overrides, conflicts |
| PUT/DELETE `/api/jobs/{id}/source-overrides/{field}` | revision-checked set/remove |

- [ ] Add API tests with another tenant's IDs (404), stale revision (409), invalid
  field/rule (422), unavailable browser capability, quota failure and cancelled Run.
  Assert non-ATS preview is never reported “verified” before detail validation.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/api/test_scrape_review.py tests/test_scrape_transfer.py -q` red.
- [ ] Add service-backed routes and existing run launch/session_work integration.
  Keep valid existing from-URL responses compatible; add optional result draftId
  for listing/review routing. Source output reports approval/validation state and
  limits. Add capability reporting without exposing implementation diagnostics.
- [ ] Full workspace backup includes DB state. Settings bundles serialize approved
  config revisions only (no job observations or overrides); strict import makes
  them unverified drafts. Section reset removes scrape configs/drafts and caches
  but preserves job observations/overrides attached to existing jobs. Full workspace
  reset removes all tenant state. Reject malicious selector payloads and unsafe URLs
  on import; retain rollback on failed replacement. Test each boundary.
- [ ] Regenerate on Windows and check drift:

```powershell
.venv/Scripts/python.exe scripts/export_openapi.py
npx.cmd --yes openapi-typescript contracts/openapi.json -o contracts/ts/api.ts
Copy-Item -LiteralPath contracts/ts/api.ts -Destination web/src/lib/api/schema.ts
.venv/Scripts/python.exe -m pytest tests/api/test_scrape_review.py tests/api/test_openapi_contract.py tests/test_scrape_transfer.py -q
```

- [ ] Commit only named API, lifecycle, test and generated files:
  `feat: expose scrape review and correction APIs`.

## Task 11: Build editable preview, rule selection, reuse, and corrections UI

**Files:** Create the five source components/hooks and SourceCorrections listed in
the file map, colocated `.test.tsx` files, and `web/e2e/scrape-review.spec.ts`;
modify `features/sources/AddSourceDialog.tsx`, `source-connection.ts`,
`SourcesPage.tsx`, `features/runs/AddUrlDialog.tsx`, `web/src/components/JobModal.tsx`,
and `web/src/i18n/resources.ts`. Mount corrections within the existing job modal;
do not introduce a duplicate job route.

**Interfaces:** `ScrapePreview({draftId: string, onApproved: (result: ApprovalResult) => void})`;
`ScrapeJobEditor({value: JobFacts, onChange: (value: JobFacts) => void})`;
`ScrapeRuleEditor({draft: Draft, onRuleChange: (rules: FieldRule[]) => void})`;
`ScrapeLimits({value: CrawlLimits, onChange: (limits: CrawlLimits) => void})`;
`SourceCorrections({jobId: number})`. Import API types from generated schemas.

- [ ] Add interaction tests for editing a salary to unknown, changing a selector,
  required revalidation, sample deselection and disabled stale approval:

```tsx
await user.click(screen.getByRole('button', { name: 'Change extraction rule' }))
await user.type(screen.getByLabelText('Selector'), '.job-location')
expect(screen.getByRole('button', { name: 'Approve and save' })).toBeDisabled()
```

- [ ] Run `npm --prefix web run test:run -- src/features/sources/scrape` red.
- [ ] Show source evidence next to fields, original units, multiple salary bands,
  nullable inputs, separate optional-field missing vs failed states, and sample
  selection. Render an inert sanitized snapshot tree with stable element IDs
  for element picking; never embed executable source HTML. Selector editing is
  advanced UI; no selectors or technical jargon in the default field editor.
- [ ] Make unsaved rule changes invalidate server validation and UI approval;
  request fresh validation before enabling approval. Show intended configuration
  and sample saves in the final action. Preserve edits across run progress and
  display revision conflicts without dropping the form.
- [ ] Add source reuse/edit/relearn/rollback, visible crawl-limit controls, clear
  partial results and safe cancellation. Single-job import exposes corrections
  and offers preview before importing; listing detection links to its draft.
  Job corrections distinguish explicit unknown from “use source value,” retain
  overrides on refresh, and display conflicting new source evidence for review.
- [ ] Localize strings, test keyboard-only element selection and 390px layout,
  and run `npm --prefix web run i18n:check`, focused Vitest and source tests green.
  Commit `feat: review and correct reusable public-page imports`.

## Task 12: Prove the complete flow and document operation

**Files:** Extend `tests/integration/test_scrape_browser.py`, create
`tests/integration/test_scrape_restart.py`, `scripts/check_scrape_browser.py`,
`docs/non-ats-imports.md`; modify `docs/deploy-railway.md`, `web/e2e/scrape-review.spec.ts`,
and `.github/workflows/_reusable-ci.yml`.

**Interfaces:** `scripts/check_scrape_browser.py` exits 0 only when the configured
worker passes sandbox/network capability checks and a controlled rendering check.
No private-network exception or external job-board crawling is enabled by this script.

- [ ] Write an integration test that opens a board, edits fields/rules, validates,
  approves, restarts API/worker, re-pulls changed fixtures, and verifies both saved
  rules and corrections with visible conflicts. Run it red before final wiring.
- [ ] Wire production entry points once prerequisites pass. Test two worker
  processes sharing host pacing and two tenants with independent caches/configs.
  Include rollback, invalid migration data, frozen description, and partial crawl.
- [ ] Build and inspect the real container; run its capability script as the
  runtime user with browser support enabled. If hosted sandbox support is absent,
  record the precise blocker and keep capability unavailable. Do not claim both
  execution modes are complete without actual browser evidence for each.
- [ ] Document supported public-page interactions, preview approval, rule/value
  correction semantics, limits, robots/throttling behavior, capabilities, data
  retention, restart persistence, and deployment configuration. Document that
  proxy-only network isolation must be verified on the target host; no no-sandbox
  fallback. Add a CI browser job using controlled fixtures and no provider keys.
- [ ] Run final checks once; broaden only on changed code or new failures:

```powershell
.venv/Scripts/python.exe -m pytest -q
uv run ruff check src tests evals
npm --prefix web run test:run
npm --prefix web run lint
npm --prefix web run build
.venv/Scripts/python.exe -m pytest tests/api/test_openapi_contract.py -q
git diff --check
```

From `web`, run `npx.cmd playwright test e2e/scrape-review.spec.ts e2e/sources.spec.ts`.
Run actual browser/restart integration separately if the normal suite excludes
integration markers. Report unavailable prerequisites distinctly from passing tests.
- [ ] Commit scoped documentation, integration and wiring files:
  `test: verify persistent non-ATS imports across browser runtimes`.

## Spec coverage and handoff

| Spec requirement | Tasks |
| --- | --- |
| Local + hosted public-page acquisition and network enforcement | 3, 4, 5, 12 |
| Classification and all list/detail/pagination modes | 1, 6, 8 |
| Full prose, grounded facts, unknowns and conflicting evidence | 1, 6, 7 |
| Editable preview, rule validation and atomic approval | 2, 9, 10, 11 |
| URL binding, multiple boards per host, stable job identities | 1, 2, 9 |
| Re-pull overrides, revision conflicts, frozen content and dedup | 2, 8, 9, 11, 12 |
| Courteous cross-user pacing, caching, robots and truthful partials | 3, 4, 8, 11 |
| Tenant isolation, migration, backup/reset/export and rollback | 2, 9, 10, 12 |
| API generation, accessibility, localization and lifecycle tests | 10, 11, 12 |

All tasks remain unchecked until executed. No runtime tests have been run merely
by writing this plan. Review each task against both this plan and the approved
spec; passing a narrow test is not a substitute for the acceptance matrix.
