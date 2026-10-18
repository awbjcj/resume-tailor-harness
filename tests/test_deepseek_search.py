import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from resume_tailor_harness.config import Settings
from resume_tailor_harness import deepseek_search
from resume_tailor_harness.deepseek_search import DeepSeekSearchTools

_NO_ENV_FILE: dict[str, Any] = {"_env_file": None}


@pytest.fixture
def calls(monkeypatch):
    requests, usage = [], []
    replies = [
        {
            "results": [
                {"title": "Source", "url": "https://example.com", "summary": "Evidence"}
            ]
        }
    ]
    original_client = httpx.Client

    def respond(request):
        requests.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": {"message": "failed"}})
        return httpx.Response(200, json=reply)

    monkeypatch.setattr(
        deepseek_search,
        "httpx",
        SimpleNamespace(
            Client=lambda **kwargs: original_client(
                **kwargs, transport=httpx.MockTransport(respond)
            ),
            TimeoutException=httpx.TimeoutException,
            TransportError=httpx.TransportError,
        ),
    )
    monkeypatch.setattr(deepseek_search, "record_direct_usage", usage.append)
    monkeypatch.setattr(deepseek_search.time, "sleep", lambda _: None)
    return SimpleNamespace(requests=requests, usage=usage, replies=replies)


def tool(**kwargs):
    return DeepSeekSearchTools(
        settings=Settings(**_NO_ENV_FILE, deepseek_api_key="direct-test", **kwargs)
    )


@pytest.mark.parametrize(
    "base", ["https://gateway.example/prefix", "https://gateway.example/prefix/v1/"]
)
@pytest.mark.parametrize("subscription", [False, True])
def test_search_request_uses_selected_endpoint_and_key(calls, base, subscription):
    tools = tool(
        **(
            {
                "sub2api_base_url": base,
                "sub2api_deepseek_key": "gateway-test",
                "deepseek_route_mode": "subscription",
            }
            if subscription
            else {}
        )
    )
    result = json.loads(tools.web_search("AI site:example.com lang:en after:2026", 7))
    request = calls.requests[0]
    expected = (
        "https://gateway.example/prefix/v1"
        if subscription
        else "https://api.deepseek.com/v1"
    )
    assert str(request.url) == f"{expected}/tools/search"
    assert (
        request.headers["authorization"]
        == f"Bearer {'gateway-test' if subscription else 'direct-test'}"
    )
    assert json.loads(request.content) == {
        "query": "AI site:example.com lang:en after:2026",
        "count": 7,
        "need_content": False,
    }
    assert result["results"][0]["summary"] == "Evidence"
    assert calls.usage[0].model == "deepseek-search"
    assert calls.usage[0].tool_units == 1
    assert calls.usage[0].input_tokens == 0


@pytest.mark.parametrize(
    "operation,reply,expected",
    [
        ("search", {"results": []}, 0),
        ("fetch", {"title": "Page", "content": "# Content"}, 1),
        ("fetch", {"title": "Page", "content": ""}, 0),
    ],
)
def test_only_nonempty_successful_requests_are_billable(
    calls, operation, reply, expected
):
    calls.replies[:] = [reply]
    tools = tool()
    result = (
        tools.web_search("query")
        if operation == "search"
        else tools.fetch_web("https://example.com/page")
    )
    assert json.loads(result) == reply
    assert calls.usage[0].model == f"deepseek-{operation}"
    assert calls.usage[0].tool_units == expected
    if operation == "fetch":
        assert json.loads(calls.requests[0].content) == {
            "url": "https://example.com/page"
        }
        assert str(calls.requests[0].url) == "https://api.deepseek.com/v1/tools/fetch"


@pytest.mark.parametrize("failure", [408, 429, 500, 504, httpx.ReadTimeout("timeout")])
def test_transient_errors_retry_and_record_success_once(calls, failure):
    calls.replies.insert(0, failure)
    tool().web_search("query")
    assert len(calls.requests) == 2
    assert len(calls.usage) == 1


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404])
def test_permanent_errors_do_not_retry_or_charge(calls, status):
    calls.replies[:] = [status]
    with pytest.raises(httpx.HTTPStatusError):
        tool().web_search("query")
    assert len(calls.requests) == 1
    assert not calls.usage


def test_exhausted_retries_do_not_charge(calls):
    calls.replies[:] = [429, 429, 429]
    with pytest.raises(httpx.HTTPStatusError):
        tool().web_search("query")
    assert len(calls.requests) == 3
    assert not calls.usage


@pytest.mark.parametrize(
    "query,count", [(" ", 5), ("a" * 129, 5), ("q", 0), ("q", 51), ("q", True)]
)
def test_invalid_search_fails_before_network(calls, query, count):
    with pytest.raises(ValueError):
        tool().web_search(query, count)
    assert not calls.requests


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:pass@example.com",
        "https:///path",
        "https://example.com/" + "a" * 8192,
    ],
)
def test_invalid_fetch_fails_before_network(calls, url):
    with pytest.raises(ValueError):
        tool().fetch_web(url)
    assert not calls.requests


