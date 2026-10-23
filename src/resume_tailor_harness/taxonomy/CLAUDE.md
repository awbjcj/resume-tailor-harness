# Taxonomy developer reference

Migrated from the project root `CLAUDE.md` (2026-08-15, CLAUDE.md split) — loads only when working under `src/resume_tailor_harness/taxonomy/`.

- **An unresolved country silently drops the region too, so the country table
  is load-bearing.** `build_location` assigns `region` only when a country
  resolved (deliberate — see
  `docs/superpowers/specs/2026-07-20-international-location-region-design.md`),
  which meant a ~45-entry hand-written country list quietly truncated most of
  the world to a bare city: "Colombo, Western Province, Sri Lanka" reached the
  board as "Colombo". `taxonomy/countries.py` now carries the whole ISO 3166-1
  standard (official short names plus an ASCII-folded variant, so "Turkiye"
  resolves as typed) with `COUNTRY_ALIASES` for the colloquial names the
  standard lacks. `_country_suffix` matches the longest trailing sequence so
  official comma-bearing names such as "Korea, Republic of" remain reachable.
  Regenerate the table; do not hand-edit it.
- **17 ISO alpha-2 codes are also USPS state codes, and "Georgia" is both a
  country and a state.** Completing the country table therefore could not be
  done alone: it would have read "Atlanta, GA" as Gabon. `_country_suffix`
  confines the ambiguity to the two-part shape, where the US-state reading
  wins ("City, ST" is far more common than "City, CountryCode", and the
  country is inferred from the state anyway); three or more parts put the
  trailing token in an unambiguous country slot ("Toronto, ON, CA"). This also
  fixed a live bug in the other direction — "San Francisco, CA" was resolving
  to Canada.
- **A workplace-type suffix is stripped before the structural read.** Boards
  glue it onto the label ("Ann Arbor, MI - Hybrid", "Seattle, WA (Hybrid)"),
  which leaves the trailing part unresolvable as either a state or a country
  and — via the region rule above — collapses the value to a bare city.
  `_strip_workplace_suffix` removes it; nothing is lost, because the workplace
  type is captured separately as its own sidebar line and `raw` keeps the
  provider's original string. A value that is *only* a workplace tag
  ("Remote", "Remote - US") is left intact for the remote branch, which is why
  the strip requires a preceding locality.
- **Skill groups are a derived display axis.** `MatrixRow.group` comes from the
  active data root's `taxonomy/skill_groups.json` (token → slug, fixed 20-slug
  vocabulary in `taxonomy/vocabulary.py`). Profile builds classify only missing
  tokens with the cheap tier; failed batches remain absent and retry on the next
  build. Match-gap refreshes apply the saved map without an LLM, and
  `overrides.yaml`'s `group:` map wins over taxonomy. User re-categorizations
  from Settings > Skill groups live in `data/profile/group_corrections.json`,
  win over both overrides and taxonomy, and are replayed by
  `decorate_matrix_groups` on every matrix rebuild. The LLM classifier never
  reads or writes corrections, and `MatrixRow.group_source` records whether a
  correction, override, or taxonomy assigned the row. Groups never alter
  `facts.json` or the hard/soft/domain categories used by fact-lock; unassigned
  rows render as Other.
- **Skill taxonomy is three-level and correction-locked.** The fixed 20-slug category
  vocabulary lives in `taxonomy/vocabulary.py` (shared by the profile matrix group axis
  and the constellation); LLM-clustered domains parent to exactly one category with a
  deterministic per-category cap (`Settings.domains_per_category_cap`, default 12)
  enforced in `classification._project_domains`, never trusted to the model. User edits
  (move/rename/merge/add/remove/alias) write intent entries to
  `data/taxonomy/taxonomy_corrections.json` via `services/taxonomy.py` and are replayed
  last by `apply_taxonomy_corrections` on every load — corrections beat LLM output;
  dangling references are inert. Legacy cluster files load aliases-only (themes ignored),
  so the first refresh reclassifies once; legacy `theme`-kind suggestions are purged.
