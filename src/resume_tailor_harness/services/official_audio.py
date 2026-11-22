"""Opt-in official transcription with a durable, bounded spend reservation."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING

import httpx

from resume_tailor_harness import realtime_speech
from resume_tailor_harness.audio_input import DecodedAudio, decoder_available
from resume_tailor_harness.llm_limits import llm_call
from resume_tailor_harness.tenancy.context import require_context
from resume_tailor_harness.tenancy.costs import (
    OPENAI_TRANSCRIBE_MODEL,
    OPENAI_REALTIME_TTS_MODEL,
    MeteredUsage,
    calculate_cost,
)
from resume_tailor_harness.tenancy.openai_credit_budget import (
    CreditBudgetError,
    mark_submitted,
    release_unsubmitted,
    reserve,
    retain_result,
    snapshot,
)
from resume_tailor_harness.tenancy.spend import SpendGate
from resume_tailor_harness.tenancy.usage import record_direct_usage

OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class Transcript:
    text: str
    billing_pending: bool


def available() -> bool:
    try:
        context = require_context()
        if (
            not context.settings.official_audio_enabled
            or not context.settings.official_audio_api_key.strip()
            or not decoder_available()
        ):
            return False
        state = snapshot()
        SpendGate().recheck("openai", OPENAI_TRANSCRIBE_MODEL, own_key=False)
        return not state.optional_work_paused
    except (RuntimeError, ValueError):
        return False


def _duration_usage(result: object) -> MeteredUsage | None:
    usage = getattr(result, "usage", None)
    if getattr(usage, "type", None) != "duration":
        return None
    seconds = getattr(usage, "seconds", None)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    if not math.isfinite(seconds) or seconds <= 0 or seconds > 121:
        return None
    try:
        microseconds = int((Decimal(str(seconds)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    except (ValueError, InvalidOperation, OverflowError):
        return None
    return MeteredUsage(
        provider="openai", model=OPENAI_TRANSCRIBE_MODEL,
        audio_input_microseconds=microseconds,
    )


def transcribe(decoded: DecodedAudio, request_id: str) -> Transcript:
    context = require_context()
    settings = context.settings
    if not settings.official_audio_enabled or not settings.official_audio_api_key.strip():
        raise CreditBudgetError("Official audio is not enabled.")
    if context.system_engine is None:
        raise CreditBudgetError("Durable credit accounting is unavailable.")
    # Allow for provider whole-second rounding above the actual decoded length.
    bound_seconds = math.ceil(decoded.duration_seconds) + 1
    bound_usage = MeteredUsage(
        provider="openai", model=OPENAI_TRANSCRIBE_MODEL,
        audio_input_microseconds=bound_seconds * 1_000_000,
    )
    bound = calculate_cost(context.system_engine, bound_usage)
    if bound.total_micros is None or bound.total_micros <= 0:
        raise CreditBudgetError("The official transcription rate is unavailable.")
    hold = reserve(
        request_id=request_id,
        operation="transcribe",
        model=OPENAI_TRANSCRIBE_MODEL,
        fingerprint=hashlib.sha256(decoded.wav).hexdigest(),
        amount_micros=bound.total_micros,
    )
    if hold.replay_text is not None:
        return Transcript(hold.replay_text, hold.billing_pending)

    # The SDK's implicit retries can create additional paid submissions. Use a
    # fixed origin, explicit key, no environment proxies, and zero retries.
    from openai import OpenAI

    buffer = io.BytesIO(decoded.wav)
    buffer.name = "recording.wav"
    try:
        with llm_call():
            SpendGate().recheck("openai", OPENAI_TRANSCRIBE_MODEL, own_key=False)
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=60) as http:
                client = OpenAI(
                    api_key=settings.official_audio_api_key,
                    base_url=OFFICIAL_OPENAI_BASE_URL,
                    max_retries=0,
                    http_client=http,
                )
                # From this point even a timeout or browser cancellation may
                # have incurred a charge. Never release or resubmit this ID.
                mark_submitted(hold.id, bound_usage)
                result = client.audio.transcriptions.create(
                    model=OPENAI_TRANSCRIBE_MODEL, file=buffer, response_format="json"
                )
        text = str(result.text or "").strip()
        usage = _duration_usage(result)
        if usage is None:
            retain_result(hold.id, text)
            return Transcript(text, True)
        record_direct_usage(
            usage,
            own_key=False,
            request_id=f"official-credit:{hold.id}",
            credit_reservation_id=hold.id,
            credit_result_text=text,
        )
        return Transcript(text, False)
    finally:
        release_unsubmitted(hold.id)


def speech_available() -> bool:
    try:
        context = require_context()
        if (
            not context.settings.official_audio_enabled
            or not context.settings.official_audio_api_key.strip()
            or not realtime_speech.encoder_available()
        ):
            return False
        state = snapshot()
        SpendGate().recheck("openai", OPENAI_REALTIME_TTS_MODEL, own_key=False)
        return not state.optional_work_paused
    except (RuntimeError, ValueError):
        return False


def synthesize(text: str, request_id: str) -> bytes:
    context = require_context()
    settings = context.settings
    if not settings.official_audio_enabled or not settings.official_audio_api_key.strip():
        raise CreditBudgetError("Official audio is not enabled.")
    if context.system_engine is None or not realtime_speech.encoder_available():
        raise CreditBudgetError("Durable audio accounting or encoding is unavailable.")
    cleaned = text.strip()
    if not cleaned or len(cleaned) > 8_192:
        raise ValueError("Speech text is empty or too long")
    input_bound = len(cleaned.encode("utf-8")) * 2 + 4_096
    bound_usage = MeteredUsage(
        provider="openai", model=OPENAI_REALTIME_TTS_MODEL,
        input_tokens=input_bound, output_tokens=4_096,
        audio_output_tokens=4_096,
    )
    bound = calculate_cost(context.system_engine, bound_usage)
    if bound.total_micros is None or bound.total_micros <= 0:
        raise CreditBudgetError("The official speech rate is unavailable.")
    hold = reserve(
        request_id=request_id, operation="speech", model=OPENAI_REALTIME_TTS_MODEL,
        fingerprint=hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
        amount_micros=bound.total_micros,
    )
    try:
        with llm_call():
            SpendGate().recheck("openai", OPENAI_REALTIME_TTS_MODEL, own_key=False)
            mark_submitted(hold.id, bound_usage)
            pcm, response = realtime_speech.render(
                cleaned,
                model=OPENAI_REALTIME_TTS_MODEL,
                voice=settings.speech_voice,
                api_key=settings.official_audio_api_key,
                base_url=OFFICIAL_OPENAI_BASE_URL,
                instructions="Read the supplied interview text naturally and accurately.",
                strict_official_origin=True,
            )
        usage = realtime_speech.metered_usage(OPENAI_REALTIME_TTS_MODEL, response)
        record_direct_usage(
            usage,
            own_key=False,
            request_id=f"official-credit:{hold.id}",
            credit_reservation_id=hold.id,
        )
        if response.get("status") != "completed":
            raise RuntimeError("Official speech did not complete")
        return realtime_speech.pcm_to_mp3(pcm)
    finally:
        release_unsubmitted(hold.id)
