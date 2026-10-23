from sqlmodel import Session, SQLModel, create_engine

from resume_tailor_harness.models.profile import Contact, ProfileFacts, Skill
from resume_tailor_harness.taxonomy.clusters import ClusterMap
from resume_tailor_harness.tracking.match_gap import (
    build_demand_graph,
    GapRow,
    MatchGapReport,
    match_gap,
    normalize_skill,
    profile_skill_tokens,
)
from resume_tailor_harness.tracking.repository import save_job
from resume_tailor_harness.tracking.tables import Job, JobStatus


def _session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _job(session, status, must_have):
    return save_job(
        session,
        Job(
            source="manual",
            company="C",
            title="T",
            status=status,
            criteria_json={"must_have_skills": must_have},
        ),
    )


def _facts(skills):
    return ProfileFacts(contact=Contact(name="A"), skills=skills)


def test_normalize_lowercases_and_collapses_whitespace():
    assert normalize_skill("  Kubernetes  ") == "kubernetes"
    assert normalize_skill("Amazon  Web   Services") == "amazon web services"


def test_skill_context_is_scoped_bounded_and_resolves_aliases():
    from resume_tailor_harness.tracking.match_gap import collect_target_skill_context
    from resume_tailor_harness.tracking.tables import utcnow

    with _session() as session:
        for index in range(4):
            session.add(Job(
                source="manual", title=f"Platform engineer {index}",
                status=JobStatus.shortlisted.value,
                jd_text="prefix " * 100 + "Build K8s operators for clusters. " + "suffix " * 100,
                criteria_json={"must_have_skills": ["K8s", "Python"]},
            ))
        session.add(Job(
            source="manual", title="Archived secret context",
            status=JobStatus.shortlisted.value, archived_at=utcnow(),
            criteria_json={"must_have_skills": ["Unseen"]},
        ))
        session.add(Job(
            source="manual", title="Rejected context", status=JobStatus.rejected.value,
            criteria_json={"must_have_skills": ["Unseen"]},
        ))
        session.commit()
        context = collect_target_skill_context(
            session, {"kubernetes", "unseen"}, {"k8s": "kubernetes"},
        )
    assert set(context) == {"kubernetes"}
    assert len(context["kubernetes"]) == 2
    assert all(len(item) <= 700 for item in context["kubernetes"])
    assert all("k8s operators" in item for item in context["kubernetes"])
    assert all("secret" not in item for item in context["kubernetes"])


def test_skill_context_does_not_match_substrings_inside_other_words():
    from resume_tailor_harness.tracking.match_gap import collect_target_skill_context

    with _session() as session:
        session.add(Job(
            source="manual", title="Developer", status=JobStatus.shortlisted.value,
            jd_text="Ongoing work on an unrelated project.",
            criteria_json={"tech_stack": ["Go", "Kubernetes"]},
        ))
        session.commit()
        context = collect_target_skill_context(session, {"go"})
    assert "Excerpt:" not in context["go"][0]
    assert "Other extracted skills: kubernetes" in context["go"][0]


def test_fallback_category_is_visible_but_never_adjacency_evidence():
    from resume_tailor_harness.taxonomy.state import GroupingStatus

    cmap = ClusterMap(
        domain_of={"python": "general-languages", "rust": "general-languages"},
        domain_label={"general-languages": "Languages: General"},
        category_of={"general-languages": "languages"},
    )
    facts = _facts({"hard": [Skill(name="Python")]})
    with _session() as session:
        _job(session, JobStatus.shortlisted.value, ["Python", "Rust"])
        graph = build_demand_graph(
            session,
            facts,
            cluster_map=cmap,
            grouping_statuses={"rust": GroupingStatus(reason="Provisional")},
        )
        nodes = {node.key: node for node in graph.skills}
        assert nodes["python"].coverage == "covered"
        assert nodes["rust"].coverage == "gap"
        status = nodes["rust"].grouping_status
        assert status is not None
        assert status["reason"] == "Provisional"
        assert not match_gap(session, facts, cluster_map=cmap).gaps[0].adjacent


def test_normalize_keeps_plus_hash_dot_drops_other_punct():
    assert normalize_skill("C++") == "c++"
    assert normalize_skill("C#") == "c#"
    assert normalize_skill("Node.js") == "node.js"
    assert normalize_skill("CI/CD") == "ci cd"


def test_profile_skill_tokens_includes_names_and_aliases():
    facts = ProfileFacts(
        contact=Contact(name="A"),
        skills={
            "languages": [Skill(name="Python"), Skill(name="Go")],
            "infra": [Skill(name="Kubernetes", aliases=["k8s", "K8S"])],
        },
    )

    assert profile_skill_tokens(facts) == {"python", "go", "kubernetes", "k8s"}


def test_profile_skill_tokens_empty_profile():
    assert profile_skill_tokens(ProfileFacts(contact=Contact(name="A"))) == set()