- **Regroup telemetry is diagnostic-only, and deliberately unrendered.**
  `refresh_clusters` returns wall-clock (`elapsedMs`) alongside a breakdown —
  `modelElapsedMs`, `operationWaitMs`, `snapshotMs`, `retrievalMs`,
  `candidateIndexMs`, `candidateRankingMs`, `commitMs`, `invalidationMs`,
  `maxInFlight`, and the embedding-cache counters. These land on the run record
  and in `run_corpus_build`'s report under `taxonomy`; **no UI reads them**, and
  none is a contract any surface depends on. They exist so a slow regroup can be
  diagnosed from a run record without re-running the classification — which of
  index build, ranking, provider batches or the commit actually cost the time.
  One caveat when comparing runs across the 2026-08-26 boundary: `elapsedMs`
  used to mean model time and now means whole-operation wall clock, with the old
  quantity available as `modelElapsedMs`.
- **Custody splits the lock that admits a mutation from the lock that guards
  the files.** `TaxonomyCustody` holds two per-workspace `RLock`s. The
  *operation* lock (`operation()`) admits one long-running mutation — a regroup
  spends minutes in LLM calls under it — while the *artifact* lock is taken only
  for the read and for the commit, so `read()` stays available throughout. A
  writer therefore: takes `operation()`, calls `read_for_mutation()` for a
  validated base, does its slow work, then calls `commit(snapshot, write)`,
  which re-reads under both locks, raises `TaxonomyConflictError` if the
  revision moved, and rolls every artifact back (via `rollback.rollback_scope`)
  if `write` raises. `mutation()` remains the short-operation shorthand that
  takes both locks at once. The artifact critical section also takes a
  per-workspace on-disk lock, so multi-worker reads and commits are coherent:
  long model work may overlap across processes, but the first commit wins and a
  stale sibling receives `TaxonomyConflictError` from the revision check.
- **A mutation base is loaded strictly; a read is not.** The lenient loaders
  (`load_cluster_map`, `load_taxonomy_corrections`, `load_taxonomy_state`)
  return empty on corruption, which is right for display and catastrophic for a
  mutation — an unreadable corrections ledger would read as "no user intent"
  and the next save would erase it. The `*_strict` variants distinguish absence
  (empty) from corruption (`ValueError`), and both `read_for_mutation()` and
  `mutation()` use them. Consequence to keep in mind when adding a caller:
  `mutation()` now *raises* on a corrupt sidecar, so any expensive work already
  done inside that caller is lost.
- **Retrieval narrows the prompt; it never forbids an answer unless it is
  semantic.** `taxonomy/embeddings.py` only reduces what the classifier is
  shown, but `_project_domains` also used `allowed_domain_ids` as a hard veto on
  existing-domain reuse. That was safe only while retrieval worked — and it
  never had. `cached_embeddings` ran ~50 sequential provider calls for a real
  map (12,752 descriptors ÷ 256) and wrote the cache **only after all of them
  succeeded**, so one rate-limited shard discarded every sibling and the next
  run repeated the loss: no tenant ever had a `skill_embeddings.json`, and every
  run silently used the lexical fallback. That fallback scored symmetric Jaccard
  over the whole descriptor, whose union denominator grows with member count, so
  the _smallest_ domain won — measured on a live 155-domain taxonomy, one domain
  ranked first for **42 of 60** consecutive queries and the top-8 union reached
  only **53 of 155** domains, making two-thirds of the taxonomy unreachable per
  batch. Now: `embed_descriptors` persists every shard that lands and degrades
  to `partial` instead of raising; `_LexicalCorpus` scores IDF-weighted query
  coverage against a domain's identity (label + human category label) with a
  discounted member-overlap term; and `enforce_candidates` gates the veto on
  `mode == "embedding"`. Cosine and lexical scores are never ranked against each
  other — an embedded query competes only among embedded candidates.
- **Regroup uses an incremental pass followed by bounded recovery rounds.**
  Previously recorded domain failures and generated General placements go
  directly to recovery. Canonicalize failures and legacy records without a
  phase use the standard path first. `taxonomy_recovery_rounds` defaults to 3;
  `taxonomy_escalation_max_skills` admits up to 300 skills per round. Durable
  `GroupingStatus.escalation_attempts` increments only on actual attempts.
  Least-attempted work runs first, with age/key tie breakers; deferral preserves
  history. Repeated attempts shrink batches (15, 3, 1 by default). A whole
  round of provider errors stops recovery until the next run. Error envelopes
  are call failures, not uncertain model judgments.
- **Recovery sees every domain, with bounded member examples.** Each domain
  includes total `skill_count` and up to eight evenly spaced members. The
  context is indexed once per classification pass and filtered per retrieval
  batch. Recovery receives the full domain directory. This reduces repeated
  context without making domains unreachable; it does not establish semantic
  accuracy without a labeled/live evaluation.
