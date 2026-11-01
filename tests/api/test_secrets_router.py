"""Secrets are write-only: GET exposes status+hint, never values."""

import pytest
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app


@pytest.fixture()
def env_file(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "ANTHROPIC_API_KEY=sk-ant-test-abcd1234\nUNMANAGED=keepme\nSOME_FLAG=\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def client(tmp_path, env_file):
    app = create_app(
        db_url="sqlite://", config_dir=tmp_path / "config", env_path=env_file
    )
    with TestClient(app) as c:
        yield c


def test_secrets_redact_write_refresh_and_clear_without_losing_other_keys(
    client, env_file
):
    body = client.get("/api/secrets").json()
    by_key = {row["key"]: row for row in body}
    assert by_key["anthropicApiKey"]["isSet"] is True
    assert by_key["anthropicApiKey"]["hint"] == "1234"
    assert by_key["openaiApiKey"]["isSet"] is False
    assert by_key["openaiApiKey"]["hint"] is None
    dumped = str(body)
    assert "sk-ant-test-abcd1234" not in dumped

    resp = client.put("/api/secrets", json={"openaiApiKey": "sk-oai-xyz98765"})
    assert resp.status_code == 200
    text = env_file.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-oai-xyz98765" in text
    assert "ANTHROPIC_API_KEY=sk-ant-test-abcd1234" in text  # untouched
    assert "UNMANAGED=keepme" in text  # unmanaged keys survive
    assert "SOME_FLAG=" in text

    client.put("/api/secrets", json={"anthropicApiKey": "sk-ant-new-key-5678"})
    from resume_tailor_harness.api.deps import get_settings_dep

    app = client.app
    assert (
        app.dependency_overrides[get_settings_dep]().anthropic_api_key
        == "sk-ant-new-key-5678"
    )

    client.put("/api/secrets", json={"anthropicApiKey": None})
    body = client.get("/api/secrets").json()
    by_key = {row["key"]: row for row in body}
    assert by_key["anthropicApiKey"]["isSet"] is False


def test_models_defaults_round_trip_and_partial_update_preserve_other_fields(client):
    body = client.get("/api/config/models").json()
    assert "cheapModel" in body and body["cheapModel"]  # defaults visible
    assert body["midModel"] == "openai:gpt-6.1-terra"
    put = client.put(
        "/api/config/models",
        json={
            "cheapModel": "claude-haiku-4-5-20251001",
            "midModel": "claude-sonnet-5",
            "premiumModel": "claude-opus-4-8",
            "midReasoningEffort": "low",
        },
    )
    assert put.status_code == 200
    assert client.get("/api/config/models").json()["midModel"] == "claude-sonnet-5"
    assert client.get("/api/config/models").json()["midReasoningEffort"] == "low"

    put = client.put(
        "/api/config/models",
        json={
            "cheapModel": "custom-cheap-non-default",
            "midModel": "openai:gpt-4.1",
            "premiumModel": "custom-premium-non-default",
            "midReasoningEffort": None,
        },
    )
    assert put.status_code == 200, put.text
    put = client.put("/api/config/models", json={"midModel": "gemini:custom"})
    assert put.status_code == 200
    body = client.get("/api/config/models").json()
    assert body["midModel"] == "gemini:custom"
    assert (
        body["cheapModel"] == "custom-cheap-non-default"
    )  # untouched by the partial PUT
    assert (
        body["premiumModel"] == "custom-premium-non-default"
    )  # untouched by the partial PUT


def test_model_catalog_keys_labels_and_capabilities(client):
    body = client.get("/api/config/models/catalog").json()
    by_provider = {row["provider"]: row for row in body}
    assert by_provider["anthropic"]["hasKey"] is True  # env_file sets this key
    assert by_provider["openai"]["hasKey"] is False
    assert {"anthropic", "openai", "gemini", "deepseek"} == set(by_provider)

    anthropic = next(row for row in body if row["provider"] == "anthropic")
    haiku = next(m for m in anthropic["models"] if m["id"] == "claude-haiku-4-5")
    opus = next(m for m in anthropic["models"] if "opus" in m["id"])
    assert haiku["label"] and haiku["supportsReasoning"] is False
    assert opus["supportsReasoning"] is True
    assert opus["reasoningEfforts"] == ["low", "medium", "high", "xhigh", "max"]
    assert haiku["supportsNativeSearch"] is True  # anthropic has native search
    haiku_55 = next(m for m in anthropic["models"] if m["id"] == "claude-haiku-5-5")
    assert haiku_55["label"] == "Claude Haiku 5.5"
    assert haiku_55["supportsReasoning"] is True
    assert haiku_55["supportsNativeSearch"] is True
    assert haiku_55["reasoningEfforts"] == ["low", "medium", "high", "xhigh", "max"]
    sonnet_55 = next(m for m in anthropic["models"] if m["id"] == "claude-sonnet-5-5")
    assert sonnet_55["label"] == "Claude Sonnet 5.5"
    assert sonnet_55["supportsReasoning"] is True
    assert sonnet_55["reasoningEfforts"] == ["low", "medium", "high", "xhigh", "max"]

    deepseek = next(row for row in body if row["provider"] == "deepseek")
    # Standalone Search works with both models through function tools.
    assert deepseek["models"][0]["supportsNativeSearch"] is True
    pro = next(m for m in deepseek["models"] if m["id"] == "deepseek:deepseek-v4-pro")
    assert pro["supportsNativeSearch"] is True
    # `none` is in the vocabulary because on the Responses API `reasoning.effort`
    # is also the thinking toggle.
    assert deepseek["models"][0]["reasoningEfforts"] == ["none", "low", "high", "max"]

    openai = next(row for row in body if row["provider"] == "openai")
    gpt = next(m for m in openai["models"] if m["id"] == "openai:gpt-5.5")
    assert gpt["reasoningEfforts"] == ["none", "low", "medium", "high", "xhigh"]
    astra = next(m for m in openai["models"] if m["id"] == "openai:gpt-6-astra")
    assert astra["reasoningEfforts"] == ["low", "medium", "high", "xhigh", "max"]
    sol_61 = next(m for m in openai["models"] if m["id"] == "openai:gpt-6.1-sol")
    assert sol_61["label"] == "GPT-6.1 Sol"
    assert sol_61["supportsReasoning"] is True
    assert sol_61["supportsNativeSearch"] is True
    assert sol_61["reasoningEfforts"] == ["low", "medium", "high", "xhigh", "max"]
    terra = next(m for m in openai["models"] if m["id"] == "openai:gpt-6.1-terra")
    assert terra["label"] == "GPT-6.1 Terra"
    assert terra["supportsReasoning"] is True
    assert terra["supportsNativeSearch"] is True
    assert terra["reasoningEfforts"] == [
        "none",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    for model_id in ("openai:gpt-6-sol", "openai:gpt-6-luna"):
        model = next(m for m in openai["models"] if m["id"] == model_id)
        assert model["reasoningEfforts"] == [
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        ]

    gemini = next(row for row in body if row["provider"] == "gemini")
    gemini_38 = next(
        m for m in gemini["models"] if m["id"] == "gemini:gemini-3.8-flash"
    )
    assert gemini_38["reasoningEfforts"] == ["low", "medium", "high"]
    argon = next(m for m in gemini["models"] if m["id"] == "gemini:gemini-4-argon")
    assert argon["label"] == "Gemini 4 Argon"
    assert argon["supportsReasoning"] is True
    assert argon["supportsNativeSearch"] is True
    assert argon["reasoningEfforts"] == ["low", "medium", "high"]

    flash = next(m for m in deepseek["models"] if m["id"] == "deepseek:deepseek-flash")
    assert flash["label"] == "DeepSeek V4.1 Flash"
    pro = next(m for m in deepseek["models"] if m["id"] == "deepseek:deepseek-v4-pro")
    assert pro["label"] == "DeepSeek V4 Pro"
    assert all("deepseek-v4-flash" not in m["id"] for m in deepseek["models"])


def test_put_models_rejects_capabilities_the_selected_model_does_not_support(client):
    response = client.put(
        "/api/config/models",
        json={
            "cheapModel": "claude-haiku-4-5-20251001",
            "cheapReasoningEffort": "high",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_MODEL_SETTING"
