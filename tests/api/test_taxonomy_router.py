import pytest
from fastapi.testclient import TestClient

import resume_tailor_harness.api.routers.match_gap as match_gap_router
import resume_tailor_harness.api.routers.taxonomy as taxonomy_router
import resume_tailor_harness.profile.effective as effective_module
from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.db import get_session
from resume_tailor_harness.taxonomy.clusters import ClusterMap, save_cluster_map
from resume_tailor_harness.tracking.repository import save_job
from resume_tailor_harness.tracking.tables import Job, JobStatus


@pytest.fixture()
def client(tmp_path, monkeypatch):
    corrections_path = tmp_path / "taxonomy_corrections.json"
    cluster_path = tmp_path / "cluster_map.json"
    facts_path = tmp_path / "facts.json"
    save_cluster_map(
        ClusterMap(
            aliases={
                "python": "python",
                "javascript": "javascript",
                "js": "javascript",
            },
            domain_of={"python": "scripting", "javascript": "web"},
            domain_label={"scripting": "Scripting", "web": "Web"},
            category_of={"scripting": "languages", "web": "frontend-web"},
        ),
        cluster_path,
    )
    monkeypatch.setattr(
        taxonomy_router,
        "_paths",
        lambda: (str(corrections_path), str(cluster_path)),
    )
    monkeypatch.setattr(match_gap_router, "_CLUSTER_PATH", str(cluster_path))
    monkeypatch.setattr(match_gap_router, "_FACTS_PATH", str(facts_path))
    monkeypatch.setattr(
        effective_module, "corrections_file_path", lambda: str(corrections_path)
    )
    monkeypatch.setattr(
        match_gap_router, "corrections_file_path", lambda: str(corrections_path)
    )
    app = create_app(db_url="sqlite://", data_dir=tmp_path / "data")
    with TestClient(app) as test_client:
        with get_session(app.state.engine) as session:
            save_job(
                session,
                Job(
                    source="manual",
                    status=JobStatus.shortlisted.value,
                    criteria_json={"must_have_skills": ["Python", "JavaScript", "JS"]},
                ),
            )
        yield test_client


def test_move_skill_to_new_domain_returns_updated_map(client):
    response = client.put(
        "/api/taxonomy/skills/python/domain",
        json={"newDomain": {"label": "Backend Languages", "category": "backend-apis"}},
    )
    assert response.status_code == 200
    payload = response.json()
    assert (
        next(s for s in payload["skills"] if s["key"] == "python")["domainId"]
        == "backend-languages"
    )


