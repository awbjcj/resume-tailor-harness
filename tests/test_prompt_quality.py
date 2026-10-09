"""Coverage and composition contracts; these do not measure model quality."""

import ast
from pathlib import Path

import pytest

from resume_tailor_harness.prompts.guidance import GUIDANCE_HEADER, with_guidance
from resume_tailor_harness.prompts.quality import (
    QUALITY_HEADER,
    TASK_QUALITY,
    UNCHANGED_KEYS,
    quality_instructions,
    with_quality,
)
from resume_tailor_harness.prompts.registry import SPECS_BY_KEY


def test_every_production_builder_has_a_reviewed_quality_policy():
    """Catch a new/missed builder, including inline scraper and H-1B prompts."""
    root = Path(__file__).resolve().parents[1] / "src/resume_tailor_harness"
    used = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "with_guidance":
                key = node.args[0]
                if isinstance(key, ast.Constant):
                    used.add(key.value)
                else:
                    # The only dynamic family is the configurable reviewer roster.
                    assert ast.unparse(key) == "f'reviewer-{name}'", path
            if node.func.id == "Agent":
                instructions = next(
                    (kw.value for kw in node.keywords if kw.arg == "instructions"), None
                )
                assert isinstance(instructions, ast.Call), path
                assert isinstance(instructions.func, ast.Name), path
                assert instructions.func.id == "with_guidance", path
    assert used <= set(TASK_QUALITY) | UNCHANGED_KEYS
    assert set(TASK_QUALITY) | UNCHANGED_KEYS == set(SPECS_BY_KEY)
    assert set(TASK_QUALITY) - used == {
        "reviewer-ats-keyword",
        "reviewer-recruiter",
        "reviewer-hiring-manager",
        "reviewer-concision",
    }


@pytest.mark.parametrize("key", sorted(TASK_QUALITY))
def test_quality_is_bounded_and_beneath_base_but_above_user_guidance(key, monkeypatch):
    monkeypatch.setattr(
        "resume_tailor_harness.prompts.guidance.guidance_for",
        lambda _: "Prefer concise prose.",
    )
    base = ["Immutable schema and evidence rules."]
    result = with_guidance(key, base)
    assert base == ["Immutable schema and evidence rules."]
    assert result[0] == base[0]
    assert result.count(QUALITY_HEADER) == 1
    assert result[-2:] == [GUIDANCE_HEADER, "Prefer concise prose."]
    assert result.index(QUALITY_HEADER) < result.index(GUIDANCE_HEADER)
    assert all(line in result for line in TASK_QUALITY[key])
    # Bound the added context rather than growing an unrelated playbook per call.
    assert sum(len(line) for line in with_quality(key, [])) < 2400


def test_fact_checker_and_unknown_tasks_are_unchanged():
    from resume_tailor_harness.tailor.agents import _reviewer_instructions

    base = _reviewer_instructions("fact-check")
    assert with_quality("reviewer-fact-check", base) == base
    assert SPECS_BY_KEY["reviewer-fact-check"].instructions == tuple(base)
    assert with_quality("unknown-task", ["base"]) == ["base"]
    assert quality_instructions("reviewer-custom")


def test_merged_panel_receives_each_individual_quality_rubric(monkeypatch):
    from resume_tailor_harness.tailor.agents import _merged_advisory_instructions

    monkeypatch.setattr(
        "resume_tailor_harness.tailor.agents.guidance_for", lambda _: "Be brief."
    )
    names = ["ats-keyword", "recruiter", "hiring-manager", "concision", "custom"]
    instructions = _merged_advisory_instructions(names)
    for name in names:
        rubric = next(
            line for line in instructions if line.startswith(f"Rubric for {name!r}:")
        )
        for rule in quality_instructions(f"reviewer-{name}"):
            assert rule in rubric
            assert rubric.index(rule) < rubric.index("User guidance")
    assert "Rubric for 'fact-check':" not in " ".join(instructions)


