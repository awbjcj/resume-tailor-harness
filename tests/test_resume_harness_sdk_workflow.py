"""Exercise SDK handoff and recovery against the real application contracts."""

import json
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from resume_harness_sdk import APIError, ResponseValidationError, ResumeHarness
from resume_harness_sdk.cli import main
from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.schemas.evidence_portfolio import EvidencePortfolioOut
from resume_tailor_harness.services.run_completions import record_run_completion
from resume_tailor_harness.tracking.tables import (
    Application,
    CoverLetter,
    Job,
    ResumeVersion,
)


@pytest.fixture
def workspace(tmp_path):
    app = create_app(
        db_url="sqlite://", data_dir=tmp_path / "data", config_dir=tmp_path / "config"
    )
    with TestClient(app) as server:
        with Session(app.state.engine) as session:
            job = Job(source="manual", status="approved", jd_text="Full saved JD")
            session.add(job)
            session.commit()
            session.refresh(job)
            assert job.id is not None
            job_id = job.id

        def dispatch(request):
            response = server.request(
                request.method,
                str(request.url),
                headers=dict(request.headers),
                content=request.content,
            )
            return httpx.Response(
                response.status_code,
                headers=dict(response.headers),
                content=response.content,
            )

        with ResumeHarness(
            base_url="http://127.0.0.1",
            api_key="rat_test",
            transport=httpx.MockTransport(dispatch),
        ) as sdk:
            yield sdk, app, job_id


def test_read_only_preparation_and_exact_older_selection(workspace):
    sdk, app, job_id = workspace
    assert sdk.application_next_step(job_id)["kind"] == "tailor"
    assert sdk.get_application_materials(job_id)["items"] == []
    assert sdk.application_context(job_id)["job"]["jdText"] == "Full saved JD"
    with Session(app.state.engine) as session:
        assert session.exec(select(Application)).first() is None
        older = ResumeVersion(job_id=job_id, round=1, fact_check_passed=True)
        newer = ResumeVersion(job_id=job_id, round=2, fact_check_passed=True)
        letter = CoverLetter(job_id=job_id, fact_check_passed=True)
        session.add_all([older, newer, letter])
        session.commit()
        session.refresh(older)
        session.refresh(newer)
        session.refresh(letter)
        older_id, newer_id, letter_id = older.id, newer.id, letter.id
    assert older_id is not None and newer_id is not None and letter_id is not None
    sdk.select_resume(job_id, older_id)
    sdk.select_cover_letter(job_id, letter_id)
    assert sdk.deselect_cover_letter(job_id)["resumeVersionId"] == older_id
    context = sdk.application_context(job_id)
    materials = context["materials"]
    assert materials == sdk.get_application_prompt(job_id)["materials"]
    assert materials["selectedResumeVersionId"] == older_id
    assert [item["id"] for item in materials["items"] if item["isSelected"]] == [
        older_id
    ]
    assert any(
        item["id"] == newer_id and not item["isSelected"] for item in materials["items"]
    )
    next_step = sdk.application_next_step(job_id)
    assert next_step["kind"] == "render" and next_step["resumeVersionId"] == older_id
    assert sdk.deselect_resume(job_id)["resumeVersionId"] is None
    assert sdk.get_application_materials(job_id)["selectedResumeVersionId"] is None


def test_blocked_selection_remains_visible_and_queue_checks_still_apply(workspace):
    sdk, app, job_id = workspace
    with Session(app.state.engine) as session:
        blocked = ResumeVersion(job_id=job_id, fact_check_passed=False)
        session.add(blocked)
        session.flush()
        blocked_id = blocked.id
        session.add(
            Application(job_id=job_id, resume_version_id=blocked_id, status="ready")
        )
        session.commit()
    selected = sdk.application_context(job_id)["materials"]["items"][0]
    assert selected["id"] == blocked_id and selected["isSelected"]
    assert not selected["applicationEligible"] and selected["downloadPath"] is None
    assert selected["blockReason"] == "fact_lock_failed"
    with Session(app.state.engine) as session:
        application = session.exec(select(Application)).one()
        application.status = "submitted"
        session.add(application)
        session.commit()
    with pytest.raises(APIError) as error:
        sdk.application_context(job_id)
    assert error.value.code == "APPLICATION_NOT_READY"
    assert (
        sdk.get_application_prompt(job_id)["materials"]["selectedResumeVersionId"]
        == blocked_id
    )
    assert sdk.application_next_step(job_id)["kind"] == "track"


