# Workflow continuation

The workspace carries the Job, chosen materials, reviewed evidence, and original
destination through preparation and recovery. It never treats preparation as
submission or a saved source as an incorporated profile fact.

## Shared contracts

- Application continuation is a read-only projection of Job, Application,
  submission history, and usable resume state. Its additive result identifies
  the next work and a local destination. Dashboard queues and Job detail use
  the same projection; historical Job statuses remain unchanged.
- Profile publication records successful evidence incorporation separately from
  facts-file modification time. Explicit refresh requests remain recoverable in
  their originating coaching session, including after that session ends.
- Application preparation shares material eligibility and exact selection across
  clipboard and SDK entry points. The clipboard entry remains available for
  existing Jobs outside the SDK preparation queue. Neither read submits a form.
- Task continuation retains a validated local destination through login and
  setup. Setup only interrupts work that needs those prerequisites. Advancing
  a saved step waits for persistence; explicit skip stays available.
- Run history offers a local path back to its result. Persist only allowlisted
  target identifiers, resolve current targets when reading, and provide a safe
  fallback when targets are gone. Opening history never replays writes.
- Application update proposal acceptance may include a user-confirmed timeline
  entry, committed with that acceptance. Status-only acceptance remains available.
  Message receipt time never supplies an appointment date by inference.

## Invariants and verification

Existing fact-lock, explicit proposal approval, tenant confinement, spending
limits, revision checks, and durable turn-per-run sessions remain in force.
Existing public fields and request forms continue to work; additions have defaults.

The additive contracts are:

| Read or action | Added behavior |
| --- | --- |
| Job detail | `nextStep` identifies the current work and its local `href`. `tab` links open the relevant Job section. |
| Dashboard summary | `queueTargets` links to actual pending work; Review and Render queues accompany existing queues. Submission history removes pending Apply work. |
| Setup status | Profile `freshness`, `publishedAt`, and `pendingSourceCount` describe successful incorporation separately from `factsBuiltAt`. |
| Coach session | `profileRefresh` retains a pending, running, failed, skipped, or completed refresh. The session refresh action works after the conversation ends. |
| Application preparation | `materials` preserves selected IDs, safe alternatives, eligibility, and actual PDF availability. Selection is labeled separately from submission. |
| Run completion | `resultHref` and `resultAvailable` lead back to the current result or a clear workspace fallback, including after transient run files expire. |
| Notification acceptance | Optional `event`, `expectedRevision`, and `eventDetailsConfirmed` capture a reviewed dated event with acceptance. An absent body retains status-only acceptance. |

Verification covers submitted Jobs leaving Apply work, missing PDFs staying
actionable, evidence arriving during a build, interrupted refresh recovery,
older selected materials surviving handoff, local return-path validation,
save failures retaining drafts, completion links after reload, and atomic,
repeat-safe optional timeline capture. Contracts are regenerated from the
server schemas, with English and Simplified Chinese copy checked together.
