import json
import re
import time

import httpx
import pytest

from resume_harness_sdk import (
    APIError,
    ResponseValidationError,
    ResumeHarness,
    RunFailed,
    RunTimeout,
)
from resume_harness_sdk.cli import main


def client(handler, **kwargs):
    return ResumeHarness(
        base_url="https://harness.example/api",
        api_key="rat_test",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_bearer_pagination_and_field_preservation():
    def handle(request):
        assert request.headers["authorization"] == "Bearer rat_test"
        assert request.url.path == "/api/shortlist"
        assert request.url.params["minFit"] == "70"
        page = int(request.url.params["page"])
        return httpx.Response(
            200, json={"data": [{"jobId": page}], "pagination": {"totalPages": 2}}
        )

    with client(handle) as sdk:
        assert list(sdk.iter_jobs(board="shortlist", minFit=70)) == [
            {"jobId": 1},
            {"jobId": 2},
        ]


def test_external_payload_and_authenticated_pdf():
    requests = []

    def handle(request):
        requests.append(request)
        return (
            httpx.Response(200, content=b"%PDF-test")
            if request.url.path.endswith("/pdf")
            else httpx.Response(202, json={"runId": "run"})
        )

    with client(handle) as sdk:
        sdk.submit_resume(
            7, {"summary_provenance": ["fact"]}, context_revision="a" * 64, agent="pi"
        )
        assert sdk.download_resume(8) == b"%PDF-test"
    assert json.loads(requests[0].content) == {
        "content": {"summary_provenance": ["fact"]},
        "contextRevision": "a" * 64,
        "agent": "pi",
    }
    assert requests[0].url.path == "/api/jobs/7/external-resume"
    assert requests[1].headers["authorization"] == "Bearer rat_test"
    assert "token" not in requests[1].url.params


def test_errors_are_structured_and_writes_not_retried():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": "QUOTA",
                    "message": "Limit reached",
                    "details": {"remaining": 0},
                }
            },
        )

    with client(handle) as sdk, pytest.raises(APIError) as exc:
        sdk.tailor([1])
    assert exc.value.status_code == 429 and exc.value.code == "QUOTA"
    assert exc.value.details == {"remaining": 0} and len(seen) == 1


def test_redirects_are_not_followed():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(307, headers={"location": "https://other.example/steal"})

    with client(handle) as sdk, pytest.raises(APIError):
        sdk.get_job(1)
    assert len(seen) == 1


@pytest.mark.parametrize("state", ["done", "error", "cancelled"])
def test_terminal_states(state):
    with client(
        lambda _: httpx.Response(200, json={"runId": "a", "state": state})
    ) as sdk:
        if state == "done":
            assert sdk.wait("a")["state"] == state
        else:
            with pytest.raises(RunFailed) as exc:
                sdk.wait("a")
            assert exc.value.run["state"] == state


def test_wait_timeout_does_not_cancel(monkeypatch):
    ticks = iter([0, 0, 2, 2])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    seen = []

    def handle(request):
        seen.append(request.method)
        return httpx.Response(200, json={"runId": "a", "state": "running"})

    with client(handle) as sdk, pytest.raises(RunTimeout) as exc:
        sdk.wait("a", timeout=1)
    assert exc.value.run_id == "a" and seen == ["GET"]


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example",
        "https://user:secret@example.com",
        "https://example.com?token=secret",
    ],
)
def test_reject_unsafe_configuration(url):
    with pytest.raises(ValueError):
        ResumeHarness(base_url=url, api_key="rat_test")


