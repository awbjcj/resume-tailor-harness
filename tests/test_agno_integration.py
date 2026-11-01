"""Exercise Agno's real agent loop and provider SDK against an offline transport.

These regressions need more than fake runners: GPT-6 must request encrypted
reasoning and replay it beside tool results, and provider cache-write usage
must survive the model parser and run aggregation into our operational trace.
"""

import json
import ast
from contextlib import asynccontextmanager
from typing import Annotated, Any

from agno.agent import Agent
import httpx
import pytest

from resume_tailor_harness.agent_trace import agent_trace, read_trace
from resume_tailor_harness.config import Settings
from resume_tailor_harness.llm_runner import (
    AgentRunner,
    build_model,
    retry_kwargs,
    tool_kwargs,
    use_json_mode_for,
)
from resume_tailor_harness.models.resume import ResumeContent
from resume_tailor_harness.h1b.models import H1BSponsorshipEvidence
from resume_tailor_harness.sessions.stream import Completed, Failed, ToolCompleted


def _response(model_id: str, output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "resp_fixture",
        "object": "response",
        "created_at": 0,
        "model": model_id,
        "status": "completed",
        "output": output,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 10},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
    }


def test_profile_preview_tool_accepts_typed_proposals_without_writing(tmp_path):
    from resume_tailor_harness.profile.conversation import make_profile_tools

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="offline-key",
        openai_base_url="https://provider.invalid/v1",
        openai_route_mode="api",
        llm_retries=0,
    )
    model = build_model("openai:gpt-6.1-terra", settings=settings)
    requests = []
    proposal = {
        "title": "Create profile",
        "changes": [
            {
                "entity": "profile",
                "operation": "create",
                "values": {"contact": {"name": "Ada"}},
                "quotes": ["My name is Ada"],
            }
        ],
    }

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert len(requests) <= 2
        if len(requests) == 1:
            output = [
                {
                    "type": "function_call",
                    "id": "fc_preview",
                    "call_id": "preview1",
                    "name": "preview_profile_changes",
                    "arguments": json.dumps({"proposal": proposal}),
                    "status": "completed",
                }
            ]
        else:
            output = [
                {
                    "type": "message",
                    "id": "msg_preview",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Review the proposed profile.",
                            "annotations": [],
                        }
                    ],
                }
            ]
        return httpx.Response(200, json=_response(model.id, output))

    runner = AgentRunner(
        Agent(
            model=model,
            tools=make_profile_tools(tmp_path, user_text="My name is Ada"),
            telemetry=False,
            **retry_kwargs(),
            **tool_kwargs(),
        ),
        settings=settings,
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model.http_client = client
        result = runner.run("Preview my requested profile.")
    assert result.content == "Review the proposed profile."
    tool_output = next(
        item["output"]
        for item in requests[1]["input"]
        if item.get("type") == "function_call_output"
    )
    # Agno stringifies dictionary tool observations as Python literals.
    observed = ast.literal_eval(tool_output)
    assert observed["valid"] is True and observed["saved"] is False
    assert not (tmp_path / "facts.json").exists()
    assert not (tmp_path / "conversation_edits.json").exists()


def _sse_response(response: dict[str, Any]) -> httpx.Response:
    events = [{"type": "response.created", "response": {**response, "output": []}}]
    for index, item in enumerate(response["output"]):
        events.append(
            {"type": "response.output_item.added", "output_index": index, "item": item}
        )
        if item["type"] == "message":
            events.append(
                {
                    "type": "response.output_text.delta",
                    "output_index": index,
                    "content_index": 0,
                    "item_id": item["id"],
                    "delta": item["content"][0]["text"],
                }
            )
        events.append(
            {"type": "response.output_item.done", "output_index": index, "item": item}
        )
    events.append({"type": "response.completed", "response": response})
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text="".join(
            f"event: {event['type']}\ndata: {json.dumps({**event, 'sequence_number': i})}\n\n"
            for i, event in enumerate(events)
        ),
    )


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("status_code, expected_requests", [(400, 1), (429, 3)])
async def test_evidence_provider_errors_use_the_correct_retry_policy(
    mode, status_code, expected_requests
):
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="offline-key",
        openai_base_url="https://provider.invalid/v1",
        openai_route_mode="api",
        llm_retries=2,
        llm_retry_delay=0,
    )
    model = build_model("openai:gpt-6.1-sol", settings=settings)
    model.max_retries = 0
    requests = []

    def reject(request):
        requests.append(request)
        return httpx.Response(
            status_code,
            json={
                "error": {
                    "code": "invalid_json_schema"
                    if status_code == 400
                    else "rate_limit_exceeded",
                    "message": "Invalid schema"
                    if status_code == 400
                    else "Rate limit reached",
                    "param": "text.format.schema",
                    "type": "invalid_request_error",
                }
            },
        )

    runner = AgentRunner(
        Agent(
            model=model,
            output_schema=H1BSponsorshipEvidence,
            telemetry=False,
            **retry_kwargs(),
        ),
        settings=settings,
    )
    transport = httpx.MockTransport(reject)
    if mode == "async":
        async with httpx.AsyncClient(transport=transport) as client:
            model.http_client = client
            try:
                result = await runner.arun("Check historical evidence.")
            finally:
                await runner.aclose()
    else:
        with httpx.Client(transport=transport) as client:
            model.http_client = client
            result = runner.run("Check historical evidence.")
    assert result.status.value == "ERROR"
    assert (
        "Invalid schema" if status_code == 400 else "Rate limit reached"
    ) in result.content
    assert len(requests) == expected_requests


