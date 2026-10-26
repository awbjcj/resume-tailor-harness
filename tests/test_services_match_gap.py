from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import cast

import resume_tailor_harness.services.match_gap as match_gap_module
from resume_tailor_harness.db import get_session, init_db, make_engine
from resume_tailor_harness.progress import ProgressReporter
from resume_tailor_harness.services.match_gap import refresh_clusters, slugify_domain
from resume_tailor_harness.taxonomy.classification import (
    ClassificationMetrics,
    ClassificationOutcome,
)
from resume_tailor_harness.taxonomy.clusters import (
    ClusterMap,
    load_cluster_map,
    save_cluster_map,
)
from resume_tailor_harness.taxonomy.state import load_taxonomy_state
from resume_tailor_harness.tracking.canonicalize import (
    IncrementalDomainGroup,
    IncrementalSkillDomains,
    SkillClusters,
)
from resume_tailor_harness.tracking.tables import Job, JobStatus


def _engine_with_target_skills(*skills: str):
    engine = make_engine("sqlite://")
    init_db(engine)
    with get_session(engine) as session:
        session.add(
            Job(
                source="manual",
                status=JobStatus.shortlisted.value,
                criteria_json={"must_have_skills": list(skills)},
            )
        )
        session.commit()
    return engine


class _AsyncCanonicalizer:
    def __init__(self, respond=None):
        self.respond = respond or (lambda new, existing: [[token] for token in new])
        self.calls = 0
        self.closed = False

    async def arun(self, prompt):
        self.calls += 1
        payload = json.loads(prompt)
        response = self.respond(payload["new"], payload["existing_canonicals"])
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            content=SkillClusters.model_validate({"clusters": response})
        )

    def run(self, prompt):
        raise AssertionError("async path expected")

    async def aclose(self):
        self.closed = True


class _AsyncThemer:
    def __init__(self, respond=None):
        self.respond = respond or (
            lambda new, existing: [
                IncrementalDomainGroup(
                    confidence="high",
                    new_label="Languages",
                    new_category="languages",
                    skills=list(new),
                )
            ]
        )
        self.calls = 0
        self.closed = False

    async def arun(self, prompt):
        self.calls += 1
        payload = json.loads(prompt)
        response = self.respond(payload["new"], payload["categories"])
        if isinstance(response, Exception):
            raise response
        if isinstance(response, IncrementalSkillDomains):
            return SimpleNamespace(content=response)
        return SimpleNamespace(content=IncrementalSkillDomains(domains=response))

    def run(self, prompt):
        raise AssertionError("async path expected")

    async def aclose(self):
        self.closed = True


def test_slugify_domain_uses_lowercase_hyphenated_alphanumeric_runs():
    assert slugify_domain("  Cloud / Data & AI  ") == "cloud-data-ai"
    assert slugify_domain("C++ / .NET") == "c-net"


def _seed_domain_backlog(path, tokens, *, attempts=0):
    from resume_tailor_harness.taxonomy.state import (
        GroupingStatus,
        TaxonomyState,
        save_taxonomy_state,
    )

    save_cluster_map(ClusterMap(aliases={t: t for t in tokens}), path)
    save_taxonomy_state(
        TaxonomyState(
            grouping_status={
                t: GroupingStatus(
                    reason="incomplete", phase="domain", escalation_attempts=attempts
                )
                for t in tokens
            }
        ),
        path,
    )


def test_recovery_usage_does_not_explode_into_repeated_singletons(tmp_path):
    path = tmp_path / "cluster_map.json"
    tokens = {f"ambiguous {i:04d}" for i in range(300)}
    _seed_domain_backlog(path, tokens, attempts=2)
    sizes = []

    def uncertain(new, _categories):
        sizes.append(len(new))
        return []

    first = refresh_clusters(
        None, path=path, demanded_tokens=tokens,
        canonicalizer=_AsyncCanonicalizer(), themer=_AsyncThemer(uncertain),
    )
    assert len(sizes) <= 30
    assert min(sizes) >= 10
    assert first["confirmedSkills"] == 0
    assert first["provisionalSkills"] == 300
    before = load_taxonomy_state(path)
    sizes.clear()
    second = refresh_clusters(
        None, path=path, demanded_tokens=tokens,
        canonicalizer=_AsyncCanonicalizer(), themer=_AsyncThemer(uncertain),
    )
    assert sizes == []
    assert second["deferredSkills"] == 300
    assert load_taxonomy_state(path).grouping_status == before.grouping_status