def test_install_skills_without_credentials_and_preserve_existing(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "skills"
    monkeypatch.setattr(
        "sys.argv", ["resume-harness", "install-skills", "--directory", str(root)]
    )
    assert main() == 0
    for name in ("resume-harness-sdk", "resume-harness-tailor", "resume-harness-apply"):
        assert (root / name / "SKILL.md").is_file()
    reference = root / "resume-harness-sdk" / "references" / "client.md"
    reference.write_text("user-edited", encoding="utf-8")
    assert main() == 1
    assert reference.read_text() == "user-edited"
    capsys.readouterr()


def test_installed_skills_include_resolvable_workflow_references(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    monkeypatch.setattr(
        "sys.argv", ["resume-harness", "install-skills", "--directory", str(root)]
    )
    assert main() == 0
    for document in root.rglob("*.md"):
        for target in re.findall(
            r"\[[^\]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")
        ):
            if not target.startswith(("http:", "https:", "#")):
                assert (document.parent / target.split("#")[0]).is_file(), target


def question_response():
    return {
        "id": 7,
        "question": "Question?",
        "context": "Example employer",
        "scope": "job",
        "jobId": 42,
        "answer": None,
        "revision": 1,
        "createdAt": "2026-10-17T00:00:00Z",
        "updatedAt": "2026-10-17T00:00:00Z",
    }


def test_application_sdk_pagination_and_additive_fields():
    def handle(request):
        page = int(request.url.params["page"])
        assert request.headers["authorization"] == "Bearer rat_test"
        assert request.url.path == "/api/application-jobs"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "jobId": page,
                        "title": None,
                        "company": None,
                        "location": None,
                        "url": None,
                        "status": "approved",
                        "future": "preserved",
                    }
                ],
                "pagination": {
                    "page": page,
                    "pageSize": 1,
                    "totalItems": 2,
                    "totalPages": 2,
                },
            },
        )

    with client(handle) as sdk:
        rows = list(sdk.iter_application_jobs(page_size=1))
        assert [row["jobId"] for row in rows] == [1, 2]
        assert dict(rows[0])["future"] == "preserved"


def test_application_sdk_validates_response_without_echoing_personal_data():
    with client(
        lambda _: httpx.Response(
            200, json={"profile": {"email": ["private@example.com"]}, "revision": "rev"}
        )
    ) as sdk:
        with pytest.raises(ResponseValidationError) as exc:
            sdk.get_application_profile()
        assert "private@example.com" not in str(exc.value)
    with client(lambda _: httpx.Response(200, content=b"<html>private</html>")) as sdk:
        with pytest.raises(ResponseValidationError):
            sdk.application_context(42)


def test_application_sdk_write_payloads_and_cover_letter_download():
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path.endswith("/pdf"):
            return httpx.Response(200, content=b"%PDF-letter")
        if request.url.path.endswith("application-profile"):
            return httpx.Response(
                200, json={"profile": {"phone": ""}, "revision": "new"}
            )
        return httpx.Response(200, json=question_response())

    with client(handle) as sdk:
        sdk.update_application_profile(
            {"phone": ""}, revision="old", user_confirmed=True
        )
        sdk.record_application_question(
            "Question?", job_id=42, context="Example employer"
        )
        sdk.answer_application_question(7, "No", revision=1, user_confirmed=True)
        assert sdk.download_cover_letter(5) == b"%PDF-letter"
    assert json.loads(requests[0].content) == {
        "profile": {"phone": ""},
        "revision": "old",
        "userConfirmed": True,
    }
    assert json.loads(requests[1].content) == {
        "question": "Question?",
        "jobId": 42,
        "context": "Example employer",
        "scope": "job",
    }
    assert json.loads(requests[2].content) == {
        "answer": "No",
        "revision": 1,
        "userConfirmed": True,
    }
    assert requests[3].url.path == "/api/cover-letters/5/pdf"
    assert requests[3].headers["authorization"] == "Bearer rat_test"


@pytest.mark.parametrize("opt_answer", [None, False, True])
def test_sdk_keeps_structured_answers_and_nullable_booleans(opt_answer):
    profile = {
        "legalName": {"givenName": "Ada", "familyName": "Lovelace"},
        "mailingAddress": {"postalCode": "00123"},
        "workEligibility": [
            {"country": "US", "currentlyOnOpt": opt_answer, "confirmedOn": "2026-10-20"}
        ],
        "experienceRanges": [
            {
                "specialty": "Software",
                "minimumYears": 3,
                "maximumYears": 6,
                "confirmedOn": "2026-10-20",
            }
        ],
        "employerAnswers": [
            {
                "employer": "Acme",
                "question": "Worked here?",
                "answer": None,
                "confirmedOn": "2026-10-20",
            }
        ],
        "sex": "Female",
        "aiMatchingPreference": "opt_in",
    }
    with client(
        lambda _: httpx.Response(200, json={"profile": profile, "revision": "rev"})
    ) as sdk:
        assert sdk.get_application_profile()["profile"] == profile


def test_sdk_rejects_a_string_in_a_structured_boolean_answer():
    profile = {
        "workEligibility": [
            {"country": "US", "currentlyOnOpt": "false", "confirmedOn": "2026-10-20"}
        ]
    }
    with client(
        lambda _: httpx.Response(200, json={"profile": profile, "revision": "rev"})
    ) as sdk:
        with pytest.raises(ResponseValidationError):
            sdk.get_application_profile()


