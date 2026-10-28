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


@pytest.mark.parametrize("reasoning", [False, True])
@pytest.mark.parametrize("search", [False, True])
@pytest.mark.parametrize("gateway", [False, True])
def test_argon_sdk_payload_and_signed_parts(reasoning, search, gateway):
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
        assert request.url.path.endswith("/models/gemini-4-argon:generateContent")
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