def test_recovery_call_budget_saves_success_and_preserves_unattempted_history(
    tmp_path, monkeypatch,
):
    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_MAX_MODEL_CALLS", "2")
    env_settings.cache_clear()
    path = tmp_path / "cluster_map.json"
    tokens = {f"skill {i:04d}" for i in range(300)}
    _seed_domain_backlog(path, tokens)
    before = load_taxonomy_state(path)
    themer = _AsyncThemer()
    try:
        result = refresh_clusters(
            None, path=path, demanded_tokens=tokens,
            canonicalizer=_AsyncCanonicalizer(), themer=themer, concurrency=8,
        )
    finally:
        env_settings.cache_clear()
    assert themer.calls == 2
    assert result["modelCalls"] == 2
    assert result["usageLimitReached"] is True
    assert result["confirmedSkills"] == 30
    assert result["deferredSkills"] == 270
    assert result["failedSkills"] == 0
    assert len(load_cluster_map(path).domain_of) == 30
    after = load_taxonomy_state(path)
    assert len(after.grouping_status) == 270
    for token, status in after.grouping_status.items():
        assert status == before.grouping_status[token]


def test_prompt_budget_defers_without_inventing_a_canonical_or_placement(
    tmp_path, monkeypatch,
):
    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_MAX_PROMPT_BYTES", "1")
    env_settings.cache_clear()
    path = tmp_path / "cluster_map.json"
    canonicalizer, themer = _AsyncCanonicalizer(), _AsyncThemer()
    try:
        result = refresh_clusters(
            None, path=path, demanded_tokens={"rust"},
            canonicalizer=canonicalizer, themer=themer,
        )
    finally:
        env_settings.cache_clear()
    assert canonicalizer.calls == themer.calls == 0
    assert result["deferredSkills"] == 1
    assert result["failedSkills"] == result["placedByFallback"] == 0
    assert result["promptBytes"] == 0
    assert load_cluster_map(path).aliases == {}
    assert load_taxonomy_state(path).grouping_status["rust"].phase == "canonicalize"


def test_explicit_skill_retry_can_revisit_automatic_retry_limit(tmp_path):
    path = tmp_path / "cluster_map.json"
    _seed_domain_backlog(path, {"rust"}, attempts=3)
    automatic = _AsyncThemer()
    refresh_clusters(
        None, path=path, demanded_tokens={"rust"},
        canonicalizer=_AsyncCanonicalizer(), themer=automatic,
    )
    assert automatic.calls == 0
    result = refresh_clusters(
        None, path=path, demanded_tokens={"rust"}, skill_keys={"rust"},
        canonicalizer=_AsyncCanonicalizer(), themer=_AsyncThemer(),
    )
    assert result["confirmedSkills"] == 1
    assert load_cluster_map(path).domain_of["rust"] == "languages"


def test_usage_budget_is_shared_with_canonical_repairs(tmp_path, monkeypatch):
    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_MAX_MODEL_CALLS", "3")
    env_settings.cache_clear()
    path = tmp_path / "cluster_map.json"
    canonicalizer = _AsyncCanonicalizer(lambda *_: [])
    themer = _AsyncThemer()
    try:
        result = refresh_clusters(
            None, path=path, demanded_tokens={f"unknown {i}" for i in range(20)},
            canonicalizer=canonicalizer, themer=themer,
        )
    finally:
        env_settings.cache_clear()
    assert canonicalizer.calls == 3
    assert themer.calls == 0
    assert result["deferredSkills"] == 20
    assert result["canonicalIdentityFiled"] == 0
    assert load_cluster_map(path).aliases == {}


def test_usage_budget_keeps_canonicals_when_domain_pass_is_deferred(tmp_path, monkeypatch):
    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_MAX_MODEL_CALLS", "2")
    env_settings.cache_clear()
    path = tmp_path / "cluster_map.json"
    canonicalizer, themer = _AsyncCanonicalizer(), _AsyncThemer()
    try:
        result = refresh_clusters(
            None, path=path, demanded_tokens={"rust"},
            canonicalizer=canonicalizer, themer=themer,
        )
    finally:
        env_settings.cache_clear()
    assert canonicalizer.calls == 2
    assert themer.calls == 0
    assert result["deferredSkills"] == 1
    assert load_cluster_map(path).aliases == {"rust": "rust"}
    assert load_cluster_map(path).domain_of == {}
    assert load_taxonomy_state(path).grouping_status["rust"].phase == "domain"


def test_prompt_budget_counts_cumulative_payloads_across_concurrent_calls(
    tmp_path, monkeypatch,
):
    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_MAX_PROMPT_BYTES", "6000")
    env_settings.cache_clear()
    path = tmp_path / "cluster_map.json"
    tokens = {f"skill {i:04d}" for i in range(100)}
    _seed_domain_backlog(path, tokens)
    payload_sizes = []

    class RecordingThemer(_AsyncThemer):
        async def arun(self, prompt):
            payload_sizes.append(len(prompt.encode("utf-8")))
            return await super().arun(prompt)

    try:
        result = refresh_clusters(
            None, path=path, demanded_tokens=tokens, concurrency=8,
            canonicalizer=_AsyncCanonicalizer(), themer=RecordingThemer(),
        )
    finally:
        env_settings.cache_clear()
    assert 0 < sum(payload_sizes) <= 6000
    assert result["promptBytes"] == sum(payload_sizes)
    confirmed = result["confirmedSkills"]
    assert isinstance(confirmed, int)
    assert 0 < confirmed < 100
    assert result["deferredSkills"] == 100 - confirmed
    assert result["usageLimitReached"] is True


