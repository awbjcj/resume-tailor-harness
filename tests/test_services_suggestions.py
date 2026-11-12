from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from resume_tailor_harness.config import Settings
from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.github.repos import RepoMeta
from resume_tailor_harness.llm_runner import (
    AgentRunner,
    INCOMPLETE_KEY,
    UnparsedAgentOutput,
)
from resume_tailor_harness.models.profile import Contact, ProfileFacts, Skill
from resume_tailor_harness.services.suggestions import (
    SuggestionContext,
    SuggestionTargetChanged,
    SuggestionTargetNotFound,
    generate_suggestion,
    purge_legacy_theme_suggestions,
    resolve_suggestion_context,
    suggestion_fingerprint,
    suggestion_statuses,
)
from resume_tailor_harness.suggestions.agents import (
    ProjectIdea,
    RepoRef,
    ResourceRef,
    SuggestionDraft,
)
from resume_tailor_harness.tracking.match_gap import (
    DemandEdge,
    DemandGraph,
    JobLite,
    SkillNode,
    DomainNode,
)
from resume_tailor_harness.tracking.tables import (
    LearningRoadmapProgress,
    SkillSuggestion,
)


class _Result:
    def __init__(self, content):
        self.content = content


class _Agent:
    def __init__(self, content):
        self.content = content

    def run(self, _prompt):
        return _Result(self.content)


def _facts():
    return ProfileFacts(
        contact=Contact(name="A"),
        skills={"infrastructure": [Skill(name="Docker")]},
    )


def _engine():
    engine = make_engine("sqlite://")
    init_db(engine)
    return engine


def _graph():
    return DemandGraph(
        target_total=2,
        clusters_stale=False,
        jobs=[
            JobLite(1, "Stripe", "Backend", "senior", "shortlisted"),
            JobLite(2, "Datadog", "Platform", "mid", "shortlisted"),
        ],
        skills=[
            SkillNode(
                "Kubernetes", "infra", False, "kubernetes", {"K8s": 1, "Kubernetes": 2}
            ),
            SkillNode("Terraform", "infra", False, "terraform", {"Terraform": 1}),
        ],
        edges=[
            DemandEdge(1, "Kubernetes", "must", "kubernetes"),
            DemandEdge(2, "Kubernetes", "tech", "kubernetes"),
            DemandEdge(2, "Terraform", "must", "terraform"),
        ],
        domains=[DomainNode("infra", "Cloud / Infrastructure")],
    )


def test_resolve_suggestion_context_uses_server_graph_for_skill_and_theme():
    skill = resolve_suggestion_context(_graph(), kind="skill", key="kubernetes")
    legacy = resolve_suggestion_context(_graph(), kind="skill", key="K8s")
    theme = resolve_suggestion_context(_graph(), kind="domain", key="infra")

    assert skill.key == "kubernetes"
    assert skill.members == ("K8s", "Kubernetes")
    assert skill.demanding_job_ids == (1, 2)
    assert legacy == skill
    assert theme.label == "Cloud / Infrastructure"
    assert theme.members == ("kubernetes", "terraform")
    assert theme.demanding_job_ids == (1, 2)
    assert theme.jobs_context == "Stripe — Backend; Datadog — Platform"


def test_resolve_suggestion_context_rejects_unknown_target():
    with pytest.raises(SuggestionTargetNotFound):
        resolve_suggestion_context(_graph(), kind="domain", key="unknown")


def test_fingerprint_changes_with_coverage_members_and_jobs():
    context = SuggestionContext(
        kind="skill",
        key="Kubernetes",
        label="Kubernetes",
        members=("Kubernetes",),
        demanding_job_ids=(1,),
        jobs_context="Stripe — Backend",
    )

    baseline = suggestion_fingerprint(context, {"docker"})
    assert baseline != suggestion_fingerprint(context, {"docker", "kubernetes"})
    assert baseline != suggestion_fingerprint(
        SuggestionContext(**{**context.__dict__, "demanding_job_ids": (1, 2)}),
        {"docker"},
    )


