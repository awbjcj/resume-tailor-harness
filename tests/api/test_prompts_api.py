"""Prompt transparency exposes immutable rules and edits guidance only."""

import pytest
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(db_url="sqlite://", config_dir=tmp_path / "config")
    with TestClient(app) as test_client:
        yield test_client


def test_get_lists_complete_prompt_contract(client) -> None:
    response = client.get("/api/agents/prompts")
    assert response.status_code == 200
    by_key = {item["key"]: item for item in response.json()}
    assert "tailor-writer" in by_key
    assert "reviewer-merged-advisory" in by_key
    assert "email-classifier" in by_key
    assert by_key["tailor-writer"]["guidance"] is None
    assert by_key["reviewer-fact-check"]["editable"] is True
    assert by_key["tailor-writer"]["instructions"]


def test_put_round_trips_and_clears_guidance(client, subtests):
    for key in ["coach", "reviewer-fact-check"]:
        with subtests.test(key=key):
            original = next(
                item
                for item in client.get("/api/agents/prompts").json()
                if item["key"] == key
            )
            response = client.put(
                f"/api/agents/prompts/{key}",
                json={"guidance": "Check cited evidence first."},
            )
            assert response.status_code == 200
            assert response.json()["guidance"] == "Check cited evidence first."
            assert response.json()["instructions"] == original["instructions"]
            listed = client.get("/api/agents/prompts").json()
            assert next(item for item in listed if item["key"] == key)["guidance"] == (
                "Check cited evidence first."
            )
            cleared = client.put(f"/api/agents/prompts/{key}", json={"guidance": ""})
            assert cleared.status_code == 200
            assert cleared.json()["guidance"] is None
            assert cleared.json()["instructions"] == original["instructions"]


def test_put_error_contracts(client) -> None:
    unknown = client.put("/api/agents/prompts/nope", json={"guidance": "x"})
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "unknown_agent"

    over_cap = client.put("/api/agents/prompts/coach", json={"guidance": "x" * 4001})
    assert over_cap.status_code == 422
    assert over_cap.json()["error"]["code"] == "VALIDATION_ERROR"
