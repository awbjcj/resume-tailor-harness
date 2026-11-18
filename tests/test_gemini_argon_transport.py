"""Capture Argon's real Generate Content SDK requests without provider calls."""

import json

from agno.models.message import Message
import httpx
from pydantic import BaseModel
import pytest

from resume_tailor_harness.config import Settings
from resume_tailor_harness.llm_runner import build_model, build_search_equipped


class Report(BaseModel):
    summary: str


@pytest.fixture(autouse=True)
def isolate_google_routing_environment(monkeypatch):
    for name in (
        "GOOGLE_GENAI_API_VERSION", "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_GENAI_USE_ENTERPRISE",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("api_version", [None, "v1", "beta"])
@pytest.mark.parametrize("reasoning", [False, True])
@pytest.mark.parametrize("search", [False, True])
@pytest.mark.parametrize("gateway", [False, True])
def test_argon_sdk_payload_and_signed_parts(reasoning, search, gateway, api_version, monkeypatch):
    if api_version:
        monkeypatch.setenv("GOOGLE_GENAI_API_VERSION", api_version)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        gemini_api_key="offline-direct-key",
        gemini_route_mode="subscription" if gateway else "api",
        sub2api_base_url="https://gateway.invalid" if gateway else "",
        sub2api_gemini_key="offline-gateway-key" if gateway else "",
    )
    if search:
        model, _ = build_search_equipped(
            "gemini:gemini-4-argon", mode="native", reasoning=reasoning, settings=settings
        )
    else:
        model = build_model(
            "gemini:gemini-4-argon", reasoning=reasoning, settings=settings
        )
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "text": '{"summary":"ok"}',
                                    "thoughtSignature": "c2lnbmVk",
                                }
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "cachedContentTokenCount": 20,
                    "toolUsePromptTokenCount": 7,
                    "candidatesTokenCount": 10,
                    "thoughtsTokenCount": 5,
                    "totalTokenCount": 122,
                },
            },
        )

    model.client_params["http_options"]["client_args"] = {
        "transport": httpx.MockTransport(respond)
    }
    try:
        result = model.invoke(
            messages=[Message(role="user", content="Return a report.")],
            assistant_message=Message(role="assistant"),
            response_format=Report,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Read evidence.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        )
        assert Report.model_validate_json(result.content).summary == "ok"
        assert result.response_usage.output_tokens == 15
        assert result.response_usage.reasoning_tokens == 5
        assert result.response_usage.input_tokens == 107
        assert result.response_usage.cache_read_tokens == 20
        assert result.response_usage.total_tokens == 122
        assert len(requests) == 1
        request = requests[0]
        assert request.url.host == (
            "gateway.invalid" if gateway else "generativelanguage.googleapis.com"
        )
        version = "v1" if api_version == "v1" else "v1beta"
        assert request.url.path == f"/{version}/models/gemini-4-argon:generateContent"
        assert request.headers["x-goog-api-key"] == (
            "offline-gateway-key" if gateway else "offline-direct-key"
        )
        body = json.loads(request.content)
        config = body["generationConfig"]
        assert config["thinkingConfig"] == {
            "thinking_level": "HIGH" if reasoning else "LOW",
            "include_thoughts": reasoning,
        }
        assert config["maxOutputTokens"] == 32_768
        assert not {"temperature", "topP", "topK"}.intersection(config)
        assert "cachedContent" not in body
        assert config["responseJsonSchema"]["properties"]["summary"]["type"] == "string"
        assert any("functionDeclarations" in tool for tool in body["tools"])
        assert any("googleSearch" in tool for tool in body["tools"]) is search
        replay, _ = model._format_messages(
            [
                Message(
                    role="assistant",
                    content=result.content,
                    provider_data=result.provider_data,
                )
            ]
        )
        assert replay[0].parts[0].thought_signature == b"signed"
    finally:
        model.get_client().close()


@pytest.mark.parametrize("api_version", [None, "v1", "beta"])
def test_transcription_preserves_beta_api_with_real_sdk(monkeypatch, api_version):
    if api_version:
        monkeypatch.setenv("GOOGLE_GENAI_API_VERSION", api_version)
    from google import genai
    from resume_tailor_harness import llm_runner

    requests = []
    clients = []
    real_client = genai.Client

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "candidates": [{
                "content": {"role": "model", "parts": [{"text": "offline transcript"}]},
                "finishReason": "STOP",
            }],
            "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 2},
        })

    def make_client(**kwargs):
        options = dict(kwargs.get("http_options") or {})
        options["client_args"] = {"transport": httpx.MockTransport(respond)}
        client = real_client(**{**kwargs, "http_options": options})
        clients.append(client)
        return client

    monkeypatch.setattr(genai, "Client", make_client)
    monkeypatch.setattr(llm_runner, "get_settings", lambda: Settings(
        _env_file=None,
        gemini_api_key="offline-direct-key",
        sub2api_base_url="https://gateway.invalid",
        sub2api_gemini_key="offline-gateway-key",
    ))
    monkeypatch.setattr(
        "resume_tailor_harness.tenancy.limits.enforce_agent_budget", lambda _: None
    )
    monkeypatch.setattr(
        "resume_tailor_harness.tenancy.spend.SpendGate.recheck", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "resume_tailor_harness.tenancy.usage.record_direct_usage", lambda _: None
    )
    try:
        assert llm_runner.transcribe(
            b"synthetic audio", "audio/webm", model_id="gemini:gemini-flash-latest"
        ) == "offline transcript"
        assert len(requests) == 1
        version = "v1" if api_version == "v1" else "v1beta"
        assert str(requests[0].url) == (
            f"https://generativelanguage.googleapis.com/{version}/"
            "models/gemini-flash-latest:generateContent"
        )
        assert requests[0].headers["x-goog-api-key"] == "offline-direct-key"
        body = json.loads(requests[0].content)
        assert body["contents"][0]["parts"][0]["inlineData"]["mime_type"] == "audio/webm"
    finally:
        for client in clients:
            client.close()


@pytest.mark.parametrize("agno", [False, True])
@pytest.mark.parametrize("vertex,enterprise,expected", [
    ("true", None, {}),
    ("1", None, {}),
    ("", "true", {}),
    ("", "1", {}),
    ("", "false", {"api_version": "v1beta"}),
    ("1", "false", {"api_version": "v1beta"}),
])
def test_vertex_routing_keeps_sdk_default(monkeypatch, agno, vertex, enterprise, expected):
    from resume_tailor_harness.llm_runner import _gemini_api_version_options

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", vertex)
    if enterprise is not None:
        monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", enterprise)
    assert _gemini_api_version_options(agno=agno) == expected


def test_agno_explicit_vertex_takes_precedence_over_enterprise(monkeypatch):
    from resume_tailor_harness.llm_runner import _gemini_api_version_options

    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "false")
    assert _gemini_api_version_options(agno=True) == {}
    assert _gemini_api_version_options() == {"api_version": "v1beta"}