def test_generate_grounds_links_verifies_repos_and_upserts():
    draft = SuggestionDraft(
        repos=[
            RepoRef(name="ok", url="https://github.com/foo/bar", why="Reference"),
            RepoRef(name="dead", url="https://github.com/foo/ghost", why="Dead"),
            RepoRef(
                name="ungrounded", url="https://github.com/foo/other", why="Missing"
            ),
        ],
        resources=[
            ResourceRef(title="Docs", url="https://k8s.io/docs", kind="doc"),
            ResourceRef(
                title="Invented", url="https://example.com/invented", kind="tutorial"
            ),
        ],
        project=ProjectIdea(
            title="Mini scheduler",
            summary="Build a scheduler",
            skills_demonstrated=["Go"],
        ),
        bridge="You already know Docker.",
    )

    def verify(_owner, name):
        if name == "bar":
            return RepoMeta("foo/bar", "https://github.com/foo/bar", 9, "A repo")
        return None

    context = resolve_suggestion_context(_graph(), kind="skill", key="kubernetes")
    engine = _engine()
    with Session(engine) as session:
        row = generate_suggestion(
            session,
            context=context,
            search_agent=_Agent(
                "Research: https://github.com/foo/bar https://github.com/foo/ghost "
                "https://k8s.io/docs"
            ),
            formatter=_Agent(draft),
            verify=verify,
            facts=_facts(),
        )

        assert [repo["url"] for repo in row.payload_json["repos"]] == [
            "https://github.com/foo/bar"
        ]
        assert row.payload_json["repos"][0]["stars"] == 9
        assert [resource["url"] for resource in row.payload_json["resources"]] == [
            "https://k8s.io/docs"
        ]
        assert row.payload_json["project"]["title"] == "Mini scheduler"

        updated = generate_suggestion(
            session,
            context=context,
            search_agent=_Agent("Grounded prose"),
            formatter=_Agent(SuggestionDraft(bridge="Updated")),
            verify=verify,
            facts=_facts(),
        )
        rows = session.exec(
            select(SkillSuggestion).where(
                SkillSuggestion.kind == "skill",
                SkillSuggestion.key == "kubernetes",
            )
        ).all()

    assert updated.id == row.id
    assert len(rows) == 1
    assert rows[0].payload_json["bridge"] == "Updated"


def test_generation_failure_preserves_last_good_cache():
    context = resolve_suggestion_context(_graph(), kind="skill", key="kubernetes")
    engine = _engine()
    with Session(engine) as session:
        original = generate_suggestion(
            session,
            context=context,
            search_agent=_Agent("Grounded prose"),
            formatter=_Agent(SuggestionDraft(bridge="Keep me")),
            verify=lambda _owner, _name: None,
            facts=_facts(),
        )

        with pytest.raises(ValueError, match="empty suggestion"):
            generate_suggestion(
                session,
                context=context,
                search_agent=_Agent("Grounded prose"),
                formatter=_Agent(SuggestionDraft()),
                verify=lambda _owner, _name: None,
                facts=_facts(),
            )
        session.expire_all()
        cached = session.get(SkillSuggestion, original.id)

    assert cached is not None
    assert cached.payload_json["bridge"] == "Keep me"


@pytest.mark.parametrize("stage", ["research", "formatter"])
@pytest.mark.parametrize("failure", ["error", "truncated", "invalid"])
def test_generation_rejects_failed_stages_with_diagnostics(stage, failure):
    result = SimpleNamespace(
        content="provider rejected request"
        if stage == "research"
        else SuggestionDraft(bridge="Incomplete"),
        status="error" if failure == "error" else "completed",
        model="test-model",
        model_provider_data=(
            {INCOMPLETE_KEY: {"reason": "max_tokens", "ceiling": 100}}
            if failure == "truncated"
            else {}
        ),
    )
    if failure == "invalid":
        result.content = None if stage == "research" else '{"bridge":'
        result.model_provider_data = {"structured_output_error": "invalid JSON"}
    failed = SimpleNamespace(run=lambda _prompt: result)
    calls = []
    formatter = SimpleNamespace(run=lambda prompt: calls.append(prompt))
    engine = _engine()
    with Session(engine) as session:
        original = SkillSuggestion(
            kind="skill", key="kubernetes", payload_json={"bridge": "Keep me"}
        )
        session.add(original)
        session.commit()
        with pytest.raises(UnparsedAgentOutput, match="suggestions-" + stage) as error:
            generate_suggestion(
                session,
                context=resolve_suggestion_context(
                    _graph(), kind="skill", key="kubernetes"
                ),
                search_agent=failed
                if stage == "research"
                else _Agent("Grounded prose"),
                formatter=failed if stage == "formatter" else formatter,
                verify=lambda _owner, _name: None,
                facts=_facts(),
            )
        assert "test-model" in str(error.value)
        if failure == "truncated":
            assert "max_tokens" in str(error.value)
        session.refresh(original)
        assert original.payload_json == {"bridge": "Keep me"}
    assert calls == []