def test_recovery_is_fair_across_runs_despite_a_persistent_early_outage(
    tmp_path, monkeypatch
):
    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_ESCALATION_MAX_SKILLS", "1")
    monkeypatch.setenv("TAXONOMY_RECOVERY_ROUNDS", "1")
    env_settings.cache_clear()
    path = tmp_path / "cluster_map.json"
    tokens = {"alpha", "beta", "zeta"}
    _seed_domain_backlog(path, tokens)
    seen = []

    def respond(new, categories):
        seen.extend(new)
        if "alpha" in new:
            return RuntimeError("provider timeout")
        return _languages(new, categories)

    try:
        for _ in range(3):
            refresh_clusters(
                None,
                path=path,
                demanded_tokens=tokens,
                canonicalizer=_AsyncCanonicalizer(),
                themer=_AsyncThemer(),
                escalation_themer=_AsyncThemer(respond),
            )
    finally:
        env_settings.cache_clear()
    assert seen == ["alpha", "beta", "zeta"]
    assert set(load_cluster_map(path).domain_of) == {"beta", "zeta"}
    assert load_taxonomy_state(path).grouping_status["alpha"].escalation_attempts == 1


def test_recovery_can_explicitly_opt_into_singleton_repair(tmp_path, monkeypatch):
    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_RECOVERY_MIN_BATCH_SIZE", "1")
    env_settings.cache_clear()
    path = tmp_path / "cluster_map.json"
    tokens = {f"skill {i}" for i in range(8)}
    _seed_domain_backlog(path, tokens)
    sizes = []

    def respond(new, categories):
        sizes.append(len(new))
        return _languages(new, categories) if len(new) == 1 else []

    try:
        result = refresh_clusters(
            None,
            path=path,
            demanded_tokens=tokens,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(),
            escalation_themer=_AsyncThemer(respond),
        )
    finally:
        env_settings.cache_clear()
    assert result["recoveryRounds"] == 3
    assert result["confirmedSkills"] == len(tokens)
    assert result["placedByFallback"] == 0
    assert sizes == [8, 3, 3, 2, *([1] * 8)]


def test_16000_skill_map_recovers_1600_backlog_with_bounded_regroups(tmp_path):
    from resume_tailor_harness.taxonomy.state import (
        GroupingStatus,
        TaxonomyState,
        save_taxonomy_state,
    )

    path = tmp_path / "cluster_map.json"
    tokens = {f"skill {i:05d}" for i in range(16000)}
    placed = {f"skill {i:05d}": f"domain-{i % 160}" for i in range(14400)}
    pending = tokens - placed.keys()
    save_cluster_map(
        ClusterMap(
            aliases={token: token for token in tokens},
            domain_of=placed,
            domain_label={f"domain-{i}": f"Domain {i}" for i in range(160)},
            category_of={f"domain-{i}": "languages" for i in range(160)},
        ),
        path,
    )
    save_taxonomy_state(
        TaxonomyState(
            grouping_status={
                token: GroupingStatus(reason="incomplete", phase="domain")
                for token in pending
            }
        ),
        path,
    )
    canonicalizer = _AsyncCanonicalizer()
    prompt_member_counts = []

    def respond(new, categories):
        prompt_member_counts.append(
            sum(len(d["skills"]) for c in categories for d in c["domains"])
        )
        return [
            IncrementalDomainGroup(
                confidence="high",
                existing_domain_id=f"domain-{i}",
                skills=[t for t in new if int(t.split()[-1]) % 160 == i],
            )
            for i in range(160)
        ]

    results = []
    for _ in range(8):
        result = refresh_clusters(
            None,
            path=path,
            demanded_tokens=tokens,
            canonicalizer=canonicalizer,
            themer=_AsyncThemer(),
            escalation_themer=_AsyncThemer(respond),
        )
        results.append(result)
        calls, prompt_bytes = result["modelCalls"], result["promptBytes"]
        assert isinstance(calls, int) and calls <= 50
        assert isinstance(prompt_bytes, int) and prompt_bytes <= 1_000_000
        if result["remainingUnassigned"] == 0:
            break
    assert sum(r["confirmedSkills"] for r in results) == 1600
    assert results[-1]["remainingUnassigned"] == 0
    assert canonicalizer.calls == 0
    assert max(prompt_member_counts) == 1280
    assert len(load_cluster_map(path).domain_of) == 16000
    assert not load_taxonomy_state(path).grouping_status


