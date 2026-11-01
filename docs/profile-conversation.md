# Conversational profile management

Profile Coach can create, inspect, update and remove the active workspace's
personal resume profile, facts, skills and skill display categories. This is one
profile per workspace; it does not create accounts or alternate resume personas.
Users can start at `/coach` without uploading a resume. Model credentials are
still required for conversation turns.

Examples include “Change my headline to Backend Engineer”, “Remove this project
highlight”, “Rename Python to Python 3”, and “Move Python into Programming”.
The coach inspects exact saved records, asks when a target is ambiguous, and
produces a change card with before/after values and the user's current words.
Apply changes commits that stored proposal; Discard leaves the profile unchanged.
Existing evidence-coaching notes and their approval flow remain available.

## Runtime boundary

The Agno coach has the existing read-only corpus tools plus:

| Tool | Purpose |
| --- | --- |
| `inspect_profile` | Read profile fields, category membership and searchable, paginated fact/skill ids. Bullets and highlights can be paged using their parent id. |
| `get_profile_change_schema` | Read the editable field contract for one entity/section. |
| `preview_profile_changes` | Validate up to 20 quoted operations and compute a preview without writing. |

The persona produces prose and metadata; the existing cheap formatter parses a
`CoachTurn` with `action=changes` and a `ProfileChangeSet`. Application code
revalidates every operation, exact current-turn quote, editable field and target
before storing a pending draft. Tool results and model text cannot approve it.
Record ids, source metadata and inference evidence are host-owned. Moving an
inferred skill preserves its inferred status and supporting evidence.

The single, hash-verified `profile-conversation` skill loads through the existing
career-skill registry and Agno `Skills` adapter. The model never selects a local
path. Influenced turns retain the resolved `SkillRef` in `agent_meta`. Prompts
remain projected by the normal prompt registry and guidance/quality composition.

## Approval and persistence

`POST /api/profile/coach/sessions/{session_id}/changes/{draft_id}` accepts:

```json
{"decision": "apply", "revision": "<the draft's 64-character revision>"}
```

`decision=discard` resolves the draft without changing profile evidence. The
endpoint accepts a draft identifier and revision, never replacement change data.
It returns the session with `changeDrafts`, whose statuses are `pending`,
`applied` or `discarded`. Repeating the same decision is idempotent. Applying an
outdated profile revision returns `409 PROFILE_STALE`; inspect and draft again.
Pending drafts remain reviewable after ending the conversation. Archived sessions
must be restored before applying changes.

Approval uses the tenant-scoped profile mutation lock, including a cross-process
file lock shared with builds, direct skill services and coach session mutations.
An exception rolls back the correction ledger, facts, matrix and draft receipt
together. This is exception rollback, matching existing profile publication; it
is not a crash-atomic multi-file database transaction.

`conversation_edits.json` stores approved corrections and replays them after
source extraction and manual skills during a corpus rebuild. Fact ids remain
addressable. Rebuilt skill ids may change, so the host also records the exact
normalized canonical skill name as its stable selector. Unknown update targets
produce a warning rather than attaching a correction to a guessed record.
Explicit skill overrides also reconcile later direct skill edits with chat edits,
so an older proposal cannot undo a newer alias, removal or restoration on rebuild.
Removing a fact also removes inferred skills whose evidence no longer exists.
Profiles created only through conversation rebuild deterministically without
calling extraction models or requiring a primary resume.

Skill display buckets can be created, renamed or removed. Removing a nonempty
bucket moves its skills to Other, preserving the records. These buckets are
distinct from `Skill.category` (`hard`, `soft`, `domain`) and the shared, fixed
taxonomy group vocabulary.

Whole-profile removal is reviewed alone. It deletes saved facts and matrix,
retains source documents and conversation history, and fences source replay.
Recreation starts with a blank profile and explicit new conversational records.
Previously registered source ids and fact ids stay excluded; newly added sources
can contribute new evidence. The old manual-skill ledger is removed as well.
This action does not delete the account, original uploads or chat history.

## Validation

Offline coverage checks read-only previews, exact current-turn quotes, target and
field validation, creation without sources, contact merge behavior, fact/skill/
category edits, inferred-evidence preservation, orphan cleanup, rebuild replay,
stale drafts, duplicate approvals, rollback, and API scope. Browser component
tests cover explicit approval, disabled decisions, discarded/applied states, and
English/Chinese labels while preserving user-entered values.

The implementation follows Agno's documented [skills adapter](https://github.com/agno-agi/docs/blob/main/skills/overview.mdx)
and [structured output/tool separation](https://github.com/agno-agi/docs/blob/main/input-output/structured-output/agent.mdx).
Harness guidance was checked against agents-best-practices 1.18.0 at
[`da245f8`](https://github.com/DenisSergeevitch/agents-best-practices/tree/da245f8cbfc4c358e8c3cde61dbb703bd40292bc).
Offline tests establish local contracts; they do not establish live model behavior.
