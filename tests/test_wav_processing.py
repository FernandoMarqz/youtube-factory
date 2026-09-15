"""Regression tests for WAV artifacts with streamed or finite RIFF chunk sizes."""

import struct
import wave
from io import BytesIO

import pytest

from youtube_factory.application.services.wav import (
    InvalidWavError,
    inspect_pcm_wav,
    normalize_pcm_wav,
)


def make_pcm_wav(
    pcm_payload: bytes,
    *,
    sample_rate_hz: int = 100,
    declared_data_size: int | None = None,
    declared_riff_size: int | None = None,
    include_junk_chunk: bool = False,
) -> bytes:
    """Build a minimal PCM WAV fixture with controllable declared RIFF chunk sizes."""
    fmt_chunk = struct.pack(
        "<4sIHHIIHH", b"fmt ", 16, 1, 1, sample_rate_hz, sample_rate_hz * 2, 2, 16
    )
    junk_chunk = b"JUNK" + struct.pack("<I", 3) + b"abc\x00" if include_junk_chunk else b""
    data_size = len(pcm_payload) if declared_data_size is None else declared_data_size
    data_chunk = b"data" + struct.pack("<I", data_size) + pcm_payload
    data_chunk += b"\x00" if len(pcm_payload) % 2 else b""
    body = b"WAVE" + fmt_chunk + junk_chunk + data_chunk
    riff_size = len(body) if declared_riff_size is None else declared_riff_size
    return b"RIFF" + struct.pack("<I", riff_size) + body


@pytest.fixture
def streamed_wav() -> bytes:
    """PCM WAV with streaming sentinels and a padded chunk before the data payload."""
    return make_pcm_wav(
        b"\x00\x00" * 250,
        declared_data_size=0xFFFFFFFF,
        declared_riff_size=0xFFFFFFFF,
        include_junk_chunk=True,
    )


def test_streamed_wav_duration_uses_physical_pcm_payload(streamed_wav: bytes) -> None:
    info = inspect_pcm_wav(streamed_wav)

    assert info.channels == 1
    assert info.sample_width_bytes == 2
    assert info.sample_rate_hz == 100
    assert info.data_size == 500
    assert info.frame_count == 250
    assert info.duration_seconds == 2.5


def test_normalized_streamed_wav_has_finite_sizes_and_standard_frame_count(
    streamed_wav: bytes,
) -> None:
    normalized, info = normalize_pcm_wav(streamed_wav)

    assert normalized[4:8] == struct.pack("<I", len(normalized) - 8)
    assert normalized[40:44] == struct.pack("<I", info.data_size)
    assert normalized[44:] == b"\x00\x00" * 250
    with wave.open(BytesIO(normalized), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 100
        assert wav_file.getnframes() == 250
        assert wav_file.getnframes() / wav_file.getframerate() == 2.5


def test_ordinary_finite_size_wav_still_works() -> None:
    original = make_pcm_wav(b"\x00\x00" * 100)
    normalized, info = normalize_pcm_wav(original)

    assert info.duration_seconds == 1.0
    with wave.open(BytesIO(normalized), "rb") as wav_file:
        assert wav_file.getnframes() == 100
        assert wav_file.getframerate() == 100


@pytest.mark.parametrize(
    "audio_bytes, message",
    [
        (make_pcm_wav(b"\x00\x00" * 4, declared_data_size=10), "truncated"),
        (make_pcm_wav(b"\x00\x00\x00"), "frame-aligned"),
    ],
)
def test_truncated_or_frame_misaligned_wav_fails_safely(audio_bytes: bytes, message: str) -> None:
    with pytest.raises(InvalidWavError, match=message):
        inspect_pcm_wav(audio_bytes)
