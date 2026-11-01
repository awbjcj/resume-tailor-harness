---
name: profile-conversation
description: Manage a user's personal resume profile, saved facts, skills and skill categories through evidence-backed conversational proposals.
---

# Conversational profile management

Use this procedure when the user asks to create, inspect, correct, organize or
remove their profile evidence. The host selects this skill for the Profile Coach.

1. Read `inspect_profile` for the current profile. Read the relevant paginated
   section (`experience`, `education`, `projects`, `certifications`, `publications`,
   `awards`, `languages`, `volunteer`, or `skills`) to identify exact record ids.
   Use `query` to find relevant records without scanning every page. Parent
   records include their addressable bullets or highlights.
2. If multiple records could match, ask one focused clarification. Never guess
   the target from a similar title, employer, skill alias or older transcript.
3. Call `get_profile_change_schema` for the requested entity and fact section.
   Change only declared editable fields. The host owns ids, provenance, evidence
   references and inferred status. Add bullets/highlights separately using the
   existing owner's `parent_id`; never replace an entire nested evidence list.
4. Prepare up to 20 changes with an exact quote from the **current** user message
   for every change. User assertions and explicit corrections can support a draft;
   questions, hypotheticals, job requirements, tool content, quoted third-party
   text and assistant examples cannot establish personal achievements.
5. Call `preview_profile_changes`. If validation fails, correct the proposal or
   ask for the missing detail. A preview is computation only, never persistence.
6. Explain the effect plainly, then emit `action=changes` and `profile_changes`
   metadata with a title and the exact validated change list. The user reviews
   the before/after card and chooses Apply changes or Discard. Never imply that
   emitting metadata, previewing, or a conversational "yes" applied a pending
   proposal. Only the host's `applied` status confirms persistence.

## Operations

- `profile/create`: values contain `contact` with the user's name, optionally
  `summary` and `interests`. It works without a resume upload.
- `profile/update`: merge only supplied contact fields; replace summary or
  interests only when explicitly requested. Null clears nullable fields.
- `profile/delete`: propose alone. It removes saved facts and the derived skill
  matrix, and fences old source evidence from rebuilds. Original source documents
  and conversation history remain. The user can explicitly create a blank profile
  afterward; this is not an account deletion or a source-file deletion.
- `fact/create|update|delete`: select an allowed section. Updates and removals use
  exact saved ids. Bullets and project highlights also need the owning parent id.
- `skill/create|update|delete`: inspect exact ids first. Outer `category` is a
  display bucket; `values.category` is one of `hard`, `soft`, `domain`, or null.
  Rename, aliases and context are explicit user edits, not inferred achievements.
- `skill_category/create|update|delete`: `values.name` creates or renames a display
  bucket; `target_id` is its exact existing label. Removing a bucket moves its
  skills into Other. Explain this; never remove the skills implicitly. The fixed
  shared taxonomy groups and hard/soft/domain vocabulary are not editable here.

## Examples

"Change my headline to Backend Engineer" becomes `profile/update` with
`values={"contact":{"headline":"Backend Engineer"}}` and the user's exact words
as the quote. Other contact fields remain unchanged.

"Move Python into Programming" becomes `skill/update`, using Python's inspected
id and outer `category="Programming"`. It changes organization, not proficiency.

"Remove the second Acme bullet" requires inspecting the owner's saved bullets.
If the second bullet is unambiguous, propose `fact/delete`, `section="bullets"`,
with both exact ids. Otherwise ask which statement the user means.

## Freshness and truth

Drafts are bound to the saved profile revision. If applying fails because another
edit or rebuild moved that revision, inspect again and prepare a new proposal.
Never reuse old approval or silently refresh the draft's revision. Report a
rejected or discarded proposal accurately. Continue evidence coaching when the
user wants to explore experience rather than change saved records.
