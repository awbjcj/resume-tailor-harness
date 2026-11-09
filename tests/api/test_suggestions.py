import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

import resume_tailor_harness.api.routers.suggestions as router_module
import resume_tailor_harness.profile.effective as effective_module
import resume_tailor_harness.services.suggestion_runs as run_module
from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.db import get_session
from resume_tailor_harness.github.repos import RepoMeta
from resume_tailor_harness.suggestions.agents import RepoRef, SuggestionDraft
from resume_tailor_harness.taxonomy.clusters import ClusterMap, save_cluster_map
from resume_tailor_harness.taxonomy.corrections import (
    TaxonomyCorrections,
    save_taxonomy_corrections,
)
from resume_tailor_harness.tracking.repository import save_job
from resume_tailor_harness.tracking.tables import Job, JobStatus


class _Result:
    def __init__(self, content):
        self.content = content


class _Agent:
    def __init__(self, content):
        self.content = content

    def run(self, _prompt):
        return _Result(self.content)


def _seed_job(engine, *, company="C", skills=None):
    with get_session(engine) as session:
        save_job(
            session,
            Job(
                source="manual",
                company=company,
                title="Platform Engineer",
                status=JobStatus.shortlisted.value,
                criteria_json={
                    "must_have_skills": skills or ["Kubernetes", "Terraform"]
                },
            ),
        )


def _configure(monkeypatch, tmp_path):
    cluster_path = tmp_path / "cluster_map.json"
    save_cluster_map(
        ClusterMap(
            aliases={"kubernetes": "kubernetes", "terraform": "terraform"},
            domain_of={"kubernetes": "infra", "terraform": "infra"},
            domain_label={"infra": "Cloud / Infrastructure"},
        ),
        cluster_path,
    )
    monkeypatch.setattr(router_module, "_CLUSTER_PATH", str(cluster_path))
    monkeypatch.setattr(
        router_module, "_FACTS_PATH", str(tmp_path / "missing-facts.json")
    )


def test_suggestion_graph_uses_effective_taxonomy_corrections(tmp_path, monkeypatch):
    cluster_path = tmp_path / "cluster_map.json"
    corrections_path = tmp_path / "taxonomy" / "taxonomy_corrections.json"
    save_cluster_map(
        ClusterMap(domain_of={"javascript": "web"}),
        cluster_path,
    )
    save_taxonomy_corrections(
        TaxonomyCorrections(aliases={"js": "javascript"}), corrections_path
    )
    monkeypatch.setattr(
        effective_module, "corrections_file_path", lambda: str(corrections_path)
    )
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app):
        _seed_job(app.state.engine, skills=["JS"])
        with get_session(app.state.engine) as session:
            _facts, graph = run_module.load_suggestion_graph(
                session,
                facts_path=str(tmp_path / "missing-facts.json"),
                cluster_path=str(cluster_path),
            )

    assert [node.key for node in graph.skills] == ["javascript"]


def _wait_for_run(client, run_id):
    for _ in range(50):
        record = client.get(f"/api/runs/{run_id}").json()
        if record["state"] in ("done", "error"):
            return record
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not finish in time")


