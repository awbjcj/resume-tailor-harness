# Skill taxonomy recovery

The previous 300-skill escalation slice was alphabetical, so persistent early
failures could starve the rest. Each retry also repeated every member of every
domain. General placements were considered finished and could incorrectly
supply same-domain adjacency in career guidance.

## Recovery behavior

A refresh performs its incremental pass, then up to three recovery rounds.
Each round admits at most 300 canonical skills. Durable attempt counts give
least-attempted work priority; deferred skills retain their previous history.
Repeated attempts reduce batch sizes to a floor (15 -> 10 -> 10 by default).
Ordinary regrouping pauses a skill after three durable recovery attempts;
explicitly selecting that skill allows another bounded retry. A whole round
of provider errors stops recovery until the next run. Provider error envelopes
are failures, not classification judgments. Cross-batch reconciliation outages
retain already valid canonical heads instead of discarding successful work.

Recovery sees every domain ID, label and category, with up to eight deterministic
member examples per domain and total membership. Retrieval batches reuse a
context indexed once per pass. The provider seam, spend gate, tenant boundary,
concurrency limit, correction precedence and atomic commit remain in place.
When a database session is available, classification also receives up to two
bounded source excerpts per skill from active target jobs. Evidence follows
aliases to the canonical skill and only the current batch's evidence enters
its prompt. Job text is untrusted data, not instructions. The model must judge
the domain label and category, rather than copy historical misfiled examples.

## Accuracy and visibility

- Confirmed placement still requires high-confidence validation.
- Missing or malformed confidence is treated as low confidence. Valid peers in
  the same model batch remain usable; an uncertain item cannot silently inherit
  high confidence or cause the whole structured response to be discarded.
- General placements are provisional and eligible for later refinement. The UI
  shows their count and allows refinement when no unassigned skills remain.
- Retrieval rank alone cannot assign a category. Missing model category
  judgments use Other; existing provisional categories survive outages.
- General buckets never establish adjacency in match-gap or tailoring. Exact
  skill matches still work.
- Contradictory retirement and assignment in one answer is rejected.
- Retired aliases stay out of recovery and the remaining-unassigned count.
  Retirement remains reversible.
- User corrections remain authoritative.
- Obsolete failure records for already confirmed or retired skills are cleared
  on refresh, including records outside the requested scope. Unresolved and
  provisional history remains available for fair retries.

Complete visibility is distinct from confirmed semantic classification. An
outage or genuinely ambiguous token cannot honestly be reported as confirmed.
Run results separate `confirmedSkills`, `provisionalSkills`, `refinedSkills`,
`recoveryRounds`, `recoveryAttemptedSkills`, `deferredSkills`, `failedSkills`
and `remainingUnassigned`. Failure counters include attempts later recovered.
`canonicalCalls` includes repairs and reconciliation; `canonicalBatches` keeps
its legacy meaning of initial batches.

## Configuration and compatibility

`TAXONOMY_RECOVERY_ROUNDS=3` (range 1-5) and
`TAXONOMY_ESCALATION_MAX_SKILLS=300` bound recovery to at most 900 skill
admissions per refresh. A zero skill limit disables escalation. These are
subordinate to the shared `TAXONOMY_MAX_MODEL_CALLS=50` and
`TAXONOMY_MAX_PROMPT_BYTES=1000000` budgets, which cover canonicalization,
repairs, reconciliation, domain classification and recovery together. A batch
reserves its allowance before dispatch, including during concurrent fan-out.
Once the allowance is exhausted, successes are saved and remaining work is
deferred without inventing judgments or incrementing unattempted retry counts.
Oversized batches are deferred as a whole; lower `CLUSTER_BATCH_SIZE` or raise
the prompt budget deliberately if a first batch cannot fit.

`TAXONOMY_RECOVERY_MIN_BATCH_SIZE=10` prevents repeated full-directory singleton
calls. The final partial batch can be smaller. `TAXONOMY_MAX_AUTO_ATTEMPTS=3`
pauses exhausted skills across ordinary regroups without hiding or retiring
them; narrow the Match / Gap filters and run Regroup again to revisit that
explicit scope (`skillKeys` in the API). Existing General
placements and user corrections remain intact. Raising the retry limit also
reopens eligible automatic work.