def test_provisional_placement_is_refined_without_losing_user_corrections(tmp_path):
    from resume_tailor_harness.taxonomy.corrections import (
        TaxonomyCorrections,
        save_taxonomy_corrections,
    )

    path = tmp_path / "cluster_map.json"
    correction_path = tmp_path / "corrections.json"
    # A manual move pins one skill, not all generated skills in that bucket.
    save_cluster_map(
        ClusterMap(
            aliases={"rust": "rust", "python": "python"},
            domain_of={
                "rust": "general-languages",
                "python": "general-languages",
            },
            domain_label={
                "general-languages": "Languages: General",
            },
            category_of={
                "general-languages": "languages",
            },
        ),
        path,
    )
    save_taxonomy_corrections(
        TaxonomyCorrections(skill_domain={"python": "general-languages"}),
        correction_path,
    )
    result = refresh_clusters(
        None,
        path=path,
        corrections_path=correction_path,
        demanded_tokens={"rust", "python"},
        canonicalizer=_AsyncCanonicalizer(),
        themer=_AsyncThemer(),
    )
    saved = load_cluster_map(path)
    assert saved.domain_of["rust"] == "languages"
    assert saved.domain_of["python"] == "general-languages"
    assert result["refinedSkills"] == 1
    assert result["processedSkillKeys"] == ["rust"]


def test_provisional_placement_survives_outage_and_remains_retryable(tmp_path):
    path = tmp_path / "cluster_map.json"
    save_cluster_map(
        ClusterMap(
            aliases={"rust": "rust"},
            domain_of={"rust": "general-languages"},
            domain_label={"general-languages": "Languages: General"},
            category_of={"general-languages": "languages"},
        ),
        path,
    )
    result = refresh_clusters(
        None,
        path=path,
        demanded_tokens={"rust"},
        canonicalizer=_AsyncCanonicalizer(),
        themer=_AsyncThemer(lambda *_: RuntimeError("provider down")),
    )
    assert load_cluster_map(path).domain_of["rust"] == "general-languages"
    assert result["recoveryRounds"] == 1
    assert result["provisionalSkills"] == 1
    assert load_taxonomy_state(path).grouping_status["rust"].escalation_attempts == 1


def test_refresh_cleans_stale_resolved_history_outside_requested_scope(tmp_path):
    from resume_tailor_harness.taxonomy.state import (
        GroupingStatus,
        RetiredSkill,
        TaxonomyState,
        save_taxonomy_state,
    )

    path = tmp_path / "cluster_map.json"
    save_cluster_map(
        ClusterMap(
            aliases={"py": "python", "old phrase": "fragment"},
            domain_of={"python": "languages", "rust": "general-languages"},
            domain_label={"languages": "Languages", "general-languages": "General"},
            category_of={"languages": "languages", "general-languages": "languages"},
        ), path,
    )
    save_taxonomy_state(
        TaxonomyState(
            grouping_status={
                token: GroupingStatus(reason="old failure", escalation_attempts=4)
                for token in ("python", "py", "old phrase", "rust", "inactive")
            },
            retired_skills={"fragment": RetiredSkill(reason="not a skill")},
        ), path,
    )
    themer = _AsyncThemer()
    refresh_clusters(
        None, path=path, demanded_tokens={"python"}, skill_keys={"python"},
        canonicalizer=_AsyncCanonicalizer(), themer=themer,
    )
    statuses = load_taxonomy_state(path).grouping_status
    assert set(statuses) == {"rust", "inactive"}
    assert statuses["rust"].escalation_attempts == 4
    assert themer.calls == 0


def test_recovery_receives_source_context_from_active_jobs(tmp_path):
    engine = _engine_with_target_skills("Rust")
    path = tmp_path / "cluster_map.json"
    _seed_domain_backlog(path, {"rust"})

    class ContextThemer(_AsyncThemer):
        async def arun(self, prompt):
            context = json.loads(prompt)["source_context"]
            assert "rust" in context
            assert "rust" in context["rust"][0]
            return await super().arun(prompt)

    with get_session(engine) as session:
        result = refresh_clusters(
            session, path=path, canonicalizer=_AsyncCanonicalizer(),
            themer=ContextThemer(),
        )
    assert result["confirmedSkills"] == 1


def test_retired_alias_does_not_reenter_recovery_or_count_as_unassigned(tmp_path):
    path = tmp_path / "cluster_map.json"
    save_cluster_map(
        ClusterMap(aliases={"eight years": "8 years", "8 years": "8 years"}), path
    )
    themer = _AsyncThemer(lambda new, _: IncrementalSkillDomains(not_skills=new))
    first = refresh_clusters(
        None,
        path=path,
        demanded_tokens={"eight years"},
        canonicalizer=_AsyncCanonicalizer(),
        themer=themer,
    )
    second = refresh_clusters(
        None,
        path=path,
        demanded_tokens={"eight years"},
        canonicalizer=_AsyncCanonicalizer(),
        themer=themer,
    )
    assert first["remainingUnassigned"] == 0
    assert second["processedSkillKeys"] == []
    assert themer.calls == 1


def test_incremental_refresh_persists_success_and_returns_metrics(tmp_path):
    engine = _engine_with_target_skills("Python", "Rust")
    path = tmp_path / "clusters.json"
    canonicalizer = _AsyncCanonicalizer()
    themer = _AsyncThemer()

    with get_session(engine) as session:
        summary = refresh_clusters(
            session,
            canonicalizer=canonicalizer,
            themer=themer,
            path=path,
            batch_size=1,
            concurrency=2,
        )

    assert load_cluster_map(path).aliases == {"python": "python", "rust": "rust"}
    assert summary["skills"] == 2
    assert summary["canonicalBatches"] == 2
    assert summary["failedCanonicalTokens"] == 0
    assert canonicalizer.closed is True
    assert themer.closed is True


