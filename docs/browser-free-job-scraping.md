# Browser-free job scraping

Research and verification date: 2026-09-22.

## Findings from GitHub

| Project | Relevant implementation | Decision for this project |
| --- | --- | --- |
| [JobSpy](https://github.com/speedyapply/JobSpy) | Its [LinkedIn reader](https://github.com/speedyapply/JobSpy/blob/main/jobspy/linkedin/__init__.py) separates guest search cards from full posting requests, deduplicates results and bounds pagination. | Add bounded HTTP search/detail acquisition, preserve sidebar facts, and skip known jobs before fetching details. A card snippet is not a complete description. |
| [JobSpy Indeed](https://github.com/speedyapply/JobSpy/blob/main/jobspy/indeed/__init__.py) and [Glassdoor](https://github.com/speedyapply/JobSpy/blob/main/jobspy/glassdoor/__init__.py) | The search implementations depend on provider-specific GraphQL requests and headers; Glassdoor obtains a CSRF token. | Do not add this package as a second network stack. Its transport would bypass our egress boundary, and these private interfaces are not a verified public-access guarantee. Parse public posting markup when accessible; report denied access. |
| [Job-alert-bot](https://github.com/Esteban-PG/Job-alert-bot) | Groups company sources by ATS platform rather than maintaining one scraper per employer. | Keep the existing shared ATS detection and provider readers as the preferred company-board path. |
| [job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator/blob/main/scripts/scraper.py) | Implements separate HTTP adapters for Greenhouse, Lever, Ashby, Workday and other ATS families. | Preserve provider-specific normalization and full-detail acquisition; validate provider fields instead of imposing one universal HTML selector. |

These are architecture references, not dependencies or copied implementations.
Research included the upstream source files and the JobSpy Context7 documentation.
Upstream coverage claims were not used as measurements for this application.

## Acquisition and extraction

Set both `BROWSER_ENABLED=false` and `PUBLIC_BROWSER_ENABLED=false` for an
installation that must never launch a browser. No public API schema, package
dependency or user configuration file changes are required. The additive
cooldown table is created automatically in the shared system database.

* Existing ATS APIs remain the preferred path for company sources. Pasted ATS
  URLs can now resolve through their provider API even if the presentation-page
  HTTP request fails. A failed API lookup preserves the original fetch error.
* LinkedIn source pulls use the HTTP connector when `BROWSER_ENABLED=false`.
  Searches page through guest results and fetch complete details. Configured
  source limits, relevance filters and known-job skips apply. Acquisition uses
  the shared robots, pacing, timeout, retry and public-egress controls. The
  default result cap is 50; the safety ceiling is 200 details and 10 listing
  pages within 300 seconds. Browser-enabled source pulls retain their existing
  browser connector. Pasted LinkedIn URLs try HTTP first in either mode.
* Public source preview, validation, approval and refresh work over HTTP when
  browsers are disabled. Relative detail links, inline cards and real next-page
  hyperlinks reuse the existing evidence and review pipeline. The initial
  response is reused during preview. JavaScript panels, load-more buttons and
  scrolling report capability unavailable, retaining inspected jobs.
* Single-posting extraction recognizes schema.org JSON-LD arrays, `@graph`,
  `ItemList`, `mainEntity`, type arrays and explicit JobPosting microdata.
  Provider-scoped HTML selectors cover public LinkedIn, Indeed, Glassdoor and
  ZipRecruiter posting layouts. They are best-effort fallbacks, not a claim that
  those sites always serve public HTML.
* JSON-LD selection matches the posting URL, retaining identity query parameters
  such as Indeed's `jk` and Glassdoor's `jl`. It does not select the first
  recommended job on a page. Both `url` and `mainEntityOfPage` constrain selection;
  unmatched structured postings cannot bypass this check through LLM extraction.
  Ambiguous lists cannot become a single job.
* Descriptions retain sections and lists. Metadata includes all stated locations,
  compensation bands with currency and period, employment type, remote
  restrictions, dates and separately stated requirements. Hourly fractions are
  preserved. Estimated salary is not represented as employer-stated pay.
  Missing facts stay unknown; a metadata-only record is not a valid description.
* Structured review supports multiple salary bands and employment-type arrays
  with matching evidence. A schema-only detail does not require an invented DOM
  description selector. Existing conflicts still require review.

Legacy learned-browser dashboard recipes, Tesla's browser portal and Adzuna's
browser enrichment remain browser-dependent. Public sources saved through the
review flow use the new HTTP replay path. Pure JavaScript content without a
supported public API is still unsupported in HTTP-only mode.

## Live verification

The following read-only checks used the project's HTTP transports, no browser
and no LLM. These are point-in-time acquisition checks, not a statistical
field-accuracy benchmark or exhaustive coverage test.

| Source | Observation |
| --- | --- |
| OpenAI / Ashby | 810 board rows had titles and nonempty descriptions. Two individual URLs also returned matching titles and descriptions (7,046 and 4,133 characters). |
| Anthropic / Greenhouse | 618 board rows had titles and nonempty descriptions. Two individual URLs returned matching titles and descriptions (9,337 and 7,964 characters). |
| Zoox / Lever | 234 board rows had titles and nonempty descriptions. Two individual URLs returned matching titles and descriptions (4,991 and 5,457 characters). |
| NVIDIA / Workday | One matching posting returned title, provider company, location and 2,644 description characters. |
| Google Careers | One matching posting returned title, company, location and 3,618 description characters from the existing embedded-data connector. |
| LinkedIn guest search | Stopped: `robots.txt disallows this path` under the shared gateway policy. No jobs were returned or claimed. |
| Indeed, Glassdoor, ZipRecruiter | Each search-page HTTP probe returned 403 from this environment. Posting parser behavior is fixture-tested; live search coverage was not verified. |

Sample posting URLs used:

* [OpenAI technical program manager](https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3)
* [OpenAI research engineer](https://jobs.ashbyhq.com/openai/240d459b-696d-43eb-8497-fab3e56ecd9b)
* [Anthropic accommodations partner](https://job-boards.greenhouse.io/anthropic/jobs/5421031008)
* [Anthropic account executive](https://job-boards.greenhouse.io/anthropic/jobs/4461450008)
* [Zoox autonomy system test engineer](https://jobs.lever.co/zoox/f4746da4-8eb8-43e2-b7ce-bf3c7cf9640d)
* [Zoox safety reporting engineer](https://jobs.lever.co/zoox/e36cc53e-5bd5-43b9-9a90-ec9b7c6abda9)
* [NVIDIA Workday posting](https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Israel-Yokneam/Software-Engineer--SPE_JR2015623)
* [Google Careers posting](https://www.google.com/about/careers/applications/jobs/results/95424090398958278)

Closed or changed postings may stop resolving. Company ATS sources are the
verified option here; this change does not promise universal access to protected
aggregators or automatically substitute a different company's job.

## Blocked-source recovery and cooldowns

URL imports now attempt employer recovery after HTTP 401/403/429/503, an
access challenge, or an active source cooldown. Supply the existing company,
title and location import fields. Redo uses the saved job's identity, and
HTTP LinkedIn detail acquisition uses the search card's identity (at most
three recovery attempts per pull). A blocked search listing supplies no job
identity, so it reports the restriction without inventing replacement jobs.

Recovery uses one focused web search and inspects at most five leads through
the public HTTP gateway. Search snippets never supply the description. Only
recognized ATS hosts or a domain matching the company's normalized name are
eligible. Automatic recovery requires one candidate with matching company,
title and location, an explicit matching `hiringOrganization` in its posting
metadata, and a description of at least 200 characters. API readers augment
the employer description without a browser or LLM. Slug-derived company names,
missing locations, unreadable candidates and multiple matches require review.
Candidate links appear in the existing import/run error view; this is not a
new review queue. Importing a selected employer URL remains the manual path.

Title matching preserves meaningful punctuation, so C++, C# and C roles stay
distinct. Recovery keeps page-only salary and work-policy metadata alongside
the native ATS description. Access-challenge HTML never supplies job facts.

Recovered imports retain the employer apply URL. An unsuccessful recovery
leaves a saved job untouched. An explicit Redo updates the same job and records
the old and new URLs in its stage outcome; it retains the existing status.
No requisition-ID matching or general licensed-provider integration is included.

The shared system database stores hashed source keys, a bounded reason and a
retry timestamp. HTTP denial and challenge cooldowns default to one hour;
robots denials last 24 hours. Throttling honors `Retry-After`, bounded to one
minute through 24 hours. Path denials do not disable unrelated paths on a
shared ATS host; throttling pauses the origin. Query strings and tenant data
are not stored. These cooldowns cover public URL imports and the shared public
gateway; provider-native board API clients retain their existing retry policy.
Queued gateway workers recheck cooldowns after obtaining their host lease.

Recovery quality depends on search indexing and exact identity evidence.
This favors review over a false match and does not guarantee coverage of every
posting. The new recovery decisions are tested offline; the live acquisition
checks above predate this recovery feature.

## Regression checks

`tests/url_ingest/test_public_readers.py` exercises equivalent public job markup
on mainstream-board and employer URLs. Expected facts are declared in the
fixtures; no provider success rate is inferred from the hostname parameterization.
It also covers recommendation contamination, malformed metadata, compensation
precision, blocked pages and ATS API recovery.

`tests/scraper/test_http_worker.py` exercises HTTP-only pagination, partial
results, blocked/throttled responses and the analyze → approve → refresh service
flow, with browser startup made fatal. `test_linkedin_http.py` covers full
details, failures, deduplication, known-job skips, caps and registry routing.

Run the ordinary offline suite and lint:

```powershell
.venv/Scripts/python.exe -m pytest tests
.venv/Scripts/python.exe -m ruff check src tests evals
```
