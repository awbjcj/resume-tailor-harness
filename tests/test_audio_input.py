import io
import shutil
import subprocess
import wave

import pytest

from resume_tailor_harness.audio_input import (
    MAX_UPLOAD_BYTES,
    InvalidAudio,
    decode_audio,
)

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="the audio decoder requires ffmpeg and ffprobe",
)


def _wav(samples: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\0\0" * samples)
    return output.getvalue()


def test_decodes_the_samples_sent_to_the_provider():
    result = decode_audio(_wav(20_000))
    assert result.duration_seconds == 1.25
    with wave.open(io.BytesIO(result.wav)) as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 16_000
        assert wav.getnframes() == 20_000


@pytest.mark.parametrize("data", [b"", b"not an audio file"], ids=["empty", "malformed"])
def test_rejects_empty_malformed_and_oversized_audio(data):
    with pytest.raises(InvalidAudio):
        decode_audio(data)


def test_rejects_oversized_audio():
    with pytest.raises(InvalidAudio, match="15 MB"):
        decode_audio(b"x" * (MAX_UPLOAD_BYTES + 1))


def test_rejects_audio_longer_than_two_minutes():
    with pytest.raises(InvalidAudio, match="120-second"):
        decode_audio(_wav(120 * 16_000 + 1_600))


def test_rejects_multiple_audio_streams():
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
            "-t", "0.2", "-map", "0:a", "-map", "1:a",
            "-c:a", "pcm_s16le", "-f", "matroska", "pipe:1",
        ],
        capture_output=True,
        check=True,
    )
    with pytest.raises(InvalidAudio, match="exactly one audio stream"):
        decode_audio(result.stdout)