@pytest.mark.parametrize("surface", ["discovery", "manual"])
async def test_h1b_tool_evidence_reaches_cache_and_api(monkeypatch, surface):
    from sqlmodel import Session

    from resume_tailor_harness.api.schemas.jobs import H1BSponsorshipEvidenceOut
    from resume_tailor_harness.h1b import service
    from resume_tailor_harness.h1b.cache import load_company_evidence
    from resume_tailor_harness.h1b.models import HISTORICAL_ONLY_CAVEAT
    from resume_tailor_harness.db import init_db, make_engine
    from resume_tailor_harness.tracking.tables import Job

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="offline-key",
        openai_base_url="https://provider.invalid/v1",
        openai_route_mode="api",
        mid_model="openai:gpt-6.1-sol",
        h1b_mcp_enabled=True,
        h1b_mcp_command="offline-fixture",
        llm_retries=0,
    )
    wages = {"min": None, "max": None, "mean": None, "median": 150000.0}
    payload = {
        "status": "matched",
        "normalized_company": "acme",
        "display_company": "Acme",
        "fiscal_periods": ["FY2026-Q1"],
        "filing_count": 10,
        "certified_count": 9,
        "denied_count": 1,
        "periods": [
            {
                "period": "FY2026-Q1",
                "filing_count": 10,
                "certified_count": 9,
                "denied_count": 1,
                "wage_summary": wages,
            }
        ],
        "wage_summary": wages,
        "source_url": None,
        "data_version": None,
        "retrieved_at": None,
        "expires_at": None,
        "confidence": 0.9,
        "caveat": HISTORICAL_ONLY_CAVEAT,
        "unavailable_reason": None,
    }
    tool_calls = []

    def get_company_stats(company: str) -> str:
        """Read historical filings for the named employer."""
        tool_calls.append(company)
        return json.dumps(
            {"filings": 10, "certified": 9, "denied": 1, "wage_stats": wages}
        )

    @asynccontextmanager
    async def fake_tools(_settings):
        yield get_company_stats

    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["text"]["format"]["strict"] is True
        output = (
            [
                {
                    "type": "function_call",
                    "id": "fc_h1b",
                    "call_id": "call_h1b",
                    "name": "get_company_stats",
                    "arguments": '{"company":"Acme"}',
                    "status": "completed",
                }
            ]
            if len(requests) == 1
            else [
                {
                    "type": "message",
                    "id": "msg_h1b",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(payload),
                            "annotations": [],
                        }
                    ],
                }
            ]
        )
        return httpx.Response(200, json=_response("gpt-6.1-sol", output))

    engine = make_engine("sqlite://")
    init_db(engine)
    monkeypatch.setattr(service, "h1b_tools", fake_tools)
    monkeypatch.setattr(
        service, "Agent", lambda **kwargs: Agent(telemetry=False, **kwargs)
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

        def offline_model(model_id, **kwargs):
            model = build_model(model_id, settings=settings, **kwargs)
            model.http_client = client
            return model

        monkeypatch.setattr(service, "build_model", offline_model)
        factory = service.DefaultSponsorshipAgentFactory(settings)
        if surface == "discovery":
            report = await service.enrich_companies(
                engine,
                ["Acme"],
                settings=settings,
                agent_factory=factory,
            )
            assert report.researched == 1
            assert report.unavailable == 0
        else:
            with Session(engine) as session:
                job = Job(source="manual", company="Acme", jd_text="Engineer")
                session.add(job)
                session.commit()
                evidence = await service.check_job_sponsorship(
                    session,
                    job,
                    settings=settings,
                    agent_factory=factory,
                )
                assert evidence is not None and evidence.status == "matched"
                assert job.analysis_meta_json is not None
                assert job.analysis_meta_json["h1b_evidence_id"] is not None
        cached = await service.enrich_companies(
            engine,
            ["Acme"],
            settings=settings,
            agent_factory=factory,
        )
        assert cached.cache_hits == 1
        assert cached.researched == 0
    assert len(requests) == 2
    assert tool_calls == ["Acme"]
    assert any(
        item.get("type") == "function_call_output" for item in requests[1]["input"]
    )
    with Session(engine) as session:
        evidence = load_company_evidence(session, ["Acme"])["acme"]
        api = H1BSponsorshipEvidenceOut.from_evidence(evidence)
    assert api.filing_count == 10
    assert api.wage_summary == {"median": 150000.0}
    assert api.periods[0].wage_summary == {"median": 150000.0}


@pytest.mark.parametrize("mode", ["sync", "async", "stream"])
@pytest.mark.parametrize(
    "model_id", ["openai:gpt-5.6-terra", "openai:gpt-6.1-sol", "openai:gpt-6.1-terra"]
)
async def test_reasoning_tool_loop_preserves_schema_and_usage(tmp_path, mode, model_id):
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="offline-key",
        openai_base_url="https://provider.invalid/v1",
        openai_route_mode="api",
        llm_retries=0,
    )
    model = build_model(model_id, reasoning=True, settings=settings)
    expected = ResumeContent.model_validate(
        {
            "contact": {"name": "Test User"},
            "skills": {
                "Languages": [{"name": "Python", "provenance": "skill-python"}],
                "Data platforms": [
                    {"name": "PostgreSQL", "provenance": "skill-postgres"}
                ],
            },
        }
    )
    calls = []

    def lookup_profile(
        fact_id: Annotated[str, "Verified profile fact identifier"],
    ) -> str:
        """Read one verified profile fact without changing the profile."""
        calls.append(fact_id)
        return "Test User" if fact_id == "contact-name" else "Unknown fact"

    reasoning = {
        "type": "reasoning",
        "id": "rs_fixture",
        "summary": [],
        "encrypted_content": "opaque-reasoning-fixture",
    }
    function_call = {
        "type": "function_call",
        "id": "fc_fixture",
        "call_id": "call_fixture",
        "name": "lookup_profile",
        "arguments": '{"fact_id":"contact-name"}',
        "status": "completed",
    }
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert str(request.url) == "https://provider.invalid/v1/responses"
        assert request.headers["authorization"] == "Bearer offline-key"
        assert len(requests) <= 2, (
            "The read-only tool loop must finish after one lookup"
        )
        output_format = body["text"]["format"]
        if output_format.get("strict"):
            schema = output_format["schema"]
            missing = set(schema["properties"]) - set(schema.get("required", []))
            if missing:
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "code": "invalid_json_schema",
                            "type": "invalid_request_error",
                            "param": "text.format.schema",
                            "message": "Invalid schema for response_format 'ResumeContent': "
                            "'schema.required' is required to include every key in properties. "
                            f"Missing {sorted(missing)!r}.",
                        }
                    },
                )
        output = (
            [reasoning, function_call]
            if len(requests) == 1
            else [
                {
                    "type": "message",
                    "id": "msg_fixture",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": expected.model_dump_json(),
                            "annotations": [],
                        }
                    ],
                }
            ]
        )
        response = _response(model.id, output)
        return (
            _sse_response(response)
            if body.get("stream")
            else httpx.Response(200, json=response)
        )

    runner = AgentRunner(
        Agent(
            model=model,
            tools=[lookup_profile],
            output_schema=ResumeContent,
            use_json_mode=use_json_mode_for(model, ResumeContent),
            telemetry=False,
            **retry_kwargs(),
            **tool_kwargs(),
        ),
        settings=settings,
    )
    trace = tmp_path / "agent.ndjson"
    transport = httpx.MockTransport(respond)
    with agent_trace(trace):
        if mode == "async":
            async with httpx.AsyncClient(transport=transport) as client:
                model.http_client = client
                try:
                    result = await runner.arun(
                        "Look up the contact name and format it."
                    )
                finally:
                    await runner.aclose()
        else:
            with httpx.Client(transport=transport) as client:
                model.http_client = client
                if mode == "stream":
                    events = list(
                        runner.stream("Look up the contact name and format it.")
                    )
                    assert not any(isinstance(event, Failed) for event in events)
                    assert (
                        sum(isinstance(event, ToolCompleted) for event in events) == 1
                    )
                    assert isinstance(events[-1], Completed)
                    result = events[-1].response
                else:
                    result = runner.run("Look up the contact name and format it.")

    assert result is not None
    assert result.content == expected
    assert calls == ["contact-name"]
    assert len(requests) == 2
    for body in requests:
        assert body["store"] is False
        assert "previous_response_id" not in body
        assert "reasoning.encrypted_content" in body.get("include", [])
        tool = next(t for t in body["tools"] if t.get("name") == "lookup_profile")
        assert tool["parameters"]["properties"]["fact_id"]["type"] == "string"
        assert body["text"]["format"] == {"type": "json_object"}
        # Agno must still instruct JSON generation and carry the full skill
        # value schema in the prompt when native grammar enforcement is unavailable.
        prompt = json.dumps(body["input"])
        assert "JSON" in prompt
        assert "TailoredSkill" in prompt

    replay = requests[1]["input"]
    assert reasoning in replay
    assert replay.index(reasoning) < next(
        i for i, item in enumerate(replay) if item.get("type") == "function_call"
    )
    assert any(
        item.get("type") == "function_call_output"
        and item.get("call_id") == "call_fixture"
        and item.get("output") == "Test User"
        for item in replay
    )
    assert result.metrics.input_tokens == 200
    assert result.metrics.cache_read_tokens == 60
    assert result.metrics.cache_write_tokens == 20
    assert result.metrics.reasoning_tokens == 10
    if mode != "stream":
        row = read_trace(trace)[0]
        assert row["cacheWriteTokens"] == 20
        assert row["toolCalls"] == 1
        assert "opaque-reasoning-fixture" not in trace.read_text(encoding="utf-8")