def test_new_catalog_entries_match_runtime_instructions(monkeypatch):
    from resume_tailor_harness.career_lab.agents import (
        build_formatter_agent,
        build_router_agent,
    )
    from resume_tailor_harness.config import Settings
    from resume_tailor_harness.h1b.service import DefaultCompanyNameResolverFactory
    from resume_tailor_harness.hiring_contacts.agents import (
        build_hiring_contact_formatter,
    )
    from resume_tailor_harness.role_preparation.agents import (
        build_role_preparation_formatter,
    )
    from resume_tailor_harness.tailor.portfolio_planner import (
        build_evidence_portfolio_agent,
    )

    monkeypatch.setattr(
        "resume_tailor_harness.prompts.guidance.guidance_for", lambda _: None
    )
    settings = Settings(_env_file=None)
    builders = {
        "career-lab-router": lambda: build_router_agent(settings),
        "career-lab-formatter": lambda: build_formatter_agent(settings),
        "h1b-company-name-resolution": lambda: DefaultCompanyNameResolverFactory(
            settings
        ).build(),
        "hiring-contact-format": build_hiring_contact_formatter,
        "role-preparation": build_role_preparation_formatter,
        "evidence-portfolio": build_evidence_portfolio_agent,
    }
    for key, build in builders.items():
        assert tuple(build()._agent.instructions) == SPECS_BY_KEY[key].instructions


def test_interview_rubric_does_not_force_metrics_star_or_invented_delivery():
    from resume_tailor_harness.interview.agent import _DEBRIEF_INSTRUCTIONS

    text = " ".join(_DEBRIEF_INSTRUCTIONS)
    assert "A top answer lands all four plus a number" not in text
    assert "do not force them into STAR" in text
    assert "A metric is not mandatory" in text
    assert "Do not infer speaking duration" in text
    for anchor in (
        "1 does not answer",
        "2 partially answers",
        "3 is relevant",
        "4 is specific",
        "5 is complete",
    ):
        assert anchor in text


def test_craft_preserves_participation_and_summary_evidence():
    from resume_tailor_harness.tailor.craft import CRAFT_WRITER

    text = " ".join(CRAFT_WRITER)
    assert "never upgrade participation to leadership" in text
    assert "summary_provenance" in text
    assert "facts cited elsewhere" not in text


def test_run_provenance_records_quality_version_without_mutating_caller_meta():
    from types import SimpleNamespace

    from resume_tailor_harness.career_skills.models import AgentFamily, AgentRunMeta
    from resume_tailor_harness.llm_runner import AgentRunner
    from resume_tailor_harness.prompts.quality import QUALITY_POLICY_VERSION

    meta = AgentRunMeta(
        agent_family=AgentFamily.JOB_ANALYSIS,
        prompt_policy_version="job-fit-v1",
        model_id="test-model",
    )
    agent = SimpleNamespace(instructions=with_quality("fit-score", ["base"]))
    runner = AgentRunner(agent, run_meta=meta)
    assert (
        runner.run_meta.prompt_policy_version == f"job-fit-v1+{QUALITY_POLICY_VERSION}"
    )
    assert meta.prompt_policy_version == "job-fit-v1"
    assert AgentRunner(agent, run_meta=runner.run_meta).run_meta == runner.run_meta
    assert (
        AgentRunner(SimpleNamespace(instructions=["gate"]), run_meta=meta).run_meta
        is meta
    )


@pytest.mark.parametrize(
    "mode,version_key",
    [
        ("literal", "prompt_version"),
        ("synthesis", "synthesis_prompt_version"),
        ("project", "project_prompt_version"),
    ],
)
def test_previous_profile_prompt_versions_are_stale(tmp_path, mode, version_key):
    import json

    from resume_tailor_harness.models.profile import Contact, ProfileFacts
    from resume_tailor_harness.profile.corpus import add_source, load_manifest
    from resume_tailor_harness.profile.fragments import (
        Produced,
        _expected_meta,
        _paths,
        _save_produced,
        fragment_cache_status,
    )

    source = tmp_path / "source.txt"
    source.write_text("A concrete source contribution.", encoding="utf-8")
    profile_dir = tmp_path / "profile"
    add_source(profile_dir, source)
    doc = load_manifest(profile_dir).docs[0].model_copy(update={"mode": mode})
    meta = _expected_meta(doc, doc.sha256)
    _save_produced(
        profile_dir,
        doc.id,
        Produced(ProfileFacts(contact=Contact(name="Morgan"))),
        meta,
    )
    assert fragment_cache_status(profile_dir, doc) == "cached"
    previous = dict(meta)
    previous[version_key] -= 1
    _paths(profile_dir, doc.id)[1].write_text(json.dumps(previous), encoding="utf-8")
    assert fragment_cache_status(profile_dir, doc) == "stale"
