from types import SimpleNamespace

import pytest

from resume_tailor_harness import provider_stream


@pytest.mark.parametrize("name", ["web_search", "web_fetch"])
@pytest.mark.parametrize("error", [False, True])
def test_anthropic_result_start_finishes_tool_before_index_only_stop(name, error):
    parsed = SimpleNamespace(provider_data={})
    token = provider_stream._request.set(provider_stream.RequestState())
    try:
        provider_stream.anthropic_delta(
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "server_tool_use",
                    "id": "call-1",
                    "name": name,
                },
            },
            parsed,
        )
        content = (
            {"error_code": "unavailable"}
            if error
            else {
                "type": "web_fetch_result",
                "url": "https://example.com",
                "content": {},
            }
            if name == "web_fetch"
            else [{"url": "https://example.com", "title": "Source"}]
        )
        provider_stream.anthropic_delta(
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": name + "_tool_result",
                    "tool_use_id": "call-1",
                    "content": content,
                },
            },
            parsed,
        )
        provider_stream.anthropic_delta(
            {"type": "content_block_stop", "index": 1}, parsed
        )
        events = parsed.provider_data[provider_stream.STREAM_KEY]["events"]
        assert [event["t"] for event in events] == ["tool_started", "tool_completed"]
        assert events[-1]["v"]["ok"] is not error
        assert events[-1]["v"]["callId"] == "call-1"
        if name == "web_search" and not error:
            assert parsed.citations.urls[0].url == "https://example.com"
    finally:
        provider_stream._request.reset(token)