def test_refresh_progress_uses_monotonic_phase_indices(tmp_path):
    class _Reporter(ProgressReporter):
        def __init__(self):
            self.phases: list[int] = []

        def begin(self, total, label, *, phase_index=None, **_extra):
            del total, label
            assert phase_index is not None
            self.phases.append(phase_index)

        def step(self, current, **_extra):
            del current

        def checkpoint(self):
            pass

    reporter = _Reporter()
    engine = _engine_with_target_skills("Python", "Rust")
    with get_session(engine) as session:
        refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(),
            path=tmp_path / "clusters.json",
            batch_size=1,
            reporter=reporter,
        )

    assert reporter.phases == list(range(1, len(reporter.phases) + 1))
    assert len(reporter.phases) >= 3


def test_existing_alias_and_theme_choices_win(tmp_path):
    engine = _engine_with_target_skills("K8s", "Kubernetes", "Go", "Rust")
    path = tmp_path / "clusters.json"
    save_cluster_map(
        ClusterMap(
            aliases={"k8s": "kubernetes", "kubernetes": "kubernetes"},
            domain_of={"kubernetes": "infra"},
            domain_label={"infra": "Infrastructure"},
        ),
        path,
    )

    with get_session(engine) as session:
        refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(),
            path=path,
        )

    assert load_cluster_map(path) == ClusterMap(
        aliases={
            "go": "go",
            "k8s": "kubernetes",
            "kubernetes": "kubernetes",
            "rust": "rust",
        },
        domain_of={"go": "languages", "kubernetes": "infra", "rust": "languages"},
        domain_label={"infra": "Infrastructure", "languages": "Languages"},
        category_of={"infra": "other", "languages": "languages"},
    )


def test_reconcile_outage_preserves_existing_map_and_saves_valid_additions(tmp_path):
    engine = _engine_with_target_skills("Python", "Rust")
    path = tmp_path / "clusters.json"
    existing = ClusterMap(
        aliases={"go": "go"},
        domain_of={"go": "languages"},
        domain_label={"languages": "Languages"},
    )
    save_cluster_map(existing, path)

    def respond(new, current):
        return RuntimeError("reconcile down") if len(new) > 1 else [[new[0]]]

    with get_session(engine) as session:
        refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(respond),
            themer=_AsyncThemer(),
            path=path,
            batch_size=1,
        )
    saved = load_cluster_map(path)
    assert saved.domain_of["go"] == "languages"
    assert {"python", "rust"} <= saved.domain_of.keys()
    assert saved.aliases["go"] == "go"


def test_model_call_failure_is_never_placed_by_the_floor(tmp_path):
    """An outage is not a judgment, so the placement floor must not absorb it.

    Filing a skill because the request failed would convert a transient error
    into a permanent misplacement, and would also hide the outage.
    """
    engine = _engine_with_target_skills("Python", "Rust")
    path = tmp_path / "clusters.json"
    canonicalizer = _AsyncCanonicalizer()

    with get_session(engine) as session:
        first = refresh_clusters(
            session,
            canonicalizer=canonicalizer,
            themer=_AsyncThemer(lambda new, existing: RuntimeError("theme down")),
            path=path,
        )
    assert load_cluster_map(path).domain_of == {}
    assert first["failedDomainTokens"] == 2

    with get_session(engine) as session:
        second = refresh_clusters(
            session,
            canonicalizer=canonicalizer,
            themer=_AsyncThemer(),
            path=path,
        )

    assert canonicalizer.calls == 2
    assert load_cluster_map(path).domain_of == {
        "python": "languages",
        "rust": "languages",
    }
    assert second["failedDomainTokens"] == 0


def test_incomplete_canonical_output_is_kept_as_its_own_canonical(tmp_path):
    """An answer that covers nothing no longer leaves the token invisible.

    This used to assert the map stayed empty and the token stayed in the
    backlog.  That was the bug: with no alias the token never reached the
    domain phase, `_retryable_canonical_tokens` forbade the placement floor
    from filing it, and `attempted` (gated on phase == "domain") sent it back
    through an identical pass one forever.  It now ends the run with a home.
    """

    engine = _engine_with_target_skills("Rust")
    path = tmp_path / "clusters.json"
    incomplete = _AsyncCanonicalizer(lambda _new, _current: [])

    with get_session(engine) as session:
        first = refresh_clusters(
            session,
            canonicalizer=incomplete,
            themer=_AsyncThemer(),
            path=path,
        )

    saved = load_cluster_map(path)
    # Kept as its own canonical -- never merged into anything on a non-answer.
    assert saved.aliases["rust"] == "rust"
    assert saved.domain_of["rust"] == "languages"
    assert first["remainingUnassigned"] == 0
    # The gap is still reported; it is simply no longer retryable backlog.
    assert first["failedCanonicalTokens"] == 1
    # Placed, so no status is owed.
    assert "rust" not in load_taxonomy_state(path).grouping_status


