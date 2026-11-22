"""LLM voice transcription: synchronous, in-memory, never persisted."""

from __future__ import annotations

from fastapi import APIRouter, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from resume_tailor_harness import llm_runner
from resume_tailor_harness.api.errors import ApiException
from resume_tailor_harness.api.schemas.base import CamelModel
from resume_tailor_harness.audio_input import InvalidAudio, decode_audio
from resume_tailor_harness.services import official_audio
from resume_tailor_harness.tenancy.context import current_context
from resume_tailor_harness.tenancy.openai_credit_budget import CreditBudgetError, snapshot

router = APIRouter()

_MAX_AUDIO_BYTES = 15 * 1024 * 1024
_ALLOWED_MIME = {
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
}


class TranscribeAvailabilityOut(CamelModel):
    available: bool


class TranscribeOut(CamelModel):
    text: str


class OfficialTranscribeAvailabilityOut(CamelModel):
    available: bool
    enabled: bool
    spent_micros: int | None = None
    held_micros: int | None = None
    remaining_micros: int | None = None
    warning: bool = False
    optional_work_paused: bool = False


class OfficialTranscribeOut(CamelModel):
    text: str
    billing_pending: bool


@router.get("/transcribe/official/availability", response_model=OfficialTranscribeAvailabilityOut)
def official_transcribe_availability():
    context = current_context()
    enabled = bool(context and context.settings.official_audio_enabled)
    if not enabled:
        return OfficialTranscribeAvailabilityOut(available=False, enabled=False)
    try:
        state = snapshot()
    except (CreditBudgetError, RuntimeError):
        return OfficialTranscribeAvailabilityOut(available=False, enabled=True)
    return OfficialTranscribeAvailabilityOut(
        available=official_audio.available(),
        enabled=True,
        spent_micros=state.spent_micros,
        held_micros=state.held_micros,
        remaining_micros=state.remaining_micros,
        warning=state.warning,
        optional_work_paused=state.optional_work_paused,
    )


@router.post("/transcribe/official", response_model=OfficialTranscribeOut)
async def official_transcribe_audio(file: UploadFile, request_id: str = Form(...)):
    data = await file.read(_MAX_AUDIO_BYTES + 1)
    try:
        decoded = await run_in_threadpool(decode_audio, data)
        result = await run_in_threadpool(official_audio.transcribe, decoded, request_id)
    except InvalidAudio as exc:
        raise ApiException(422, "VALIDATION_ERROR", str(exc)) from exc
    except CreditBudgetError as exc:
        raise ApiException(409, "AUDIO_UNAVAILABLE", str(exc)) from exc
    except Exception as exc:
        raise ApiException(502, "TRANSCRIBE_FAILED", "Transcription failed") from exc
    return OfficialTranscribeOut(text=result.text, billing_pending=result.billing_pending)


@router.get("/transcribe/availability", response_model=TranscribeAvailabilityOut)
def transcribe_availability():
    return TranscribeAvailabilityOut(available=llm_runner.transcription_available())


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe_audio(file: UploadFile):
    if not llm_runner.transcription_available():
        raise ApiException(
            400,
            "TRANSCRIBE_UNAVAILABLE",
            "Voice transcription needs a Gemini or OpenAI API key",
        )
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in _ALLOWED_MIME:
        raise ApiException(
            422, "VALIDATION_ERROR", f"unsupported audio type: {mime or 'unknown'}"
        )
    audio = await file.read()
    if not audio:
        raise ApiException(422, "VALIDATION_ERROR", "empty audio")
    if len(audio) > _MAX_AUDIO_BYTES:
        raise ApiException(422, "VALIDATION_ERROR", "audio exceeds the 15 MB limit")
    try:
        text = await run_in_threadpool(llm_runner.transcribe, audio, mime)
    except ValueError as exc:
        raise ApiException(400, "TRANSCRIBE_UNAVAILABLE", str(exc)) from exc
    except Exception as exc:
        raise ApiException(502, "TRANSCRIBE_FAILED", "Transcription failed") from exc
    return TranscribeOut(text=text)
