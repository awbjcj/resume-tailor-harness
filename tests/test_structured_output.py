from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from resume_tailor_harness.config import Settings
from resume_tailor_harness.llm_runner import (
    AgentRunner,
    INCOMPLETE_KEY,
    UnparsedAgentOutput,
    expect_schema,
)
from resume_tailor_harness.structured_output import (
    StructuredOutputError,
    parse_structured_content,
)


class Output(BaseModel):
    value: int
    evidence: str = ""


@pytest.mark.parametrize(
    "raw",
    [
        '\ufeff{"value": 7}',
        '```json\n{"value": 7}\n```',
        '<think>private notes</think>\n{"value":7}',
        '{"value": 7,}',
        '{"value": 7, "evidence": "literal ,} and ```json and \\"quotes\\"",}',
    ],
)
def test_complete_json_noise_is_recovered_without_inventing_values(raw):
    parsed = parse_structured_content(raw, Output)
    assert isinstance(parsed, Output)
    assert parsed.value == 7
    if "literal" in raw:
        assert parsed.evidence == 'literal ,} and ```json and "quotes"'


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "Concurrency limit exceeded for user, please retry later",
        '{"value": 7',
        '{"value": 7} {"value": 8}',
        '{"value": 7, "value": 8}',
        '{"value": NaN}',
        '{"evidence":"required value missing"}',
        '{"value": "private-invalid-input"}',
    ],
)
def test_invalid_or_ambiguous_documents_are_not_silently_repaired(raw):
    with pytest.raises(StructuredOutputError) as caught:
        parse_structured_content(raw, Output)
    assert "private-invalid-input" not in str(caught.value)


class Agent:
    output_schema = Output

    def __init__(self, contents, *, status="COMPLETED"):
        self.contents = iter(contents)
        self.prompts = []
        self.status = status

    def run(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=next(self.contents), status=self.status)

    async def arun(self, prompt):
        return self.run(prompt)


@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_runner_retries_with_bounded_feedback_and_records_every_attempt(
    monkeypatch, mode
):
    settled = []
    monkeypatch.setattr(
        "resume_tailor_harness.llm_runner.record_call",
        lambda _agent, response: settled.append(response),
    )
    settings = Settings(_env_file=None, llm_retries=1, llm_retry_delay=0)  # type: ignore[call-arg]
    agent = Agent(['{"value":"private-invalid-input"}', '\ufeff{"value":7,}'])
    runner = AgentRunner(agent, settings=settings)
    result = (
        await runner.arun("Original task")
        if mode == "async"
        else runner.run("Original task")
    )
    assert result.content == Output(value=7)
    assert agent.prompts[0] == "Original task"
    assert agent.prompts[1].startswith("Original task")
    assert "value: int_parsing" in agent.prompts[1]
    assert "private-invalid-input" not in agent.prompts[1]
    assert len(settled) == 2


def test_provider_error_does_not_get_retried_as_bad_json():
    agent = Agent(
        ["Concurrency limit exceeded for user, please retry later"], status="ERROR"
    )
    result = AgentRunner(agent).run("Original task")
    assert len(agent.prompts) == 1
    with pytest.raises(UnparsedAgentOutput, match="status=ERROR"):
        expect_schema(result, Output, source="test")


def test_final_parse_failure_contains_validation_reason():
    settings = Settings(_env_file=None, llm_retries=0)  # type: ignore[call-arg]
    result = AgentRunner(Agent(['{"value":']), settings=settings).run("p")
    with pytest.raises(UnparsedAgentOutput, match="invalid JSON at line 1"):
        expect_schema(result, Output, source="test")


