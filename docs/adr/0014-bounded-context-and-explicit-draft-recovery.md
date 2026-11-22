# 14. Bounded working context and explicit draft recovery

Date: 2026-11-08

## Status

Accepted for implementation following the long-task context review.

## Decision

Retain complete session transcripts under ADR 0006. Model input is a separate,
bounded projection. Career Lab normally includes all turns; above 160,000 UTF-8
bytes it selects verbatim, turn-cited working memory from older turns and keeps
the latest pair intact. The same projection reaches router and persona. Store
the versioned selection atomically with the successful reply, never rewrite
the source transcript. A recovery receipt may retain a prepared selection before
reply completion so retries need not summarize it again.

The tool-free selection model may choose salient constraints, corrections,
decisions, unresolved work and results. Code checks every quote against its
source, verifies the covered-prefix digest on reload, and retains previous
selections without recursive paraphrase. This does not prove semantic recall;
the persona must retrieve original cited turns when detail is missing or unclear.
Selections never become applicant evidence, action approval or completion receipts.
Current corrections take precedence over historical selections.

Whole application prompt projections are bounded for Coach and Interview;
Career Lab retains its separate 256,000-byte hard guard. Source JSON is allocated
before serialization, with explicit omission markers. Scoring gets complete
interview answers, including completed questions, or fails before producing scores.

An existing Career Lab session can retain one recovery operation. Its immutable
request, covered context, source fingerprints, skill hash and model/policy identity
bind the saved draft. Explicit resume validates these again and reuses a completed
drafting stage; incomplete drafting may run again. The final turn append and
committed receipt share one session-file atomic write. Operation IDs and attempt
checks fence stale workers and make resume after a lost completion repeat-safe.
Starting a different request supersedes the previous recovery operation.

## Limits and consequences

- Extraction: at most eight bounded 60,000-byte batches per preparation; individual
  turn fragments are at most 10,000 characters. Provider retries remain governed
  by AgentRunner. Memory: 256 selections and 48,000 bytes. Overflow rejects safely
  rather than dropping previous decisions. Very large legacy histories can still
  require user-directed decomposition.
- Recovery: at most three attempts within one hour from the original preparation.
  Resuming does not reset those limits. Existing durable account/platform usage
  and SpendGate remain the spending authority; no new per-task dollar limit is
  invented. An in-flight provider response before its receipt is durable can be
  lost and billed again on an explicit retry.
- Current source/model/skill changes invalidate recovery. No stale draft is
  silently applied under a different policy. A new request prepares fresh work.
- Run progress checkpoints still mean cancellation checks. Committed partial
  results are now flushed durably and survive subsequent phases and restart.
  Generic run recovery continues to mark interrupted work as an error; it never
  deserializes and invokes arbitrary worker closures.
- There is no automatic external-write replay, new scheduler, vector database,
  shared agent memory or multi-agent topology. The first resumable workflow is
  Career Lab drafting; generic partial-result durability supports other workflows.
- Character/byte guards are application limits, not model-token-window claims.
  Provider system prompts, skills, reasoning/output and tool-loop growth still
  consume provider capacity. Live long-horizon quality remains an evaluation task.

## Verification

`test_long_task_context.py`, `test_career_lab_service.py`,
`test_mock_interview_service.py`, `api/test_run_manager.py`, and Career Lab UI
tests cover projection, citation validation, restart, stale work, operation replay,
latest corrections and user-visible resume. The targeted dev-PR workflow prevents
these regressions before promotion to main. Full offline CI remains the release gate.
