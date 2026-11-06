"""Provider selection must configure the model actually used on the first run."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, current_thread

import httpx
import pytest
from agno.agent import Agent
from fastapi.testclient import TestClient

from resume_tailor_harness.api.app import create_app
from resume_tailor_harness.llm_runner import (
    AgentRunner,
    build_model,
    refresh_agent_api_key,
    split_provider,
)
from resume_tailor_harness.services.provider_setup import tier_models
from resume_tailor_harness.tenancy.context import use_context
from resume_tailor_harness.tenancy.spend import SpendGate


@pytest.fixture
def local_app(tmp_path):
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    return create_app(app_mode="local", env_path=env, data_dir=tmp_path / "data")


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "deepseek"])
def test_start_with_one_provider_key(local_app, provider):
    with TestClient(local_app) as client:
        key = f"test-{provider}-key"
        assert (
            client.get("/api/setup/status").json()["secrets"]["modelTiersReady"]
            is False
        )
        response = client.put(
            "/api/setup/provider", json={"provider": provider, "apiKey": key}
        )
        assert response.status_code == 204, response.text
        context = local_app.state.default_context
        with use_context(context):
            for model in tier_models(context.settings):
                assert split_provider(model)[0] == provider
                assert SpendGate().open(model).api_key == key
        assert (
            client.get("/api/setup/status").json()["secrets"]["modelTiersReady"] is True
        )
        response = client.get("/api/setup/provider")
        assert response.json()["selectedProvider"] == provider
        assert key not in response.text


def test_local_endpoint_is_bound_to_its_model_and_credential(local_app):
    platform_env = local_app.state.env_path
    local_app.state.settings = local_app.state.settings.model_copy(
        update={
            "openai_api_key": "platform-key",
            "sub2api_openai_key": "gateway-key",
            "sub2api_base_url": "https://gateway.example",
        }
    )
    connection = {
        "provider": "openai",
        "baseUrl": "http://127.0.0.1:9001/proxy/v2/",
        "modelId": "vendor/responses-model",
        "apiKey": "custom-endpoint-key",
    }
    with TestClient(local_app) as client:
        assert client.put("/api/setup/provider", json=connection).status_code == 204
        context = local_app.state.default_context
        model_id = "openai:vendor/responses-model"
        assert tier_models(context.settings) == (model_id,) * 3
        with use_context(context):
            route = SpendGate().open(model_id)
            assert (route.base_url, route.api_key, route.own_key) == (
                "http://127.0.0.1:9001/proxy/v2",
                "custom-endpoint-key",
                True,
            )
            model = build_model(model_id)
            assert model.id == "vendor/responses-model"
            assert model.base_url == route.base_url
            assert model.api_key == route.api_key
            native = SpendGate().open("openai:gpt-6.1-terra")
            assert (native.base_url, native.api_key) == (
                "https://gateway.example",
                "gateway-key",
            )
        response = client.get("/api/setup/provider")
        assert response.json()["customEndpoint"] == {
            "provider": "openai",
            "baseUrl": "http://127.0.0.1:9001/proxy/v2",
            "modelId": "vendor/responses-model",
            "selected": True,
        }
        assert "custom-endpoint-key" not in response.text
        assert (
            client.get("/api/setup/status").json()["secrets"]["modelTiersReady"] is True
        )

        del connection["apiKey"]
        rejected = client.put(
            "/api/setup/provider",
            json={**connection, "baseUrl": "https://other.example/v1"},
        )
        assert rejected.json()["error"]["code"] == "API_KEY_REQUIRED"
        assert local_app.state.default_context is context
        assert (
            client.put(
                "/api/setup/provider", json={**connection, "modelId": "another-model"}
            ).status_code
            == 204
        )
        assert platform_env.read_text(encoding="utf-8") == ""

        assert (
            client.put("/api/setup/provider", json={"provider": "openai"}).status_code
            == 204
        )
        assert client.get("/api/setup/provider").json()["customEndpoint"] is None
        assert "custom-endpoint-key" not in context.paths.secrets_env.read_text(
            encoding="utf-8"
        )


@pytest.mark.parametrize("refresh", [False, True])
def test_namespaced_anthropic_model_keeps_its_own_key_on_the_wire(local_app, refresh):
    local_app.state.settings = local_app.state.settings.model_copy(
        update={"openai_api_key": "unrelated-platform-key"}
    )
    model_name = "openai:vendor-model"
    requests: list[tuple[str, str | None, str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                str(request.url),
                request.headers.get("x-api-key"),
                json.loads(request.content)["model"],
            )
        )
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": model_name,
                "content": [{"type": "text", "text": "ready"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    with TestClient(local_app) as client:
        response = client.put(
            "/api/setup/provider",
            json={
                "provider": "anthropic",
                "baseUrl": "https://endpoint.example/proxy",
                "modelId": model_name,
                "apiKey": "local-anthropic-key",
            },
        )
        assert response.status_code == 204
        context = local_app.state.default_context
        with (
            use_context(context),
            httpx.Client(transport=httpx.MockTransport(respond)) as http,
        ):
            model = build_model(context.settings.mid_model)
            model.http_client = http
            agent = Agent(model=model, telemetry=False)
            if refresh:
                refresh_agent_api_key(agent)
            result = AgentRunner(agent, settings=context.settings).run("Ready?")
        assert result.content == "ready"
        assert requests == [
            (
                "https://endpoint.example/proxy/v1/messages",
                "local-anthropic-key",
                model_name,
            )
        ]


def test_custom_endpoint_reports_when_tiers_use_another_model(local_app):
    with TestClient(local_app) as client:
        response = client.put(
            "/api/setup/provider",
            json={
                "provider": "openai",
                "baseUrl": "https://endpoint.example/v1",
                "modelId": "proxy-model",
                "apiKey": "custom-endpoint-key",
            },
        )
        assert response.status_code == 204
        assert (
            client.get("/api/setup/provider").json()["customEndpoint"]["selected"]
            is True
        )

        assert (
            client.put(
                "/api/secrets", json={"openaiApiKey": "standard-openai-key"}
            ).status_code
            == 200
        )
        models = {
            tier: "openai:gpt-6-luna"
            for tier in ("cheapModel", "midModel", "premiumModel")
        }
        assert client.put("/api/config/models", json=models).status_code == 200
        body = client.get("/api/setup/provider").json()
        assert body["modelTiersReady"] is True
        assert body["customEndpoint"]["selected"] is False
        assert body["customEndpoint"]["modelId"] == "proxy-model"


def test_local_cli_reuses_the_endpoint_in_the_implicit_workspace(
    local_app, monkeypatch
):
    from resume_tailor_harness.tenancy import local

    monkeypatch.setattr(local, "env_settings", lambda: local_app.state.settings)
    with TestClient(local_app) as client:
        saved = client.put(
            "/api/setup/provider",
            json={
                "provider": "openai",
                "baseUrl": "http://127.0.0.1:9001/api",
                "modelId": "test-model",
                "apiKey": "local-test-key",
            },
        )
        assert saved.status_code == 204
        implicit = local.resolve_local_context(local_app.state.data_dir)
        assert implicit is not None
        with use_context(implicit):
            route = SpendGate().open(implicit.settings.mid_model)
            assert (route.sdk_base_url, route.api_key) == (
                "http://127.0.0.1:9001/api",
                "local-test-key",
            )
        explicit = local.resolve_local_context(
            local_app.state.data_dir, implicit.username
        )
        assert explicit is not None and explicit.local_provider_endpoint is None
        for context in (implicit, explicit):
            assert context.engine is not None and context.system_engine is not None
            context.engine.dispose()
            context.system_engine.dispose()


def test_saved_connection_from_before_exact_urls_keeps_its_working_path(local_app):
    with TestClient(local_app) as client:
        context = local_app.state.default_context
        context.paths.secrets_env.write_text(
            "LOCAL_LLM_PROVIDER=openai\nLOCAL_LLM_MODEL=proxy-model\n"
            "LOCAL_LLM_BASE_URL=https://endpoint.example/proxy\nLOCAL_LLM_API_KEY=legacy-key\n"
            "CHEAP_MODEL=openai:proxy-model\nMID_MODEL=openai:proxy-model\nPREMIUM_MODEL=openai:proxy-model\n",
            encoding="utf-8",
        )
        # A settings save rebuilds the same overlay that startup reads.
        assert (
            client.put("/api/secrets", json={"githubToken": "test-token"}).status_code
            == 200
        )
        endpoint = client.get("/api/setup/provider").json()["customEndpoint"]
        assert endpoint["baseUrl"] == "https://endpoint.example/proxy/v1"
        assert endpoint["selected"] is True
        with use_context(local_app.state.default_context):
            route = SpendGate().open("openai:proxy-model")
            assert route.sdk_base_url == endpoint["baseUrl"]
            assert route.api_key == "legacy-key"


def test_workspace_refresh_uses_platform_config_published_while_it_waits(
    local_app, monkeypatch
):
    from resume_tailor_harness.api import deps

    platform_thread = current_thread()
    waiting = Event()
    release = Event()
    original_lock = deps.env_lock

    @contextmanager
    def pause_workspace_refresh(path):
        if current_thread() is not platform_thread:
            waiting.set()
            assert release.wait(timeout=5)
        with original_lock(path):
            yield

    with TestClient(local_app), ThreadPoolExecutor(max_workers=1) as pool:
        context = local_app.state.default_context
        base = local_app.state.settings
        monkeypatch.setattr(deps, "env_lock", pause_workspace_refresh)

        def refresh_workspace():
            with use_context(context):
                deps.refresh_app_settings(local_app, base)

        refresh = pool.submit(refresh_workspace)
        try:
            assert waiting.wait(timeout=5)
            deps.refresh_platform_settings(
                local_app,
                base.model_copy(update={"openai_api_key": "new-platform-key"}),
            )
        finally:
            release.set()
        refresh.result(timeout=5)
        assert (
            local_app.state.default_context.platform_provider_keys["openai"]
            == "new-platform-key"
        )


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/model",
        "https://user:private@provider.example",
        "http://[broken",
        "https://example.org:99999/v1",
    ],
)
def test_rejects_invalid_custom_urls_without_persisting(local_app, url):
    with TestClient(local_app) as client:
        response = client.put(
            "/api/setup/provider",
            json={
                "provider": "openai",
                "baseUrl": url,
                "modelId": "model",
                "apiKey": "test-key",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_BASE_URL"
        assert url not in response.text and "test-key" not in response.text
        assert not local_app.state.default_context.paths.secrets_env.exists()


def test_hosted_setup_can_choose_a_provider_and_cannot_repoint_its_endpoint(
    mu_client, mu_app
):
    login = mu_client.post(
        "/api/auth/login", json={"identifier": "owner", "password": "owner-password"}
    )
    assert login.status_code == 200
    assert mu_client.get("/api/setup/provider").json()["customEndpointAllowed"] is False
    response = mu_client.put(
        "/api/setup/provider",
        json={
            "provider": "gemini",
            "baseUrl": "http://127.0.0.1:9001",
            "modelId": "x",
            "apiKey": "custom-key",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CUSTOM_ENDPOINT_UNAVAILABLE"
    assert not mu_app.state.default_context.paths.secrets_env.exists()

    response = mu_client.put(
        "/api/setup/provider",
        json={"provider": "gemini", "apiKey": "member-gemini-key"},
    )
    assert response.status_code == 204, response.text
    assert (
        mu_client.get("/api/setup/status").json()["secrets"]["modelTiersReady"] is True
    )
    assert mu_client.get("/api/config/models").json()["midModel"].startswith("gemini:")

    env = mu_app.state.default_context.paths.secrets_env
    with env.open("a", encoding="utf-8") as handle:
        handle.write(
            "LOCAL_LLM_PROVIDER=gemini\nLOCAL_LLM_MODEL=gemini-3.8-flash\n"
            "LOCAL_LLM_BASE_URL=http://127.0.0.1:9001\nLOCAL_LLM_API_KEY=bad-key\n"
        )
    assert mu_client.get("/api/setup/provider").json()["customEndpoint"] is None


def test_provider_validation_does_not_echo_submitted_key(local_app):
    with TestClient(local_app) as client:
        key = "do-not-echo-this-value"
        response = client.put(
            "/api/setup/provider", json={"provider": [], "apiKey": {"value": key}}
        )
        assert response.status_code == 422
        assert key not in response.text


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"modelId": "proxy-model", "apiKey": "test-key"}, "INVALID_BASE_URL"),
        ({"apiKey": "cl\N{LATIN SMALL LETTER E WITH ACUTE}-test"}, "INVALID_API_KEY"),
    ],
)
def test_rejects_incomplete_connection_or_unusable_header(local_app, payload, code):
    with TestClient(local_app) as client:
        response = client.put(
            "/api/setup/provider", json={"provider": "openai", **payload}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == code
        assert not local_app.state.default_context.paths.secrets_env.exists()
