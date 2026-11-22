"""Profile build launches as a run; preconditions fail fast with 400."""

import io

import pytest
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app


@pytest.fixture()
def client(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "ANTHROPIC_API_KEY=sk-ant-test-abcd1234\nMID_MODEL=anthropic:claude-sonnet-4-6\n",
        encoding="utf-8",
    )
    app = create_app(
        db_url="sqlite://",
        config_dir=tmp_path / "config",
        env_path=env,
        data_dir=tmp_path / "data",
    )
    with TestClient(app) as c:
        yield c


def test_build_without_resume_is_400(client):
    resp = client.post("/api/profile/build")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SETUP_INCOMPLETE"


def test_build_with_only_project_sources_requires_a_resume(client):
    created = client.post(
        "/api/profile/sources",
        files={
            "file": (
                "dossier.md",
                b"---\nrepo_url: https://github.com/me/project\n---\n# Project",
                "text/markdown",
            )
        },
    )
    assert created.status_code == 201
    response = client.post("/api/profile/build")
    assert response.status_code == 400
    assert "primary resume" in response.json()["error"]["message"]


def test_build_does_not_reimport_a_deleted_legacy_resume(client):
    client.post(
        "/api/profile/documents",
        files={"file": ("resume.txt", b"old wizard resume", "text/plain")},
        data={"docType": "resume"},
    )
    created = client.post(
        "/api/profile/sources",
        files={"file": ("resume.txt", b"corpus resume", "text/plain")},
    )
    assert created.status_code == 201
    assert (
        client.delete(f"/api/profile/sources/{created.json()['id']}").status_code == 204
    )
    response = client.post("/api/profile/build")
    assert response.status_code == 400
    assert client.get("/api/profile/sources").json() == []


@pytest.mark.parametrize("retain_project", [False, True])
def test_new_wizard_resume_registers_in_existing_manifest(client, monkeypatch, retain_project):
    old = client.post(
        "/api/profile/sources",
        files={"file": ("old.txt", b"old source resume", "text/plain")},
    )
    assert old.status_code == 201
    if retain_project:
        assert client.post(
            "/api/profile/sources",
            files={"file": ("dossier.md", b"---\nrepo_url: https://github.com/me/project\n---\n# Project", "text/markdown")},
        ).status_code == 201
    assert client.delete(f"/api/profile/sources/{old.json()['id']}").status_code == 204
    uploaded = client.post(
        "/api/profile/documents",
        files={"file": ("new.txt", b"new wizard resume", "text/plain")},
        data={"docType": "resume"},
    )
    assert uploaded.status_code == 201
    sources = client.get("/api/profile/sources").json()
    assert any(row["filename"] == "new.txt" and row["primary"] for row in sources)
    assert client.get("/api/setup/status").json()["profile"]["hasResume"] is True
    from resume_tailor_harness.services import profile_build

    monkeypatch.setattr(profile_build, "run_corpus_build", lambda *args, **kwargs: {})
    assert client.post("/api/profile/build").status_code == 202


def test_build_without_key_is_400(tmp_path):
    app = create_app(
        db_url="sqlite://",
        config_dir=tmp_path / "config",
        env_path=tmp_path / ".env",
        data_dir=tmp_path / "data",
    )
    with TestClient(app) as client:
        client.post(
            "/api/profile/documents",
            files={"file": ("resume.txt", io.BytesIO(b"experience"), "text/plain")},
            data={"docType": "resume"},
        )
        resp = client.post("/api/profile/build")
        assert resp.status_code == 400


def test_build_with_non_anthropic_key_launches_run(tmp_path, monkeypatch):
    """profile build uses Settings.mid_model, which may be a non-Anthropic
    provider (see llm_runner.split_provider) — any configured LLM key, not
    specifically ANTHROPIC_API_KEY, must satisfy the precondition."""
    env = tmp_path / ".env"
    env.write_text(
        "OPENAI_API_KEY=sk-oai-test-abcd1234\nMID_MODEL=openai:gpt-4.1\n",
        encoding="utf-8",
    )
    app = create_app(
        db_url="sqlite://",
        config_dir=tmp_path / "config",
        env_path=env,
        data_dir=tmp_path / "data",
    )
    with TestClient(app) as client:
        client.post(
            "/api/profile/documents",
            files={"file": ("resume.txt", io.BytesIO(b"experience"), "text/plain")},
            data={"docType": "resume"},
        )
        from resume_tailor_harness.services import profile_build

        monkeypatch.setattr(
            profile_build,
            "run_corpus_build",
            lambda reporter, **kwargs: {
                "experiences": 1,
                "projects": 0,
                "warnings": [],
            },
        )
        resp = client.post("/api/profile/build")
        assert resp.status_code == 202