def test_get_returns_empty_envelope_for_valid_uncached_target(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        response = client.get(
            "/api/suggestions",
            params={"kind": "skill", "key": "Kubernetes"},
        )

    assert response.status_code == 200
    assert response.json() == {"suggestion": None, "stale": False}


def test_unknown_targets_use_standard_not_found_envelope(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        get_response = client.get(
            "/api/suggestions",
            params={"kind": "skill", "key": "Unknown"},
        )
        post_response = client.post(
            "/api/suggestions/generate",
            json={"kind": "domain", "key": "unknown"},
        )

    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "NOT_FOUND"
    assert post_response.status_code == 404
    assert post_response.json()["error"]["code"] == "NOT_FOUND"


def test_generate_rejects_browser_supplied_context(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        response = client.post(
            "/api/suggestions/generate",
            json={
                "kind": "skill",
                "key": "Kubernetes",
                "members": ["Browser controlled"],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_skill_then_get_cached_suggestion(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    draft = SuggestionDraft(
        repos=[
            RepoRef(name="foo/bar", url="https://github.com/foo/bar", why="Reference")
        ],
        bridge="Bridge",
    )
    monkeypatch.setattr(
        run_module,
        "build_search_agent",
        lambda: _Agent("Research: https://github.com/foo/bar"),
    )
    monkeypatch.setattr(run_module, "build_formatter_agent", lambda: _Agent(draft))
    monkeypatch.setattr(
        run_module,
        "verify_repo",
        lambda owner, name, token="": RepoMeta(
            "foo/bar", "https://github.com/foo/bar", 5, "Repository"
        ),
    )

    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        launched = client.post(
            "/api/suggestions/generate",
            json={"kind": "skill", "key": "Kubernetes"},
        )
        assert launched.status_code == 202
        record = _wait_for_run(client, launched.json()["runId"])
        cached = client.get(
            "/api/suggestions",
            params={"kind": "skill", "key": "Kubernetes"},
        )

    assert record["state"] == "done"
    assert cached.json()["suggestion"]["repos"][0]["stars"] == 5
    assert cached.json()["stale"] is False


def test_theme_cache_becomes_stale_when_demanding_jobs_change(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(run_module, "build_search_agent", lambda: _Agent("Research"))
    monkeypatch.setattr(
        run_module,
        "build_formatter_agent",
        lambda: _Agent(SuggestionDraft(bridge="Theme bridge")),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        app = create_app(db_url="sqlite://", runs_root=tmp_path, run_executor=executor)
        with TestClient(app) as client:
            _seed_job(app.state.engine)
            launched = client.post(
                "/api/suggestions/generate",
                json={"kind": "domain", "key": "infra"},
            )
            assert launched.status_code == 202, launched.json()
            assert _wait_for_run(client, launched.json()["runId"])["state"] == "done"
            # Terminal status precedes completion-ledger bookkeeping. Drain
            # that worker before another fixture write: shared-cache SQLite
            # rejects simultaneous writers immediately with SQLITE_LOCKED.
            executor.submit(lambda: None).result(timeout=5)

            _seed_job(app.state.engine, company="D", skills=["Terraform"])
            cached = client.get(
                "/api/suggestions",
                params={"kind": "domain", "key": "infra"},
            )

    assert cached.json()["suggestion"]["key"] == "infra"
    assert cached.json()["stale"] is True


def test_suggestion_runs_dedupe_and_report_not_found_per_target(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(run_module, "build_search_agent", lambda: _Agent("Research"))
    monkeypatch.setattr(
        run_module,
        "build_formatter_agent",
        lambda: _Agent(SuggestionDraft(bridge="Bridge")),
    )
    monkeypatch.setattr(run_module, "verify_repo", lambda *_args, **_kwargs: None)
    app = create_app(db_url="sqlite://", runs_root=tmp_path)

    with TestClient(app) as client:
        _seed_job(app.state.engine)
        response = client.post(
            "/api/suggestion-runs",
            json={
                "targets": [
                    {"kind": "skill", "key": "kubernetes"},
                    {"kind": "skill", "key": "kubernetes"},
                    {"kind": "skill", "key": "terraform"},
                    {"kind": "domain", "key": "missing"},
                ]
            },
        )

        assert response.status_code == 202
        results = response.json()["results"]
        assert [(item["outcome"], item["key"]) for item in results] == [
            ("accepted", "kubernetes"),
            ("accepted", "terraform"),
            ("not_found", "missing"),
        ]
        for item in results[:2]:
            record = _wait_for_run(client, item["runId"])
            assert record["state"] == "done", record


def test_learning_library_keeps_orphaned_advice_and_progress(tmp_path, monkeypatch):
    from resume_tailor_harness.tracking.tables import SkillSuggestion

    _configure(monkeypatch, tmp_path)
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        with get_session(app.state.engine) as session:
            row = SkillSuggestion(
                kind="domain",
                key="infra",
                payload_json={
                    "repos": [],
                    "resources": [],
                    "bridge": "Learn infrastructure",
                    "citations": [],
                    "project": None,
                },
            )
            orphan = SkillSuggestion(
                kind="skill",
                key="retired-skill",
                payload_json={
                    "repos": [],
                    "resources": [],
                    "bridge": "Keep this plan",
                    "citations": [],
                    "project": None,
                },
            )
            session.add(row)
            session.add(orphan)
            session.commit()
            session.refresh(row)
            row_id = row.id
        response = client.get("/api/learning-roadmaps")
        assert response.status_code == 200
        plans = {item["label"]: item for item in response.json()}
        assert plans["Cloud / Infrastructure"]["available"] is True
        assert plans["retired-skill"]["available"] is False
        assert (
            plans["retired-skill"]["envelope"]["suggestion"]["bridge"]
            == "Keep this plan"
        )
        for status in ["in_progress", "completed", "archived", "planned"]:
            assert (
                client.patch(
                    f"/api/learning-roadmaps/{row_id}", json={"status": status}
                ).status_code
                == 204
            )
            saved = next(
                item
                for item in client.get("/api/learning-roadmaps").json()
                if item["id"] == row_id
            )
            assert saved["status"] == status
        assert (
            client.patch(
                f"/api/learning-roadmaps/{row_id}", json={"status": "unknown"}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                "/api/learning-roadmaps/99999", json={"status": "planned"}
            ).status_code
            == 404
        )
        # Replacing generated content does not reset user-owned learning state.
        client.patch(f"/api/learning-roadmaps/{row_id}", json={"status": "completed"})
        with get_session(app.state.engine) as session:
            saved_row = session.get(SkillSuggestion, row_id)
            assert saved_row is not None
            saved_row.payload_json = {
                **saved_row.payload_json,
                "bridge": "Updated advice",
            }
            session.add(saved_row)
            session.commit()
        saved = next(
            item
            for item in client.get("/api/learning-roadmaps").json()
            if item["id"] == row_id
        )
        assert saved["status"] == "completed"
        assert saved["envelope"]["suggestion"]["bridge"] == "Updated advice"


def test_roadmap_generation_returns_quota_error_envelope(monkeypatch, tmp_path):
    from resume_tailor_harness.api.runs.manager import RunManager, RunQuotaError

    _configure(monkeypatch, tmp_path)
    app = create_app(db_url="sqlite://", runs_root=tmp_path)

    def reject(*args, **kwargs):
        raise RunQuotaError("Concurrent run limit reached")

    monkeypatch.setattr(RunManager, "submit", reject)
    with TestClient(app, raise_server_exceptions=False) as client:
        _seed_job(app.state.engine)
        response = client.post(
            "/api/suggestions/generate",
            json={"kind": "domain", "key": "infra"},
        )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_roadmap_generation_rejects_a_superseded_selection_before_research(
    monkeypatch, tmp_path
):
    from resume_tailor_harness.tracking.tables import SkillSuggestion

    _configure(monkeypatch, tmp_path)
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        with get_session(app.state.engine) as session:
            legacy = SkillSuggestion(kind="skill", key="K8s")
            canonical = SkillSuggestion(kind="skill", key="kubernetes")
            session.add_all([legacy, canonical])
            session.commit()
            legacy_id = legacy.id
        response = client.post(
            "/api/suggestions/generate",
            json={"kind": "skill", "key": "kubernetes", "expectedRoadmapId": legacy_id},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ROADMAP_CHANGED"


def test_roadmap_generation_reuses_legacy_row_and_keeps_its_progress(
    monkeypatch, tmp_path
):
    from resume_tailor_harness.tracking.tables import (
        LearningRoadmapProgress,
        SkillSuggestion,
    )

    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(run_module, "build_search_agent", lambda: _Agent("Research"))
    monkeypatch.setattr(
        run_module,
        "build_formatter_agent",
        lambda: _Agent(SuggestionDraft(bridge="New advice")),
    )
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        with get_session(app.state.engine) as session:
            row = SkillSuggestion(kind="skill", key="Kubernetes")
            session.add(row)
            session.commit()
            assert row.id is not None
            row_id = row.id
            session.add(
                LearningRoadmapProgress(suggestion_id=row_id, status="completed")
            )
            session.commit()

        response = client.post(
            "/api/suggestions/generate",
            json={"kind": "skill", "key": "kubernetes", "expectedRoadmapId": row_id},
        )
        assert response.status_code == 202, response.json()
        assert _wait_for_run(client, response.json()["runId"])["state"] == "done"
        with get_session(app.state.engine) as session:
            saved = session.get(SkillSuggestion, row_id)
            progress = session.get(LearningRoadmapProgress, row_id)
            assert saved is not None and saved.key == "kubernetes"
            assert saved.payload_json["bridge"] == "New advice"
            assert progress is not None and progress.status == "completed"


def test_concurrent_first_progress_updates_both_succeed(tmp_path, monkeypatch):
    from threading import Barrier

    from sqlmodel import Session, select

    from resume_tailor_harness.db import init_db, make_engine
    from resume_tailor_harness.services.learning_roadmaps import update_roadmap
    from resume_tailor_harness.tracking.tables import (
        LearningRoadmapProgress,
        SkillSuggestion,
    )

    engine = make_engine(f"sqlite:///{tmp_path / 'progress.db'}")
    init_db(engine)
    with Session(engine) as session:
        row = SkillSuggestion(kind="skill", key="python")
        session.add(row)
        session.commit()
        row_id = row.id
    assert row_id is not None
    original_get = Session.get

    def slow_get(self, entity, ident, **kwargs):
        result = original_get(self, entity, ident, **kwargs)
        if entity is LearningRoadmapProgress and result is None:
            # Widen the first-save race: both requests used to observe no row.
            time.sleep(0.1)
        return result

    monkeypatch.setattr(Session, "get", slow_get)
    start = Barrier(2)

    def save():
        with Session(engine) as session:
            start.wait(timeout=5)
            return update_roadmap(session, row_id, "in_progress")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [executor.submit(save) for _ in range(2)]
        assert all(result.result(timeout=5) for result in results)
    with Session(engine) as session:
        rows = session.exec(select(LearningRoadmapProgress)).all()
        assert len(rows) == 1
        assert rows[0].status == "in_progress"
    engine.dispose()


def test_duplicate_roadmap_generation_joins_active_run(monkeypatch, tmp_path):
    from threading import Event

    _configure(monkeypatch, tmp_path)
    release = Event()

    class SlowAgent(_Agent):
        def run(self, prompt):
            assert release.wait(timeout=5)
            return super().run(prompt)

    monkeypatch.setattr(run_module, "build_search_agent", lambda: SlowAgent("Research"))
    monkeypatch.setattr(
        run_module,
        "build_formatter_agent",
        lambda: _Agent(SuggestionDraft(bridge="Bridge")),
    )
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        try:
            first = client.post(
                "/api/suggestions/generate", json={"kind": "domain", "key": "infra"}
            )
            second = client.post(
                "/api/suggestions/generate", json={"kind": "domain", "key": "infra"}
            )
            assert first.status_code == second.status_code == 202
            assert first.json()["runId"] == second.json()["runId"]
        finally:
            release.set()
        assert _wait_for_run(client, first.json()["runId"])["state"] == "done"


def test_roadmap_generation_does_not_join_an_unchecked_run(monkeypatch, tmp_path):
    from threading import Event

    from resume_tailor_harness.tracking.tables import SkillSuggestion

    _configure(monkeypatch, tmp_path)
    release = Event()

    class SlowAgent(_Agent):
        def run(self, prompt):
            assert release.wait(timeout=5)
            return super().run(prompt)

    monkeypatch.setattr(run_module, "build_search_agent", lambda: SlowAgent("Research"))
    monkeypatch.setattr(
        run_module,
        "build_formatter_agent",
        lambda: _Agent(SuggestionDraft(bridge="Bridge")),
    )
    app = create_app(db_url="sqlite://", runs_root=tmp_path)
    with TestClient(app) as client:
        _seed_job(app.state.engine)
        with get_session(app.state.engine) as session:
            row = SkillSuggestion(kind="domain", key="infra")
            session.add(row)
            session.commit()
            row_id = row.id
        try:
            first = client.post(
                "/api/suggestions/generate", json={"kind": "domain", "key": "infra"}
            )
            second = client.post(
                "/api/suggestions/generate",
                json={"kind": "domain", "key": "infra", "expectedRoadmapId": row_id},
            )
            assert first.status_code == 202
            assert second.status_code == 409
            assert second.json()["error"]["code"] == "CONFLICT"
        finally:
            release.set()
        assert _wait_for_run(client, first.json()["runId"])["state"] == "done"