def test_match_gap_aggregates_by_frequency():
    with _session() as session:
        _job(session, JobStatus.shortlisted.value, ["Kubernetes", "Python"])
        _job(session, JobStatus.approved.value, ["Kubernetes", "Go"])

        report = match_gap(session, _facts({"lang": [Skill(name="Python")]}))

        assert report.target_total == 2
        pairs = [(g.skill, g.demand_count) for g in report.gaps]
        assert pairs[0] == ("Kubernetes", 2)
        assert ("Go", 1) in pairs
        assert all(g.skill != "Python" for g in report.gaps)


def test_match_gap_excludes_pre_shortlist_jobs():
    with _session() as session:
        _job(session, JobStatus.filtered.value, ["Rust"])
        _job(session, JobStatus.rejected.value, ["Scala"])
        _job(session, JobStatus.shortlisted.value, ["Kubernetes"])

        report = match_gap(session, _facts({}))

        assert report.target_total == 1
        assert {g.skill for g in report.gaps} == {"Kubernetes"}


def test_match_gap_alias_is_not_a_gap():
    with _session() as session:
        job = _job(session, JobStatus.shortlisted.value, ["k8s"])

        report = match_gap(
            session,
            _facts({"infra": [Skill(name="Kubernetes", aliases=["k8s"])]}),
        )

        assert report.gaps == []
        assert job.id is not None
        assert report.per_job[job.id] == []


def test_match_gap_per_job_lists_missing():
    with _session() as session:
        job = _job(session, JobStatus.shortlisted.value, ["Kubernetes", "Python"])

        report = match_gap(session, _facts({"lang": [Skill(name="Python")]}))

        assert job.id is not None
        assert report.per_job[job.id] == ["Kubernetes"]


def test_match_gap_honors_canonicalizer():
    with _session() as session:
        _job(session, JobStatus.shortlisted.value, ["k8s"])

        def canon(tokens):
            return {
                t: ("kubernetes" if t in {"k8s", "kubernetes"} else t) for t in tokens
            }

        report = match_gap(
            session,
            _facts({"infra": [Skill(name="Kubernetes")]}),
            canonicalizer=canon,
        )

        assert report.gaps == []


def test_match_gap_empty_db():
    with _session() as session:
        report = match_gap(session, _facts({}))

        assert report == MatchGapReport(target_total=0, gaps=[], per_job={})


def test_match_gap_excludes_archived_targets():
    from resume_tailor_harness.tracking.repository import archive_job

    facts = _facts({"lang": [Skill(name="Python")]})
    with _session() as s:
        _job(s, JobStatus.shortlisted.value, ["Python", "Go"])
        hidden = _job(s, JobStatus.shortlisted.value, ["Rust"])
        assert hidden.id is not None
        archive_job(s, hidden.id)
        report = match_gap(s, facts)
        assert report.target_total == 1


def test_gap_row_demand_share():
    assert GapRow(skill="X", demand_count=2, target_total=3).demand_share == 67


def test_demand_graph_marks_same_theme_as_adjacent():
    with _session() as session:
        _job(session, JobStatus.shortlisted.value, ["FastAPI"])
        facts = _facts({"Frameworks": [Skill(name="Flask")]})
        cluster_map = ClusterMap(
            aliases={"flask": "flask", "fastapi": "fastapi"},
            domain_of={"flask": "web", "fastapi": "web"},
            domain_label={"web": "Web Frameworks"},
        )
        graph = build_demand_graph(session, facts, cluster_map)
    node = next(item for item in graph.skills if item.key == "fastapi")
    assert node.coverage == "adjacent"
    assert node.covered is False
    assert graph.domains[0].gap_count == 0
    assert graph.domains[0].adjacent_count == 1


def test_demand_graph_distinguishes_covered_and_true_gap():
    with _session() as session:
        _job(session, JobStatus.shortlisted.value, ["Python", "Rust"])
        graph = build_demand_graph(
            session,
            _facts({"Languages": [Skill(name="Python")]}),
            ClusterMap.empty(),
        )
    by_key = {node.key: node for node in graph.skills}
    assert by_key["python"].coverage == "covered"
    assert by_key["python"].covered is True
    assert by_key["rust"].coverage == "gap"


def test_match_gap_flags_adjacent_and_cluster_map_precedes_callable():
    with _session() as session:
        _job(session, JobStatus.shortlisted.value, ["FastAPI"])
        facts = _facts({"Frameworks": [Skill(name="Flask")]})
        cluster_map = ClusterMap(
            domain_of={"flask": "web", "fastapi": "web"},
            domain_label={"web": "Web"},
        )

        def wrong_canonicalizer(tokens):
            return {token: "same" for token in tokens}

        report = match_gap(
            session,
            facts,
            canonicalizer=wrong_canonicalizer,
            cluster_map=cluster_map,
        )
    assert [(gap.skill, gap.adjacent) for gap in report.gaps] == [("FastAPI", True)]
