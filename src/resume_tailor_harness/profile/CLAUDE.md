# Profile developer reference

Migrated from the project root `CLAUDE.md` (2026-08-15, CLAUDE.md split) — loads only when working under `src/resume_tailor_harness/profile/`.

- **Profile coaching is turn-per-run and evidence-locked.** Durable sessions follow
  ADR 0006, while the ADR 0005 amendment requires every draft note to retain
  verbatim quotes from the current user turn. The former batch interview API,
  CLI command, and web panel are retired; its history remains read-only input
  for avoiding repeated questions.
- **Conversational edits are reviewed data changes.** The coach's profile tools
  only read or preview; `profile/conversation.py` validates closed operations and
  editable field allowlists. `services/profile_conversation.py` applies the exact
  stored draft after a revision-bound approval, under the profile process lock,
  with rollback across the edit ledger, facts, matrix and session receipt. Each
  proposal quotes the current user turn. `conversation_edits.json` replays after
  source extraction and manual skills; unknown targets warn instead of guessing.
  Category operations affect the profile's skill display buckets, never the fixed
  hard/soft/domain or shared taxonomy vocabularies. Inferred skills keep their
  evidence-only status when organized. Full removal fences source replay;
  explicit recreation begins from a blank profile. Conversations can create and
  rebuild a profile without a primary resume. The hash-verified
  `profile-conversation` skill ref is retained in influenced coach turn metadata.
  See `docs/profile-conversation.md` for the API and acceptance cases.
- **GitHub depth is two-tier; dossiers win.** `profile/github_harvest.py` writes
  qualifying repositories' root docs (README files plus CLAUDE, CONTEXT, and
  AGENTS markdown, capped at 30 KB per file) as deterministic
  `sources/github--<repo>.md` documents with `origin="github"` and
  `mode="project"` during build phase 0 and `profile sync-github`. A markdown
  upload with `repo_url:` frontmatter, such as output from
  `.claude/skills/project-dossier`, supersedes the auto-document for the same
  normalized repository URL. Harvest also discovers root files named
  `*dossier*.md` (max 5 per repo, 30 KB each) whose `repo_url` frontmatter
  matches the repo; each becomes its own `github--<repo>--<stem>.md` project
  source and replaces that repo's README virtual doc. Manual uploads still
  supersede all harvested docs for the repo. `project_extractor.py` can emit exactly one Project
  plus skills, never Experience or Education. GitHub failures become build
  warnings; rate-limited harvests stop early without deleting existing sources.
- **GitHub branch choices are per repository.** `github_repo_branches` maps
  case-insensitive `owner/repo` keys (or legacy short names) to case-sensitive
  branch names; omitted entries follow the repository default. Contents listing
  and every dossier/README request use the same `ref`. Explicit-ref failures keep
  the previous saved files and branch metadata. API sync, ordinary builds, coach
  rebuilds and CLI operations all pass the same saved mapping. Synced sources
  retain `github_branch` for display; uploaded overrides remain authoritative.
- **Source CRUD preserves user intent.** File replacement keeps a source's id,
  primary/mode/anchor and repository identity, invalidates changed fragments,
  and converts a replaced GitHub document into an uploaded override. Explicit
  removals persist exclusions in `sources.json`; removing a repository's last
  source also excludes its shallow metadata project. Automatic harvest cleanup
  does not create exclusions. Restore clears them for the next sync. An empty
  existing manifest is intentional and must not trigger legacy resume migration.
  Dossiers and synthesis documents may stay registered without a primary resume;
  adding the next literal resume promotes it automatically. Profile builds require
  a primary resume, while source management and GitHub sync do not.
  Source mutations and harvest commits share the per-tenant corpus lock;
  extraction publishes hash changes onto the latest manifest instead of saving
  a stale snapshot. `fragment_status=missing` means extraction has not run;
  the API's separate `file_exists` field indicates whether source bytes exist.