def test_public_envelope_writes_preserve_scopes_and_revision_conflicts(workspace):
    sdk, _, job_id = workspace
    snapshot = sdk.get_application_profile()
    sdk.patch_application_profile(
        {
            "profile": {"preferredName": "Confirmed name"},
            "revision": snapshot["revision"],
            "userConfirmed": True,
        }
    )
    with pytest.raises(APIError) as stale:
        sdk.patch_application_profile(
            {
                "profile": {"preferredName": "Outdated name"},
                "revision": snapshot["revision"],
                "userConfirmed": True,
            }
        )
    assert stale.value.code == "PROFILE_STALE"
    assert sdk.get_application_profile()["profile"]["preferredName"] == "Confirmed name"
    question = sdk.create_application_question(
        {"question": "Office days?", "jobId": job_id, "context": "US; this role only"}
    )
    answered = sdk.update_application_question(
        question["id"],
        {
            "answer": "Three",
            "revision": question["revision"],
            "userConfirmed": True,
        },
    )
    repeated = sdk.create_application_question(
        {"question": "Office days?", "jobId": job_id, "context": "US; this role only"}
    )
    assert repeated == answered
    with pytest.raises(APIError) as unknown:
        sdk.update_application_question(
            question["id"],
            {
                "answer": "Five",
                "revision": answered["revision"],
                "userConfirmed": True,
                "unknown": "must reach server validation",
            },
        )
    assert unknown.value.status_code == 422
    assert sdk.get_application_question(question["id"])["answer"] == "Three"


def test_durable_recovery_after_run_files_are_gone(workspace):
    sdk, app, job_id = workspace
    with Session(app.state.engine) as session:
        completion = record_run_completion(
            session,
            run_id="old-run",
            kind="tailor",
            label="Prepared resume",
            status="succeeded",
            error=None,
            completed_at=datetime.now(timezone.utc),
            logs=[{"message": "Saved document", "state": "running"}],
            meta={"jobId": job_id},
        )
        completion_id = completion.id
    with pytest.raises(APIError) as missing:
        sdk.get_run("old-run")
    assert missing.value.status_code == 404
    recovered = sdk.get_run_completion("old-run")
    assert recovered["id"] == completion_id and recovered["readAt"] is None
    assert recovered["resultAvailable"] and recovered["resultHref"].startswith(
        "/pipeline?"
    )
    assert sdk.list_run_completions(unread_only=True) == [recovered]
    assert sdk.get_run_logs(completion_id) == [
        {"message": "Saved document", "state": "running"}
    ]
    assert sdk.get_run_completion("old-run")["readAt"] is None
    assert sdk.setup_status()["profile"]["freshness"] == "missing"


@pytest.mark.parametrize("materials", [None, "absent"])
def test_older_servers_do_not_invent_materials_or_next_steps(materials):
    payload: dict[str, object] = {"prompt": "Legacy handoff"}
    if materials is None:
        payload["materials"] = None

    def handle(request):
        return httpx.Response(
            200, json={"id": 1} if request.url.path == "/api/jobs/1" else payload
        )

    with ResumeHarness(
        base_url="https://harness.example",
        api_key="rat_test",
        transport=httpx.MockTransport(handle),
    ) as sdk:
        assert sdk.get_application_materials(1) is None
        assert sdk.application_next_step(1) is None


@pytest.mark.parametrize(
    "malformed",
    [
        {
            "materials": {
                "selectedResumeVersionId": None,
                "selectedCoverLetterId": None,
                "items": [
                    {
                        "id": 1,
                        "kind": "resume",
                        "isSelected": True,
                        "applicationEligible": "true",
                        "pdfAvailable": False,
                        "downloadPath": None,
                    }
                ],
            }
        },
        {"materials": {"items": []}},
    ],
)
def test_invalid_material_metadata_does_not_echo_applicant_data(malformed):
    with ResumeHarness(
        base_url="https://harness.example",
        api_key="rat_test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"prompt": "private applicant information", **malformed}
            )
        ),
    ) as sdk:
        with pytest.raises(ResponseValidationError) as invalid:
            sdk.get_application_prompt(1)
        assert "private applicant" not in str(invalid.value)


