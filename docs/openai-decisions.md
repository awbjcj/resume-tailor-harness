# Optional fast skill classification

Administrators can enable **Fast skill classification** on **Admin → Provider
routing**, enter a direct OpenAI API key, and save. Saving a key alone does not
enable the feature. It defaults to off, and turning it off retains the existing
classification behavior. Removing the key also requires disabling the feature.
Changes apply to newly started operations; running operations retain their
settings snapshot.

The dedicated `OPENAI_DECISIONS_API_KEY` is separate from `OPENAI_API_KEY`, member
keys and `SUB2API_OPENAI_KEY`. Calls use `gpt-6-luna` at the fixed
`https://api.openai.com/v1/decisions` endpoint, ignoring `OPENAI_BASE_URL` and the
general OpenAI route. Redirects and ambient HTTP proxies are disabled. Enabling
the feature authorizes direct API billing against that key's organization or
project balance. A ChatGPT/Sub2API subscription does not fund these calls.
Uncertain cases still use the configured ordinary model routes, so an operation
can incur both kinds of usage. The admin API never returns the stored key.

The feature sends skill names, the relevant group/domain catalog, and bounded
job excerpts used for disambiguation to OpenAI. It does not send entire resumes
or execute instructions contained in source text. Members cannot override the
feature or its key through workspace secrets or settings bundles.

## Quality and latency policy

- Personal profile groups use the user's full current catalog in batches of
  40. Manual corrections are excluded before dispatch. Only unresolved items
  go to the existing profile classifier. The existing revision check, lock and
  rollback remain the publication boundary.
- Fixed category classification uses the 20-category vocabulary. An incremental
  taxonomy pass first selects a category, then selects an existing specific
  domain from that category's **complete** directory. Calls contain at most
  60 questions and use the existing concurrency limit. A category with more than
  254 specific domains falls back rather than silently truncating its choices.
  General fallback buckets are never accepted as confirmed domains.
- The confidence floors are 0.90 for groups/categories and 0.95 for domains,
  with a minimum 0.20 probability margin over the next option. Each response is
  checked against the original question and its allowed choices. Refusals,
  duplicate/missing/malformed answers, low confidence, narrow margins, and
  `defer` choices use the standard classifier. These are conservative initial
  admission rules, **not calibrated accuracy guarantees**.
- Synonym canonicalization, new-domain creation, non-skill retirement, and
  premium recovery remain generative. Decisions cannot create domains, merge
  skills, retire skills, or overwrite explicit corrections. A category judgment
  alone never establishes domain membership or skill transferability.
- Transport failures open a circuit for the remainder of the operation and use
  the standard path. A request times out after 20 seconds without automatic paid
  retries. Large catalogs/payloads fall back. This limits outage overhead.
  Denied shared funding also skips the optional path; the standard classifier
  still enforces its own route and funding policy, including eligible BYOK.
- A taxonomy run probes its first batch before concurrent dispatch. If a batch
  of at least 20 skills confirms fewer than 20% of domains, subsequent batches
  use the standard classifier. This avoids repeatedly buying a fast pass that
  mostly defers. It is an initial yield heuristic, not a calibrated optimum.

Each Decisions request counts against the taxonomy operation's call and prompt
byte budgets. Valid siblings survive a deferred or failed generative fallback;
deferred items remain retryable. Recovery does not run Decisions again. The
fast path requires room for at least three calls (category, domain and
possible fallback); a nearly exhausted call budget goes to the standard path.
Oversized optional requests leave room for a smaller standard prompt, and
queued batches recheck call headroom before starting the fast path.
Choosing from a full category addresses the low top-16 recall in the live-data benchmark,
but an incorrect category can still reduce domain accuracy. Representative
human-reviewed labels are needed before claiming improved classification quality.

## Accounting and diagnostics

`SpendGate.open_decisions` uses the dedicated shared platform key and checks
eligibility on every call. Member allowances and the global platform cap still
apply; administrators remain subject to the global cap. Concurrent BYOK calls
cannot reclassify this usage as user-funded. Usage records include input,
cache-read and cache-write counts, zero output tokens and `reasoning_mode=decisions`.
The quota rate card lists this endpoint separately as `gpt-6-luna:decisions`.
This is an internal billing identity; requests and usage receipts retain the
native `gpt-6-luna` model ID. Both preflight and settlement require the endpoint's
rate, so an ordinary Luna rate cannot silently substitute for a missing one.
The Standard input/cache rates and zero output price are documented in
[cost quota operations](cost-quotas.md#openai-decisions-endpoint-2026-11-03).
Receipt IDs make settlement repeat-safe. Missing or incompatible receipts and
settlement failures are errors.

Run traces record separate `profile-groups-decisions`, `skill-categories-decisions`
and `skill-domains-decisions` families without prompt or completion text. Regroup
diagnostics include `decisionsCalls`, `decisionsChoicesAccepted` (category plus
domain choices, not unique skills), and `decisionsProviderFallback`.
`decisionsLowYieldBypass` identifies operations that switched to the standard
classifier after low domain yield.

The earlier live-data benchmark measured a 6–17× reduction in model-call wall
time with matched batches, but did not establish superior semantic accuracy.
Those figures do not measure this hybrid pipeline, its fallback rate, or total
Regroup latency. Direct Decisions was not the cheapest treatment for every task.
Actual cost depends on catalog size, fallback frequency, caching and the
deployment's existing subscription arrangement.

A smoke test of this adapter against the frozen production sample accepted
21 of 40 profile groups in 1.30 seconds. For 40 domain candidates, it accepted
18 categories and only one domain in 2.67 seconds. Three direct calls succeeded;
no assignments were published. This high fallback rate motivated the early
yield check. The smoke test did not run the generative fallback and cannot
establish an end-to-end speedup or classification accuracy.

Official references: [Decisions guide](https://developers.openai.com/api/docs/guides/decisions),
[request/response contract](https://developers.openai.com/api/reference/resources/decisions/methods/create),
[pricing](https://developers.openai.com/api/docs/pricing).
