# Reliable public non-ATS URL imports

Date: 2026-09-05
Status: Written specification approved by the user on 2026-09-05.

## Outcome and approved scope

Users can import a public job posting or register a public job board in both
local and hosted installations. Dynamic rendering and Agno-assisted extraction
recover the actual posting structure and fields. Board registration includes an
editable extraction preview, explicit approval, and a persistent configuration
bound to the board URL. Subsequent pulls reuse approved configuration and retain
manual corrections. Accuracy takes priority over throughput.

Support static pages, JavaScript results, linked details, inline details,
detail panels, numbered/next pagination, load-more controls, and infinite scroll.
Do not automate login, solve access challenges, submit applications, or bypass
access restrictions. Existing known-ATS readers remain the preferred route.

## Current implementation and gaps

- `discovery/url_ingest/service.py` uses deterministic readers and an LLM
  fallback. Browser escalation depends on a short-text shell heuristic, which
  can miss missing job content on pages with substantial navigation text.
- `ExtractedJob` and `RawJob` carry company, title, location, and description;
  salary and work policy are recovered downstream from description text.
- `discovery/scraper/learn.py` already uses Agno structured output to learn CSS
  recipes. Listing-only learning can guess unseen detail structure. A nonempty
  description selector currently bypasses richer field extraction.
- Recipe schema requires a pagination mode even for unpaginated boards. The
  cache and scrape-source identity use host-level keys.
- Unknown source detection ends at `ATS_NOT_DETECTED`. Scrape preview validates
  URL/browser configuration without proving that jobs can be extracted.
- `AddUrlDialog` imports immediately. `AddSourceDialog` provides verification,
  but does not expose a complete scrape configuration and correction workflow.
- The current Docker image disables browsers and does not install Chromium.

## Architecture and alternatives

Extend the existing learn-and-replay pipeline. Fixed site selectors alone do not
meet dynamic site coverage; unrestricted browser agents on every pull make
behavior and resource use harder to control. Use deterministic execution of
validated plans, with bounded model assistance to propose or repair those plans.

Responsibilities:

1. **Public page acquisition:** guarded HTTP first, then Playwright when posting
   content, controls, or required detail structure cannot be recovered. Evaluate
   content sufficiency, not just total text length. Preserve structured data
   before pruning HTML; capture final URL and a bounded source snapshot.
2. **Page understanding:** classify single posting, listing, empty listing,
   blocked page, or unrelated content. Identify cards, stable detail identities,
   detail views, and optional navigation. Return schema-validated declarations.
3. **Plan validation/execution:** resolve selectors against observed pages,
   inspect representative detail views, and test navigation progress. Execute
   only application-owned actions: navigate, open detail, expand description,
   next/load-more, scroll, and close detail. Never execute model-generated code.
4. **Field extraction:** use supported JobPosting metadata and visible job
   content, with Agno extraction when deterministic evidence is insufficient.
   Preserve source evidence and conflicts instead of trusting schema validity
   or a model's confidence score as proof of factual correctness.
5. **Review/persistence:** save editable drafts, approved immutable revisions,
   extraction observations, and independent per-job field overrides.
6. **Ingestion:** feed validated jobs through existing identity, source-priority,
   relevance, and tracking rules without resetting application progress.

Use existing AgentRunner/expect_schema, configured model selection, tenant
context, cancellation, and spend governance. Treat all page content as untrusted
data. Reuse agents within a run; bound model input, output, and call count.

## User workflows

### Add a board

Unknown public URLs offer browser extraction. Analysis creates a draft and
shows up to three distinct job details, selecting different visible layouts
where possible. A board with fewer jobs previews all available jobs. Report
observed results as a sample, never an exhaustive board count.

The preview includes editable job fields, source snippets, missing/conflicting
field indicators, navigation outcome, and crawl limits. Users can distinguish
“edit this job” from “change extraction rule.” A field rule editor supports
selecting an observed element, inspecting its text, and an advanced selector
input. Rule changes must be revalidated on the samples before approval.

Approval atomically saves the URL-bound configuration and selected corrected
sample jobs. Remaining discovery happens in subsequent pulls. Show which sample
jobs will be imported and which rules will be reused before approval. An empty
board may be saved as an unverified source but must not acquire an approved
extraction recipe until a real posting has been validated.

### Add one job

Single-job URLs continue to import directly when validation succeeds. The result
exposes source evidence, unknown fields, and editable corrections. A listing URL
entered here offers the board-preview flow rather than merging many postings
into one description. Uncertain identity or an invalid description requires
review before creating a job. Users can also open the review before import.

### Re-pull and configuration editing