- **Canonicalization repairs omissions and isolates refinement failures.**
  Shrinking rounds retain valid partitions. Singleton repair is bounded by
  `taxonomy_canonical_repair_max_singletons`; surviving output omissions keep
  their own canonical instead of inventing a synonym. Initial provider errors
  remain retryable. Cross-batch reconciliation already has valid canonical
  heads: an incomplete answer or call failure retains those heads and records
  a non-retryable refinement gap, so successful siblings can be saved.
  `canonicalCalls` includes repairs/reconciliation; `canonicalBatches` retains
  the legacy initial-batch meaning.
- **The canonicalizer runs on the mid tier, not premium.** It used to run on
  `premium_model` while the harder domain judgment ran on `mid_model` —
  inverted, and premium was not buying completeness: every one of the 446
  failure records on the reference workspace was an incomplete premium
  partition. Repair rounds and the identity backstop now absorb coverage loss
  that used to be permanent, so the cheaper tier's downside is bounded.
  Escalation keeps `premium_model`; the ambiguous tail is where it earns its
  cost. Watch the ratio of `canonicalRepaired` to `canonicalIdentityFiled` on a
  run record — a large `canonicalIdentityFiled` means the repair rounds stopped
  pulling their weight, and the tier is the first thing to reconsider. Repair
  rounds catch *omissions*; nothing catches a confidently *wrong* merge, which
  is the known risk this tier change accepts.
- **The Message Batches API was evaluated and rejected — on latency and seam
  cost, not on ignorance.** It cannot reach these call sites without bypassing
  agno (`acall` → `AgentRunner.arun` → `Agent(output_schema=...)`; batches need
  raw `client.messages.batches.create`), which would mean re-implementing
  structured-output binding, `SpendGate.open` gating, `SpendGate.settle` usage
  recording, and the `is_transient` predicate outside the `build_model` seam,
  and forking provider support since the seam covers four vendors and Batches
  is Anthropic-only. The pipeline is also only partly batchable — reconcile is
  strictly sequential by design — so it would take three dispatches of up to an
  hour each and turn an interactive Regroup into an overnight job. And the
  money is not there: a regroup is a sub-dollar operation, so halving it does
  not pay for a second dispatch architecture. **The trigger to revisit is rate
  limiting, not cost:** if regroups start failing with `kind="call"` 429s, the
  Batches API's separate and much higher throughput ceiling becomes the actual
  reason to adopt it. Full evaluation:
  `docs/superpowers/specs/2026-08-27-taxonomy-canonicalize-repair-design.md`.
- **Fallback placement is provisional, visible and refinable.** After
  recovery, uncertain answers may enter `general-<category>` when
  `taxonomy_placement_floor` is enabled. Only a model category judgment or
  previous provisional category supplies the category; retrieval rank alone
  cannot. Missing judgments use `general-other`. Deferred skills and unresolved
  provider/canonicalization failures are not newly filed. Existing provisional
  placements survive outages and are eligible for later regrouping; user
  corrections remain protected. General buckets never establish same-domain
  adjacency in match-gap or tailoring. Category membership is not evidence of
  transferability. Results distinguish confirmed, provisional, refined,
  failed, deferred, retired and unassigned skills.
- **`not_skills` is a terminal disposition, and it is reversible.** The domain
  classifier may return tokens that name no skill (`8+ years of machine learning
experience`); they land in `TaxonomyState.retired_skills`, are subtracted from
  `demanded` on every later run, and are never re-sent. Without it the backlog
  re-bought the same verdict forever. They stay visible via
  `MatchGapOut.retiredSkills` and return through
  `POST /api/match-gap/restore-skills` — deliberately synchronous, since it only
  edits the state file.
- **"Reorganize domains" cannot assign a skill.** `maintain_taxonomy` merges,
  splits, renames and reparents _domains_, and gates on not increasing the
  unassigned count; nothing in it lowers that count. The button is named for
  what it does so it is not mistaken for a second Regroup.

- **Use source evidence for the ambiguous tail.** With an active database
  session, regroup supplies up to two bounded excerpts per skill from active
  target jobs. Evidence follows aliases and is included only for the current
  batch. Treat job text as data. Existing domain examples can contain historical
  mistakes; a member match must not override the meaning of its label/category.
  Refresh also clears stale failure records for already confirmed or retired
  skills, while preserving unresolved and provisional retry history.

See `docs/skill-taxonomy-recovery.md` for settings, compatibility, the
16,000-skill convergence regression and exported-workspace validation.
