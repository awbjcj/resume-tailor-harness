import pytest
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.models.profile import Contact, ProfileFacts, Skill
from resume_tailor_harness.profile.store import save_facts


@pytest.fixture()
def client(tmp_path):
    data_dir = tmp_path / "data"
    app = create_app(
        db_url="sqlite://",
        data_dir=data_dir,
        config_dir=tmp_path / "config",
        env_path=tmp_path / ".env",
    )
    with TestClient(app) as test_client:
        yield test_client, data_dir


def _seed_facts(data_dir):
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        skills={"Languages": [Skill(name="Python", aliases=["py"])]},
    )
    save_facts(facts, data_dir / "profile" / "facts.json")
    return facts


def test_list_skills_before_profile_build_is_empty(client):
    test_client, _ = client
    resp = test_client.get("/api/profile/skills")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_skills_returns_flat_rows(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    resp = test_client.get("/api/profile/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["name"] == "Python"
    assert body[0]["category"] is None


def test_add_skill_requires_a_built_profile(client):
    test_client, _ = client
    resp = test_client.post("/api/profile/skills", json={"name": "Rust"})
    assert resp.status_code == 400


def test_add_skill_creates_a_manual_entry(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    resp = test_client.post(
        "/api/profile/skills", json={"name": "Rust", "category": "hard"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "new_skill"
    assert body["name"] == "Rust"

    listed = test_client.get("/api/profile/skills").json()
    assert any(row["name"] == "Rust" for row in listed)


def test_add_skill_rejects_a_duplicate(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    resp = test_client.post("/api/profile/skills", json={"name": "python"})
    assert resp.status_code == 422


def test_add_skill_rejects_whitespace_only_name(client):
    test_client, data_dir = client
    _seed_facts(data_dir)

    resp = test_client.post("/api/profile/skills", json={"name": "   "})

    assert resp.status_code == 422


def test_add_alias_attaches_to_the_chosen_skill(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    skill_id = test_client.get("/api/profile/skills").json()[0]["id"]

    resp = test_client.post(
        f"/api/profile/skills/{skill_id}/aliases", json={"alias": "Python3"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "alias"
    assert body["aliasText"] == "Python3"
    assert body["targetSkillDisplay"] == "Python"


def test_add_alias_rejects_unknown_skill_id(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    resp = test_client.post("/api/profile/skills/nope/aliases", json={"alias": "x"})
    assert resp.status_code == 404


def test_add_alias_rejects_whitespace_only_text(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    skill_id = test_client.get("/api/profile/skills").json()[0]["id"]

    resp = test_client.post(
        f"/api/profile/skills/{skill_id}/aliases", json={"alias": "   "}
    )

    assert resp.status_code == 422


def _seed_kubernetes(data_dir):
    facts = ProfileFacts(
        contact=Contact(name="Ada"),
        skills={"hard": [Skill(name="Kubernetes", category="hard")]},
    )
    save_facts(facts, data_dir / "profile" / "facts.json")


def test_delete_skill_then_lists_suppressed(client):
    test_client, data_dir = client
    _seed_kubernetes(data_dir)

    resp = test_client.delete("/api/profile/skills/kubernetes")
    assert resp.status_code == 204

    listed = test_client.get("/api/profile/suppressed-skills").json()
    assert [row["token"] for row in listed] == ["kubernetes"]
    assert listed[0]["display"] == "Kubernetes"
    assert not any(
        row["name"] == "Kubernetes"
        for row in test_client.get("/api/profile/skills").json()
    )


def test_restore_suppressed_skill(client):
    test_client, data_dir = client
    _seed_kubernetes(data_dir)
    test_client.delete("/api/profile/skills/kubernetes")

    resp = test_client.post("/api/profile/suppressed-skills/kubernetes/restore")
    assert resp.status_code == 204
    assert test_client.get("/api/profile/suppressed-skills").json() == []


def test_delete_unknown_skill_404(client):
    test_client, data_dir = client
    _seed_kubernetes(data_dir)
    resp = test_client.delete("/api/profile/skills/nope")
    assert resp.status_code == 404


def test_delete_skill_before_build_400(client):
    test_client, _ = client
    resp = test_client.delete("/api/profile/skills/kubernetes")
    assert resp.status_code == 400


def test_skill_create_and_edit_are_atomic_and_readable(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    response = test_client.post(
        "/api/profile/skills",
        json={
            "name": "Rust",
            "aliases": ["rustlang"],
            "group": "languages",
            "category": "hard",
        },
    )
    assert response.status_code == 201
    response = test_client.put(
        "/api/profile/skills/rust",
        json={
            "name": "Rust programming",
            "aliases": ["rs"],
            "group": "systems-embedded",
            "category": "hard",
        },
    )
    assert response.status_code == 204
    listed = test_client.get("/api/profile/skills").json()
    skill = next(s for s in listed if s["name"] == "Rust programming")
    assert skill["aliases"] == ["rs", "Rust"]
    rows = test_client.get("/api/profile/matrix").json()["rows"]
    assert (
        next(r for r in rows if r["display"] == "Rust programming")["group"]
        == "systems-embedded"
    )
    response = test_client.post(
        "/api/profile/skills", json={"name": "Go", "group": "missing"}
    )
    assert response.status_code == 422
    assert not any(
        s["name"] == "Go" for s in test_client.get("/api/profile/skills").json()
    )


def test_merge_validation_and_delete_restore_immediately(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    test_client.post("/api/profile/skills", json={"name": "Python 3"})
    response = test_client.post(
        "/api/profile/skills/merge",
        json={"keys": ["python", "python 3"], "into": "python"},
    )
    assert response.status_code == 204
    skill = test_client.get("/api/profile/skills").json()[0]
    assert "Python 3" in skill["aliases"]
    test_client.delete("/api/profile/skills/python")
    assert test_client.get("/api/profile/skills").json() == []
    test_client.post("/api/profile/suppressed-skills/python/restore")
    assert test_client.get("/api/profile/skills").json()[0]["id"] == skill["id"]
    response = test_client.put("/api/profile/skills/nope", json={"name": "A"})
    assert response.status_code == 404


def test_cleanup_contract_preview_policy_and_restore(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    test_client.post("/api/profile/skills", json={"name": "Willingness to travel"})
    preview = test_client.get("/api/profile/skills/cleanup").json()
    assert preview["beforeCount"] == 2 and preview["afterCount"] == 1
    assert preview["pruned"][0]["reason"] == "Travel or relocation requirement"
    assert (
        test_client.patch(
            "/api/profile/skills/cleanup", json={"enabled": False}
        ).status_code
        == 204
    )
    assert test_client.get("/api/profile/skills/cleanup").json()["enabled"] is False
    assert test_client.post("/api/profile/skills/cleanup").status_code == 200
    assert len(test_client.get("/api/profile/skills").json()) == 1
    assert (
        test_client.post(
            "/api/profile/suppressed-skills/willingness%20to%20travel/restore"
        ).status_code
        == 204
    )
    assert len(test_client.get("/api/profile/skills").json()) == 2


def test_group_category_crud_surfaces_custom_catalog(client):
    test_client, data_dir = client
    _seed_facts(data_dir)
    assert (
        test_client.post(
            "/api/profile/skill-categories", json={"label": "My engineering"}
        ).status_code
        == 201
    )
    catalog = test_client.get("/api/profile/matrix").json()
    category = next(c for c in catalog["categories"] if c["label"] == "My engineering")
    assert category["customized"] is True
    assert (
        test_client.post(
            "/api/profile/skill-groups",
            json={"label": "My tools", "category": category["slug"]},
        ).status_code
        == 201
    )
    group = next(
        g
        for g in test_client.get("/api/profile/matrix").json()["groups"]
        if g["label"] == "My tools"
    )
    assert (
        test_client.put(
            "/api/profile/skills/python/group", json={"group": group["slug"]}
        ).status_code
        == 200
    )
    assert (
        test_client.put(
            f"/api/profile/skill-categories/{category['slug']}",
            json={"label": "Engineering"},
        ).status_code
        == 204
    )
    assert (
        test_client.put(
            f"/api/profile/skill-groups/{group['slug']}",
            json={"label": "Tools", "category": "technical"},
        ).status_code
        == 204
    )
    assert (
        test_client.delete(
            f"/api/profile/skill-categories/{category['slug']}"
        ).status_code
        == 204
    )
    assert (
        test_client.delete(f"/api/profile/skill-groups/{group['slug']}").status_code
        == 204
    )
    assert test_client.delete("/api/profile/skill-groups/other").status_code == 422
    assert test_client.get("/api/profile/skills").json()[0]["name"] == "Python"


def test_skill_rebuild_requires_profile_before_starting_model_work(client):
    test_client, _ = client
    assert (
        test_client.post(
            "/api/profile/skills/rebuild", json={"reclassifyOnly": True}
        ).status_code
        == 400
    )


def test_skill_reclassification_launches_tenant_scoped_singleton_run(
    client, monkeypatch
):
    import threading
    from resume_tailor_harness.api.routers import profile_skills as router

    test_client, data_dir = client
    _seed_facts(data_dir)
    started = threading.Event()
    release = threading.Event()
    calls = []

    def work(directory, _reporter, *, reclassify_only):
        calls.append((directory, reclassify_only))
        started.set()
        release.wait(timeout=3)
        return {"classified": 1}

    monkeypatch.setattr(
        router, "model_access_available", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(router, "rebuild_profile_skills", work)
    try:
        response = test_client.post(
            "/api/profile/skills/rebuild", json={"reclassifyOnly": True}
        )
        assert response.status_code == 202
        assert response.json()["kind"] == "profile-skills-rebuild"
        assert started.wait(timeout=1)
        assert calls == [(data_dir / "profile", True)]
        assert (
            test_client.post("/api/profile/skills/rebuild", json={}).status_code == 409
        )
    finally:
        release.set()