def test_a_backstopped_token_reaches_the_placement_floor(tmp_path):
    """The floor may file it because the backstop marked it retryable=False.

    Before the backstop this token had no alias at all, so the domain phase
    never saw it and `_retryable_canonical_tokens` withheld it from the floor
    -- the two conditions that made it permanently invisible.
    """

    class _RefusingCanonicalizer:
        calls = 0

        async def arun(self, prompt):
            return SimpleNamespace(
                content=SkillClusters.model_validate({"clusters": []})
            )

        def run(self, prompt):
            raise AssertionError("async path expected")

    engine = _engine_with_target_skills("Quantum Widgetry")
    path = tmp_path / "cluster_map.json"

    with get_session(engine) as session:
        result = refresh_clusters(
            session,
            canonicalizer=_RefusingCanonicalizer(),
            themer=_AsyncThemer(lambda _new, _categories: []),
            escalation_themer=_AsyncThemer(lambda _new, _categories: []),
            path=path,
        )

    placed = load_cluster_map(path).domain_of
    assert "quantum widgetry" in placed
    assert placed["quantum widgetry"].startswith("general-")
    assert result["placedByFallback"] == 1


def test_refresh_clusters_serializes_concurrent_calls(tmp_path, monkeypatch):
    engine = _engine_with_target_skills("Python")
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    calls = 0

    async def classify(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            first_entered.set()
            assert release_first.wait(timeout=2)
        else:
            second_entered.set()
        return ClassificationOutcome(
            additions=ClusterMap.empty(),
            failures=(),
            metrics=ClassificationMetrics(0, 0, 0, 0, 0),
        )

    monkeypatch.setattr(match_gap_module, "classify_incrementally", classify)

    def run():
        with get_session(engine) as session:
            return refresh_clusters(
                session,
                canonicalizer=_AsyncCanonicalizer(),
                themer=_AsyncThemer(),
                path=tmp_path / "clusters.json",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run)
        assert first_entered.wait(timeout=1)
        second = pool.submit(run)
        try:
            assert not second_entered.wait(timeout=0.2)
        finally:
            release_first.set()
        first.result(timeout=2)
        second.result(timeout=2)

    assert second_entered.is_set()


def test_refresh_keeps_profile_alias_tokens_without_job_demand(tmp_path):
    engine = _engine_with_target_skills()
    path = tmp_path / "cluster_map.json"
    save_cluster_map(
        ClusterMap(aliases={"k8s": "kubernetes", "kubernetes": "kubernetes"}),
        path,
    )
    with get_session(engine) as session:
        refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(),
            path=path,
            extra_tokens={"kubernetes", "k8s"},
        )
    kept = load_cluster_map(path)
    assert kept.aliases["k8s"] == "kubernetes"
    assert kept.aliases["kubernetes"] == "kubernetes"


def test_refresh_keeps_override_only_alias_head_without_job_demand(tmp_path):
    engine = _engine_with_target_skills()
    path = tmp_path / "cluster_map.json"
    save_cluster_map(
        ClusterMap(aliases={"golang": "go", "go": "go"}),
        path,
    )
    with get_session(engine) as session:
        refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(),
            path=path,
            extra_tokens={"golang", "go"},
        )
    kept = load_cluster_map(path)
    assert kept.aliases == {"go": "go", "golang": "go"}


def test_scoped_refresh_changes_only_requested_unassigned_skills(tmp_path):
    engine = _engine_with_target_skills("Assigned", "Alpha", "Beta", "Hidden")
    path = tmp_path / "cluster_map.json"
    original = ClusterMap(
        aliases={
            "assigned": "assigned",
            "hidden": "hidden",
        },
        domain_of={"assigned": "stable-domain"},
        domain_label={"stable-domain": "Stable domain"},
        category_of={"stable-domain": "backend-apis"},
    )
    save_cluster_map(original, path)

    with get_session(engine) as session:
        result = refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(
                lambda new, _categories: [
                    IncrementalDomainGroup(
                        confidence="high",
                        new_label="Scoped domain",
                        new_category="languages",
                        skills=list(new),
                    )
                ]
            ),
            path=path,
            skill_keys={"alpha", "beta"},
        )

    after = load_cluster_map(path)
    assert result["processedSkillKeys"] == ["alpha", "beta"]
    assert after.domain_of["assigned"] == "stable-domain"
    assert after.aliases["hidden"] == "hidden"
    assert "hidden" not in after.domain_of
    assert after.domain_of["alpha"] == after.domain_of["beta"] == "scoped-domain"


