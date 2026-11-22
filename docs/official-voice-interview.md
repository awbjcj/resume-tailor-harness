# Official interview voice and OpenAI credit accounting

Official voice is off by default. It records a bounded clip, transcribes it,
and places the text in the answer editor. A candidate can edit the text and
must send it explicitly. Interview scoring and run history still use the normal
text interview flow. If voice is unavailable, typing remains available.

## Configure the actual credit period

1. Use a dedicated OpenAI project whose only application traffic uses the
   official audio and Decisions adapters. Use separate platform-owned keys for
   those adapters, not the general `OPENAI_API_KEY` or Sub2API credentials.
   The application cannot see or prevent provider traffic made outside these
   adapters, and cannot prove that two different keys belong to different
   OpenAI projects. Reconcile provider usage separately.
2. Set `OPENAI_CREDIT_BUDGET_ENABLED=true` and
   `OPENAI_CREDIT_PROJECT_ISOLATED=true` only after arranging that isolation.
   Configure `OPENAI_CREDIT_CYCLE_START` and `OPENAI_CREDIT_CYCLE_END` with
   the **actual** credit-period bounds from OpenAI, including timezone offsets
   (for example, `2026-11-01T00:00:00-04:00`). The interval is start-inclusive
   and end-exclusive; an expired or malformed period disables optional work.
3. The Resume allocation is at most $15: the default
   `OPENAI_CREDIT_PROJECT_CAP_MICROS=15000000` is USD micro-units. The setting
   may be lowered but cannot exceed $15. For independent deployments, allocate
   smaller caps whose sum is at most $15; each deployment otherwise sees only
   its own database. The separate approved allocations are VSDA $30, Deal $25,
   Resume $15, and Video Dedup $30, for a total of $100.
4. To enable official interview voice, set `OFFICIAL_AUDIO_ENABLED=true` and
   `OFFICIAL_AUDIO_API_KEY` to its dedicated project key. Decisions uses its
   existing opt-in and `OPENAI_DECISIONS_API_KEY`; when credit accounting is
   enabled it is included in the same period. These settings are deployment
   owned and cannot be overridden by workspace secrets.

The authoritative accounting store is `data/system.db`; it must be persistent
across restarts. All workers sharing one allocation must use the same SQLite
database on storage with reliable SQLite locking. Do not treat independent
SQLite databases as a shared balance. Overlapping period definitions are
rejected. A configured cap can be lowered during a period but cannot be raised
again during that period.

## Limits and pricing

Uploads are limited to 15 MiB. The server requires ffmpeg and ffprobe, rejects
multiple audio streams, decodes to a single mono stream, and checks the decoded
samples against 120 seconds before sending that stream to OpenAI. Both tools
are installed in the production container. The browser automatically stops a
recording at two minutes, but the server limit is authoritative.

As verified on November 22, 2026, the official transcription model is
`gpt-transcribe` at $0.0045 per audio minute. Realtime interviewer speech uses
`gpt-realtime-2.1-mini`, with distinct text and audio token rates. The existing
rate card and immutable usage ledger represent the billed duration directly;
they do not invent token counts. The provider may omit or return incompatible
usage, so the reserved amount remains held until an operator can reconcile it.
Older transcription models including `whisper-1` and `gpt-4o-mini-transcribe`
are deprecated and scheduled to shut down on February 26, 2027. Check current
model access and rates before enabling or changing these settings.

The application reserves a conservative bound before each official voice or
Decisions submission, records supported usage once, and keeps the hold after a
timeout, cancellation, missing receipt, or process restart. It never automatically
retries a submitted recording. A retry of the same recording ID reuses its
result when available; a pending request cannot submit again. Decisions uses a
stable identity for equivalent requests within the period. At 80% of the cap,
the interface displays a warning; optional voice and Decisions calls stop
before their reserved total would exceed 95%. Text fallback is not dependent on
voice availability.

The displayed amount conservatively includes all recorded shared OpenAI usage
in the period, including usage routed through gateways, plus outstanding holds.
This can overstate the isolated project's actual provider spend. Other OpenAI
traffic is not reserved by this feature and may be in flight before it appears
in the usage ledger. The isolation requirement above is therefore essential:
the application cannot enforce the project's hard cap for traffic bypassing the
budgeted adapters, other independent databases, or external applications.
Administrators can also read the cycle totals from
`GET /api/admin/openai-credit/summary`, including when only Decisions is enabled.

## Reconcile an uncertain request

Do not retry an uncertain request with a new ID or delete its reservation to
make room. Compare the affected period and provider usage dashboard with the
durable rows in `openai_credit_reservations`, `usage_events`, and
`usage_line_items`; reservations contain an opaque user-scoped ID, operation,
model, creation time, state and maximum held amount. Submitted rows without a
matching settled event need investigation. Transcripts and cached Decisions
results are retained in the protected system database to support safe replay;
audio input is not retained. Include this database in the normal protected
backup and access policy.

An administrator can list unresolved holds with
`GET /api/admin/openai-credit/reservations`. The response includes `nextOffset`
when more holds remain; supply it as the `offset` query parameter to continue.
After obtaining provider billing evidence, post it to
`/api/admin/openai-credit/reservations/{reservationId}/reconcile` with a
reason identifying that evidence. To confirm a request was not billed, use
`{"outcome":"unbilled","reason":"provider case …"}`. For billed
transcription, use `{"outcome":"usage","reason":"provider receipt …",
"audioInputMicroseconds":1250000}`, replacing the example duration with the
provider-reported amount. For speech, provide `inputTokens`, `outputTokens`,
`cacheReadTokens`, and `audioOutputTokens`; for Decisions, provide
`inputTokens`, `cacheReadTokens`, and `cacheWriteTokens`. The operation type
and model come from the reservation, not the request. A billed reconciliation
creates the normal usage and quota entries and an audit row atomically. A
confirmed unbilled outcome releases the hold and creates an audit row. Both
operations require an administrator and a nonempty evidence reference.

Leave uncertain holds in place until evidence is available. A hold belongs to
the period in which its request was submitted; changing the period to hide it
does not reconcile it. Compare application totals with the provider's credit
dashboard before enabling a new period.

Official sources: [file transcription](https://developers.openai.com/api/docs/guides/speech-to-text),
[pricing](https://developers.openai.com/api/docs/pricing), and
[Decisions pricing](https://developers.openai.com/api/docs/guides/decisions#pricing-and-availability).