The UI offers reuse, edit-and-preview, and relearn. Re-pulls use the approved
revision. A proposed repair never silently replaces it. Layout or field-evidence
failures mark affected results for review; validated unaffected jobs may proceed.
Every result identifies its configuration revision and extraction outcome.

Partial/throttled/blocked/failed runs remain distinguishable from a verified
empty listing. Show discovered, inspected, imported, duplicate, filtered,
review-needed, and failed counts separately. Do not infer disappearance or close
jobs from an incomplete crawl.

## Field contract and correctness

Preserve full meaningful description content rather than a summary, including
requirements and compensation/work-arrangement sections. Capture:

- Title, company, source URL, application URL, and source posting identifier.
- Multiple locations and their original text.
- Salary minimum/maximum, currency, period, and original compensation text;
  preserve multiple location-dependent bands instead of inventing one range.
- Remote, hybrid, onsite, or unknown; geographic restrictions and stated office
  attendance requirements are separate from the work-policy category.
- Employment type and posted/closing dates when explicitly supported.

Missing facts are null, with “not stated” distinct from extraction failure.
Preserve literal unknown corrections as explicit overrides. Do not infer onsite
from a street address or remote from an online application process. Do not
annualize salary or convert currency at extraction time. Each non-null extracted
field links to a snapshot and source snippet/structured-data path. Conflicting
structured and visible evidence is retained and flagged for review.

Automatic acceptance requires an evidenced title and recoverable substantive
description belonging to that job. Reject navigation, access pages, generic
company prose, and combined descriptions from unrelated cards. Missing optional
facts alone must not reject an otherwise valid posting.

## Persistent state and compatibility

Store state in tenant-confined durable storage using the repository's workspace
persistence conventions; ephemeral browser files are never authoritative.

- **Source configuration:** normalized submitted URL, observed final URL,
  revision, approval state, page/detail rules, optional pagination (including
  none), crawl limits, and last validation outcome.
- **Extraction observation:** stable job identity, configuration revision,
  timestamp, extracted values, evidence references, and validation result.
- **Manual override:** stable job identity, field, value (including explicit
  null), revision, and timestamp. Removing an override is a separate operation
  from setting an unknown value.

Normalize scheme/host case and default ports. Preserve path, meaningful query
parameters, and SPA route fragments; remove only recognized tracking parameters.
Do not merge distinct hosts or board paths. Redirects are observed aliases and
must not silently rebind an approved source. Multiple board URLs per host work.

Prefer explicit posting IDs, otherwise validated canonical detail URLs. Inline
jobs require a stable observed identifier; ambiguous identities require review
and must not attach old overrides by title alone. Existing cross-source dedup
remains authoritative when connecting observations to a canonical job.

Apply manual overrides over new observations. Changed source values under an
override generate a conflict for review, not an automatic replacement. Equal-tier
pulls currently preserve first-seen data: observations must therefore persist
independently of ingest no-ops. Once a job advances past raw, preserve frozen
description and existing tailored artifacts; new source content is reviewable
without implicitly re-basing them. Explicit corrections follow the existing
job-edit/invalidation contract and never reset status or delete artifacts.

Approval uses revision checks to reject stale drafts and is atomic with sample
ingestion. Repeated approval is idempotent. Retain prior approved revisions for
rollback. Back up/reset/export the new state with its tenant workspace. Migrate
legacy host recipes as unverified candidates for each matching configured URL;
do not treat old cache entries as user-approved rules.

## Local and hosted browser execution

Use the same extraction pipeline and capability reporting in both modes. Local
execution uses isolated browser contexts without reusing logged-in profiles.
Hosted execution requires Chromium/system dependencies in the image and a
bounded browser worker process, isolated from API request handling. Persist
review state before releasing worker resources; close contexts on cancellation,
timeouts, and failures. An unavailable worker returns a specific capability
error rather than “no jobs.” Deployment itself is outside this design task.

All browser traffic, including redirects, frames, scripts, and background
requests, must satisfy the public-network boundary. Use an enforcing egress
proxy/gateway with validated DNS pinning, not merely a pre-navigation URL check.
Block direct browser egress that bypasses it and disable service workers.
Reject private/link-local/metadata destinations. HTTP fetches continue through
`security/outbound.py`. Preserve browser sandboxing; do not solve hosted startup
issues by disabling it. Isolate tenant cookies, caches, snapshots, and job state.

## Conservative crawl policy

Default per-pull ceilings are 10 listing pages, 50 distinct detail inspections,
and five minutes of total elapsed time, including delays. A first listing counts
as one page; inline/panel inspections count toward the detail ceiling. Preview
uses at most three details and shares the same host scheduling policy.

