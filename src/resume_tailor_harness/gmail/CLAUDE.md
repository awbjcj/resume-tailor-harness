# Gmail integration developer reference

Migrated from the project root `CLAUDE.md` (2026-08-15, CLAUDE.md split) — loads only when working under `src/resume_tailor_harness/gmail/`.

- **The Gmail token exchange must reconcile scopes; oauthlib cannot.** Connect
  sends `include_granted_scopes=true`, so Google returns the union of every
  scope the shared OAuth client holds — the Gmail pair _plus_ the three
  identity scopes from sign-in. oauthlib reads RFC 6749 §3.3 as a raw set
  inequality (`OAuth2Token.scope_changed`) and raises a bare `Warning` from
  inside `fetch_token` on **any** difference, so it cannot tell a harmless
  incremental superset from a grant missing what was asked for. It fired on
  every connect by a Google-signed-in user, and the callback's blanket
  `except Exception` turned it into `?gmail=error` — i.e. adding Google
  sign-in silently broke Gmail connect for exactly the users it targeted.
  `_exchange_token` (`api/routers/gmail.py`) is the one seam that clears
  `oauth2session.scope` to drop that comparison, then makes the distinction
  explicitly: no `gmail.readonly` in the grant raises `GmailScopeMissing`
  rather than storing a token that reports a connection the user never gave.
  It then restores the session scope to what was **granted**, because
  `Flow.credentials` copies it into `Credentials.scopes` and `to_json` persists
  only that list — the one `has_compose`/`draftCapable` later read. Storing the
  _requested_ pair would claim compose access a user may have withheld on
  Google's granular consent screen. Never call `flow.fetch_token` directly
  here. Pinned by `tests/api/test_gmail_oauth_scope.py`, which drives the real
  google-auth-oauthlib stack over a stubbed token endpoint — a faked `Flow`
  exercises none of this.
- **Gmail is multi-user; drafts only, never send.** The platform OAuth client
  (`GOOGLE_OAUTH_CLIENT_ID/SECRET`) can be overridden per user via
  `secrets.env`; per-user tokens live at `{workspace}/gmail_token.json`
  (`gmail/auth.py` is the only credential seam; scopes = readonly + compose).
  The web callback authenticates via a signed link-token state, never the
  session cookie. An in-process scheduler (`gmail/scheduler.py`, every
  `gmail_sync_interval_hours`) runs `services/gmail_sync.run_gmail_sync`
  per connected user — sync proposals land in the notification bell; nothing
  auto-applies. `services/email_writer.py` grounds drafts in facts.json
  only (human gate, no LLM fact-check round) and saves them as in-thread
  Gmail drafts via `EmailDraft` rows; drafts never gate job deletion but
  cascade on delete. `gmail.send` is permanently out of scope.
- **Gmail does not own reminders, and used to by accident.**
  `create_follow_up_reminders` once had exactly one call site — *inside*
  `run_gmail_sync`, after `build_service()` raises for a user with no token —
  and `gmail/scheduler.py` only iterates users owning a `gmail_token.json`. So
  a user who never connected Gmail silently received **no reminders at all**,
  and nothing said so. `services/reminder_scheduler.py` now owns them on its
  own hourly tick that runs for every user regardless of Gmail state;
  `run_gmail_sync` returns pending counts, sync statistics, and continuation state,
  and does email classification only.
  Keep it that way: reminders are a property of having dated events, not of
  having connected a mailbox. Pinned by
  `tests/test_reminder_scheduler.py::test_reminder_pass_runs_without_any_gmail_token`
  and by a source-level assertion that `gmail_sync` no longer imports the
  reminder helpers.

- **Sync treats transport failures separately from lost authorization.** Gmail
  reads go through `requests.execute_read` (bounded SDK retries); only a missing
  message is skipped, while an incomplete metadata scan remains a failure.
  Credential refresh serializes per workspace and writes atomically. A temporary
  refresh failure preserves the token and returns `GMAIL_API_ERROR`; Google's
  explicit `invalid_grant` retires the unusable token, stopping repeated scheduled
  failures until the user reconnects. Local manual and scheduled syncs pass the
  configured data directory; hosted tenant context still takes precedence.
- **AI classification is optional.** Construct it lazily after matching and
  deterministic rules. On provider failure, disable AI for the remainder of the
  pass, retain rule-based proposals, and record warnings in the result and run
  log. Authentication errors must not be swallowed by body hydration.
- **Sync is resumable and incremental.** `scan.py` checkpoints history plus
  independent inbox/recruiting backfill cursors in the tenant database, keyed by
  a hash of the connected mailbox identity. Backfills have a fixed upper time
  boundary and no 90-day cutoff. Capture history before starting them; new mail
  is processed while the backfill continues. Persist each discovered page before
  processing; commit receipts, proposals, and pending-ID removal together. An
  expired history cursor restarts discovery while retaining cached evidence.
- **Budgets limit each run, not mailbox coverage.** `gmail_max_messages` controls
  page size (max 500), `gmail_sync_max_pages` controls pages per run, and
  `gmail_max_ai_calls` bounds optional AI. The result reports `has_more` plus
  processed/cached/read/matching counts. After backfill and deferred processing,
  an unchanged mailbox needs only its profile read, with zero message reads or AI
  calls. HTTP batches contain at most
  25 reads; failed parts use the existing bounded retry seam. Batching saves
  connections, not quota. Body transport failures leave the page retryable.
- **Company identity is only a candidate match.** Hydrate recruiting/company
  candidates before matching so HTML-only messages and body-only requisitions
  work. Prefer an exact JR/R/REQ reference from the job URL/source identity;
  otherwise use a unique role title for multiple applications at one company.
  Ambiguous or explicitly different requisitions must not update an arbitrary
  application. Proposals remain reviewable notifications, never auto-applied.
- **Precision precedes a guessed decision.** Rules require decision phrases,
  discard quoted history, and avoid receipt/marketing/conditional messages.
  AI returns structured labels with confidence >= 0.9 and an exact evidence quote;
  ungrounded answers are discarded. Company/domain and requisition indexes are
  built once per pass. A prior message-to-application association cannot transfer
  silently when another job is archived. Cached unmatched messages are reconsidered
  when the application catalog changes, without rereading available evidence.
- **Chronology spans runs.** Select the latest cached decision per application,
  using Gmail's receipt timestamp, so later backfill pages cannot resurrect old
  stages. Supersede older pending Gmail proposals; keep accepted/dismissed/cleared
  identities. Acceptance atomically claims a still-pending notification and applies
  only a forward transition against the current application status. A workspace
  lock serializes manual/scheduled syncs, including separate SQLite workers.
- **Cache custody.** `gmail_receipts` stores normalized metadata and at most 4,000
  body characters, not attachments. It is tenant/account-scoped and cleared by a
  jobs/all workspace reset. Bump `PROCESSING_VERSION` when decision semantics change.
  Completed classifications, including `none`, are fingerprinted by classifier
  input, rules version, and AI mode, independently of the application catalog.
  Rematching must reuse them; failed/deferred classifications remain retryable.
  History/backfill overlaps reuse known incoming messages. Refresh metadata for
  excluded/missing messages so recovery from spam/trash can be processed.
  Gmail read/unread changes do not redownload messages; archived/deleted mail does
  not undo an already recorded employer decision. See `docs/gmail-sync.md`.
