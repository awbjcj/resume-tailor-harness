# Long-task context harness adoption

## Changed rules

The durable transcript and model working context have different contracts.
Completed answers remain mandatory debrief evidence. Every selected source is
represented or explicitly omitted. Required current input is not silently sliced.
Continuation is cited untrusted history; only deterministic records grant approval
or establish committed work. Explicit resume validates current versions and
fences stale attempts. See ADR 0014 for scope and numerical limits.

## Implementation surfaces

- `sessions/context.py`: shared allocation, omission and total-prompt accounting.
- `career_lab/continuation.py`: bounded quote selection, source digest and validation.
- `career_lab/recovery.py`: durable operation identity, retries, expiry and stages.
- Existing Career Lab store/services/router/UI: atomic receipt commit, scoped
  resume endpoint and reload-visible recovery action in both conversation views.
- Coach and Interview prompt assembly; completed-answer debrief projection.
- RunManager: durable partial results across subsequent phases and restarts.
- Agent trace: counts, context policy and covered-source digest, without raw text.
- OpenAPI/TypeScript contracts, regression tests, targeted dev CI and failure note.

## Verification and effectiveness

Run the focused tests in `.github/workflows/context-regressions.yml`, the complete
offline pytest suite, Ruff, Pyright, Career Lab frontend tests and the web build.
Exact results are recorded in the implementation handoff; this file does not
claim a live-provider quality score. Offline tests must never call a real model.

Measure retained constraint/correction recall, source coverage, malformed or
unsupported memory, rework after interruption, total usage per accepted task and
latency. Compare fresh, long-history, repeated compaction, skill switch and
restart on the same tasks. Citation validity alone does not establish recall.
Treat mandatory authority/provenance violations as failures, not weighted scores.

## Manual follow-up

Calibrate limits against actual workload and provider capacity. Production
endurance, semantic memory recall and recovery objectives were not measured by
the offline checks. Other workflows keep explicit retry and durable partial
results; extending stage replay needs a workflow-specific idempotency contract.
Failure memory was added for the reproduced evidence-loss paths. No universal
instruction templates or additional memory backends were introduced.

## Validation recorded 2026-11-08

- Complete offline Python suite: `python -m pytest -q`, exit 0 after registering
  the continuation builder with the mandatory guidance and quality policies.
- Pyright: zero errors and warnings. Ruff and `git diff --check`: passed.
- Career Lab frontend tests: 45 passed. ESLint, localization coverage and
  production web build: passed.
- The build still reports the existing initial bundle size warning (261,794
  gzip bytes versus the 200,000-byte target); the build/performance check exits 0.
- No live-provider endurance or semantic recall evaluation was performed.
- Implementation is isolated on `codex/long-task-context` from `dev`; no deployment
  or remote branch update was performed.