def test_typed_but_incomplete_or_failed_response_is_never_accepted():
    for response in (
        SimpleNamespace(content=Output(value=7), status="ERROR"),
        SimpleNamespace(
            content=Output(value=7),
            model_provider_data={INCOMPLETE_KEY: {"reason": "max_output_tokens"}},
        ),
    ):
        with pytest.raises(UnparsedAgentOutput):
            expect_schema(response, Output, source="test")


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "first_output",
    [
        None,  # SDK connection error, wrapped by Agno with no status code.
        "",
        '{"value":',
        '{"value":"wrong-type"}',
        '{"value":1,"value":7,"evidence":"original evidence"}',
        '{"value":7} {"evidence":"original evidence"}',
    ],
)
async def test_real_agno_and_sdk_recover_invalid_json_with_correction_feedback(
    mode, first_output
):
    import json

    import httpx
    from agno.agent import Agent as AgnoAgent

    from resume_tailor_harness.llm_runner import build_model
    from tests.test_agno_integration import _response

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="offline-key",
        openai_base_url="https://provider.invalid/v1",
        openai_route_mode="api",
        llm_retries=1,
        llm_retry_delay=0,
    )
    model = build_model("openai:gpt-6.1-terra", settings=settings)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        if first_output is None and len(requests) == 1:
            raise httpx.ConnectError("temporary connection failure", request=request)
        text = (
            first_output
            if len(requests) == 1
            else '{"value":7,"evidence":"original evidence"}'
        )
        return httpx.Response(
            200,
            json=_response(
                model.id,
                [
                    {
                        "type": "message",
                        "id": "msg_output",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": text, "annotations": []}
                        ],
                    }
                ],
            ),
        )

    runner = AgentRunner(
        AgnoAgent(model=model, output_schema=Output, telemetry=False, retries=0),
        settings=settings,
    )
    transport = httpx.MockTransport(respond)
    if mode == "async":
        async with httpx.AsyncClient(transport=transport) as client:
            model.http_client = client
            try:
                result = await runner.arun("Use original evidence")
            finally:
                await runner.aclose()
    else:
        with httpx.Client(transport=transport) as client:
            model.http_client = client
            result = runner.run("Use original evidence")
    assert expect_schema(result, Output, source="integration") == Output(
        value=7, evidence="original evidence"
    )
    assert len(requests) == 2
    assert ("OUTPUT CORRECTION" in json.dumps(requests[1]["input"])) == (
        first_output is not None
    )
    assert requests[1]["text"]["format"]["type"] == "json_schema"


@pytest.mark.parametrize("mode", ["sync", "async", "stream"])
async def test_typed_output_from_ambiguous_raw_json_is_rejected_when_exhausted(mode):
    from resume_tailor_harness.sessions.stream import Completed, Failed

    raw = '{"value":1,"value":7}'
    response = SimpleNamespace(
        content=Output(value=7),
        messages=[SimpleNamespace(role="assistant", content=raw)],
    )

    class ParsedAgent:
        output_schema = Output

        def run(self, prompt, **kwargs):
            return iter([response]) if kwargs.get("stream") else response

        async def arun(self, prompt):
            return response

    settings = Settings(_env_file=None, llm_retries=0)  # type: ignore[call-arg]
    runner = AgentRunner(ParsedAgent(), settings=settings)
    if mode == "stream":
        events = list(runner.stream("p"))
        assert not any(isinstance(event, Completed) for event in events)
        assert isinstance(events[-1], Failed)
        assert events[-1].code == "INVALID_STRUCTURED_OUTPUT"
    else:
        result = await runner.arun("p") if mode == "async" else runner.run("p")
        with pytest.raises(UnparsedAgentOutput, match="duplicate object keys"):
            expect_schema(result, Output, source="test")


@pytest.mark.parametrize("visible", [False, True])
def test_structured_stream_retries_only_before_visible_output(visible):
    from agno.run.agent import RunEvent

    from resume_tailor_harness.sessions.stream import Completed, Failed

    class StreamingAgent:
        output_schema = Output

        def __init__(self):
            self.prompts = []

        def run(self, prompt, **kwargs):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                if visible:
                    yield SimpleNamespace(event=RunEvent.run_content, content="partial")
                yield SimpleNamespace(content='{"value":')
            else:
                yield SimpleNamespace(content='{"value":7}')

    agent = StreamingAgent()
    settings = Settings(_env_file=None, llm_retries=1, llm_retry_delay=0)  # type: ignore[call-arg]
    events = list(AgentRunner(agent, settings=settings).stream("Original task"))
    assert len(agent.prompts) == (1 if visible else 2)
    assert isinstance(events[-1], Failed if visible else Completed)
    if not visible:
        assert "OUTPUT CORRECTION" in agent.prompts[1]