def test_build_launches_run(client, monkeypatch):
    client.post(
        "/api/profile/documents",
        files={"file": ("resume.txt", io.BytesIO(b"experience"), "text/plain")},
        data={"docType": "resume"},
    )

    from resume_tailor_harness.services import profile_build

    def fake_run(reporter, **kwargs):
        return {"experiences": 2, "projects": 1, "warnings": []}

    monkeypatch.setattr(profile_build, "run_corpus_build", fake_run)
    resp = client.post("/api/profile/build")
    assert resp.status_code == 202
    body = resp.json()
    assert body["kind"] == "profile-build"
    assert body["runId"]


def test_build_does_not_join_a_run_with_unknown_source_coverage(client, monkeypatch):
    import threading
    from resume_tailor_harness.services import profile_build

    client.post(
        "/api/profile/sources", files={"file": ("resume.txt", b"resume", "text/plain")}
    )
    started = threading.Event()
    release = threading.Event()

    def build(_reporter, **_kwargs):
        started.set()
        assert release.wait(3)
        return {}

    monkeypatch.setattr(profile_build, "run_corpus_build", build)
    try:
        first = client.post("/api/profile/build")
        assert first.status_code == 202
        assert started.wait(2)
        client.post(
            "/api/profile/sources/note", json={"title": "Late", "text": "New evidence"}
        )
        second = client.post("/api/profile/build")
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "PROFILE_BUILD_BUSY"
        assert second.json()["error"]["details"]["runId"] == first.json()["runId"]
    finally:
        release.set()


def test_profile_build_uses_saved_repository_branch_choices(client, monkeypatch):
    import threading
    from resume_tailor_harness.services import profile_build

    client.post(
        "/api/profile/sources", files={"file": ("resume.txt", b"resume", "text/plain")}
    )
    client.put(
        "/api/config/profile",
        json={
            "githubUsername": "ada",
            "githubRepoBranches": {"ada/engine": "feature/dossier"},
        },
    )
    seen = {}
    finished = threading.Event()

    def build(reporter, **kwargs):
        seen.update(kwargs)
        finished.set()
        return {"experiences": 1, "projects": 1, "warnings": []}

    monkeypatch.setattr(profile_build, "run_corpus_build", build)
    assert client.post("/api/profile/build").status_code == 202
    assert finished.wait(2)
    assert seen["github_branches"] == {"ada/engine": "feature/dossier"}


def test_build_registers_wizard_resume_as_primary_source(client, monkeypatch):
    client.post(
        "/api/profile/documents",
        files={"file": ("resume.txt", io.BytesIO(b"experience"), "text/plain")},
        data={"docType": "resume"},
    )
    from resume_tailor_harness.services import profile_build

    monkeypatch.setattr(
        profile_build,
        "run_corpus_build",
        lambda reporter, **kwargs: {"experiences": 0, "projects": 0, "warnings": []},
    )
    assert client.post("/api/profile/build").status_code == 202

    sources = client.get("/api/profile/sources").json()
    assert len(sources) == 1
    assert sources[0]["primary"] is True and sources[0]["mode"] == "literal"


def test_build_with_registered_sources_skips_document_store(client, monkeypatch):
    """A corpus source satisfies the precondition without any wizard document."""
    import io as _io

    client.post(
        "/api/profile/sources",
        files={"file": ("resume.txt", _io.BytesIO(b"experience"), "text/plain")},
    )
    from resume_tailor_harness.services import profile_build

    monkeypatch.setattr(
        profile_build,
        "run_corpus_build",
        lambda reporter, **kwargs: {"experiences": 0, "projects": 0, "warnings": []},
    )
    assert client.post("/api/profile/build").status_code == 202