def test_generation_recovers_formatter_json_with_shared_runner():
    outputs = iter(['{"bridge":', '```json\n{"bridge":"Start with Docker",}\n```'])
    prompts = []

    def run(prompt):
        prompts.append(prompt)
        return SimpleNamespace(content=next(outputs), status="COMPLETED")

    formatter = AgentRunner(
        SimpleNamespace(output_schema=SuggestionDraft, run=run),
        settings=Settings(_env_file=None, llm_retries=1, llm_retry_delay=0),  # type: ignore[call-arg]
    )
    with Session(_engine()) as session:
        row = generate_suggestion(
            session,
            context=resolve_suggestion_context(_graph(), kind="domain", key="infra"),
            search_agent=_Agent("Grounded prose"),
            formatter=formatter,
            verify=lambda _owner, _name: None,
            facts=_facts(),
        )
        assert row.payload_json["bridge"] == "Start with Docker"
        assert row.kind == "domain"
    assert len(prompts) == 2
    assert "OUTPUT CORRECTION" in prompts[1]


def test_generate_suggestion_reuses_and_canonicalizes_legacy_cache_row():
    context = resolve_suggestion_context(_graph(), kind="skill", key="kubernetes")
    engine = _engine()
    with Session(engine) as session:
        legacy = SkillSuggestion(
            kind="skill", key="K8s", payload_json={"bridge": "old"}
        )
        session.add(legacy)
        session.commit()
        legacy_id = legacy.id

        generated = generate_suggestion(
            session,
            context=context,
            search_agent=_Agent("Grounded prose"),
            formatter=_Agent(SuggestionDraft(bridge="Updated")),
            verify=lambda _owner, _name: None,
            facts=_facts(),
        )

    assert generated.id == legacy_id
    assert generated.key == "kubernetes"


def test_suggestion_statuses_use_canonical_keys_and_prefer_canonical_rows():
    graph = _graph()
    context = resolve_suggestion_context(graph, kind="skill", key="kubernetes")
    current = suggestion_fingerprint(context, {"docker"})
    engine = _engine()
    with Session(engine) as session:
        session.add(
            SkillSuggestion(
                kind="skill",
                key="K8s",
                fingerprint="old",
                payload_json={"bridge": "legacy"},
            )
        )
        session.add(
            SkillSuggestion(
                kind="skill",
                key="kubernetes",
                fingerprint=current,
                payload_json={"bridge": "canonical"},
            )
        )
        session.commit()

        statuses = suggestion_statuses(session, graph, {"docker"})

    assert [(status.key, status.state) for status in statuses] == [
        ("kubernetes", "ready")
    ]


def test_roadmap_library_keeps_superseded_alias_progress_and_points_to_winner():
    from resume_tailor_harness.services.learning_roadmaps import list_roadmaps

    engine = _engine()
    with Session(engine) as session:
        legacy = SkillSuggestion(
            kind="skill",
            key="K8s",
            payload_json={
                "bridge": "old",
                "repos": [],
                "resources": [],
                "citations": [],
            },
        )
        canonical = SkillSuggestion(
            kind="skill",
            key="kubernetes",
            payload_json={
                "bridge": "current",
                "repos": [],
                "resources": [],
                "citations": [],
            },
        )
        session.add_all([legacy, canonical])
        session.commit()
        assert legacy.id is not None and canonical.id is not None
        session.add(
            LearningRoadmapProgress(suggestion_id=legacy.id, status="completed")
        )
        session.commit()

        plans = {plan.id: plan for plan in list_roadmaps(session, _graph(), set())}
        old, current = plans[legacy.id], plans[canonical.id]
        assert old.label == "K8s"
        assert old.status == "completed"
        assert old.envelope.suggestion is not None
        assert old.envelope.suggestion.bridge == "old"
        assert old.available is False
        assert old.superseded_by_id == canonical.id
        assert current.available is True
        assert current.superseded_by_id is None