- **Profile rebuilds regenerate inferred skills.** `profile build` strips and re-derives
  all `inferred=true` skills; durable corrections belong in `data/profile/overrides.yaml`,
  not hand-edits to facts.json.
- **Profile skill management is durable and source-preserving.** `manual_skills.json`
  replays additions, edits, merges, and suppressions; suppressions retain snapshots for
  immediate restore. Restores are exempt from future automatic pruning. Cleanup merges
  exact names/explicit synonyms and removes only conservative non-skill patterns; it
  never prunes by popularity or evidence count. Facts, ledger, organization, and matrix
  mutations share a per-profile thread/process lock and roll back together on errors.
- **User organization is a display layer.** `group_corrections.json` owns category/group
  catalogs, deletions, explicit assignments, and automatic reclassifications. Custom
  groups use stable `custom-` ids; deleting containers moves their contents to Other.
  The shared matching taxonomy and fact-lock's hard/soft/domain skill types stay closed.
  Skill-only rebuilds infer from saved facts, classify against the current user catalog,
  preserve manual assignments, and reject stale results after concurrent edits.
  Coach category previews and approval use this same catalog; its revision is part of
  the draft's stale check. `conversation_organization.py` mutates only owned in-memory
  copies. All profile rebuild paths apply cleanup and reconcile explicit skill snapshots,
  including renames and restores of skills created through conversation.
- **Synthesis ingest is text-only.** markitdown converts slide text frames, tables, and
  speaker notes; images/diagrams are skipped, and an LLM image description is never
  verification evidence (it would punch a hole in fact-lock). Put key numbers in slide
  text or speaker notes so they are extractable.
- **Profile build fans out per document.** `extract_fragments` /
  `extract_synthesis_fragments` share one cache walk; production runs concurrently via
  `gather_isolated` with the permit acquired only in `llm_runner.acall`. The CLI and API both
  build through `services/profile_build.run_corpus_build` -- the single place the facts+matrix
  bound-artifact pair is written.
- **Project highlights are addressable facts.** `Project.highlights` holds
  `Bullet` objects, not strings, so `index_facts` registers a per-highlight id
  and the provenance gate can reject a fabricated project bullet. Its
  `mode="before"` migration accepts stored legacy string lists with deterministic
  non-empty ids; merge retains the full Bullet rather than flattening it to text.
- **Labeled dossiers retain their complete evidence bank.** `profile/dossier.py`
  recognizes the project-resume-dossier Name/Context/Evidence format and keeps
  source wording, aliases, citations, commits, and measurement limits. Each
  explained, cited skill example becomes a project highlight; skills point to
  those facts after stable id assignment. Exact repeated examples share a fact.
  Missing context/citations are reported as verification drops; fenced examples
  and unsupported model-added skills are excluded. Freeform/older documents keep
  model extraction. This checks source structure, not repository truth or
  authorship; ingestion never executes cited paths or measurement commands.
  Cross-project skill merge unions contexts and source refs. Project dedup
  remaps evidence ids to retained highlights. The matrix uses project highlights
  and explicit evidence links, including broad skills absent from tech lists.
  Increment `PROJECT_PROMPT_VERSION` when this projection changes so cached
  project fragments rebuild. The bundled project-dossier skill is hash pinned.
- **Bullet aspects are durable classifications.** New extractors emit the closed
  aspect vocabulary, while profile build backfills only bullets with
  `aspect is None`. A hand-corrected aspect therefore survives rebuilds; an
  unclassified legacy bullet remains valid and merely has no diversity signal.
- **Anchored coach notes ride verified synthesis.** A seeded `CoachTopic.owner_id`
  becomes a synthesis-mode corpus anchor when its draft is approved, so the
  generated stub merges by the exact experience id rather than heuristic title
  matching. Model-added topics remain unanchored literal notes. The opening
  agenda is seeded from non-empty below-target evidence owners, and user uploads
  that yielded no bullet are question material, never claimable fact.