def test_move_unknown_domain_is_404_envelope(client):
    response = client.put(
        "/api/taxonomy/skills/python/domain", json={"domainId": "ghost"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UNKNOWN_DOMAIN"


def test_bad_category_is_400_envelope(client):
    response = client.put(
        "/api/taxonomy/skills/python/domain",
        json={"newDomain": {"label": "X", "category": "bad"}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_CATEGORY"


def test_remove_then_readd_skill(client):
    assert client.delete("/api/taxonomy/skills/python").status_code == 200
    assert all(
        s["key"] != "python" for s in client.get("/api/match-gap").json()["skills"]
    )
    response = client.post(
        "/api/taxonomy/skills",
        json={"token": "python", "domainId": "scripting"},
    )
    assert response.status_code == 200
    assert any(s["key"] == "python" for s in response.json()["skills"])


def test_discard_alias_hides_demand_and_edges_and_is_restorable(client):
    before = client.get("/api/match-gap").json()
    response = client.post("/api/taxonomy/discard-skills", json={"skillKeys": ["JS", "JavaScript"]})
    assert response.status_code == 200
    body = response.json()
    assert [skill["key"] for skill in body["skills"]] == ["python"]
    assert {edge["skillKey"] for edge in body["edges"]} == {"python"}
    assert [entry["key"] for entry in body["retiredSkills"]] == ["javascript"]
    assert body["taxonomyRevision"] != before["taxonomyRevision"]
    repeat = client.post("/api/taxonomy/discard-skills", json={"skillKeys": ["js"]}).json()
    assert repeat["retiredSkills"] == body["retiredSkills"]
    assert client.get("/api/match-gap").json()["skills"] == body["skills"]
    assert client.post("/api/match-gap/restore-skills", json={"skillKeys": ["javascript"]}).status_code == 200
    restored = client.get("/api/match-gap").json()
    assert restored["skills"] == before["skills"]
    assert restored["edges"] == before["edges"]
    assert restored["retiredSkills"] == []


def test_discard_unknown_batch_is_atomic_and_bounds_are_enforced(client):
    response = client.post("/api/taxonomy/discard-skills", json={"skillKeys": ["python", "unknown"]})
    assert response.status_code == 404
    assert client.get("/api/match-gap").json()["retiredSkills"] == []
    for values in [[], [" "], ["python"] * 501]:
        assert client.post("/api/taxonomy/discard-skills", json={"skillKeys": values}).status_code == 422


def test_cleanup_reviews_previously_assigned_requirements_and_preserves_source(client):
    from resume_tailor_harness.taxonomy.clusters import load_cluster_map

    _, path = taxonomy_router._paths()
    cmap = load_cluster_map(path)
    cmap.domain_of["8+ years of machine learning experience"] = "scripting"
    save_cluster_map(cmap, path)
    with get_session(client.app.state.engine) as session:
        save_job(session, Job(
            source="manual", status=JobStatus.shortlisted.value,
            jd_text="Bachelor's degree and 8+ years of machine learning experience. Python required.",
            criteria_json={"must_have_skills": ["Bachelor's degree in computer engineering", "8+ years of machine learning experience", "Python"]},
        ))
    preview = client.get("/api/match-gap").json()["cleanupCandidates"]
    assert {item["reason"] for item in preview} == {"Education or degree requirement", "Years-of-experience requirement"}
    result = client.post("/api/taxonomy/discard-skills", json={"skillKeys": [item["key"] for item in preview]})
    assert result.status_code == 200
    assert result.json()["cleanupCandidates"] == []
    assert {skill["key"] for skill in result.json()["skills"]} == {"javascript", "python"}
    with get_session(client.app.state.engine) as session:
        from sqlmodel import select
        job = session.exec(select(Job).where(Job.jd_text != "")).first()
        assert job is not None and "Bachelor's degree" in job.jd_text
        assert job.criteria_json is not None
        assert len(job.criteria_json["must_have_skills"]) == 3


def test_discard_refuses_corrupt_state_without_overwriting_it(client):
    from pathlib import Path
    from resume_tailor_harness.taxonomy.state import taxonomy_state_path

    _, path = taxonomy_router._paths()
    state_path = taxonomy_state_path(Path(path))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{broken", encoding="utf-8")
    response = client.post("/api/taxonomy/discard-skills", json={"skillKeys": ["python"]})
    assert response.status_code == 400
    assert state_path.read_text(encoding="utf-8") == "{broken"


def test_compound_domain_patch_and_merge(client):
    patched = client.patch(
        "/api/taxonomy/domains/web",
        json={"label": "Frontend", "category": "tools-platforms"},
    )
    assert patched.status_code == 200
    domain = next(item for item in patched.json()["domains"] if item["id"] == "web")
    assert (domain["label"], domain["category"]) == ("Frontend", "tools-platforms")

    merged = client.post("/api/taxonomy/domains/web/merge", json={"into": "scripting"})
    assert merged.status_code == 200
    assert all(item["id"] != "web" for item in merged.json()["domains"])


def test_alias_unknown_skill_and_cycle_use_stable_envelopes(client):
    unknown = client.post(
        "/api/taxonomy/aliases", json={"token": "ghost", "canonical": "python"}
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "UNKNOWN_SKILL"

    assert (
        client.post(
            "/api/taxonomy/aliases", json={"token": "js", "canonical": "javascript"}
        ).status_code
        == 200
    )
    cycle = client.post(
        "/api/taxonomy/aliases", json={"token": "javascript", "canonical": "js"}
    )
    assert cycle.status_code == 400
    assert cycle.json()["error"]["code"] == "ALIAS_CYCLE"


def test_empty_token_is_400_invalid_skill_token(client):
    response = client.post(
        "/api/taxonomy/aliases", json={"token": "   ", "canonical": "python"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SKILL_TOKEN"
