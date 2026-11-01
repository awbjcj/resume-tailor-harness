"""Review is a browser action bound to the authenticated user's workspace."""

from sqlalchemy.orm import Session as SystemSession
from sqlmodel import Session, select

from resume_tailor_harness.api.auth import hash_password
from resume_tailor_harness.services.config_store import YamlConfigStore
from resume_tailor_harness.tenancy.system_db import User
from resume_tailor_harness.tenancy.workspace import provision_workspace
from resume_tailor_harness.tracking.tables import Job
from resume_tailor_harness.workspace_agent import actions
from resume_tailor_harness.workspace_agent.models import WorkspacePlan, WorkspaceChange
from resume_tailor_harness.workspace_agent.tables import WorkspaceNote


def test_browser_review_rejects_pat_payload_tampering_and_other_tenants(
    mu_app, mu_client
):
    assert (
        mu_client.get(
            "/api/workspace-agent/proposals",
            params={"surface": "coach", "sessionId": "s1"},
        ).status_code
        == 401
    )
    assert (
        mu_client.post(
            "/api/auth/login",
            json={"identifier": "owner", "password": "owner-password"},
        ).status_code
        == 200
    )
    engine = mu_app.state.engine
    root = mu_app.state.data_dir
    config = YamlConfigStore(root / "config")
    with Session(engine) as session:
        session.add(
            Job(
                source="manual",
                company="PrivateCo",
                title="Private role",
                jd_text="Private description",
            )
        )
        session.commit()
    plan = actions.prepare_plan(
        engine,
        root,
        config,
        WorkspacePlan(
            title="Private changes",
            changes=[
                WorkspaceChange(
                    operation="note.create",
                    job_id=1,
                    values={"title": "Private note", "body": "Interview preparation"},
                    reason="Save notes",
                )
            ],
        ),
        "Save my note",
    )
    actions.save_plan(
        engine,
        plan,
        surface="coach",
        session_id="s1",
        run_id="r1",
        source_text="Save my note",
    )
    url = f"/api/workspace-agent/proposals/{plan['id']}/review"
    payload = {
        "digest": plan["digest"],
        "actionIds": [plan["actions"][0]["id"]],
        "decision": "apply",
    }
    page = mu_client.get(
        "/api/workspace-agent/proposals", params={"surface": "coach", "sessionId": "s1"}
    )
    assert page.status_code == 200, page.text
    assert page.json()["proposals"][0]["title"] == "Private changes"
    token = mu_client.post(
        "/api/account/tokens", json={"name": "external-agent"}
    ).json()["token"]
    mu_client.cookies.clear()
    denied = mu_client.post(
        url, json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert denied.status_code == 403, denied.text
    with Session(engine) as session:
        assert session.exec(select(WorkspaceNote)).all() == []
    with SystemSession(mu_app.state.system_engine) as session:
        session.add(
            User(
                id="other-reviewer",
                username="alice",
                password_hash=hash_password("alice-password"),
            )
        )
        session.commit()
    provision_workspace(
        root, "other-reviewer", template_dir=mu_app.state.template_config_dir
    )
    assert (
        mu_client.post(
            "/api/auth/login",
            json={"identifier": "alice", "password": "alice-password"},
        ).status_code
        == 200
    )
    assert (
        mu_client.get(
            "/api/workspace-agent/proposals",
            params={"surface": "coach", "sessionId": "s1"},
        ).json()["proposals"]
        == []
    )
    assert mu_client.post(url, json=payload).status_code == 409
    mu_client.cookies.clear()
    mu_client.post(
        "/api/auth/login", json={"identifier": "owner", "password": "owner-password"}
    )
    assert (
        mu_client.post(
            url, json={**payload, "values": {"body": "tampered"}}
        ).status_code
        == 422
    )
    assert mu_client.post(url, json={**payload, "digest": "0" * 64}).status_code == 409
    applied = mu_client.post(url, json=payload)
    assert applied.status_code == 200, applied.text
    assert applied.json()["actions"][0]["receipt"]["state"] == "applied"
    assert mu_client.post(url, json=payload).json() == applied.json()
    with Session(engine) as session:
        assert len(session.exec(select(WorkspaceNote)).all()) == 1
