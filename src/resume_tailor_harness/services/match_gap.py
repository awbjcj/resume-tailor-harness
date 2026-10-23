"""Match-gap Skill classification application module."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from pathlib import Path

from sqlmodel import Session

from resume_tailor_harness.config import get_settings
from resume_tailor_harness.llm_runner import Runner, run_with_cleanup
from resume_tailor_harness.progress import ProgressReporter
from resume_tailor_harness.taxonomy.classification import (
    ClassificationFailure,
    ClassificationMetrics,
    ClassificationOutcome,
    classify_incrementally,
)
from resume_tailor_harness.taxonomy.clusters import (
    ClusterMap,
    merge_cluster_map,
    save_cluster_map,
    slugify_domain as slugify_domain,
)
from resume_tailor_harness.taxonomy.corrections import (
    apply_taxonomy_corrections,
)
from resume_tailor_harness.taxonomy.custody import TaxonomyCustody, TaxonomySnapshot
from resume_tailor_harness.taxonomy.embeddings import (
    CandidateContext,
    EmbeddingProvider,
    build_candidate_context,
)
from resume_tailor_harness.taxonomy.maintenance import (
    maintain_taxonomy as evaluate_maintenance,
)
from resume_tailor_harness.taxonomy.maintenance import pinned_domains_and_skills
from resume_tailor_harness.taxonomy.state import (
    ALGORITHM_VERSION,
    GroupingStatus,
    TaxonomyState,
    taxonomy_generation_dir,
    restore_retired_skills,
    set_grouping_statuses,
    snapshot_before_maintenance,
    undo_last_maintenance,
)
from resume_tailor_harness.taxonomy.vocabulary import SKILL_GROUPS, is_general_domain
from resume_tailor_harness.tracking.match_gap import normalize_skill
from resume_tailor_harness.tracking.match_gap import (
    collect_target_skill_context,
    collect_target_skill_tokens,
)
from resume_tailor_harness.tracking.canonicalize import build_classification_agents

# Domains that exist only to guarantee every demanded skill has a home.  The
# prefix is a naming convention, not a protected kind: maintenance is expected
# to split these into real domains over time.
FLOOR_DOMAIN_PREFIX = "general-"


class _MonotonicPhaseReporter(ProgressReporter):
    """Add a run-wide phase index to nested classification progress segments.

    Every method the delegate owns must be forwarded, including the terminal
    ones this wrapper has no opinion about: it deliberately never calls
    ``super().__init__``, so any inherited method that reached the base class's
    own record would fail on state that was never created.
    """

    def __init__(self, delegate: ProgressReporter) -> None:
        self._delegate = delegate
        self._phase_index = 0

    def begin(
        self,
        total: int,
        label: str,
        *,
        phase_index: int | None = None,
        phase_count: int | None = None,
        **extra: object,
    ) -> None:
        # A nested segment counts its own phases from one; the run-wide index
        # is this wrapper's whole purpose, so an inner phase_index is dropped.
        self._phase_index += 1
        self._delegate.begin(
            total,
            label,
            phase_index=self._phase_index,
            phase_count=phase_count,
            **extra,
        )

    def step(self, current: int, *, label: str | None = None, **extra: object) -> None:
        self._delegate.step(current, label=label, **extra)

    def checkpoint(self) -> None:
        self._delegate.checkpoint()

    def done(self, *, error: str | None = None, **extra: object) -> None:
        self._delegate.done(error=error, **extra)

    def cancelled(self, **extra: object) -> None:
        self._delegate.cancelled(**extra)


def floor_domain(category: str) -> tuple[str, str]:
    """Return the id and label of the general domain backing a category."""

    label = SKILL_GROUPS.get(category, SKILL_GROUPS["other"])
    return f"{FLOOR_DOMAIN_PREFIX}{category}", f"{label}: General"


def _unassigned(cmap: ClusterMap, tokens: set[str]) -> set[str]:
    """Canonical forms of ``tokens`` that still hold no domain in ``cmap``."""

    return {
        canonical
        for token in tokens
        if (canonical := cmap.aliases.get(token, token)) not in cmap.domain_of
    }


def _combine_recovery(
    outcomes: list[ClassificationOutcome],
) -> ClassificationOutcome | None:
    if not outcomes:
        return None
    additions = ClusterMap()
    for outcome in outcomes:
        additions = merge_cluster_map(additions, outcome.additions)
    return ClassificationOutcome(
        additions=additions,
        failures=tuple(failure for outcome in outcomes for failure in outcome.failures),
        not_skills=frozenset(
            token for outcome in outcomes for token in outcome.not_skills
        ),
        fallback_categories={
            token: category
            for outcome in outcomes
            for token, category in outcome.fallback_categories.items()
        },
        metrics=ClassificationMetrics(
            canonical_batches=sum(o.metrics.canonical_batches for o in outcomes),
            domain_batches=sum(o.metrics.domain_batches for o in outcomes),
            prompt_bytes=sum(o.metrics.prompt_bytes for o in outcomes),
            elapsed_ms=sum(o.metrics.elapsed_ms for o in outcomes),
            max_in_flight=max(o.metrics.max_in_flight for o in outcomes),
            canonical_calls=sum(o.metrics.canonical_calls for o in outcomes),
        ),
    )


def _retryable_canonical_tokens(
    failures: Sequence[ClassificationFailure],
) -> set[str]:
    """Tokens canonicalization still owes a verdict on, so nothing may file them.

    A provider outage has supplied no canonical judgment. Keep the original
    token pending instead of filing it under an invented interpretation.
    """

    return {
        normalized
        for failure in failures
        if failure.phase == "canonicalize" and failure.retryable
        for token in failure.tokens
        if (normalized := normalize_skill(token))
    }


def _apply_placement_floor(
    merged: ClusterMap,
    *,
    target_raw: set[str],
    not_skills: set[str],
    excluded: set[str],
    hints: dict[str, str],
    enabled: bool,
) -> tuple[ClusterMap, list[str]]:
    """Give every still-unplaced skill a home in its category's general domain.

    Bounded recovery has declined to commit, so the choice is between a skill
    nobody can see and a skill filed one level too coarsely.  The second is
    strictly more useful and is visibly provisional, and maintenance can split
    a general domain into real ones later.  The category is the model's own
    stated intent wherever it gave one, so this honours the classification it
    was unwilling to certify rather than inventing a new one.

    ``excluded`` names the tokens the floor must not touch, on two axes.  A
    token whose model *call* failed carries no judgment to honour, only an
    outage, and filing a skill because a request timed out would turn a
    transient error into a permanent misplacement.  A token canonicalization
    still owes a verdict on is excluded for the same reason from the other end:
    it has no settled canonical form to file.  Both keep their failed status
    and are retried on the next run.
    """

    remaining = sorted(_unassigned(merged, target_raw) - not_skills - excluded)
    if not enabled or not remaining:
        return merged, []
    additions = ClusterMap()
    for canonical in remaining:
        # Candidate retrieval is not a category judgment. In particular, the
        # top lexical match must not silently become a durable classification.
        category = hints.get(canonical) or "other"
        if category not in SKILL_GROUPS:
            category = "other"
        domain_id, label = floor_domain(category)
        additions.domain_of[canonical] = domain_id
        additions.domain_label.setdefault(domain_id, label)
        additions.category_of.setdefault(domain_id, category)
    return merge_cluster_map(merged, additions), remaining


def _domain_members(cmap: ClusterMap, domain_id: str) -> frozenset[str]:
    return frozenset(
        token
        for token, assigned_domain_id in cmap.domain_of.items()
        if assigned_domain_id == domain_id
    )


def _invalidate_changed_domain_suggestions(
    session: Session | None, before: ClusterMap, after: ClusterMap
) -> int:
    """Mark cached domain advice stale when a taxonomy operation changes it.

    Skill suggestions remain valid as long as their individual canonical and
    demand context are unchanged.  Domain suggestions summarize membership, so
    they must be refreshed after a regroup, maintenance generation, or undo.
    """

    if session is None:
        return 0
    changed_ids = {
        domain_id
        for domain_id in set(before.domain_label)
        | set(before.domain_of.values())
        | set(after.domain_label)
        | set(after.domain_of.values())
        if _domain_members(before, domain_id) != _domain_members(after, domain_id)
    }
    if not changed_ids:
        return 0
    from sqlmodel import select

    from resume_tailor_harness.tracking.tables import SkillSuggestion

    rows = session.exec(
        select(SkillSuggestion).where(SkillSuggestion.kind == "domain")
    ).all()
    changed = 0
    for row in rows:
        if row.key in changed_ids and row.fingerprint != "stale:taxonomy-change":
            row.fingerprint = "stale:taxonomy-change"
            changed += 1
    if changed:
        session.commit()
    return changed


def refresh_clusters(
    session: Session | None,
    *,
    canonicalizer: Runner | None = None,
    themer: Runner | None = None,
    path: str | Path,
    reporter: ProgressReporter | None = None,
    batch_size: int | None = None,
    concurrency: int | None = None,
    reconcile_batch_size: int | None = None,
    extra_tokens: frozenset[str] | set[str] = frozenset(),
    corrections_path: str | Path | None = None,
    skill_keys: set[str] | frozenset[str] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    demanded_tokens: set[str] | frozenset[str] | None = None,
    category_hints: dict[str, str] | None = None,
    skill_context: dict[str, list[str]] | None = None,
    escalation_themer: Runner | None = None,
) -> dict[str, object]:
    """Recover pending/provisional skills in a complete or explicit scope."""
    started = time.monotonic()
    settings = get_settings()
    size = settings.cluster_batch_size if batch_size is None else batch_size
    width = settings.llm_concurrency if concurrency is None else concurrency
    reconcile_size = (
        settings.cluster_reconcile_batch_size
        if reconcile_batch_size is None
        else reconcile_batch_size
    )
    if size < 1:
        raise ValueError("batch_size must be at least 1")
    if width < 1:
        raise ValueError("concurrency must be at least 1")
    if reconcile_size < 1:
        raise ValueError("reconcile_batch_size must be at least 1")
    if canonicalizer is None and themer is None and escalation_themer is None:
        agents = build_classification_agents()
        canonicalizer = agents.canonicalizer
        themer = agents.themer
        escalation_themer = agents.escalation_themer
    # Narrowed by the raise rather than by `assert`, which `-O` strips out.
    if canonicalizer is None or themer is None:
        raise ValueError("canonicalizer and themer must be provided together")

    correction_file = (
        corrections_path
        if corrections_path is not None
        else Path(path).with_name("taxonomy_corrections.json")
    )
    phase_reporter = _MonotonicPhaseReporter(reporter) if reporter is not None else None
    custody = TaxonomyCustody(path, correction_file)
    operation_wait_started = time.monotonic()
    with custody.operation():
        operation_wait_ms = round((time.monotonic() - operation_wait_started) * 1000)
        snapshot_started = time.monotonic()
        snapshot = custody.read_for_mutation()
        snapshot_ms = round((time.monotonic() - snapshot_started) * 1000)
        corrections = snapshot.corrections
        taxonomy_state = snapshot.state
        demanded = (
            (
                set(demanded_tokens)
                if demanded_tokens is not None
                else (
                    collect_target_skill_tokens(session)
                    if session is not None
                    else set()
                )
            )
            | set(extra_tokens)
            | set(corrections.added_skills)
        )
        demanded -= set(corrections.removed_skills)
        # A retired token names no skill.  Dropping it here is what stops the
        # backlog from re-buying the same LLM verdict on every single run.
        existing = snapshot.effective
        demanded = {
            normalize_skill(token) for token in demanded if normalize_skill(token)
        }
        demanded = {
            token
            for token in demanded
            if existing.aliases.get(token, token) not in taxonomy_state.retired_skills
        }
        _, pinned_skills = pinned_domains_and_skills(existing, corrections)
        # Moving one skill pins that skill, not every other generated member
        # of its category bucket. Domain edits do pin the whole domain.
        pinned_domains = (
            set(corrections.domain_renames)
            | set(corrections.domain_category)
            | set(corrections.domain_merges)
            | set(corrections.domain_merges.values())
        )
        provisional = {
            token
            for token, domain in existing.domain_of.items()
            if is_general_domain(domain)
            and domain not in pinned_domains
            and token not in pinned_skills
        }
        demanded_canonicals = {existing.aliases.get(token, token) for token in demanded}
        normalized_requested = {
            token for raw in (skill_keys or set()) if (token := normalize_skill(raw))
        }
        skipped_unknown: set[str] = set()
        skipped_assigned: set[str] = set()
        target_raw: set[str] = set()
        if skill_keys is None:
            target_raw = {
                token
                for token in demanded
                if existing.domain_of.get(existing.aliases.get(token, token)) is None
                or existing.aliases.get(token, token) in provisional
            }
        else:
            for token in normalized_requested:
                canonical = existing.aliases.get(token, token)
                if token not in demanded and canonical not in demanded_canonicals:
                    skipped_unknown.add(token)
                elif (
                    existing.domain_of.get(canonical) is not None
                    and canonical not in provisional
                ):
                    skipped_assigned.add(token)
                else:
                    target_raw.add(token)

        # A token that already failed a pass skips straight to escalation: a
        # replay of the identical batch, prompt, and gates is exactly why
        # clicking Regroup twice used to change nothing.
        attempted = {
            token
            for token, status in taxonomy_state.grouping_status.items()
            if status.phase == "domain"
        }
        first_pass = {
            token
            for token in target_raw
            if existing.aliases.get(token, token) not in attempted | provisional
        }
        source_context = (
            skill_context
            if skill_context is not None
            else collect_target_skill_context(session, target_raw, existing.aliases)
            if session is not None
            else {}
        )

        candidate_context: CandidateContext | None = None
        if first_pass:
            if phase_reporter is not None:
                phase_reporter.begin(1, "Retrieving taxonomy candidates")
            candidate_context = asyncio.run(
                build_candidate_context(
                    cluster_path=path,
                    tokens=first_pass,
                    existing=existing,
                    provider=embedding_provider,
                    revision=snapshot.effective_sha256,
                    checkpoint=(
                        phase_reporter.checkpoint
                        if phase_reporter is not None
                        else None
                    ),
                )
            )
            if phase_reporter is not None:
                phase_reporter.step(1, label="Retrieved taxonomy candidates")
        # Retrieval may only veto reuse it did not surface when it is actually
        # semantic.  Under a lexical or partial fallback it narrows the prompt
        # but no longer forbids an otherwise valid domain.
        enforce_candidates = (
            candidate_context is not None and candidate_context.mode == "embedding"
        )
        escalation_cap = settings.taxonomy_escalation_max_skills

        recovery_attempts = {
            token: status.escalation_attempts
            for token, status in taxonomy_state.grouping_status.items()
        }
        attempted_this_run: set[str] = set()
        recovery_rounds = 0

        async def classify_both() -> tuple[
            ClassificationOutcome, ClassificationOutcome | None, ClusterMap, set[str]
        ]:
            nonlocal recovery_rounds
            first = await classify_incrementally(
                demanded_tokens=first_pass,
                existing=existing,
                canonicalizer=canonicalizer,
                themer=themer,
                batch_size=size,
                concurrency=width,
                category_cap=settings.domains_per_category_target,
                reconcile_batch_size=reconcile_size,
                reporter=phase_reporter,
                candidate_context=candidate_context,
                allow_category_growth=True,
                min_new_domain_members=2,
                category_hints=category_hints,
                skill_context=source_context,
                enforce_candidates=enforce_candidates,
                repair_max_singletons=(
                    settings.taxonomy_canonical_repair_max_singletons
                ),
            )
            after_first = merge_cluster_map(existing, first.additions)
            # Temporarily remove only generated provisional placements from the
            # classifier's input. The saved last-good map remains intact, and
            # anything we cannot improve is restored before committing.
            targeted = {after_first.aliases.get(token, token) for token in target_raw}
            for token in provisional & targeted:
                after_first.domain_of.pop(token, None)
            canonical_failed = _retryable_canonical_tokens(first.failures)
            retired = set(first.not_skills)
            recovery: list[ClassificationOutcome] = []
            for _round in range(settings.taxonomy_recovery_rounds):
                pending = (
                    _unassigned(after_first, target_raw) - retired - canonical_failed
                )
                ordered = sorted(
                    pending,
                    key=lambda token: (
                        recovery_attempts.get(token, 0),
                        token in provisional,
                        taxonomy_state.grouping_status[token].last_attempted_at
                        if token in taxonomy_state.grouping_status
                        else "",
                        token,
                    ),
                )
                leftovers = ordered[:escalation_cap]
                if not leftovers:
                    break
                recovery_rounds += 1
                # Retry history changes the batch shape across runs as well as
                # within this run: 15 -> 3 -> 1 at the default batch size.
                tiers: dict[int, set[str]] = {}
                for token in leftovers:
                    tries = recovery_attempts.get(token, 0)
                    repair_size = max(1, size // (4 ** min(tries + 1, 4)))
                    tiers.setdefault(repair_size, set()).add(token)
                    recovery_attempts[token] = tries + 1
                    attempted_this_run.add(token)
                    after_first.aliases.setdefault(token, token)
                for repair_size, tokens in sorted(tiers.items(), reverse=True):
                    second = await classify_incrementally(
                        demanded_tokens=tokens,
                        existing=after_first,
                        canonicalizer=canonicalizer,
                        themer=escalation_themer or themer,
                        batch_size=repair_size,
                        concurrency=width,
                        category_cap=settings.domains_per_category_target,
                        reconcile_batch_size=reconcile_size,
                        reporter=phase_reporter,
                        candidate_context=None,
                        allow_category_growth=True,
                        min_new_domain_members=1,
                        category_hints=category_hints,
                        skill_context=source_context,
                    )
                    recovery.append(second)
                    retired.update(second.not_skills)
                    after_first = merge_cluster_map(after_first, second.additions)
                # A whole round of transport errors is an outage, not a reason
                # to spend the remaining budget replaying the same requests.
                round_results = recovery[-len(tiers) :]
                if all(
                    o.failures
                    and all(f.kind == "call" for f in o.failures)
                    and not o.additions.domain_of
                    and not o.not_skills
                    for o in round_results
                ):
                    break
            remaining = (
                _unassigned(after_first, target_raw) - retired - canonical_failed
            )
            deferred = remaining - attempted_this_run
            return first, _combine_recovery(recovery), after_first, deferred

        outcome, escalated, merged, deferred = asyncio.run(
            run_with_cleanup(
                classify_both(),
                canonicalizer,
                themer,
                *((escalation_themer,) if escalation_themer is not None else ()),
            )
        )
        not_skills = set(outcome.not_skills) | set(
            escalated.not_skills if escalated else ()
        )
        escalated_count = (
            len(escalated.additions.domain_of) if escalated is not None else 0
        )
        # Both passes report; the escalation pass is where the hard cases end
        # up, so hiding its failures would hide exactly the interesting ones.
        all_failures = tuple(outcome.failures) + tuple(
            escalated.failures if escalated else ()
        )
        last_domain_failure = {
            normalize_skill(token): failure
            for failure in all_failures
            if failure.phase == "domain"
            for token in failure.tokens
        }
        call_failed = {
            token
            for token, failure in last_domain_failure.items()
            if failure.kind == "call"
        }
        canonical_failed = _retryable_canonical_tokens(all_failures)
        merged, floor_placed = _apply_placement_floor(
            merged,
            target_raw=target_raw,
            not_skills=not_skills,
            excluded=call_failed | canonical_failed | deferred,
            hints={
                **{
                    token: existing.category_of[existing.domain_of[token]]
                    for token in provisional
                    if existing.domain_of[token] in existing.category_of
                },
                **outcome.fallback_categories,
                **(escalated.fallback_categories if escalated else {}),
            },
            enabled=settings.taxonomy_placement_floor,
        )
        for token in provisional:
            if token not in merged.domain_of and token not in not_skills:
                merged.domain_of[token] = existing.domain_of[token]
        # This is a growing canonical taxonomy rather than a view cache.  Even
        # an unscoped refresh may only add or clarify its current unassigned
        # backlog; it must never prune established domains or aliases that are
        # merely outside today's visible jobs.
        final = apply_taxonomy_corrections(merged, corrections)
        if phase_reporter is not None:
            phase_reporter.checkpoint()
        # Distinct tokens, not token-attempts: a token the first pass and the
        # escalation pass both failed is one unresolved skill, not two.
        canonical_failures = len(
            {
                token
                for failure in all_failures
                if failure.phase == "canonicalize"
                for token in failure.tokens
            }
        )
        domain_failures = len(
            {
                token
                for failure in all_failures
                if failure.phase == "domain"
                for token in failure.tokens
            }
        )
        failure_reasons: dict[str, int] = {}
        for failure in all_failures:
            failure_reasons[failure.message] = failure_reasons.get(
                failure.message, 0
            ) + len(failure.tokens)
        requested_canonicals = {final.aliases.get(token, token) for token in target_raw}
        retired_canonicals = {
            final.aliases.get(token, token) for token in not_skills
        } & requested_canonicals
        assigned = {token for token in requested_canonicals if token in final.domain_of}
        provisional_now = {
            token
            for token in requested_canonicals
            if is_general_domain(final.domain_of.get(token))
        }
        statuses: dict[str, GroupingStatus] = {}
        for failure in all_failures:
            failure_state = "failed" if failure.kind == "call" else "uncertain"
            for token in failure.tokens:
                canonical = final.aliases.get(
                    normalize_skill(token), normalize_skill(token)
                )
                if canonical not in final.domain_of and canonical not in retired_canonicals:
                    statuses[canonical] = GroupingStatus(
                        state=failure_state,
                        reason=failure.message,
                        phase=failure.phase,
                    )
        for token in requested_canonicals - assigned - retired_canonicals:
            statuses.setdefault(
                token,
                GroupingStatus(
                    state="uncertain",
                    reason="no high-confidence existing or coherent new domain",
                    # Canonicalization settled; only the domain is unresolved.
                    phase="domain",
                ),
            )

        for token in provisional_now:
            statuses[token] = GroupingStatus(
                state="uncertain",
                phase="domain",
                reason="Provisional category placement; a specific domain still needs confirmation",
            )
        for token, status in statuses.items():
            previous = taxonomy_state.grouping_status.get(token)
            if token in deferred and previous is not None:
                statuses[token] = previous
            else:
                status.escalation_attempts = recovery_attempts.get(token, 0)
        # Older refreshes retained failures for skills already placed. Clear
        # those obsolete records even outside this run's requested scope,
        # while preserving unresolved history and provisional retry counts.
        resolved_keys = {
            token
            for token in target_raw | taxonomy_state.grouping_status.keys()
            if (
                final.aliases.get(token, token)
                in taxonomy_state.retired_skills.keys() | retired_canonicals
                or (
                    final.aliases.get(token, token) in final.domain_of
                    and not is_general_domain(
                        final.domain_of[final.aliases.get(token, token)]
                    )
                )
            )
        }

        def commit_refresh(_current: TaxonomySnapshot) -> object:
            save_cluster_map(final, path)
            return set_grouping_statuses(
                path,
                assigned=assigned | resolved_keys,
                statuses=statuses,
                retired={token: "not a skill" for token in retired_canonicals},
            )

        commit_started = time.monotonic()
        custody.commit(snapshot, commit_refresh)
        commit_ms = round((time.monotonic() - commit_started) * 1000)
        invalidation_started = time.monotonic()
        stale_suggestions = _invalidate_changed_domain_suggestions(
            session, existing, final
        )
        invalidation_ms = round((time.monotonic() - invalidation_started) * 1000)
        domains_created = len(set(final.domain_label) - set(existing.domain_label))
        aliases_merged = sum(
            final.aliases.get(token, token) != token for token in target_raw
        )
    # "Deferred" means the escalation cap postponed it, not that anything
    # judged it -- it escalates first on the next run.  Collapsing it into
    # "uncertain" is what made monotonic progress read as a plateau.
    deferred_canonicals = deferred & requested_canonicals
    uncertain_domain = len(
        [
            token
            for token, status in statuses.items()
            if status.state == "uncertain"
            and status.phase == "domain"
            and token not in deferred_canonicals
        ]
    )
    uncertain_canonical = len(
        [
            token
            for token, status in statuses.items()
            if status.state == "uncertain" and status.phase == "canonicalize"
        ]
    )
    escalated_metrics = escalated.metrics if escalated else None
    model_elapsed_ms = outcome.metrics.elapsed_ms + (
        escalated.metrics.elapsed_ms if escalated else 0
    )
    retrieval_metrics = candidate_context.metrics if candidate_context else None
    return {
        "skills": len(set(final.aliases.values())),
        "domains": len(final.domain_label),
        "failedCanonicalTokens": canonical_failures,
        "failedDomainTokens": domain_failures,
        "canonicalBatches": outcome.metrics.canonical_batches
        + (escalated.metrics.canonical_batches if escalated else 0),
        "canonicalCalls": outcome.metrics.canonical_calls
        + (escalated.metrics.canonical_calls if escalated else 0),
        "domainBatches": outcome.metrics.domain_batches
        + (escalated.metrics.domain_batches if escalated else 0),
        "promptBytes": outcome.metrics.prompt_bytes
        + (escalated.metrics.prompt_bytes if escalated else 0),
        "elapsedMs": round((time.monotonic() - started) * 1000),
        "modelElapsedMs": model_elapsed_ms,
        "operationWaitMs": operation_wait_ms,
        "snapshotMs": snapshot_ms,
        "retrievalMs": retrieval_metrics.elapsed_ms if retrieval_metrics else 0,
        "candidateIndexMs": retrieval_metrics.index_ms if retrieval_metrics else 0,
        "candidateRankingMs": (
            retrieval_metrics.ranking_ms if retrieval_metrics else 0
        ),
        "embeddingDescriptors": (
            retrieval_metrics.descriptors if retrieval_metrics else 0
        ),
        "embeddingCacheHits": (
            retrieval_metrics.cache_hits if retrieval_metrics else 0
        ),
        "embeddingCacheMisses": (
            retrieval_metrics.cache_misses if retrieval_metrics else 0
        ),
        "embeddingProviderBatches": (
            retrieval_metrics.provider_batches if retrieval_metrics else 0
        ),
        "embeddingCacheBytes": (
            retrieval_metrics.cache_bytes if retrieval_metrics else 0
        ),
        "commitMs": commit_ms,
        "invalidationMs": invalidation_ms,
        "maxInFlight": max(
            outcome.metrics.max_in_flight,
            escalated.metrics.max_in_flight if escalated else 0,
        ),
        "embeddingMode": outcome.metrics.embedding_mode,
        # Retrieval degrading to a lexical fallback used to be invisible, which
        # is how it ran that way for the entire life of the feature.
        "embeddingDegraded": candidate_context is not None
        and candidate_context.degraded,
        "embeddingReason": candidate_context.reason if candidate_context else "",
        "escalatedSkills": escalated_count,
        "recoveryRounds": recovery_rounds,
        "recoveryAttemptedSkills": len(attempted_this_run),
        "provisionalSkills": len(provisional_now),
        "refinedSkills": len((provisional & assigned) - provisional_now),
        "confirmedSkills": len(assigned - provisional_now),
        "placedByFallback": len(floor_placed),
        "retiredSkills": sorted(retired_canonicals),
        "algorithmVersion": ALGORITHM_VERSION,
        "requestedSkills": sorted(requested_canonicals),
        "processedSkillKeys": sorted(target_raw),
        "assignedSkills": len(assigned),
        "uncertainSkills": len(
            [status for status in statuses.values() if status.state == "uncertain"]
        ),
        "deferredSkills": len(deferred_canonicals),
        "uncertainDomainSkills": uncertain_domain,
        "uncertainCanonicalSkills": uncertain_canonical,
        "canonicalRepairRounds": outcome.metrics.canonical_repair_rounds
        + (escalated_metrics.canonical_repair_rounds if escalated_metrics else 0),
        "canonicalRepaired": outcome.metrics.canonical_repaired
        + (escalated_metrics.canonical_repaired if escalated_metrics else 0),
        "canonicalIdentityFiled": outcome.metrics.canonical_identity_filed
        + (escalated_metrics.canonical_identity_filed if escalated_metrics else 0),
        "failedSkills": len(
            [status for status in statuses.values() if status.state == "failed"]
        ),
        "failureReasons": failure_reasons,
        "domainsCreated": domains_created,
        "aliasesMerged": aliases_merged,
        "remainingUnassigned": len(
            requested_canonicals - assigned - retired_canonicals
        ),
        "skippedAlreadyAssigned": sorted(skipped_assigned),
        "skippedUnknown": sorted(skipped_unknown),
        "skippedStaleSkills": len(skipped_assigned) + len(skipped_unknown),
        "staleSuggestions": stale_suggestions,
    }


def restore_skills(
    *, path: str | Path, skill_keys: set[str] | frozenset[str]
) -> dict[str, object]:
    """Un-retire tokens so the next regroup reconsiders them as real skills."""

    correction_file = Path(path).with_name("taxonomy_corrections.json")
    with TaxonomyCustody(path, correction_file).mutation():
        _state, restored = restore_retired_skills(path, set(skill_keys))
    return {"restoredSkills": restored, "restored": len(restored)}


def maintain_taxonomy(
    session: Session | None,
    *,
    judge: Runner,
    path: str | Path,
    corrections_path: str | Path | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, object]:
    """Run one correction-safe, versioned taxonomy maintenance generation."""

    settings = get_settings()
    correction_file = (
        corrections_path
        if corrections_path is not None
        else Path(path).with_name("taxonomy_corrections.json")
    )
    custody = TaxonomyCustody(path, correction_file)
    with custody.operation():
        snapshot = custody.read_for_mutation()
        corrections = snapshot.corrections
        existing = snapshot.effective
        outcome = asyncio.run(
            run_with_cleanup(
                evaluate_maintenance(
                    cluster_path=str(path),
                    cmap=existing,
                    corrections=corrections,
                    judge=judge,
                    max_churn=settings.taxonomy_maintenance_max_churn,
                    embedding_provider=embedding_provider,
                ),
                judge,
            )
        )
        final = apply_taxonomy_corrections(outcome.cluster_map, corrections)
        changed = outcome.changed and final != existing

        def commit_maintenance(current: TaxonomySnapshot) -> TaxonomyState:
            if not changed:
                return current.state
            # The generation file lives outside custody's rollback set, so a
            # failed map write would otherwise strand a snapshot that the
            # restored state no longer references.
            state, generation = snapshot_before_maintenance(path, existing)
            try:
                save_cluster_map(final, path)
            except BaseException:
                (taxonomy_generation_dir(path) / generation.snapshot).unlink(
                    missing_ok=True
                )
                raise
            return state

        state = custody.commit(snapshot, commit_maintenance)
        stale_suggestions = _invalidate_changed_domain_suggestions(
            session, existing, final
        )
    return {
        "changed": changed,
        "generationId": state.generation_id,
        "algorithmVersion": ALGORITHM_VERSION,
        "maintenanceDue": state.maintenance_due,
        "actions": [action.model_dump(mode="json") for action in outcome.actions],
        "rejectedActions": list(outcome.rejected_actions),
        "embeddingMode": outcome.embedding_mode,
        "churnedSkills": outcome.churned_skills,
        "undoAvailable": state.can_undo,
        "staleSuggestions": stale_suggestions,
    }


def undo_taxonomy_maintenance(
    session: Session | None,
    *,
    path: str | Path,
    corrections_path: str | Path | None = None,
) -> dict[str, object]:
    """Restore the immediately preceding generated taxonomy version."""

    correction_file = (
        corrections_path
        if corrections_path is not None
        else Path(path).with_name("taxonomy_corrections.json")
    )
    custody = TaxonomyCustody(path, correction_file)
    with custody.mutation():
        snapshot = custody.read_for_mutation()
        corrections = snapshot.corrections
        existing = snapshot.effective
        restored, state = undo_last_maintenance(path)
        final = apply_taxonomy_corrections(restored, corrections)
        save_cluster_map(final, path)
        stale_suggestions = _invalidate_changed_domain_suggestions(
            session, existing, final
        )
    return {
        "restored": True,
        "generationId": state.generation_id,
        "algorithmVersion": ALGORITHM_VERSION,
        "maintenanceDue": state.maintenance_due,
        "undoAvailable": state.can_undo,
        "staleSuggestions": stale_suggestions,
    }
