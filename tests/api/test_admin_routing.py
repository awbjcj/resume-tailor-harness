from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.api.auth import hash_password
from resume_tailor_harness.tenancy.system_db import User
from resume_tailor_harness.tenancy.workspace import provision_workspace


def _login(client, username="owner", password="owner-password"):
    return client.post(
        "/api/auth/login", json={"identifier": username, "password": password}
    )


def _add_member(app) -> None:
    with Session(app.state.system_engine) as session:
        session.add(
            User(
                id="member000001",
                username="member",
                password_hash=hash_password("member-password"),
                role="user",
            )
        )
        session.commit()
    provision_workspace(
        app.state.data_dir,
        "member000001",
        template_dir=app.state.template_config_dir,
    )


def test_routing_configuration_is_admin_only(mu_app, mu_client):
    _add_member(mu_app)
    assert _login(mu_client, "member", "member-password").status_code == 200
    assert mu_client.get("/api/admin/routing").status_code == 403
    assert mu_client.get("/api/admin/routing/decisions").status_code == 403
    assert (
        mu_client.put(
            "/api/admin/routing/decisions", json={"enabled": True, "apiKey": "key"}
        ).status_code
        == 403
    )
    assert (
        mu_client.put("/api/admin/routing", json={"baseUrl": "https://x"}).status_code
        == 403
    )


def test_admin_can_write_routes_without_reading_back_secrets(mu_app, mu_client):
    assert _login(mu_client).status_code == 200
    response = mu_client.put(
        "/api/admin/routing",
        json={
            "baseUrl": "https://sub2api.example.com",
            "anthropicKey": "anthropic-secret-1234",
            "openaiKey": "openai-secret-5678",
            "anthropicRouteMode": "subscription",
            "openaiRouteMode": "auto",
            "geminiRouteMode": "api",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseUrl"] == "https://sub2api.example.com"
    anthropic = next(
        row for row in payload["providers"] if row["provider"] == "anthropic"
    )
    assert anthropic["routeMode"] == "subscription"
    assert anthropic["effectiveMode"] == "subscription"
    assert anthropic["key"] == {"isSet": True, "hint": "1234"}
    assert "anthropic-secret" not in response.text
    assert mu_app.state.settings.sub2api_anthropic_key == "anthropic-secret-1234"
    env_text = mu_app.state.env_path.read_text(encoding="utf-8")
    assert "SUB2API_ANTHROPIC_KEY=anthropic-secret-1234" in env_text


def test_invalid_route_document_is_rejected_without_changing_the_env(mu_app, mu_client):
    assert _login(mu_client).status_code == 200
    before = mu_app.state.env_path.read_text(encoding="utf-8")

    response = mu_client.put(
        "/api/admin/routing",
        json={"openaiRouteMode": "subscription"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ROUTING_CONFIG"
    assert mu_app.state.env_path.read_text(encoding="utf-8") == before


def test_local_mode_refreshes_the_default_context_and_clears_route_cache(tmp_path):
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    app = create_app(
        db_url=f"sqlite:///{(tmp_path / 'data' / 'local.db').as_posix()}",
        app_mode="local",
        env_path=env,
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
    )
    with TestClient(app) as client:
        previous = app.state.default_context
        previous.spend_decisions["claude-sonnet-5"] = object()

        response = client.put(
            "/api/admin/routing",
            json={
                "baseUrl": "https://sub2api.example.com",
                "anthropicKey": "ant-subscription-key",
            },
        )

        assert response.status_code == 200
        refreshed = app.state.default_context
        assert refreshed is not previous
        assert refreshed.settings.sub2api_anthropic_key == "ant-subscription-key"
        assert refreshed.spend_decisions == {}
        enrolled = client.put(
            "/api/admin/routing/decisions",
            json={"enabled": True, "apiKey": "direct-key-test"},
        )
        assert enrolled.status_code == 200
        assert app.state.default_context.settings.openai_decisions_enabled is True
        assert (
            app.state.default_context.settings.openai_decisions_api_key
            == "direct-key-test"
        )


def test_decisions_enrollment_is_separate_explicit_and_write_only(mu_app, mu_client):
    assert _login(mu_client).status_code == 200
    url = "/api/admin/routing/decisions"
    assert mu_client.get(url).json()["enabled"] is False
    before = mu_app.state.env_path.read_bytes()
    assert mu_client.put(url, json={"enabled": True}).status_code == 422
    assert mu_app.state.env_path.read_bytes() == before
    secret = "sk-direct-decisions-test"
    response = mu_client.put(url, json={"apiKey": secret})
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["keyConfigured"] is True
    assert secret not in response.text
    assert mu_client.put(url, json={"enabled": True}).json()["enabled"] is True
    assert mu_app.state.settings.openai_decisions_api_key == secret
    assert mu_app.state.settings.openai_route_mode == "auto"
    assert mu_app.state.settings.sub2api_openai_key == ""
    assert mu_app.state.settings.openai_api_key == ""
    assert mu_client.put(url, json={"apiKey": None}).status_code == 422
    response = mu_client.put(url, json={"enabled": False, "apiKey": None})
    assert response.status_code == 200
    assert response.json()["keyConfigured"] is False
    assert secret not in mu_app.state.env_path.read_text(encoding="utf-8")


def test_decisions_rejects_gateway_key_and_endpoint_overrides(mu_app, mu_client):
    assert _login(mu_client).status_code == 200
    mu_app.state.settings.sub2api_openai_key = "gateway-test"
    url = "/api/admin/routing/decisions"
    before = mu_app.state.env_path.read_bytes()
    assert (
        mu_client.put(url, json={"enabled": True, "apiKey": "gateway-test"}).status_code
        == 422
    )
    assert (
        mu_client.put(url, json={"endpoint": "https://gateway.example"}).status_code
        == 422
    )
    assert mu_client.put(url, json={"enabled": None}).status_code == 422
    assert mu_app.state.env_path.read_bytes() == before


def test_decisions_validation_never_reflects_rejected_secrets(mu_client):
    assert _login(mu_client).status_code == 200
    secret = "sk-rejected-test-secret-" + "x" * 512
    response = mu_client.put("/api/admin/routing/decisions", json={"apiKey": secret})
    assert response.status_code == 422
    assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"