Expose limits in the source UI; users may lower or raise them within operator
caps. Initial operator caps are 50 listing pages, 200 details, and 15 minutes.
Increases do not weaken access or pacing rules. Enforce one active page acquisition
per host across tenants/workers, coordinated by shared leases. Maintain a minimum
three-second gap plus zero-to-two-second jitter between top-level page/detail
acquisitions and result-changing actions; honor any longer explicit crawl delay.

Page assets required for accurate rendering are separately bounded; do not delay
every script by three seconds and break rendering. Block unnecessary media and
known tracking requests, cap concurrent subrequests at four per host, and apply
rate-limit backoff to all traffic. Preserve CSS and content-bearing scripts.
Initial page budgets are 200 requests and 20 MiB transferred; exceeding either
produces a partial result rather than an unbounded retry.

Respect robots.txt for each fetched origin with an identifiable crawler user
agent. Cache successful robots decisions for up to 24 hours. Missing robots
(404/410) permits crawling; access denial, server errors, or unavailable policy
pause that origin with a visible reason. Honor Retry-After. Without it, back off
30 seconds then 60 seconds, with at most two retries within the run deadline.
Stop on access challenges or persistent throttling; never rotate identities to
evade limits. Retry budgets include model repair: at most one proposed plan
repair per run, never automatic adoption of a changed approved plan.

Deduplicate before detail acquisition, reuse tenant-scoped cached responses,
and use conditional requests where supported. Reuse unchanged evidence hashes
to avoid repeated LLM extraction. Use a 24-hour detail cache by default; explicit
refresh revalidates it under the same pacing rules. Do not skip a known job
forever when its cached observation needs refreshing. Stop pagination when no
new stable identities appear. Never claim complete coverage after reaching a
limit or encountering unverified navigation.

## Integration boundaries

Extend `discovery/url_ingest`, `discovery/scraper`, and source services with
focused acquisition, plan validation, observation, and override interfaces.
Extend extraction-to-ingestion contracts so structured facts survive instead of
being available only through appended description text. Reuse downstream
location/salary/work-policy normalization without losing original evidence.

Use the existing Run substrate for analysis and pull progress. Add draft review,
rule revalidation, approval, revision retrieval, and override mutation endpoints
under existing API conventions. Retain existing single-job route behavior for
valid callers. Update `AddSourceDialog`, `AddUrlDialog`, source controls, job
correction surfaces, OpenAPI, and generated TypeScript together. All new states
need accessible labels and project localization coverage.

## Acceptance and verification

1. Static and JavaScript fixtures extract title/full description and all stated
   fields exactly, including separate location-based salaries and remote limits.
2. Navigation-heavy shells still escalate to rendering when job content is absent.
3. Linked, inline, and panel detail fixtures and all pagination modes work;
   duplicate loops terminate and unpaginated boards need no invented control.
4. Listing-only guesses cannot approve unseen detail selectors. Wrong-job text,
   absent title, and conflicting evidence produce reviewable failures.
5. Users correct sample values and extraction rules, revalidate, approve, restart,
   and re-pull with the saved rules and overrides intact.
6. Two URLs on one host retain distinct configs; tenants cannot access one
   another's drafts, evidence, revisions, caches, or overrides.
7. Source changes under overrides create conflicts. Equal-tier ingest and frozen
   descriptions preserve tracking IDs, progress, and existing artifacts.
8. Stale/concurrent approvals fail safely; repeated approval imports no duplicate
   jobs. Legacy recipe migration is repeatable and preserves old configuration.
9. Local and actual container-browser tests use controlled public-page fixtures
   to verify worker lifecycle, cancellation, rendering, and persistence.
10. Network tests verify robots decisions, pacing across workers, request/byte
    caps, redirects, DNS rebinding defenses, subresource blocking, Retry-After,
    and no bypass to private destinations.
11. End-to-end UI tests cover editing, validation errors, approval, reuse,
    relearning, unknown fields, conflicts, partial results, and capability errors.
12. Run repository Python/frontend checks and generated-contract drift checks.
    Deterministic fixtures establish regression correctness. Optional public-site
    smoke tests use the same pacing and report observed coverage only; no claim
    of universal site support or measured LLM accuracy without evidence.

## Delivery boundary

This specification changes no runtime behavior. After written-spec approval,
create the implementation plan using the requested brainstorming workflow's
writing-plans skill. Implementation branches originate from dev and PRs target
dev. Hosted deployment and public-site credentials are not implicit prerequisites
for the design or deterministic tests.
