"""Strict RIFF/WAV PCM inspection and normalization without external media tooling."""

from dataclasses import dataclass
from struct import pack, unpack_from

_UNKNOWN_STREAM_SIZE = 0xFFFFFFFF
_RIFF_HEADER_SIZE = 12
_CHUNK_HEADER_SIZE = 8
_PCM_FORMAT = 1


class InvalidWavError(ValueError):
    """Raised when bytes cannot be safely interpreted as supported PCM WAV audio."""


@dataclass(frozen=True, slots=True)
class WavPcmInfo:
    """Physical PCM layout measured from a RIFF/WAV byte sequence."""

    channels: int
    sample_width_bytes: int
    sample_rate_hz: int
    data_offset: int
    data_size: int

    @property
    def frame_size_bytes(self) -> int:
        """Return the byte width of one interleaved PCM frame."""
        return self.channels * self.sample_width_bytes

    @property
    def frame_count(self) -> int:
        """Return the count derived from physically available, aligned PCM bytes."""
        return self.data_size // self.frame_size_bytes

    @property
    def duration_seconds(self) -> float:
        """Return duration derived from actual PCM data, not declared RIFF chunk sizes."""
        return self.data_size / (self.sample_rate_hz * self.frame_size_bytes)


def inspect_pcm_wav(audio_bytes: bytes) -> WavPcmInfo:
    """Locate and validate PCM WAV chunks, respecting RIFF padding and physical boundaries."""
    if len(audio_bytes) < _RIFF_HEADER_SIZE:
        raise InvalidWavError("WAV artifact is shorter than a RIFF header")
    if audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        raise InvalidWavError("audio artifact is not a RIFF/WAV file")

    fmt_values: tuple[int, int, int, int, int] | None = None
    data_offset: int | None = None
    data_size: int | None = None
    cursor = _RIFF_HEADER_SIZE
    while cursor < len(audio_bytes):
        if len(audio_bytes) - cursor < _CHUNK_HEADER_SIZE:
            raise InvalidWavError("WAV artifact has a truncated chunk header")
        chunk_id = audio_bytes[cursor : cursor + 4]
        declared_size = unpack_from("<I", audio_bytes, cursor + 4)[0]
        chunk_data_offset = cursor + _CHUNK_HEADER_SIZE
        remaining_bytes = len(audio_bytes) - chunk_data_offset

        if chunk_id == b"data":
            if declared_size == _UNKNOWN_STREAM_SIZE:
                physical_size = remaining_bytes
                next_cursor = len(audio_bytes)
            else:
                if declared_size > remaining_bytes:
                    raise InvalidWavError("WAV data chunk is truncated")
                physical_size = declared_size
                next_cursor = chunk_data_offset + declared_size + (declared_size % 2)
                if next_cursor > len(audio_bytes):
                    raise InvalidWavError("WAV data chunk padding is truncated")
            if data_offset is None:
                data_offset = chunk_data_offset
                data_size = physical_size
            cursor = next_cursor
            continue

        if declared_size == _UNKNOWN_STREAM_SIZE or declared_size > remaining_bytes:
            raise InvalidWavError("WAV chunk is truncated or has an unknown non-data size")
        chunk_end = chunk_data_offset + declared_size
        next_cursor = chunk_end + (declared_size % 2)
        if next_cursor > len(audio_bytes):
            raise InvalidWavError("WAV chunk padding is truncated")
        if chunk_id == b"fmt ":
            if declared_size < 16:
                raise InvalidWavError("WAV fmt chunk is too short")
            audio_format, channels, sample_rate_hz, _, block_align, bits_per_sample = unpack_from(
                "<HHIIHH", audio_bytes, chunk_data_offset
            )
            fmt_values = (
                audio_format,
                channels,
                sample_rate_hz,
                block_align,
                bits_per_sample,
            )
        cursor = next_cursor

    if fmt_values is None or data_offset is None or data_size is None:
        raise InvalidWavError("WAV artifact must contain fmt and data chunks")

    audio_format, channels, sample_rate_hz, block_align, bits_per_sample = fmt_values
    if audio_format != _PCM_FORMAT:
        raise InvalidWavError("WAV audio format must be PCM")
    if channels <= 0 or sample_rate_hz <= 0:
        raise InvalidWavError("WAV channels and sample rate must be positive")
    if bits_per_sample <= 0 or bits_per_sample % 8 != 0:
        raise InvalidWavError("WAV sample width must be a positive whole number of bytes")
    sample_width_bytes = bits_per_sample // 8
    frame_size_bytes = channels * sample_width_bytes
    if block_align != frame_size_bytes:
        raise InvalidWavError("WAV block alignment does not match its PCM format")
    if data_size == 0:
        raise InvalidWavError("WAV data payload must not be empty")
    if data_size % frame_size_bytes != 0:
        raise InvalidWavError("WAV data payload is not frame-aligned")
    return WavPcmInfo(
        channels=channels,
        sample_width_bytes=sample_width_bytes,
        sample_rate_hz=sample_rate_hz,
        data_offset=data_offset,
        data_size=data_size,
    )


def normalize_pcm_wav(audio_bytes: bytes) -> tuple[bytes, WavPcmInfo]:
    """Rebuild a canonical PCM WAV header while preserving the validated PCM payload exactly."""
    info = inspect_pcm_wav(audio_bytes)
    pcm_payload = audio_bytes[info.data_offset : info.data_offset + info.data_size]
    byte_rate = info.sample_rate_hz * info.frame_size_bytes
    if byte_rate > _UNKNOWN_STREAM_SIZE:
        raise InvalidWavError("WAV byte rate exceeds RIFF limits")
    data_padding = b"\x00" if len(pcm_payload) % 2 else b""
    fmt_chunk = pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,
        _PCM_FORMAT,
        info.channels,
        info.sample_rate_hz,
        byte_rate,
        info.frame_size_bytes,
        info.sample_width_bytes * 8,
    )
    data_chunk = b"data" + pack("<I", len(pcm_payload)) + pcm_payload + data_padding
    riff_body = b"WAVE" + fmt_chunk + data_chunk
    return b"RIFF" + pack("<I", len(riff_body)) + riff_body, info
