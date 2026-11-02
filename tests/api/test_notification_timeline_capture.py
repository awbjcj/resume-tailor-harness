from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.tracking.tables import Application, ApplicationEvent, Job, Notification


@pytest.fixture
def client():
    with TestClient(create_app(db_url="sqlite://")) as client:
        yield client


def _proposal(client: TestClient):
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        job = Job(source="manual", company="Acme", title="Engineer")
        session.add(job)
        session.flush()
        assert job.id is not None
        application = Application(job_id=job.id, status="submitted")
        session.add(application)
        session.flush()
        assert application.id is not None
        session.add(Notification(
            application_id=application.id, kind="interview", proposed_status="interview",
            evidence="Technical interview on November 6 at 2 PM New York time.",
            message_id="mailbox:account-1:provider-id",
            created_at=datetime(2026, 11, 2, 12, tzinfo=timezone.utc),
        ))
        session.commit()
    [proposal] = client.get("/api/notifications").json()
    return proposal


def _capture(proposal):
    return {
        "expectedRevision": proposal["revision"],
        "eventDetailsConfirmed": True,
        "event": {
            "kind": "technical_round",
            "occurredAt": "2026-11-06T19:00:00Z",
            "timezone": "America/New_York",
        },
    }


def test_accept_without_a_body_still_changes_status_without_inventing_a_date(client):
    proposal = _proposal(client)
    response = client.post(f"/api/notifications/{proposal['id']}/accept")
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "accepted"
    assert client.get(f"/api/jobs/{proposal['jobId']}/events").json() == []
    assert client.get(f"/api/jobs/{proposal['jobId']}").json()["application"]["status"] == "interview"


def test_accept_and_capture_confirmed_date_as_one_repeat_safe_command(client):
    proposal = _proposal(client)
    body = _capture(proposal)
    response = client.post(f"/api/notifications/{proposal['id']}/accept", json=body)
    assert response.status_code == 200, response.text
    [event] = client.get(f"/api/jobs/{proposal['jobId']}/events").json()
    assert event["occurredAt"] == "2026-11-06T19:00:00Z"
    assert event["timezone"] == "America/New_York"
    assert event["source"] == "mailbox"
    assert proposal["evidence"] in event["notes"]
    assert proposal["messageId"] in event["notes"]
    assert event["occurredAt"] != proposal["createdAt"]
    assert client.post(f"/api/notifications/{proposal['id']}/accept", json=body).status_code == 404
    assert len(client.get(f"/api/jobs/{proposal['jobId']}/events").json()) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"eventDetailsConfirmed": False},
        {"expectedRevision": None},
        {"event": {"kind": "technical_round"}},
        {"event": {"kind": "technical_round", "occurredAt": "2026-11-06T19:00:00Z"}},
        {"event": {"kind": "technical_round", "occurredAt": "2026-11-06T19:00:00Z", "timezone": "Invalid/Zone"}},
        {"event": {"kind": "offer_received", "occurredAt": "2026-11-06T19:00:00Z", "allDay": True}},
    ],
)
def test_invalid_capture_leaves_the_proposal_and_status_unchanged(client, change):
    proposal = _proposal(client)
    response = client.post(
        f"/api/notifications/{proposal['id']}/accept", json={**_capture(proposal), **change},
    )
    assert response.status_code == 422, response.text
    assert client.get("/api/notifications").json()[0]["state"] == "pending"
    assert client.get(f"/api/jobs/{proposal['jobId']}").json()["application"]["status"] == "submitted"
    assert client.get(f"/api/jobs/{proposal['jobId']}/events").json() == []


def test_changed_proposal_returns_a_conflict_without_writing_an_event(client):
    proposal = _proposal(client)
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        notice = session.get(Notification, proposal["id"])
        assert notice is not None
        notice.evidence = "Correction: select an interview slot."
        session.add(notice)
        session.commit()
    response = client.post(f"/api/notifications/{proposal['id']}/accept", json=_capture(proposal))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NOTIFICATION_CHANGED"
    with Session(client.app.state.engine) as session:  # type: ignore[attr-defined]
        assert session.exec(select(ApplicationEvent)).all() == []
        notice = session.get(Notification, proposal["id"])
        assert notice is not None and notice.state == "pending"
