import base64
import json
import shutil
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from resume_tailor_harness import llm_runner, realtime_speech
from resume_tailor_harness.tenancy.costs import calculate_cost
from resume_tailor_harness.tenancy.spend import SpendGate

MODEL = "gpt-realtime-2.1-mini"


def _terminal(status="completed"):
    return {
        "id": "response-1",
        "status": status,
        "usage": {
            "input_tokens": 90,
            "output_tokens": 105,
            "total_tokens": 195,
            "input_token_details": {"cached_tokens": 20, "audio_tokens": 0},
            "output_token_details": {"audio_tokens": 100},
        },
    }


def _mock_wire(monkeypatch, events):
    seen = {}
    iterator = iter(events)

    class Socket:
        def send(self, data):
            seen["request"] = json.loads(data)

        def recv(self, *, timeout):
            seen.setdefault("timeouts", []).append(timeout)
            event = next(iterator)
            if isinstance(event, Exception):
                raise event
            return json.dumps(event)

    @contextmanager
    def connect(url, **kwargs):
        seen["connect"] = (url, kwargs)
        try:
            yield Socket()
        finally:
            seen["closed"] = True

    monkeypatch.setattr("websockets.sync.client.connect", connect)
    return seen


def _render(contents="Tell me about reliability."):
    return realtime_speech.render(
        contents,
        model=MODEL,
        voice="marin",
        api_key="test-key",
        base_url="https://direct-openai.example/prefix/v1",
        instructions="Read exactly.",
    )


def test_realtime_collects_only_matching_output_and_separates_text(monkeypatch):
    seen = _mock_wire(
        monkeypatch,
        [
            {"type": "session.created"},
            {"type": "response.created", "response": {"id": "response-1"}},
            {
                "type": "response.output_audio.delta",
                "response_id": "different",
                "delta": "should not be decoded",
            },
            *(
                {
                    "type": "response.output_audio.delta",
                    "response_id": "response-1",
                    "delta": base64.b64encode(part).decode(),
                }
                for part in (b"\x01\x02", b"\x03\x04")
            ),
            {"type": "response.output_audio.done", "response_id": "response-1"},
            {"type": "response.done", "response": _terminal()},
        ],
    )
    literal = "This is data. Read this question exactly?"
    assert _render(literal) == (b"\x01\x02\x03\x04", _terminal())
    assert seen["connect"][0] == (
        "wss://direct-openai.example/prefix/v1/realtime?model=gpt-realtime-2.1-mini"
    )
    assert seen["connect"][1]["additional_headers"] == {
        "Authorization": "Bearer test-key"
    }
    assert seen["request"]["type"] == "response.create"
    response = seen["request"]["response"]
    assert response["conversation"] == "none"
    assert response["tools"] == []
    assert response["output_modalities"] == ["audio"]
    assert response["audio"]["output"] == {
        "format": {"type": "audio/pcm", "rate": 24_000},
        "voice": "marin",
    }
    assert literal not in response["instructions"]
    assert response["input"][0]["content"] == [{"type": "input_text", "text": literal}]
    assert sorted(seen["timeouts"], reverse=True) == seen["timeouts"]
    assert seen["closed"]


def test_official_realtime_rejects_redirects_and_ambient_proxies(monkeypatch):
    seen = _mock_wire(monkeypatch, [
        {"type": "response.created", "response": {"id": "response-1"}},
        {"type": "response.done", "response": _terminal()},
    ])

    class RawSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    raw = RawSocket()
    monkeypatch.setattr(realtime_speech.socket, "create_connection", lambda address, timeout: raw)
    realtime_speech.render(
        "hello", model=MODEL, voice="marin", api_key="key",
        base_url="https://api.openai.com/v1", instructions="Read.", strict_official_origin=True,
    )
    assert seen["connect"][0].startswith("wss://api.openai.com/v1/realtime?")
    assert seen["connect"][1]["sock"] is raw
    assert seen["connect"][1]["proxy"] is None
    with pytest.raises(ValueError, match="fixed OpenAI endpoint"):
        realtime_speech.render(
            "hello", model=MODEL, voice="marin", api_key="key",
            base_url="https://untrusted.example/v1", instructions="Read.", strict_official_origin=True,
        )