def test_multiple_legacy_roadmaps_only_allow_the_row_generation_will_reuse():
    from resume_tailor_harness.services.learning_roadmaps import list_roadmaps
    from resume_tailor_harness.services.suggestions import find_suggestion_row

    graph = _graph()
    context = resolve_suggestion_context(graph, kind="skill", key="kubernetes")
    with Session(_engine()) as session:
        payload = {"bridge": "saved", "repos": [], "resources": [], "citations": []}
        session.add_all(
            [
                SkillSuggestion(kind="skill", key="Kubernetes", payload_json=payload),
                SkillSuggestion(kind="skill", key="K8s", payload_json=payload),
            ]
        )
        session.commit()
        winner = find_suggestion_row(session, context)
        assert winner is not None
        plans = list_roadmaps(session, graph, set())
        available = [plan for plan in plans if plan.available]
        superseded = [plan for plan in plans if not plan.available]
        assert [plan.id for plan in available] == [winner.id]
        assert [plan.superseded_by_id for plan in superseded] == [winner.id]

        winner.fingerprint = suggestion_fingerprint(context, set())
        session.add(winner)
        session.commit()
        statuses = suggestion_statuses(session, graph, set())
        assert [(item.key, item.state) for item in statuses] == [
            ("kubernetes", "ready")
        ]


def test_generation_does_not_replace_a_different_row_after_selection_changes():
    context = resolve_suggestion_context(_graph(), kind="skill", key="kubernetes")
    with Session(_engine()) as session:
        legacy = SkillSuggestion(
            kind="skill", key="K8s", payload_json={"bridge": "old"}
        )
        session.add(legacy)
        session.commit()
        legacy_id = legacy.id
        session.add(
            SkillSuggestion(
                kind="skill", key="kubernetes", payload_json={"bridge": "current"}
            )
        )
        session.commit()

        with pytest.raises(SuggestionTargetChanged):
            generate_suggestion(
                session,
                context=context,
                search_agent=_Agent("Grounded prose"),
                formatter=_Agent(SuggestionDraft(bridge="replacement")),
                verify=lambda _owner, _name: None,
                facts=_facts(),
                expected_roadmap_id=legacy_id,
            )
        rows = {
            row.key: row.payload_json["bridge"]
            for row in session.exec(select(SkillSuggestion)).all()
        }
        assert rows == {"K8s": "old", "kubernetes": "current"}


def test_generation_rechecks_the_selected_row_after_research():
    context = resolve_suggestion_context(_graph(), kind="skill", key="kubernetes")
    with Session(_engine()) as session:
        legacy = SkillSuggestion(
            kind="skill", key="K8s", payload_json={"bridge": "old"}
        )
        session.add(legacy)
        session.commit()
        legacy_id = legacy.id

        class _Research:
            def run(self, _prompt):
                session.add(
                    SkillSuggestion(
                        kind="skill",
                        key="kubernetes",
                        payload_json={"bridge": "current"},
                    )
                )
                session.commit()
                return _Result("Grounded prose")

        with pytest.raises(SuggestionTargetChanged):
            generate_suggestion(
                session,
                context=context,
                search_agent=_Research(),
                formatter=_Agent(SuggestionDraft(bridge="replacement")),
                verify=lambda _owner, _name: None,
                facts=_facts(),
                expected_roadmap_id=legacy_id,
            )
        rows = {
            row.key: row.payload_json["bridge"]
            for row in session.exec(select(SkillSuggestion)).all()
        }
        assert rows == {"K8s": "old", "kubernetes": "current"}


def test_purge_legacy_theme_suggestions_deletes_only_theme_rows():
    engine = _engine()
    with Session(engine) as session:
        session.add(SkillSuggestion(kind="theme", key="old-theme", payload_json={}))
        session.add(SkillSuggestion(kind="skill", key="python", payload_json={}))
        session.commit()

        assert purge_legacy_theme_suggestions(session) == 1

        remaining = session.exec(select(SkillSuggestion)).all()
        assert [row.kind for row in remaining] == ["skill"]