def test_evidence_contract_uses_server_schema_and_keeps_additive_fields():
    payload = EvidencePortfolioOut(status="inherited").model_dump(
        mode="json", by_alias=True
    )
    payload["future"] = {"retained": True}

    def handle(request):
        assert request.url.path == "/api/resume-versions/8/evidence-portfolio"
        return httpx.Response(200, json=payload)

    with ResumeHarness(
        base_url="https://harness.example",
        api_key="rat_test",
        transport=httpx.MockTransport(handle),
    ) as sdk:
        assert sdk.get_evidence_portfolio(8) == payload


def test_cli_text_import_keeps_complete_camelcase_body(tmp_path, monkeypatch, capsys):
    body = {
        "jdText": "Real saved job description",
        "company": "Example",
        "location": "New York",
    }
    path = tmp_path / "job.json"
    path.write_text(json.dumps(body), encoding="utf-8-sig")

    def handle(request):
        assert request.url.path == "/api/jobs" and request.method == "POST"
        assert json.loads(request.content) == body
        return httpx.Response(201, json={"id": 42})

    monkeypatch.setattr(
        ResumeHarness,
        "from_env",
        lambda: ResumeHarness(
            base_url="https://harness.example",
            api_key="rat_test",
            transport=httpx.MockTransport(handle),
        ),
    )
    monkeypatch.setattr("sys.argv", ["resume-harness", "add-job", "--input", str(path)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out) == {"id": 42}


@pytest.mark.parametrize(
    "args,method,path,body,response",
    [
        (
            ["application-next-step", "42"],
            "GET",
            "/api/jobs/42",
            None,
            {
                "id": 42,
                "nextStep": {
                    "jobId": 42,
                    "kind": "render",
                    "href": "/pipeline?job=42",
                    "resumeVersionId": 8,
                },
            },
        ),
        (
            ["application-handoff", "42"],
            "GET",
            "/api/jobs/42/application-prompt",
            None,
            {"prompt": "Handoff", "future": "retained"},
        ),
        (
            ["application-materials", "42"],
            "GET",
            "/api/jobs/42/application-prompt",
            None,
            {"prompt": "Handoff", "materials": None},
        ),
        (
            ["run-completion", "old-run"],
            "GET",
            "/api/run-completions/by-run/old-run",
            None,
            {
                "id": 2,
                "runId": "old-run",
                "kind": "tailor",
                "label": "Ready",
                "status": "succeeded",
                "completedAt": "2026-11-02T00:00:00Z",
            },
        ),
        (
            ["run-logs", "2"],
            "GET",
            "/api/run-completions/2/logs",
            None,
            [{"message": "Saved"}],
        ),
        (
            ["run-completions", "--limit", "5", "--unread-only"],
            "GET",
            "/api/run-completions",
            None,
            [],
        ),
        (
            ["add-job-url", "https://jobs.example/42", "--no-browser"],
            "POST",
            "/api/jobs/from-url",
            {
                "url": "https://jobs.example/42",
                "company": None,
                "title": None,
                "location": None,
                "allowBrowser": False,
                "publicExtraction": False,
            },
            {"runId": "url-run"},
        ),
        (
            ["redo", "42", "--stage", "render", "--stage", "render"],
            "POST",
            "/api/redo",
            {"jobIds": [42], "stages": ["render"], "deep": False},
            {"runId": "redo-run"},
        ),
    ],
)
def test_workflow_cli_uses_authenticated_public_interfaces(
    monkeypatch, capsys, args, method, path, body, response
):
    seen = []

    def handle(request):
        seen.append(request)
        assert request.method == method and request.url.path == path
        assert request.headers["authorization"] == "Bearer rat_test"
        assert (json.loads(request.content) if request.content else None) == body
        if args[0] == "run-completions":
            assert dict(request.url.params) == {
                "limit": "5",
                "unread_only": "true",
                "surface": "operations",
            }
        return httpx.Response(200, json=response)

    monkeypatch.setattr(
        ResumeHarness,
        "from_env",
        lambda: ResumeHarness(
            base_url="https://harness.example",
            api_key="rat_test",
            transport=httpx.MockTransport(handle),
        ),
    )
    monkeypatch.setattr("sys.argv", ["resume-harness", *args])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    if args[0] == "application-handoff":
        assert result["future"] == "retained"
    assert len(seen) == 1
