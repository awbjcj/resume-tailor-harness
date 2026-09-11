# Public job pages and boards

Add a public URL from the job importer or choose browser extraction when adding
a source. Known ATS URLs use their existing readers. A validated single posting
imports directly. A board opens a preview with up to three sample postings.

Review the full descriptions, locations, salary bands, and work arrangements.
Blank values mean unknown. Salary amounts retain their stated currency, period,
and original text. The app does not convert or annualize them. Source evidence
appears beside the preview and on imported jobs. Extraction conflicts require
review. The app does not resolve them automatically based on model confidence.

Job corrections and extraction rules have different scopes. Job corrections,
including explicit unknown values, persist independently of future observations.
Removing an override returns the field to its extracted value. The rule editor
can select inert text from a captured page or accept an advanced CSS selector.
Changed rules must be validated before approval. Approval saves the source and
selected sample jobs in one transaction. Stale draft or override revisions are
rejected.

Sources bind to the normalized full URL, preserving meaningful query parameters
and fragments. Several boards on one host can have separate configurations.
Source controls support re-pull, cache refresh, edit and preview, relearn,
enable or disable, and revision-history restore. Relearning proposes a draft and
does not replace approved rules. Layout failures retain affected jobs for review.

## Supported acquisition and limits

The renderer handles linked details, inline cards, detail panels, next or
numbered pagination, load-more controls, and bounded scrolling through declared
browser actions. It does not execute generated code. It supports public GET/HEAD
requests and narrowly classified JSON job-search POST requests. Login,
challenges, application submission, GraphQL, and unclassified write requests
are unsupported. Some public sites require manual import.

Defaults are 10 listing pages, 50 details, and 300 seconds per run. User
controls are capped at 50 pages, 200 details, and 900 seconds. Network requests
and response bytes have independent budgets. Shared installations allow two
browser workers. Page acquisition for a host runs one at a time, followed by at
least three seconds plus jitter, or a longer robots delay. Resource requests
within that acquisition share its lease. Robots failures stop acquisition;
404/410 allow it. Rate limits use bounded retries and Retry-After. Cancellation
and exhausted budgets terminate the child browser and preserve partial results.

The workspace caches detail snapshots and extractions for 24 hours. Expired
static pages with validators use conditional requests. Dynamic pages render again
because an unchanged HTML shell does not prove unchanged jobs. An explicit
refresh bypasses cached detail extraction. Incomplete pulls never close or delete
existing jobs. Existing application progress remains intact.

## Local and hosted runtime

Install the locked dependencies and Chromium with `uv sync --frozen` and
`uv run playwright install chromium` (Linux also needs Playwright's system
dependencies). `PUBLIC_BROWSER_ENABLED=true` enables the isolated importer;
`BROWSER_ENABLED` separately controls legacy browser connectors.

The Docker image installs Chromium. Run the application as its existing
unprivileged runtime user. Chromium's sandbox remains enabled. Hosts that cannot
provide it must report browser capability unavailable. The app has no no-sandbox
fallback. Docker requires user-namespace system calls permitted by the supplied
`deploy/playwright-seccomp.json`, derived from the official Playwright 1.62.0
[Docker profile](https://github.com/microsoft/playwright/blob/v1.62.0/utils/docker/seccomp_profile.json).
See also the [Playwright container instructions](https://playwright.dev/docs/docker).

The controlled capability probe runs without outbound network access:

```powershell
docker run --rm --network none --init --security-opt seccomp=deploy/playwright-seccomp.json --user resume-tailor-harness --mount "type=bind,source=$PWD/scripts,target=/checks,readonly" --entrypoint python resume-agent-non-ats:test /checks/check_public_browser.py
```

Verify sandbox and proxy-only acquisition on the actual deployment host before
enabling public browser use. A local Docker probe does not verify a Railway
deployment. The parent performs DNS-pinned public requests. The child routes
responses through that gateway, blocks service workers and WebSockets, and uses
a denying proxy for unhandled traffic. Browser fixtures cover private subresource
blocking, delayed rendering, cancellation, and process cleanup.

## Persistence and verification

Drafts, immutable source revisions, snapshots, observations, and overrides are
workspace database records. They survive restarts and full workspace backups.
Settings bundles export portable URL, rule, and limit definitions without
observations or job corrections. Unverified candidates are not re-exported.
Imported settings and legacy recipes remain disabled and unverified until
reviewed. Resetting the Sources settings section removes scrape configurations,
drafts, and caches while preserving evidence and corrections attached to existing
jobs. Account or workspace reset clears all associated scraping state. Snapshots
remain until reset. The 24-hour cache lifetime controls freshness, not automatic
deletion of evidence.

Run the ordinary backend and frontend suites plus
`RUN_PUBLIC_BROWSER_TESTS=1` with `tests/scraper/test_browser_worker.py` and
`tests/scraper/test_public_flow.py`. `web/e2e/public-scrape.spec.ts` verifies the
review at mobile and desktop widths. These controlled fixtures do not measure
accuracy on arbitrary live sites or live LLM providers.