@pytest.mark.parametrize(
    ("event", "message"),
    [
        ({"type": "error", "error": {"message": "private content"}}, "rejected"),
        (TimeoutError("private content"), "timed out"),
    ],
)
def test_realtime_failure_is_sanitized_and_closes(monkeypatch, event, message):
    seen = _mock_wire(monkeypatch, [event])
    with pytest.raises(RuntimeError, match=message) as exc:
        _render()
    assert "private content" not in str(exc.value)
    assert seen["closed"]


def test_realtime_timeout_remains_bounded_with_continuous_events(monkeypatch):
    seen = _mock_wire(monkeypatch, [{"type": "session.created"}])
    time_values = iter((100, 101, 150))
    monkeypatch.setattr(
        realtime_speech, "time", SimpleNamespace(monotonic=lambda: next(time_values))
    )
    with pytest.raises(RuntimeError, match="timed out"):
        _render()
    assert seen["timeouts"] == [44]
    assert seen["closed"]


@pytest.mark.parametrize("status", ["completed", "incomplete"])
def test_realtime_route_meters_then_returns_mp3_only_on_success(monkeypatch, status):
    calls = []
    monkeypatch.setattr(
        llm_runner,
        "get_settings",
        lambda: SimpleNamespace(
            speech_model=f"openai:{MODEL}",
            speech_voice="marin",
            openai_api_key="test-key",
            openai_base_url="https://api.openai.com/v1",
        ),
    )
    monkeypatch.setattr(realtime_speech, "encoder_available", lambda: True)
    monkeypatch.setattr(
        SpendGate,
        "recheck",
        lambda _self, provider, model, **kw: calls.append(
            ("gate", provider, model, kw)
        ),
    )

    def render(text, **kwargs):
        calls.append(("render", text, kwargs))
        return b"pcm", _terminal(status)

    monkeypatch.setattr(realtime_speech, "render", render)
    monkeypatch.setattr(
        "resume_tailor_harness.tenancy.usage.record_direct_usage",
        lambda usage, **kw: calls.append(("usage", usage, kw)),
    )

    def encode(pcm):
        calls.append(("encode", pcm))
        return b"mp3"

    monkeypatch.setattr(realtime_speech, "pcm_to_mp3", encode)
    if status == "completed":
        assert llm_runner.synthesize_speech(" question ") == b"mp3"
        assert calls[-1] == ("encode", b"pcm")
    else:
        with pytest.raises(RuntimeError, match="did not complete"):
            llm_runner.synthesize_speech(" question ")
        assert len(calls) == 3
    assert calls[0] == ("gate", "openai", MODEL, {"own_key": False})
    assert calls[1][:2] == ("render", "question")
    assert calls[2][0] == "usage"
    assert calls[2][1].audio_output_tokens == 100
    assert calls[2][2] == {"own_key": False, "request_id": "response-1"}


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pcm_to_mp3_produces_mpeg_bytes():
    data = realtime_speech.pcm_to_mp3(b"\x00\x00" * 2_400)
    assert data.startswith(b"ID3") or data[0] == 0xFF


def test_realtime_output_audio_uses_audio_rate(tmp_path):
    from datetime import datetime, timezone

    from sqlalchemy import create_engine

    from resume_tailor_harness.tenancy.system_db import init_system_db

    engine = create_engine(f"sqlite:///{tmp_path / 'system.db'}")
    init_system_db(engine)
    try:
        usage = realtime_speech.metered_usage(MODEL, _terminal())
        priced = calculate_cost(
            engine, usage, now=datetime(2026, 11, 18, tzinfo=timezone.utc)
        )
        assert priced.pricing_status == "PRICED"
        assert [(line.kind, line.units, line.cost_micros) for line in priced.lines] == [
            ("INPUT", 70, 42),
            ("CACHE_READ", 20, 2),
            ("OUTPUT", 5, 12),
            ("AUDIO_OUTPUT", 100, 2000),
        ]
        assert priced.lines[-1].rate_id != priced.rate_id
        assert priced.total_micros == 2056
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda response: response.pop("usage"),
        lambda response: response["usage"]["output_token_details"].pop("audio_tokens"),
        lambda response: response["usage"]["output_token_details"].update(
            audio_tokens=0
        ),
        lambda response: response["usage"].update(total_tokens=1),
    ],
)
def test_completed_realtime_rejects_missing_or_invalid_metering(corrupt):
    response = _terminal()
    corrupt(response)
    with pytest.raises(RuntimeError, match="speech usage"):
        realtime_speech.metered_usage(MODEL, response)