def test_budget_denial_prevents_request(calls, monkeypatch):
    def denied(*args, **kwargs):
        raise RuntimeError("budget exhausted")

    monkeypatch.setattr(deepseek_search.SpendGate, "open", denied)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        tool().web_search("query")
    assert not calls.requests
    assert not calls.usage


def test_settlement_failure_is_not_retried(calls, monkeypatch):
    def failed(_usage):
        raise RuntimeError("settlement failed")

    monkeypatch.setattr(deepseek_search, "record_direct_usage", failed)
    with pytest.raises(RuntimeError, match="settlement failed"):
        tool().web_search("query")
    assert len(calls.requests) == 1


@pytest.mark.parametrize("own_key", [False, True])
def test_successful_tool_requests_settle_through_hosted_ledger(
    calls, monkeypatch, tmp_path, own_key
):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from resume_tailor_harness.tenancy.context import UserContext, use_context
    from resume_tailor_harness.tenancy.costs import seed_llm_rates
    from resume_tailor_harness.tenancy.system_db import (
        User,
        UsageEvent,
        make_system_engine,
        init_system_db,
    )
    from resume_tailor_harness.tenancy.usage import record_direct_usage
    from resume_tailor_harness.tenancy.workspace import WorkspacePaths

    engine = make_system_engine(tmp_path)
    init_system_db(engine)
    seed_llm_rates(engine)
    with Session(engine) as session:
        session.add(
            User(
                id="search-user",
                username="search-user",
                password_hash="hash",
                role="user",
            )
        )
        session.commit()
    settings = Settings(**_NO_ENV_FILE, cost_quota_enforcement="enforce")
    context = UserContext(
        user_id="search-user",
        username="search-user",
        role="user",
        paths=WorkspacePaths(tmp_path / "workspace"),
        settings=settings,
        engine=None,
        system_engine=engine,
        own_key_providers=frozenset({"deepseek"} if own_key else set()),
        platform_provider_keys={} if own_key else {"deepseek": "shared-key"},
        user_provider_keys={"deepseek": "personal-key"} if own_key else {},
    )
    monkeypatch.setattr(deepseek_search, "record_direct_usage", record_direct_usage)
    with use_context(context):
        DeepSeekSearchTools(settings=settings).web_search("query")
        calls.replies.append({"results": []})
        DeepSeekSearchTools(settings=settings).web_search("empty query")
    with Session(engine) as session:
        events = list(session.scalars(select(UsageEvent).order_by(UsageEvent.ts)))
    assert len(events) == 2
    assert [event.cost_micros for event in events] == [750, 0]
    assert [event.tool_cost_micros for event in events] == [750, 0]
    assert [event.quota_cost_micros for event in events] == [0 if own_key else 750, 0]
    assert all(event.own_key == own_key for event in events)
    assert all(event.pricing_status == "PRICED" for event in events)
    assert (
        calls.requests[0].headers["authorization"]
        == f"Bearer {'personal-key' if own_key else 'shared-key'}"
    )


@pytest.mark.parametrize(
    "model_id", ["deepseek:deepseek-flash", "deepseek:deepseek-v4-pro"]
)
async def test_agno_executes_search_and_replays_sources_through_responses(
    calls, model_id
):
    from agno.agent import Agent
    from openai import AsyncOpenAI
    from resume_tailor_harness.llm_runner import build_search_equipped

    settings = Settings(**_NO_ENV_FILE, deepseek_api_key="direct-test")
    model, tools = build_search_equipped(model_id, "native", settings=settings)
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        output = (
            [
                {
                    "id": "fc_search",
                    "type": "function_call",
                    "call_id": "call_search",
                    "name": "web_search",
                    "arguments": json.dumps({"query": "AI site:example.com"}),
                    "status": "completed",
                }
            ]
            if len(requests) == 1
            else [
                {
                    "id": "msg_answer",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Answer with source https://example.com",
                            "annotations": [],
                        }
                    ],
                }
            ]
        )
        return httpx.Response(
            200,
            json={
                "id": f"resp_{len(requests)}",
                "object": "response",
                "created_at": 0,
                "model": model.id,
                "status": "completed",
                "output": output,
            },
        )

    async with AsyncOpenAI(
        api_key="direct-test",
        base_url=model.base_url,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        model.async_client = client
        result = await Agent(model=model, tools=tools, telemetry=False).arun(
            "Research AI"
        )
    assert result.content == "Answer with source https://example.com"
    assert len(requests) == 2
    assert requests[0]["reasoning"]["effort"] == "none"
    assert {tool["name"] for tool in requests[0]["tools"]} == {
        "web_search",
        "fetch_web",
    }
    assert all(tool["type"] == "function" for tool in requests[0]["tools"])
    tool_output = next(
        item
        for item in requests[1]["input"]
        if item.get("type") == "function_call_output"
    )
    assert tool_output["call_id"] == "call_search"
    assert (
        json.loads(tool_output["output"])["results"][0]["url"] == "https://example.com"
    )
    assert len(calls.requests) == len(calls.usage) == 1
