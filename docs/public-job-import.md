# Public job pages and boards

Add a public URL from the job importer or choose browser extraction when adding
a source. Known ATS URLs retain their existing readers. A validated single posting
imports directly; a board opens a preview with up to three sample postings.

Review the full descriptions, locations, salary bands and work arrangements.
Blank values mean unknown. Salary amounts retain their stated currency, period
and original text; they are not converted or annualized. Source evidence is
available beside the preview and on imported jobs. Extraction conflicts require
review instead of being silently resolved by model confidence.

Job corrections and extraction rules have different scopes. Job corrections,
including explicit unknown values, persist independently of future observations.
Removing an override resumes using extracted values. The rule editor can select
inert text from a captured page or accept an advanced CSS selector. Changed rules
must be validated before approval. Approval saves the source and selected sample
jobs in one transaction. Stale draft or override revisions are rejected.

Sources bind to the normalized full URL, preserving meaningful query parameters
and fragments. Several boards on one host can have separate configurations.
Source controls offer re-pull, cache refresh, edit-and-preview, relearn, enable or
disable, and revision history/restore. Relearning proposes a draft; it does not
replace approved rules. Layout failures retain affected jobs for review.

## Supported acquisition and limits

The renderer handles linked details, inline cards, detail panels, next/numbered
pagination, load-more controls and bounded scrolling using declared browser
actions. It does not execute generated code. Public GET/HEAD requests and narrowly
classified JSON job-search POST requests are supported. Login, challenges,
application submission, GraphQL and unclassified write requests are unsupported.
Some public sites therefore require manual import.

Defaults are 10 listing pages, 50 details and 300 seconds per run. User controls
are capped at 50 pages, 200 details and 900 seconds. Network requests and response
bytes have independent budgets. Shared installation leases limit browser workers
to two and serialize page acquisition per host, followed by at least three seconds
plus jitter (or a longer robots delay). Resource requests within an acquisition
share that lease. Robots failures stop acquisition; 404/410 allow it. Rate limits
use bounded retries and Retry-After. Cancellation and exhausted budgets terminate
the child browser and preserve partial results.

Detail snapshots and extractions are cached for 24 hours in the workspace.
Expired static pages with validators use conditional requests. Dynamic pages
are rendered again because an unchanged HTML shell does not prove unchanged jobs.
Explicit refresh bypasses cached detail extraction. Incomplete pulls never close
or delete existing jobs. Existing application progress remains intact.

## Local and hosted runtime

Install the locked dependencies and Chromium with `uv sync --frozen` and
`uv run playwright install chromium` (Linux also needs Playwright's system
dependencies). `PUBLIC_BROWSER_ENABLED=true` enables the isolated importer;
`BROWSER_ENABLED` separately controls legacy browser connectors.

The Docker image installs Chromium. Run the application as its existing
unprivileged runtime user. Chromium's sandbox remains enabled: hosts that cannot
provide it must report browser capability unavailable. There is no no-sandbox
fallback. Docker requires user-namespace system calls permitted by the supplied
`deploy/playwright-seccomp.json`, derived from the official Playwright 1.62.0
[Docker profile](https://github.com/microsoft/playwright/blob/v1.62.0/utils/docker/seccomp_profile.json).
See also the [Playwright container instructions](https://playwright.dev/docs/docker).

The controlled capability probe can run without outbound network access:

```powershell
docker run --rm --network none --init --security-opt seccomp=deploy/playwright-seccomp.json --user resume-tailor-harness --mount "type=bind,source=$PWD/scripts,target=/checks,readonly" --entrypoint python resume-agent-non-ats:test /checks/check_public_browser.py
```

Verify sandbox and proxy-only acquisition on the actual deployment host before
enabling public browser use. A local Docker probe is not Railway deployment
verification. The parent performs DNS-pinned public requests; the child routes
responses through that gateway, blocks service workers/WebSockets and uses a
denying proxy for unhandled traffic. Browser fixtures cover private subresource
blocking, delayed rendering, cancellation and process cleanup.

## Persistence and verification

Drafts, immutable source revisions, snapshots, observations and overrides are
workspace database records and survive restarts/full workspace backups. Settings
bundles export portable URL/rule/limit definitions, without observations or job
corrections. Imported settings and legacy recipes remain disabled and unverified
until reviewed. Account/workspace reset clears the associated scraping state.
Snapshots currently remain until reset; the 24-hour cache lifetime is freshness,
not automatic deletion of evidence.

Run the ordinary backend/frontend suites plus
`RUN_PUBLIC_BROWSER_TESTS=1` with `tests/scraper/test_browser_worker.py` and
`tests/scraper/test_public_flow.py`. `web/e2e/public-scrape.spec.ts` verifies the
review at mobile and desktop widths. These controlled fixtures do not measure
accuracy on arbitrary live sites or live LLM providers.