def test_soft_target_allows_a_thirteenth_coherent_domain(tmp_path):
    engine = _engine_with_target_skills("Vision One", "Vision Two")
    path = tmp_path / "cluster_map.json"
    domains = {f"domain-{index}": f"Domain {index}" for index in range(12)}
    existing = ClusterMap(
        aliases={f"skill-{index}": f"skill-{index}" for index in range(12)},
        domain_of={f"skill-{index}": f"domain-{index}" for index in range(12)},
        domain_label=domains,
        category_of={domain_id: "ai-ml" for domain_id in domains},
    )
    save_cluster_map(existing, path)

    with get_session(engine) as session:
        result = refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(
                lambda new, _categories: [
                    IncrementalDomainGroup(
                        confidence="high",
                        new_label="Computer Vision",
                        new_category="ai-ml",
                        skills=list(new),
                    )
                ]
            ),
            path=path,
        )

    after = load_cluster_map(path)
    assert result["domainsCreated"] == 1
    assert (
        len([domain for domain in after.category_of.values() if domain == "ai-ml"])
        == 13
    )
    assert after.domain_of["vision one"] == after.domain_of["vision two"]


def test_singleton_new_domain_is_placed_by_the_escalation_pass(tmp_path):
    """A lone new skill is the common case, so one pass declining is not the end.

    The first pass still refuses to mint a domain for a single token, but the
    escalation pass sees the whole taxonomy and may place it -- otherwise every
    genuinely novel skill would be permanently unassignable.
    """

    engine = _engine_with_target_skills("Niche Tool")
    path = tmp_path / "cluster_map.json"

    with get_session(engine) as session:
        result = refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(),
            path=path,
        )

    assert load_cluster_map(path).domain_of == {"niche tool": "languages"}
    assert "niche tool" not in load_taxonomy_state(path).grouping_status
    assert result["uncertainSkills"] == 0
    assert result["remainingUnassigned"] == 0


def test_fifty_requested_skills_all_receive_an_outcome(tmp_path):
    tokens = {f"skill {index:02d}" for index in range(50)}
    engine = _engine_with_target_skills(*sorted(tokens))
    path = tmp_path / "cluster_map.json"

    with get_session(engine) as session:
        result = refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(
                lambda new, _categories: [
                    IncrementalDomainGroup(
                        confidence="high",
                        new_label="Fixture skills",
                        new_category="tools-platforms",
                        skills=list(new),
                    )
                ]
            ),
            path=path,
            batch_size=10,
        )

    after = load_cluster_map(path)
    statuses = load_taxonomy_state(path).grouping_status
    outcomes = set(after.domain_of) | set(statuses)
    assert set(cast(list[str], result["processedSkillKeys"])) == tokens
    assert tokens <= outcomes


def _languages(new, _categories):
    return [
        IncrementalDomainGroup(
            confidence="high",
            new_label="Languages", new_category="languages", skills=list(new)
        )
    ]


def test_a_token_naming_no_skill_is_retired_and_leaves_the_backlog(tmp_path):
    """Retirement is what stops the backlog from re-buying the same verdict.

    Without a terminal disposition, a phrase like an experience requirement is
    re-sent to the model on every single run, forever.
    """

    engine = _engine_with_target_skills("Python", "Ten Years Of Experience")
    path = tmp_path / "cluster_map.json"

    def respond(new, _categories):
        real = [token for token in new if token == "python"]
        return IncrementalSkillDomains(
            domains=_languages(real, None) if real else [],
            not_skills=[token for token in new if token != "python"],
        )

    with get_session(engine) as session:
        first = refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(respond),
            path=path,
        )

    assert first["retiredSkills"] == ["ten years of experience"]
    assert load_cluster_map(path).domain_of == {"python": "languages"}
    assert "ten years of experience" in load_taxonomy_state(path).retired_skills

    repeat = _AsyncThemer(respond)
    with get_session(engine) as session:
        second = refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=repeat,
            path=path,
        )

    assert second["processedSkillKeys"] == []
    assert repeat.calls == 0


def test_manual_discard_stays_out_of_regroup_through_aliases(tmp_path):
    from resume_tailor_harness.services.taxonomy import discard_skills

    engine = _engine_with_target_skills("Python", "Five years experience", "5 years of experience")
    path = tmp_path / "cluster_map.json"
    save_cluster_map(ClusterMap(aliases={"five years experience": "5 years of experience"}), path)
    discard_skills(
        tmp_path / "taxonomy_corrections.json", path, ["Five years experience"],
    )
    canonicalizer = _AsyncCanonicalizer()
    themer = _AsyncThemer(_languages)
    with get_session(engine) as session:
        result = refresh_clusters(session, canonicalizer=canonicalizer, themer=themer, path=path)
        repeat = refresh_clusters(session, canonicalizer=canonicalizer, themer=themer, path=path)
    assert result["processedSkillKeys"] == ["python"]
    assert repeat["processedSkillKeys"] == []
    assert "5 years of experience" in load_taxonomy_state(path).retired_skills


