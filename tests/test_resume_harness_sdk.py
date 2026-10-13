import json

import httpx
import pytest

from resume_harness_sdk import APIError, ResumeHarness, RunFailed, RunTimeout
from resume_harness_sdk import client as module
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
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
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
    for name in ("resume-harness-sdk", "resume-harness-tailor"):
        assert (root / name / "SKILL.md").is_file()
    reference = root / "resume-harness-sdk" / "references" / "client.md"
    reference.write_text("user-edited", encoding="utf-8")
    assert main() == 1
    assert reference.read_text() == "user-edited"
    capsys.readouterr()
