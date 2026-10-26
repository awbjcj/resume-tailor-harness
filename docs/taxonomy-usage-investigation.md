# Skill categorization usage investigation — October 25, 2026

## Evidence

The supplied `usage_2026-10-24_to_2026-10-25.csv` contains 1,404 requests
and $102.1167 in billed cost. Of these, 1,399 GPT-6.1 Sol requests account
for $102.1159 and 49,866,902 input tokens (the CSV's input column, separately
from cache reads). Their median input is 35,431 tokens; 1,356 responses have
fewer than 250 output tokens. These calls span 18:57:26–19:29:14 EDT on
October 25. The other five requests are GPT-6 Luna and cost about $0.0007.

This is repeated large-input traffic, not large generated answers. The CSV
contains no operation/run IDs or prompts, so it cannot establish which exact
Regroup runs produced each request. Available local agent traces predate the
incident. No paid model calls were made to reproduce the problem.

## Confirmed code-level cause

The recovery change in `262480a0` added up to three rounds per refresh and
persisted recovery attempt counts. In `services/match_gap.py`, the old recovery
batch formula shrank 60-token batches to 15, 3, then 1. Counts persisted across
runs, so difficult skills reached singleton batches permanently. The 300-skill
limit applied separately to every round, not to the entire operation.

Recovery calls bypass candidate retrieval and receive the full domain directory
with representative members from `taxonomy/classification.py`. Provisional
General placements reenter recovery on the next ordinary Regroup. There was
neither an automatic retry ceiling nor a shared call/prompt budget. The attempt
count improved scheduling fairness but increased calls per skill as it grew.

An offline reproduction used 300 unresolved skills with two previous attempts,
160 domains and 14,400 existing domain members. A fake provider returned an
uncertain answer for each request:

| Measurement | Before | After |
| --- | ---: | ---: |
| First Regroup model calls | 900 | 30 |
| Skills per recovery call | 1 | 10 |
| First Regroup task-prompt bytes | 29,024,100 | 972,060 |
| Next ordinary Regroup model calls | 900 | 0 |
| Confirmed ambiguous skills | 0 | 0 |
| Preserved provisional skills | 300 | 300 |

This measures orchestration and payload reduction, not live classification
accuracy or a guaranteed billing reduction.

## Controls

The operation now shares a default 50-call and 1,000,000-byte task-prompt
budget across initial canonicalization, its repairs, reconciliation, domain
classification and all recovery rounds. Reservations occur before dispatch;
concurrent fan-out cannot admit more than the shared allowance. Successful
results still commit. Unattempted work is deferred without inventing a
canonical, a placement, a provider failure or another retry attempt.

Recovery batches stop shrinking at ten skills by default (a final partial
batch can be smaller). Three cumulative recovery attempts pause a skill during
ordinary Regroup. Narrowing the Match / Gap filters before regrouping explicitly
scopes a retry (`skillKeys` in the API), under the same per-run budget. Saved
General placements and user corrections survive. The completion message
distinguishes paused retries from backlog work deferred to the next run, in
English and Simplified Chinese.

These limits count application calls and task-prompt bytes, not dollars.
Runner/provider retries, system/schema overhead, output and embeddings are
additional; existing spend governance remains in force. The limits are per
operation, not a daily or account-wide cap. See
[configuration](configuration.md#skill-taxonomy) for environment controls.

Regression coverage includes concurrent admission, cumulative prompt bytes,
canonical repair exhaustion, preserving valid canonicals after deferral,
successful partial commits, unchanged unattempted history, automatic retry
limits, explicit retry and bounded convergence of a 16,000-skill map.

The change requires rollout to the running application; editing the local
checkout does not change a deployed instance or an already running operation.

## Verification results

- The initial regression tests failed against the old behavior, including
  900 calls where at most 30 were expected, ignored call/prompt limits and
  repeated automatic retries beyond the intended ceiling.
- Final focused taxonomy/service/API/custody run: 100 passed.
- Full Python suite: 4,502 passed, 5 skipped, one failed.
  `test_same_workspace_mutations_serialize_across_processes` timed out waiting
  five seconds for a spawned process to enter its lock, then its cleanup tried
  to join an unstarted follower. That test passed in the final 100-test rerun.
  The full-suite run itself was not completely green.
- Full web suite: 946 passed across 212 files, including the new completion
  message regression. Production build and translation catalog check passed.
- Ruff, Pyright, ESLint and whitespace checks passed.
