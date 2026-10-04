# Agent workspace improvements

Completed implementation stages:

1. Upgraded Agno from 2.9.0 to 3.1.1 and verified provider/tool/stream compatibility.
2. Added an authenticated AG-UI projection of the durable run stream. Preserved
   cursor replay, cancellation, tenant ownership and the nonterminal settled state.
3. Rendered Scout's persisted research proposals inline with citations and the same
   approval services/cache as its proposal ledger.
4. Added a Career Lab draft workspace with version selection and section feedback.
5. Shared explicit per-turn context between workspace controls and chat; exposed
   real run progress without inventing percentages or completed stages.
6. Added a job-context assistant panel using the existing Career Lab session/run APIs.

Keep the existing React components and use AG-UI's typed protocol SDK. A wholesale
CopilotKit runtime/persistence replacement would duplicate the application's
existing launch, auth and session infrastructure. Application writes remain in
the existing approved deterministic services; model output never executes UI code.

Validation: Python provider and stream tests, frontend interaction tests, lint,
contract regeneration, production build, and browser checks where available.
No provider calls, commits, deployment or remote publication are required.

## Transport and UI boundaries

`GET /api/runs/{id}/stream?protocol=ag-ui&offset=N` projects the existing event
log with the Python AG-UI SDK. The native representation remains available.
The existing SSE authentication and run ownership checks cover both formats.
This is an observation endpoint, not a replacement for the launch API or a
drop-in HttpAgent POST endpoint. Clients still launch and cancel through the
application APIs. The TypeScript SDK validates events before they reach the
existing chat reducer.

The `rawEvent.index` field carries the durable source cursor. Run-start frames
do not consume it. `resume.settled` is a custom, nonterminal event: it must not
be mistaken for persisted completion. Tool arguments and results intentionally
remain bounded previews; structured research cards resolve persisted proposal
IDs instead of parsing those previews or executing model-generated components.

Shared context uses the existing typed per-turn context contract and session
query cache. Draft revisions reference an exact session and turn, then prepare
an editable request in the composer. They never overwrite an earlier artifact.
Approvals reuse the existing server validation and additionally guard concurrent
decisions from inline cards and the ledger within the same query client.

The job assistant uses the same Career Lab session APIs, with explicit job,
resume and profile context. Its model responses remain draft-only. Full workspace
navigation uses the same session ID, rather than creating another conversation.

## Validation (2026-10-04)

- Full frontend suite: 204 files / 831 tests passed. Subsequent targeted runs
  passed the new reconnect regression and three job-assistant lifecycle tests.
- Full Python run: 4,074 passed, 5 skipped, one failure in the unchanged
  `test_refresh_cluster_launches_are_coalesced_while_active` test, accompanied by
  SQLite thread-affinity errors. That test passed on isolated rerun. Do not
  describe the full run as entirely green.
- Focused Python provider transport, streaming, MCP and OpenAPI checks: 211
  passed. The final AG-UI projection tests (including distinct tool-result IDs)
  passed separately: 3 tests.
- Browser tests: all 10 Career Lab, Scout ledger and board scenarios passed;
  the final sidebar layout was rechecked after the last layout change. Tests
  use mocked API/provider data, including AG-UI SSE frames, not live model calls.
- Python and frontend lint, TypeScript/production build, i18n coverage, generated
  OpenAPI/TypeScript contract checks, and whitespace checks passed.
- npm audit reports 10 advisories (8 high, 2 moderate). All reported vulnerable
  package versions match the pre-change lockfile; neither new AG-UI nor Zod
  dependencies appears in the advisory list. No broad dependency remediation
  was folded into this work.

Screenshots are generated under `web/e2e/__screenshots__/` (ignored outputs):
`agui-draft-workspace.png` and `agui-job-assistant.png`.

## Review fixes and test deployment

New Career Lab sessions start with empty context rather than inheriting the
displayed job thread. Revision feedback resets whenever the selected draft
changes, including selection from chat and newly arriving drafts. Job modal
actions wrap within the header on narrow screens.

The review regressions passed (21 focused frontend tests), along with all 10
Career Lab, Scout and board browser scenarios, including fully reachable job
actions at a 375-pixel viewport. Frontend lint and the browser suite's production
build passed; the three AG-UI backend projection tests passed again.

Branch `codex/ag-ui-chat-test` is intended for the isolated Railway `ag-ui-test`
environment, with its own empty data volume. Production remains on `main`.
