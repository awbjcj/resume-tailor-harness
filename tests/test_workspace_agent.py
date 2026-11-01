"""Effects, ownership, stale approval and replay tests for conversational CRUD."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlmodel import Session, select

from resume_tailor_harness.db import init_db, make_engine
from resume_tailor_harness.services.config_store import YamlConfigStore
from resume_tailor_harness.tracking.tables import Job, Application, ApplicationEvent
from resume_tailor_harness.workspace_agent import actions, reads
from resume_tailor_harness.workspace_agent.models import WorkspaceChange, WorkspacePlan
from resume_tailor_harness.workspace_agent.runtime import (
    WorkspaceTools,
    use_workspace_tools,
    workspace_tools,
)
from resume_tailor_harness.workspace_agent.tables import (
    WorkspaceNote,
    WorkspaceActionReceipt,
)


@pytest.fixture
def workspace(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'workspace.db').as_posix()}")
    init_db(engine)
    with Session(engine) as session:
        session.add(
            Job(source="manual", company="Acme", title="Engineer", jd_text="Build APIs")
        )
        session.add(
            Job(source="manual", company="Acme", title="Manager", jd_text="Lead teams")
        )
        session.commit()
    yield engine, tmp_path, YamlConfigStore(tmp_path / "config")
    engine.dispose()


def propose(workspace, *changes, user_text="Add a recruiter note"):
    engine, root, config = workspace
    plan = actions.prepare_plan(
        engine,
        root,
        config,
        WorkspacePlan(title="Review changes", changes=list(changes)),
        user_text,
    )
    actions.save_plan(
        engine,
        plan,
        surface="career-lab",
        session_id="session1",
        run_id="r1",
        source_text=user_text,
    )
    return plan


def decide(workspace, plan, decision="apply", ids=None):
    return actions.resolve_plan(
        workspace[0],
        workspace[1],
        workspace[2],
        plan["id"],
        digest=plan["digest"],
        action_ids=ids or [a["id"] for a in plan["actions"]],
        decision=decision,
        actor="human1",
    )


def note(**kwargs):
    return WorkspaceChange(
        operation="note.create",
        job_id=1,
        values={"title": "Recruiter", "body": "Discuss API ownership"},
        reason="Save the preparation",
        **kwargs,
    )


def test_tools_and_publishing_do_not_apply_changes(workspace):
    engine, root, config = workspace
    toolkit = WorkspaceTools(engine, root, config, "Save a note")
    with use_workspace_tools(toolkit):
        tools = {f.__name__: f for f in workspace_tools()}
        output = tools["preview_workspace_changes"](
            WorkspacePlan(title="A note", changes=[note()])
        )
        assert output["saved"] is False
        assert "resolve_plan" not in tools
    with Session(engine) as session:
        assert session.exec(select(WorkspaceNote)).all() == []
    plan = toolkit.plans[0]
    actions.save_plan(
        engine,
        plan,
        surface="coach",
        session_id="s1",
        run_id="r1",
        source_text="Save a note",
    )
    with Session(engine) as session:
        assert session.exec(select(WorkspaceNote)).all() == []
    assert decide(workspace, plan)["actions"][0]["receipt"]["state"] == "applied"


def test_same_approval_is_repeat_safe_and_notes_keep_history(workspace):
    plan = propose(workspace, note())
    first, second = decide(workspace, plan), decide(workspace, plan)
    assert first == second
    note_id = first["actions"][0]["receipt"]["result"]["note_id"]
    edit = propose(
        workspace,
        WorkspaceChange(
            operation="note.update",
            job_id=1,
            target_id=note_id,
            values={"title": "Updated", "body": "Practice trade-offs"},
            reason="Correction",
        ),
    )
    decide(workspace, edit)
    with Session(workspace[0]) as session:
        saved = session.get(WorkspaceNote, note_id)
        assert saved is not None
        assert saved.revision == 2
        assert [v["body"] for v in saved.history] == [
            "Discuss API ownership",
            "Practice trade-offs",
        ]


def test_reject_stale_digest_cross_job_and_discarded_approval(workspace):
    plan = propose(workspace, note())
    with pytest.raises(ValueError, match="reviewed"):
        actions.resolve_plan(
            workspace[0],
            workspace[1],
            workspace[2],
            plan["id"],
            digest="0" * 64,
            action_ids=[plan["actions"][0]["id"]],
            decision="apply",
            actor="human1",
        )
    with Session(workspace[0]) as session:
        job = session.get(Job, 1)
        assert job is not None
        job.title = "Edited elsewhere"
        session.add(job)
        session.commit()
    with pytest.raises(ValueError, match="changed"):
        decide(workspace, plan)
    decide(workspace, plan, "discard")
    with pytest.raises(ValueError, match="resolved"):
        decide(workspace, plan)
    valid = propose(workspace, note())
    saved = decide(workspace, valid)
    note_id = saved["actions"][0]["receipt"]["result"]["note_id"]
    with pytest.raises(ValueError, match="belong"):
        propose(
            workspace,
            WorkspaceChange(
                operation="note.delete", job_id=2, target_id=note_id, reason="Wrong job"
            ),
        )


def test_batch_events_and_notes_commit_with_receipts(workspace):
    plan = propose(
        workspace,
        WorkspaceChange(
            operation="event.create",
            job_id=1,
            values={
                "kind": "application_submitted",
                "occurred_at": "2026-11-01T10:00:00-05:00",
            },
            reason="User reports submission",
        ),
        note(),
    )
    decide(workspace, plan)
    with Session(workspace[0]) as session:
        assert len(session.exec(select(ApplicationEvent)).all()) == 1
        assert session.exec(select(Application)).one().status == "submitted"
        assert len(session.exec(select(WorkspaceActionReceipt)).all()) == 2


def test_effects_roll_back_if_receipt_transaction_fails(workspace, monkeypatch):
    plan = propose(workspace, note())

    def fail(self):
        raise RuntimeError("disk failure")

    monkeypatch.setattr(actions.ActionSession, "finish", fail)
    with pytest.raises(RuntimeError):
        decide(workspace, plan)
    with Session(workspace[0]) as session:
        assert session.exec(select(WorkspaceNote)).all() == []
        assert session.exec(select(WorkspaceActionReceipt)).all() == []


def test_concurrent_approvals_apply_once(workspace):
    plan = propose(workspace, note())
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: decide(workspace, plan), range(2)))
    assert results[0] == results[1]
    with Session(workspace[0]) as session:
        assert len(session.exec(select(WorkspaceNote)).all()) == 1


def test_reads_are_paginated_and_do_not_create_application(workspace):
    with Session(workspace[0]) as session:
        result = reads.find_jobs(session, "Acme", limit=1)
        assert len(result["records"]) == 1 and result["next_offset"] == 1
        assert reads.public_job_context(session, 1)["application"] == {}
        assert session.exec(select(Application)).all() == []


def test_delete_preserves_invested_work_and_archive_is_allowed(workspace):
    decide(workspace, propose(workspace, note()))
    with pytest.raises(ValueError, match="Archive"):
        propose(
            workspace,
            WorkspaceChange(operation="job.delete", job_id=1, reason="Remove"),
        )
    decide(
        workspace,
        propose(
            workspace,
            WorkspaceChange(operation="job.archive", job_id=1, reason="Archive"),
        ),
    )
    with Session(workspace[0]) as session:
        job = session.get(Job, 1)
        assert job is not None and job.archived_at is not None


def test_profile_changes_require_current_evidence_and_approval(workspace):
    text = "My name is Alex"
    change = WorkspaceChange(
        operation="profile.change",
        reason="Create profile",
        values={
            "title": "Create profile",
            "changes": [
                {
                    "entity": "profile",
                    "operation": "create",
                    "values": {"contact": {"name": "Alex"}},
                    "quotes": [text],
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="quote"):
        propose(workspace, change, user_text="What jobs are available?")
    plan = propose(workspace, change, user_text=text)
    assert not (workspace[1] / "profile/facts.json").exists()
    decide(workspace, plan)
    assert (
        json.loads((workspace[1] / "profile/facts.json").read_text())["contact"]["name"]
        == "Alex"
    )


def test_skill_tools_never_expose_script_execution():
    from resume_tailor_harness.career_skills.agno import skill_kwargs
    from resume_tailor_harness.career_skills.registry import CareerSkillRegistry
    from resume_tailor_harness.career_skills.models import AgentFamily

    skill = CareerSkillRegistry.from_paths("skills", "skills-lock.json").require(
        "workspace-management", family=AgentFamily.CAREER_LAB, use="career_lab"
    )
    attached = skill_kwargs(skill)["skills"]
    assert [tool.name for tool in attached.get_tools()] == ["get_skill_instructions"]


def test_job_create_update_delete_and_no_silent_upsert(workspace):
    from resume_tailor_harness.tracking.dedup import compute_dedup_key

    change = WorkspaceChange(
        operation="job.create",
        values={
            "company": "NewCo",
            "title": "Analyst",
            "jd_text": "Analyze operations",
            "url": "https://example.com/job",
        },
        reason="Save public posting",
    )
    created = decide(workspace, propose(workspace, change))["actions"][0]["receipt"][
        "result"
    ]["job_id"]
    with Session(workspace[0]) as session:
        assert session.get(Job, created) is not None
    duplicate = propose(workspace, change)
    with pytest.raises(ValueError, match="already exists"):
        decide(workspace, duplicate)
    decide(
        workspace,
        propose(
            workspace,
            WorkspaceChange(
                operation="job.update",
                job_id=created,
                values={"title": "Senior Analyst"},
                reason="Correct title",
            ),
        ),
    )
    with Session(workspace[0]) as session:
        saved = session.get(Job, created)
        assert saved is not None and saved.title == "Senior Analyst"
        assert saved.dedup_key == compute_dedup_key("NewCo", "Senior Analyst")
    decide(
        workspace,
        propose(
            workspace,
            WorkspaceChange(
                operation="job.delete", job_id=created, reason="Remove posting"
            ),
        ),
    )
    with Session(workspace[0]) as session:
        assert session.get(Job, created) is None


def test_questions_and_personal_answer_approval(workspace):
    from resume_tailor_harness.tracking.tables import ApplicationQuestion

    plan = propose(
        workspace,
        WorkspaceChange(
            operation="question.create",
            job_id=1,
            reason="Save screening question",
            values={"question": "Why this role?", "jobId": 1},
        ),
    )
    result = decide(workspace, plan)
    question_id = result["actions"][0]["receipt"]["result"]["id"]
    decide(
        workspace,
        propose(
            workspace,
            WorkspaceChange(
                operation="question.update",
                job_id=1,
                target_id=question_id,
                values={"answer": "I enjoy building APIs."},
                reason="User answer",
            ),
        ),
    )
    with Session(workspace[0]) as session:
        row = session.get(ApplicationQuestion, question_id)
        assert row is not None and row.answer == "I enjoy building APIs."
    decide(
        workspace,
        propose(
            workspace,
            WorkspaceChange(
                operation="question.delete",
                job_id=1,
                target_id=question_id,
                reason="Remove answer",
            ),
        ),
    )
    with Session(workspace[0]) as session:
        assert session.get(ApplicationQuestion, question_id) is None


def test_settings_compare_and_swap_and_unknown_effects_block_replay(
    workspace, monkeypatch
):
    original = workspace[2].get("search").model_dump()
    plan = propose(
        workspace,
        WorkspaceChange(
            operation="search.update",
            values={"keywords": ["Python"]},
            reason="Search preference",
        ),
    )
    assert workspace[2].get("search").model_dump() == original
    decide(workspace, plan)
    assert workspace[2].get("search").model_dump()["keywords"] == ["Python"]
    unknown = propose(
        workspace,
        WorkspaceChange(
            operation="search.update",
            values={"keywords": ["Rust"]},
            reason="New preference",
        ),
    )

    def crash(*args):
        raise RuntimeError("process interrupted")

    monkeypatch.setattr(actions, "_execute_file", crash)
    with pytest.raises(RuntimeError):
        decide(workspace, unknown)
    with pytest.raises(ValueError, match="unknown"):
        decide(workspace, unknown)
    assert (
        actions.proposal_view(workspace[0], unknown["id"])["actions"][0]["receipt"][
            "state"
        ]
        == "outcome_unknown"
    )


def test_expired_proposal_can_be_discarded_but_not_applied(workspace):
    from datetime import timedelta
    from resume_tailor_harness.tracking.tables import utcnow
    from resume_tailor_harness.workspace_agent.tables import WorkspaceProposal

    plan = propose(workspace, note())
    with Session(workspace[0]) as session:
        row = session.get(WorkspaceProposal, plan["id"])
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        session.add(row)
        session.commit()
    with pytest.raises(ValueError, match="expired"):
        decide(workspace, plan)
    assert (
        decide(workspace, plan, "discard")["actions"][0]["receipt"]["state"]
        == "discarded"
    )


def test_unobserved_citations_and_budget_are_rejected(workspace):
    toolkit = WorkspaceTools(workspace[0], workspace[1], workspace[2], "Save a note")
    tools = {f.__name__: f for f in toolkit.functions()}
    with pytest.raises(ValueError, match="cited"):
        tools["preview_workspace_changes"](
            WorkspacePlan(
                title="Unsupported citation",
                changes=[note(citations=["https://example.com/invented"])],
            )
        )
    toolkit.calls = 15
    with pytest.raises(ValueError, match="limit"):
        tools["find_saved_jobs"]()


def test_notes_protect_jobs_across_existing_delete_paths(workspace):
    from resume_tailor_harness.tracking.repository import delete_job, progressed_job_ids

    decide(workspace, propose(workspace, note()))
    with Session(workspace[0]) as session:
        assert 1 in progressed_job_ids(session, [1, 2])
        assert delete_job(session, 1) is False


def test_artifact_selection_and_delete_require_separate_approval(workspace):
    from resume_tailor_harness.tracking.tables import ResumeVersion

    with Session(workspace[0]) as session:
        session.add(ResumeVersion(job_id=1, content_json={"summary": "APIs"}))
        session.add(ResumeVersion(job_id=1, content_json={"summary": "Systems"}))
        session.commit()
    decide(
        workspace,
        propose(
            workspace,
            WorkspaceChange(
                operation="artifact.select",
                job_id=1,
                target_id=1,
                values={"kind": "resume"},
                reason="Choose resume",
            ),
        ),
    )
    with pytest.raises(ValueError, match="Selected"):
        propose(
            workspace,
            WorkspaceChange(
                operation="artifact.delete",
                job_id=1,
                target_id=1,
                values={"kind": "resume"},
                reason="Remove selected",
            ),
        )
    plan = propose(
        workspace,
        WorkspaceChange(
            operation="artifact.delete",
            job_id=1,
            target_id=2,
            values={"kind": "resume"},
            reason="Remove unused",
        ),
    )
    decide(workspace, plan)
    with Session(workspace[0]) as session:
        assert session.get(ResumeVersion, 1) is not None
        assert session.get(ResumeVersion, 2) is None


def test_builders_attach_read_preview_tools_only_when_bound_to_workspace(
    workspace, monkeypatch
):
    from types import SimpleNamespace
    from resume_tailor_harness.career_lab import agents as lab
    from resume_tailor_harness.discovery import scout
    from resume_tailor_harness.profile import coach
    from resume_tailor_harness.interview import agent as interview
    from resume_tailor_harness.interview.store import InterviewStyle
    from resume_tailor_harness.career_skills.registry import CareerSkillRegistry
    from resume_tailor_harness.career_skills.models import AgentFamily

    captured = []

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    for module in (lab, scout, coach, interview):
        monkeypatch.setattr(module, "Agent", FakeAgent)
        monkeypatch.setattr(module, "build_model", lambda *a, **kw: "model")
        monkeypatch.setattr(
            module,
            "provider_capabilities",
            lambda *a: SimpleNamespace(
                supports_prompt_cache=False, supports_reasoning=False
            ),
        )
    # Native provider tools are dictionaries, not callable Python tools.
    native = {"type": "web_search"}
    monkeypatch.setattr(
        scout, "build_search_equipped", lambda *a, **kw: ("model", [native])
    )
    skill = CareerSkillRegistry.from_paths("skills", "skills-lock.json").require(
        "workspace-management", family=AgentFamily.CAREER_LAB, use="career_lab"
    )
    with use_workspace_tools(
        WorkspaceTools(workspace[0], workspace[1], workspace[2], "Manage jobs")
    ):
        lab.build_persona_agent(skill)
        coach.build_coach_agent([])
        interview.build_interviewer_agent(InterviewStyle())
        scout.build_scout_agent(
            lambda name, url: "", company_intelligence_tool=lambda companies: ""
        )
    for kwargs in captured:
        names = {getattr(tool, "__name__", "") for tool in kwargs["tools"]}
        assert {
            "find_saved_jobs",
            "read_job_workspace",
            "preview_workspace_changes",
            "inspect_profile",
            "read_change_receipts",
        } <= names
        assert not names & {
            "resolve_plan",
            "apply_workspace_draft",
            "update_profile",
            "exec_command",
        }
        assert kwargs["tool_call_limit"] == 15
    assert native in captured[-1]["tools"]


def test_turn_publication_requires_successful_tenant_bound_conversation(workspace):
    from resume_tailor_harness.config import Settings
    from resume_tailor_harness.tenancy.context import UserContext, use_context
    from resume_tailor_harness.tenancy.workspace import WorkspacePaths
    from resume_tailor_harness.workspace_agent.runtime import workspace_turn
    from resume_tailor_harness.workspace_agent.tables import WorkspaceProposal

    engine, root, config = workspace
    context = UserContext(
        user_id="test",
        username="test",
        role="member",
        paths=WorkspacePaths(root),
        settings=Settings(),
        engine=engine,
        system_engine=None,
        own_key_providers=frozenset(),
    )

    @workspace_turn("coach")
    def chat(*, message, fail=False):
        tools = {f.__name__: f for f in workspace_tools()}
        tools["preview_workspace_changes"](
            WorkspacePlan(title="Save note", changes=[note()])
        )
        if fail:
            raise RuntimeError("cancelled")
        return {"sessionId": "persisted-chat"}

    with use_context(context):
        with pytest.raises(RuntimeError):
            chat(message="Save note", fail=True)
        with Session(engine) as session:
            assert session.exec(select(WorkspaceProposal)).all() == []
        chat(message="Save note")
    with Session(engine) as session:
        assert (
            session.exec(select(WorkspaceProposal)).one().session_id == "persisted-chat"
        )
        assert session.exec(select(WorkspaceNote)).all() == []


def test_reject_order_dependent_status_batch(workspace):
    with pytest.raises(ValueError, match="separately"):
        propose(
            workspace,
            WorkspaceChange(
                operation="application.update",
                job_id=1,
                values={"status": "rejected"},
                reason="User reports rejection",
            ),
            WorkspaceChange(
                operation="event.create",
                job_id=1,
                values={
                    "kind": "application_submitted",
                    "occurred_at": "2026-11-01T10:00:00Z",
                },
                reason="Record earlier submission",
            ),
        )


def test_application_profile_patch_keeps_unrelated_answers(workspace):
    from resume_tailor_harness.services.agent_applications import read_profile

    first = propose(
        workspace,
        WorkspaceChange(
            operation="application_profile.update",
            values={"fullName": "Alex", "email": "alex@example.com"},
            reason="User provided contact",
        ),
    )
    decide(workspace, first)
    second = propose(
        workspace,
        WorkspaceChange(
            operation="application_profile.update",
            values={"fullName": "Alex Example"},
            reason="Correct name",
        ),
    )
    decide(workspace, second)
    saved = read_profile(workspace[2]).profile
    assert saved.full_name == "Alex Example"
    assert saved.email == "alex@example.com"