The budget counts application-level calls and serialized UTF-8 task payloads,
not invoice dollars. System instructions, schemas, generated output, embeddings,
and runner/provider retries are additional. Existing spend governance still
applies. Run results include `modelCalls`, `maxModelCalls`, `promptBytes`,
`maxPromptBytes`, `usageLimitReached`, `retryLimitSkills`, and `deferredSkills`.

`TAXONOMY_PLACEMENT_FLOOR` still controls new provisional placements. Disabling
it does not erase existing placements.

`GroupingStatus.escalation_attempts` defaults to zero for old records. Existing
cluster maps and correction ledgers need no migration. The first regroup can
refine legacy generated General buckets. Personal data is not rewritten until
regroup/profile build runs. Older code can read the resulting files, but will
again treat General placements as terminal and ignore attempt history.

## Verification boundary

The offline regression has 16,000 canonical skills in 160 domains: 14,400
placed and 1,600 unresolved. Mock model responses resolve the backlog over
bounded regroups, without re-canonicalizing existing skills. Each run stays
within 50 calls and 1 MB of task prompts; large maps can require more regroups
than the previous two-run regression, which lacked those usage limits.
Domain member examples are bounded at 1,280 per prompt instead of 16,000:
92% fewer member entries. This does not measure total tokens, live latency or
cost savings.

Other regressions cover queue fairness across outages, shrinking-batch repair,
provisional refinement, user correction precedence, retirement contradictions,
source-evidence boundaries, stale-status cleanup and false-adjacency prevention.

## Export validation (October 23, 2026)

The latest export contains 21,424 canonical skills accumulated over time. Its
1,336 active target jobs plus profile skills demand 14,686 non-retired canonical
skills: 12,250 specific placements, 1,302 unassigned and 1,134 provisional.
There are also 1,092 stale failure records for already specific placements.

A live pilot used 30 evenly spaced unassigned skills and the configured
DeepSeek model on a separate copy. Name-only recovery produced 15 specific
placements, 14 provisional placements and one incorrect retirement. Adding
source context produced 21 specific placements, nine provisional placements
and no retirements. The source showed that the wrongly retired unfamiliar name
was an enterprise AI platform. A further prompt correction prevents copying
historical domain errors solely because their example members match.

Three full refreshes of the isolated export produced:

| State | Specific placements | Provisional | Unassigned | Newly retired |
| --- | ---: | ---: | ---: | ---: |
| Original | 12,250 | 1,134 | 1,302 | — |
| Refresh 1 | 12,714 | 1,567 | 402 | 3 |
| Refresh 2 | 13,126 | 1,550 | 0 | 7 |
| Refresh 3 | 13,504 | 1,170 | 0 | 2 |

The 2,436 original unresolved/provisional skills yielded 1,254 specific
placements, 1,170 provisional placements and 12 retirements. All 1,092 stale
specific-placement failure records were cleared. The three refreshes took
441.5 seconds and 251 application-level domain batches, with no canonicalizer
or embedding calls and no terminal provider failures. Provider-internal retries
are additional. Singleton recovery grew the taxonomy from 377 to 953 domains;
future maintenance should evaluate fragmentation without forcing unrelated
skills together.

On this snapshot, taxonomy context alone shrank from 482,814 to 84,650 bytes
(82.5%); member entries shrank from 19,415 to 2,077. Source evidence and system
instructions are additional. This is not an end-to-end latency or cost claim.
These full runs preceded the final confidence-parser hardening, which was
validated separately with focused regressions and a final live pilot.
The final-code pilot assigned 19 of the same 30 skills to specific domains and
kept 11 provisional, with no retirements or terminal provider failures.

These are coverage measurements and inspected examples, not an independently
labeled semantic accuracy score. Generated specific placements still require
a separate quality evaluation before claiming a particular precision rate.
The source export and working tenant data are not modified by this validation.
