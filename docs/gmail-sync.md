# Gmail synchronization

The web Sync action and scheduled sync share a durable, incremental pipeline.
Status changes remain proposals for the user to accept.

## Large mailboxes

The first sync records Gmail's current history ID, then starts two independent
backfills: inbox messages and recruiting search results, including archived mail.
Both scans continue through saved page tokens with no fixed age cutoff. New
messages are discovered through Gmail history while old mail is still being read.
Routine read/unread changes do not cause message downloads.

Each run processes at most `GMAIL_SYNC_MAX_PAGES` pages of at most
`GMAIL_MAX_MESSAGES` messages each (page size capped at 500). Defaults are 20 pages
of 50 messages. A partial run returns `has_more: true` and a progress message;
the next manual or scheduled sync continues saved work. Increasing budgets changes
throughput, not which messages are permanently eligible. The existing scheduler
interval still controls when scheduled passes run.

Metadata and relevant bodies use serial HTTP batches of 25, respecting Google's
recommendation to stay below 50. Only failed batch parts are retried. Batching
reduces connection overhead; each inner request still consumes Gmail quota.
Once backfill and deferred processing finish, an unchanged mailbox requires one
profile request and no message reads or AI calls.

## Decision accuracy

- Company names and domains use complete normalized names, not arbitrary substrings
  or the first word of a multiword company. Indexes are built once per pass.
- Requisition identifiers take precedence and are scoped by company when available.
  Distinct roles at one employer require a unique role/requisition match. Ambiguous
  mail is retained without proposing a status.
- Rules look for actual hiring decisions, excluding quoted replies, common
  conditional statements, acknowledgements, and marketing language. A word such as
  “unfortunately” is insufficient to infer rejection.
- Optional AI must provide a permitted label, confidence of at least 0.9, and an
  exact evidence quote from the current message. Unsupported output is ignored.
  `GMAIL_MAX_AI_CALLS` defaults to 20 per run; 0 disables AI. Temporary provider
  failures and budget deferrals remain retryable, without discarding rule results.
- Newest decisions win across pages and separate syncs. Older backfill emails cannot
  create an older pending stage after a newer decision. Already dismissed or cleared
  proposals do not reappear. Accepting a stale proposal cannot regress current status.
- Versioned classification changes also correct or withdraw existing pending
  proposals; accepted and dismissed decisions remain untouched.

These are conservative safeguards, not a measured production accuracy percentage.
Unfamiliar wording, missing role identifiers, unsupported languages, and evidence
beyond the 4,000-character body excerpt can remain unresolved. The recruiting query
is broad but is not a guarantee of finding every archived message with unusual wording.

## Recovery and data boundaries

Discovered IDs are saved before downloading. Message receipts, proposal writes, and
page completion commit together. Cancellation or transport/database failure leaves
unfinished work available for retry. If Gmail history or a page token expires,
discovery restarts using cached results. Concurrent manual/scheduled runs for a
workspace are serialized, including separate SQLite server processes.

Cache and checkpoints live in each tenant's database and are additionally keyed by
the connected mailbox identity. Reconnecting another Gmail account cannot reuse
the previous account's classifications or notification identities. Cached metadata
and bounded body excerpts support reconsidering unmatched messages when applications
change. Attachments and credentials are not cached here. Jobs/all workspace reset
clears the cache and checkpoints; Gmail label changes do not erase recorded decisions.

The legacy `sync-status` CLI and draft-thread lookup retain their separate bounded
recent-message reader. They do not use the web/scheduled sync checkpoint.

## Validation

Offline integration tests cover 1,000 and 10,000 emails across 500 and 5,000
applications. They verify complete resumable discovery, one metadata/body download
per message, no new downloads or AI calls on an unchanged mailbox, and chronological
proposal selection. Other tests cover cancellation, atomic rollback, history expiry,
mailbox switching, partial batch failure, expired page tokens, AI budgets,
classification upgrades, stale approval, and labeled
positive/negative recruiting examples. These test transport call counts and outcomes;
their runtime is not a production Gmail latency benchmark.

Protocol references: [Gmail synchronization](https://developers.google.com/workspace/gmail/api/guides/sync)
and [Gmail batching](https://developers.google.com/workspace/gmail/api/guides/batch).
