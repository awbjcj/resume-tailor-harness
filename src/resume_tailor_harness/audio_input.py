"""Decode an untrusted recording into the one audio stream we will submit.

Container duration and MIME metadata are not trustworthy.  Both the duration
check and the provider payload use the same bounded decoded PCM samples.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import wave
from dataclasses import dataclass

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_RECORDING_SECONDS = 120
_SAMPLE_RATE = 16_000
_SAMPLE_WIDTH = 2
_MAX_PCM_BYTES = MAX_RECORDING_SECONDS * _SAMPLE_RATE * _SAMPLE_WIDTH


class InvalidAudio(ValueError):
    """The recording cannot safely be sent to a provider."""


@dataclass(frozen=True)
class DecodedAudio:
    wav: bytes
    sample_count: int

    @property
    def duration_seconds(self) -> float:
        return self.sample_count / _SAMPLE_RATE


def decoder_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def decode_audio(data: bytes) -> DecodedAudio:
    if not data:
        raise InvalidAudio("The recording is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidAudio("The recording exceeds the 15 MB limit.")
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise InvalidAudio("Audio decoding is unavailable.")

    # Only pipe is permitted: a malicious playlist or container must not make
    # the decoder open local files or fetch a URL.  Probe all streams before
    # decoding, then explicitly map the single checked audio stream.
    try:
        probe = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-protocol_whitelist", "pipe",
                "-show_entries", "stream=codec_type",
                "-of", "json",
                "pipe:0",
            ],
            input=data,
            capture_output=True,
            timeout=15,
            check=True,
        )
        streams = json.loads(probe.stdout).get("streams", [])
        if sum(stream.get("codec_type") == "audio" for stream in streams) != 1:
            raise InvalidAudio("The recording must contain exactly one audio stream.")
        decoded = subprocess.run(
            [
                ffmpeg,
                "-hide_banner", "-loglevel", "error", "-nostdin", "-xerror",
                "-protocol_whitelist", "pipe",
                "-i", "pipe:0",
                "-map", "0:a:0", "-vn", "-sn", "-dn",
                # Derive timestamps from decoded samples rather than trusting
                # attacker-controlled gaps or timestamps in the container.
                "-af", "asetpts=N/SR/TB",
                # Read a little beyond the limit so overlong recordings are
                # rejected rather than silently truncated before submission.
                "-t", "120.1",
                "-ac", "1", "-ar", str(_SAMPLE_RATE), "-f", "s16le", "pipe:1",
            ],
            input=data,
            capture_output=True,
            timeout=30,
            check=True,
        )
    except InvalidAudio:
        raise
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        raise InvalidAudio("The recording could not be decoded.") from None
    pcm = decoded.stdout
    if not pcm or len(pcm) % _SAMPLE_WIDTH:
        raise InvalidAudio("The recording contains no valid audio samples.")
    if len(pcm) > _MAX_PCM_BYTES:
        raise InvalidAudio("The recording exceeds the 120-second limit.")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(_SAMPLE_WIDTH)
        wav.setframerate(_SAMPLE_RATE)
        wav.writeframes(pcm)
    return DecodedAudio(output.getvalue(), len(pcm) // _SAMPLE_WIDTH)
