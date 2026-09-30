"""Responses-capable providers use Responses, including legacy and custom IDs.

Capture the real SDK request offline: checking only the adapter class would
miss a changed invocation path or a gateway URL that still selects chat.
"""

import json

from agno.models.message import Message
import httpx
from openai import AsyncOpenAI
import pytest

from resume_tailor_harness.config import Settings
from resume_tailor_harness.llm_runner import (
    MODEL_CATALOG,
    build_model,
    build_search_equipped,
)
from resume_tailor_harness.models.resume import ResumeContent


@pytest.mark.parametrize(
    "model_id",
    [
        entry.id
        for provider in ("openai", "deepseek")
        for entry in MODEL_CATALOG[provider]
    ]
    + ["openai:gpt-4o-mini", "openai:custom-model", "deepseek:custom-model"],
)
@pytest.mark.parametrize("reasoning", [False, True])
@pytest.mark.parametrize("route_mode", ["api", "subscription"])
@pytest.mark.parametrize("search_mode", [None, "native", "tool"])
async def test_supported_providers_send_responses_with_tools_and_resume_schema(
    model_id, reasoning, route_mode, search_mode
):
    settings = Settings(
        _env_file=None,
        openai_api_key="direct-test-key",
        openai_base_url="https://direct.example/v1",
        sub2api_base_url="https://gateway.example",
        sub2api_openai_key="subscription-test-key",
        openai_route_mode=route_mode,
        deepseek_api_key="direct-test-key",
        sub2api_deepseek_key="subscription-test-key",
        deepseek_route_mode=route_mode,
    )
    if search_mode is None:
        model = build_model(model_id, reasoning=reasoning, settings=settings)
        native_tools = []
    else:
        model, tools = build_search_equipped(
            model_id,
            mode=search_mode,
            reasoning=reasoning,
            settings=settings,
            tool_search=object(),
        )
        native_tools = tools if search_mode == "native" else []

    requests = []
    output = ResumeContent.model_validate({"contact": {"name": "Test User"}})

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "model": model.id,
                "status": "completed",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": output.model_dump_json(),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    async with AsyncOpenAI(
        api_key=model.api_key,
        base_url=model.base_url,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        model.async_client = client
        result = await model.ainvoke(
            messages=[Message(role="user", content="Tailor the resume.")],
            assistant_message=Message(role="assistant"),
            response_format=ResumeContent,
            tools=[
                *native_tools,
                {
                    "type": "function",
                    "function": {
                        "name": "lookup_profile",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    },
                },
            ],
        )

    assert ResumeContent.model_validate_json(result.content) == output
    assert len(requests) == 1
    request = requests[0]
    provider, selected_model = model_id.split(":", 1)
    if route_mode == "subscription":
        expected_url = "https://gateway.example/v1/responses"
    elif provider == "deepseek":
        expected_url = "https://api.deepseek.com/responses"
    else:
        expected_url = "https://direct.example/v1/responses"
    key = "direct-test-key" if route_mode == "api" else "subscription-test-key"
    assert request.method == "POST"
    assert str(request.url) == expected_url
    assert request.headers["authorization"] == f"Bearer {key}"
    body = json.loads(request.content)
    assert body["model"] == selected_model
    assert model.provider.lower() == provider
    assert body["text"]["format"]["name"] == "ResumeContent"
    assert body["text"]["format"]["type"] == "json_schema"
    assert any(tool.get("name") == "lookup_profile" for tool in body["tools"])
    assert "messages" not in body
    assert "reasoning_effort" not in body
    if model_id == "openai:gpt-6.1-sol":
        assert body["reasoning"]["effort"] in ("low", "medium", "high", "xhigh", "max")
    if search_mode == "native":
        assert {"type": "web_search"} in body["tools"]


@pytest.mark.parametrize("provider", ["anthropic", "gemini"])
@pytest.mark.parametrize("reasoning", [False, True])
def test_providers_without_native_responses_keep_native_adapters(provider, reasoning):
    from agno.models.anthropic import Claude
    from agno.models.google import Gemini

    settings = Settings(_env_file=None)
    expected_class = Claude if provider == "anthropic" else Gemini
    for entry in MODEL_CATALOG[provider]:
        model = build_model(entry.id, reasoning=reasoning, settings=settings)
        assert isinstance(model, expected_class), entry.id