def test_cli_application_prompt_is_markdown(monkeypatch, capsys):
    payload = {
        "job": {
            "jobId": 42,
            "title": None,
            "company": None,
            "location": None,
            "url": None,
            "status": "approved",
            "jdText": "JD",
        },
        "prompt": "# Job application\n\nReady to use.\n",
        "profile": {},
        "profileRevision": "rev",
        "questions": [],
        "attachments": [],
        "submissionPolicy": "stop_before_submit",
    }
    monkeypatch.setattr(
        ResumeHarness,
        "from_env",
        lambda: client(lambda _: httpx.Response(200, json=payload)),
    )
    monkeypatch.setattr("sys.argv", ["resume-harness", "application-prompt", "42"])
    assert main() == 0
    assert capsys.readouterr().out == payload["prompt"]


@pytest.mark.parametrize(
    "command,expected_method,expected_path",
    [
        ("update-application-profile", "PATCH", "/api/application-profile"),
        ("record-application-question", "POST", "/api/application-questions"),
        ("answer-application-question", "PATCH", "/api/application-questions/7"),
    ],
)
def test_cli_application_writes_forward_exact_json_body(
    tmp_path, monkeypatch, capsys, command, expected_method, expected_path
):
    body = {
        "revision": 1,
        "answer": "User answer",
        "userConfirmed": True,
        "unknown": "API must validate",
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(body), encoding="utf-8-sig")

    def handle(request):
        assert request.method == expected_method and request.url.path == expected_path
        assert json.loads(request.content) == body
        return httpx.Response(
            422,
            json={"error": {"code": "VALIDATION_ERROR", "message": "Unknown field"}},
        )

    monkeypatch.setattr(ResumeHarness, "from_env", lambda: client(handle))
    args = ["resume-harness", command, "--input", str(path)]
    if command == "answer-application-question":
        args.append("7")
    monkeypatch.setattr("sys.argv", args)
    assert main() == 1
    assert "VALIDATION_ERROR" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args,method,path,body",
    [
        (["approve", "42"], "PATCH", "/api/jobs/42", {"status": "approved"}),
        (
            ["cover-letter", "42"],
            "POST",
            "/api/cover-letters",
            {"jobIds": [42], "approved": False},
        ),
        (["select-resume", "42", "81"], "POST", "/api/jobs/42/select-resume/81", None),
        (
            ["select-cover-letter", "42", "12"],
            "POST",
            "/api/jobs/42/select-cover-letter/12",
            None,
        ),
        (["application-events", "42"], "GET", "/api/jobs/42/events", None),
    ],
)
def test_cli_interactive_preparation_commands(
    monkeypatch, capsys, args, method, path, body
):
    def handle(request):
        assert request.method == method and request.url.path == path
        assert request.headers["authorization"] == "Bearer rat_test"
        assert (json.loads(request.content) if request.content else None) == body
        if args[0] == "application-events":
            payload = []
        elif args[0].startswith("select-"):
            payload = {
                "id": 1,
                "jobId": 42,
                "resumeVersionId": 81,
                "coverLetterId": 12,
                "status": "ready",
                "notes": None,
                "submittedAt": None,
                "updatedAt": "2026-10-29T18:05:00Z",
                "future": "preserved",
            }
        else:
            payload = {"runId": "test"}
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(ResumeHarness, "from_env", lambda: client(handle))
    monkeypatch.setattr("sys.argv", ["resume-harness", *args])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    if args[0].startswith("select-"):
        assert result["future"] == "preserved"


def test_cli_event_write_forwards_body_and_surfaces_api_error(
    tmp_path, monkeypatch, capsys
):
    body = {"kind": "application_submitted", "occurredAt": "without-offset"}
    path = tmp_path / "event.json"
    path.write_text(json.dumps(body), encoding="utf-8-sig")
    seen = []

    def handle(request):
        seen.append(request)
        assert request.method == "POST" and request.url.path == "/api/jobs/42/events"
        assert json.loads(request.content) == body
        return httpx.Response(
            422, json={"error": {"code": "VALIDATION_ERROR", "message": "Invalid time"}}
        )

    monkeypatch.setattr(ResumeHarness, "from_env", lambda: client(handle))
    monkeypatch.setattr(
        "sys.argv",
        ["resume-harness", "record-application-event", "42", "--input", str(path)],
    )
    assert main() == 1
    assert len(seen) == 1
    assert "VALIDATION_ERROR" in capsys.readouterr().err