def test_a_retired_skill_can_be_restored_to_the_backlog(tmp_path):
    """A wrong retirement must be one call from being undone."""

    from resume_tailor_harness.services.match_gap import restore_skills

    engine = _engine_with_target_skills("Kubeflow")
    path = tmp_path / "cluster_map.json"

    def retire_everything(new, _categories):
        return IncrementalSkillDomains(domains=[], not_skills=list(new))

    with get_session(engine) as session:
        refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(retire_everything),
            path=path,
        )
    assert "kubeflow" in load_taxonomy_state(path).retired_skills

    restored = restore_skills(path=path, skill_keys={"Kubeflow"})
    assert restored == {"restored": 1, "restoredSkills": ["kubeflow"]}
    assert load_taxonomy_state(path).retired_skills == {}

    with get_session(engine) as session:
        again = refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(_languages),
            path=path,
        )
    assert again["processedSkillKeys"] == ["kubeflow"]
    assert load_cluster_map(path).domain_of == {"kubeflow": "languages"}


def test_a_skill_that_failed_before_goes_straight_to_escalation(tmp_path):
    """Repeat runs must differ, or clicking Regroup again is a pure replay.

    A token carrying a recorded failure skips the first pass entirely and is
    retried against the whole taxonomy with the escalation classifier.
    """

    engine = _engine_with_target_skills("Python")
    path = tmp_path / "cluster_map.json"

    with get_session(engine) as session:
        refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=_AsyncThemer(lambda new, categories: RuntimeError("themer down")),
            path=path,
        )
    assert load_taxonomy_state(path).grouping_status["python"].state == "failed"

    first_pass = _AsyncThemer(_languages)
    escalation = _AsyncThemer(_languages)
    with get_session(engine) as session:
        result = refresh_clusters(
            session,
            canonicalizer=_AsyncCanonicalizer(),
            themer=first_pass,
            escalation_themer=escalation,
            path=path,
        )

    metrics = cast(Mapping[str, int], result)
    assert metrics["elapsedMs"] >= metrics["modelElapsedMs"]
    assert metrics["maxInFlight"] <= 2
    assert metrics["operationWaitMs"] >= 0
    assert metrics["snapshotMs"] >= 0
    assert metrics["retrievalMs"] >= 0
    assert metrics["commitMs"] >= 0

    assert first_pass.calls == 0
    assert escalation.calls == 1
    assert result["escalatedSkills"] == 1
    assert load_cluster_map(path).domain_of == {"python": "languages"}
    assert "python" not in load_taxonomy_state(path).grouping_status


def test_the_deferred_backlog_is_reported_separately_from_uncertainty(
    tmp_path, monkeypatch
):
    """ "Deferred" and "uncertain" are different futures and must read that way.

    The cap already deferred work correctly; it just never said so, so a user
    could not tell monotonic progress from a permanent plateau.
    """

    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_ESCALATION_MAX_SKILLS", "1")
    monkeypatch.setenv("TAXONOMY_RECOVERY_ROUNDS", "1")
    env_settings.cache_clear()

    engine = _engine_with_target_skills("Alpha Skill", "Beta Skill")
    path = tmp_path / "cluster_map.json"

    try:
        with get_session(engine) as session:
            result = refresh_clusters(
                session,
                canonicalizer=_AsyncCanonicalizer(),
                themer=_AsyncThemer(lambda _new, _categories: []),
                escalation_themer=_AsyncThemer(_languages),
                path=path,
            )
    finally:
        env_settings.cache_clear()

    assert result["deferredSkills"] == 1
    # The deferred token is not double-counted as a domain-phase verdict.
    assert result["uncertainDomainSkills"] == 0
    assert result["uncertainCanonicalSkills"] == 0
    # The pre-existing total is untouched, so old consumers keep working.
    assert result["uncertainSkills"] == 1


def test_the_escalation_cap_defers_instead_of_flooring(tmp_path, monkeypatch):
    """What the per-run bound skips has not been judged, so it must not be filed.

    The escalation cap exists to bound cost. Treating what it defers as
    "unplaceable" would file skills the expensive pass never even saw.
    """

    from resume_tailor_harness.config import env_settings

    monkeypatch.setenv("TAXONOMY_ESCALATION_MAX_SKILLS", "1")
    monkeypatch.setenv("TAXONOMY_RECOVERY_ROUNDS", "1")
    env_settings.cache_clear()

    engine = _engine_with_target_skills("Alpha Skill", "Beta Skill")
    path = tmp_path / "cluster_map.json"

    # The first pass refuses everything; only escalation can place a token.
    def decline(_new, _categories):
        return []

    escalation = _AsyncThemer(_languages)
    try:
        with get_session(engine) as session:
            result = refresh_clusters(
                session,
                canonicalizer=_AsyncCanonicalizer(),
                themer=_AsyncThemer(decline),
                escalation_themer=escalation,
                path=path,
            )
    finally:
        env_settings.cache_clear()

    placed = load_cluster_map(path).domain_of
    assert placed == {"alpha skill": "languages"}
    assert result["escalatedSkills"] == 1
    assert result["placedByFallback"] == 0
    # The deferred token keeps a status so it escalates first next run.
    assert "beta skill" in load_taxonomy_state(path).grouping_status
