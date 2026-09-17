"""Offline audio configuration, filter construction and real FFmpeg mix tests."""

import math
import shutil
import struct
import subprocess
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_rendering import fixture_project

from youtube_factory.adapters.ffmpeg import FFmpegRenderer
from youtube_factory.adapters.ffmpeg.audio import LoudnessMeasurement, parse_loudnorm_report
from youtube_factory.adapters.local import LocalCaptionAlignmentProvider
from youtube_factory.application.config import AudioConfig, load_channel_config
from youtube_factory.application.exceptions import (
    AudioProcessingError,
    AudioValidationError,
    MusicAssetError,
)
from youtube_factory.application.use_cases import CaptionProjectUseCase, RenderProjectUseCase
from youtube_factory.domain.models import AudioMixReport, ContentManifest


def _audio_config(*, music: bool = False, loop: bool = True) -> AudioConfig:
    config = load_channel_config("engineering-es").audio.model_dump()
    config["music"] |= {
        "enabled": music,
        "mode": "manual",
        "file_path": "assets/music/test.wav" if music else None,
        "loop": loop,
        "fade_in_seconds": 0.1,
        "fade_out_seconds": 0.1,
    }
    return AudioConfig.model_validate(config)


def _tone_wav(
    path: Path,
    *,
    frequency: float,
    seconds: float,
    amplitude: float,
    channels: int,
    sample_rate: int,
    voiced_seconds: float | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for index in range(round(seconds * sample_rate)):
            signal = (
                amplitude * math.sin(2 * math.pi * frequency * index / sample_rate)
                if voiced_seconds is None or index < voiced_seconds * sample_rate
                else 0
            )
            frames.extend(struct.pack("<h", round(signal * 32767)) * channels)
        wav.writeframes(frames)


def test_audio_config_is_typed_immutable_and_validated() -> None:
    config = load_channel_config("engineering-es").audio
    assert config.narration.normalize
    assert config.narration.target_lufs == -16
    assert config.narration.true_peak_db == -1.5
    assert config.music.enabled and config.music.mode == "catalog"
    with pytest.raises(ValidationError):
        config.music.gain_db = 0
    for section, change in (
        ("narration", {"target_lufs": -5}),
        ("narration", {"true_peak_db": 0}),
        ("music", {"enabled": True, "mode": "manual", "file_path": None}),
        ("music", {"enabled": True, "mode": "manual", "file_path": "../secret.mp3"}),
        ("music", {"gain_db": 2}),
        ("music", {"fade_in_seconds": -1}),
        ("ducking", {"ratio": 0}),
        ("ducking", {"attack_ms": 0}),
        ("ducking", {"release_ms": -1}),
    ):
        payload = config.model_dump()
        payload[section] |= change
        with pytest.raises(ValidationError):
            AudioConfig.model_validate(payload)


def test_loudnorm_json_parsing_and_invalid_measurements() -> None:
    valid = (
        'prefix\n{ "input_i": "-25.10", "input_tp": "-10.00", '
        '"input_lra": "1.20", "input_thresh": "-35.00", '
        '"target_offset": "0.03" }\nsuffix'
    )
    assert parse_loudnorm_report(valid).integrated_lufs == -25.1
    silent = valid.replace("-25.10", "-inf").replace("-10.00", "-inf")
    assert parse_loudnorm_report(silent).silent
    with pytest.raises(AudioProcessingError, match="measurement JSON"):
        parse_loudnorm_report("no report")
    with pytest.raises(AudioProcessingError, match="non-finite"):
        parse_loudnorm_report(valid.replace("-25.10", "nan"))


def test_music_input_and_audio_filter_graph_are_explicit(tmp_path: Path) -> None:
    _, _, inputs = fixture_project(tmp_path)
    renderer = FFmpegRenderer()
    music = _audio_config(music=True)
    prepared = replace(inputs, audio=music)
    with pytest.raises(MusicAssetError, match="missing"):
        renderer._music_input("ffprobe", prepared)
    music_path = inputs.project_directory / "assets/music/test.wav"
    music_path.parent.mkdir(parents=True)
    music_path.write_bytes(b"not media")
    renderer._run = lambda command, stage: '{"streams":[{"codec_type":"video"}]}'  # type: ignore[method-assign]
    with pytest.raises(MusicAssetError, match="no valid audio stream"):
        renderer._music_input("ffprobe", prepared)
    measured = LoudnessMeasurement(-25, -10, 1, -35, 0)
    command = FFmpegRenderer.build_command(
        "ffmpeg",
        prepared,
        load_channel_config("engineering-es").render,
        tmp_path / "out.mp4",
        narration_measurement=measured,
        music_path=music_path,
        music_duration_seconds=0.4,
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "-stream_loop" in command and command[command.index("-stream_loop") + 1] == "-1"
    assert "measured_I=-25" in graph
    assert "volume=-22.0dB" in graph
    assert "afade=t=in:st=0:d=0.100000" in graph
    assert "afade=t=out:st=1.900000:d=0.100000" in graph
    assert "sidechaincompress=threshold=0.03:ratio=8.0" in graph
    assert "amix=inputs=2:duration=first:dropout_transition=0:normalize=0" in graph
    assert "alimiter=" in graph
    assert command[command.index("-map") + 3] == "[aout]"
    no_music = replace(inputs, audio=_audio_config())
    plain = FFmpegRenderer.build_command(
        "ffmpeg",
        no_music,
        load_channel_config("engineering-es").render,
        tmp_path / "plain.mp4",
        narration_measurement=measured,
    )
    plain_graph = plain[plain.index("-filter_complex") + 1]
    assert "sidechaincompress" not in plain_graph
    assert "[voice]anull[mixed]" in plain_graph
    assert "-stream_loop" not in plain
    unlooped = replace(prepared, audio=_audio_config(music=True, loop=False))
    no_loop = FFmpegRenderer.build_command(
        "ffmpeg",
        unlooped,
        load_channel_config("engineering-es").render,
        tmp_path / "unlooped.mp4",
        narration_measurement=measured,
        music_path=music_path,
        music_duration_seconds=0.4,
    )
    no_loop_graph = no_loop[no_loop.index("-filter_complex") + 1]
    assert "-stream_loop" not in no_loop
    assert "afade=t=out:st=0.300000:d=0.100000" in no_loop_graph


def test_audio_validation_rejects_excess_peak_and_loudness(tmp_path: Path) -> None:
    _, _, inputs = fixture_project(tmp_path)
    prepared = replace(inputs, audio=_audio_config())
    voice = LoudnessMeasurement(-25, -10, 1, -35, 0)
    with pytest.raises(AudioValidationError, match="true peak"):
        FFmpegRenderer._validate_audio(prepared, voice, LoudnessMeasurement(-16, -0.5, 1, -26, 0))
    with pytest.raises(AudioValidationError, match="integrated loudness"):
        FFmpegRenderer._validate_audio(prepared, voice, LoudnessMeasurement(-21, -3, 1, -31, 0))
    FFmpegRenderer._validate_audio(
        prepared,
        LoudnessMeasurement(None, None, None, None, None),
        LoudnessMeasurement(None, None, None, None, None),
    )
    with pytest.raises(AudioValidationError, match="silent despite audible"):
        FFmpegRenderer._validate_audio(
            prepared, voice, LoudnessMeasurement(None, None, None, None, None)
        )


def _music_amplitude(samples: bytes, start: float, end: float) -> float:
    rate = 48000
    pcm = memoryview(samples).cast("h")
    left = round(start * rate)
    right = round(end * rate)
    sine = cosine = 0.0
    for index in range(left, right):
        value = pcm[index * 2] / 32768
        angle = 2 * math.pi * 440 * index / rate
        sine += value * math.sin(angle)
        cosine += value * math.cos(angle)
    return 2 * math.hypot(sine, cosine) / (right - left)


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable"
)
def test_real_normalized_music_ducking_and_captioned_mp4(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    directory = inputs.project_directory
    _tone_wav(
        directory / "narration.wav",
        frequency=620,
        seconds=2,
        amplitude=0.03,
        channels=1,
        sample_rate=16000,
        voiced_seconds=1,
    )
    _tone_wav(
        directory / "assets/music/test.wav",
        frequency=440,
        seconds=0.4,
        amplitude=0.25,
        channels=2,
        sample_rate=22050,
    )
    channel = load_channel_config("engineering-es")
    CaptionProjectUseCase(store, LocalCaptionAlignmentProvider(), channel).execute(project_id)
    source_paths = [
        directory / name
        for name in (
            "narration.wav",
            "assets/music/test.wav",
            "word-alignment.json",
            "captions.json",
            "visual-assets.json",
        )
    ]
    before = [path.read_bytes() for path in source_paths]
    config = _audio_config(music=True)
    artifact = RenderProjectUseCase(
        store, FFmpegRenderer(), channel.render, channel.captions, config
    ).execute(project_id)
    assert artifact.audio_mix is not None
    report = artifact.audio_mix
    assert isinstance(report, AudioMixReport)
    assert report.normalization_enabled and report.music_enabled and report.ducking_enabled
    assert report.narration_input_lufs is not None
    assert report.final_integrated_lufs is not None
    assert abs(report.final_integrated_lufs - config.narration.target_lufs) <= 2
    assert report.final_true_peak_db is not None
    assert report.final_true_peak_db <= config.narration.true_peak_db + 0.25
    assert (artifact.audio_sample_rate_hz, artifact.audio_channels) == (48000, 2)
    assert (artifact.width, artifact.height, artifact.frame_rate) == (1080, 1920, 30)
    assert (artifact.video_codec, artifact.audio_codec, artifact.pixel_format) == (
        "h264",
        "aac",
        "yuv420p",
    )
    assert abs(artifact.duration_seconds - 2) <= 2 / 30
    assert (directory / "audio-mix.json").is_file()
    manifest = ContentManifest.model_validate_json((directory / "manifest.json").read_text("utf-8"))
    assert "audio-mix.json" in manifest.artifacts
    assert manifest.audio_mixer is not None and manifest.audio_mixer.music_enabled
    decoded = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(directory / "render/short.mp4"),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert _music_amplitude(decoded, 1.3, 1.6) > 1.3 * _music_amplitude(decoded, 0.5, 0.8)
    assert _music_amplitude(decoded, 0.02, 0.06) < _music_amplitude(decoded, 0.2, 0.3)
    assert _music_amplitude(decoded, 1.94, 1.98) < _music_amplitude(decoded, 1.7, 1.8)
    assert [path.read_bytes() for path in source_paths] == before
    quieter_music = AudioConfig.model_validate(
        config.model_dump() | {"music": config.music.model_dump() | {"gain_db": -28.0}}
    )
    RenderProjectUseCase(
        store, FFmpegRenderer(), channel.render, channel.captions, quieter_music
    ).execute(project_id)
    assert [path.read_bytes() for path in source_paths] == before
    assert "-28" in (directory / "audio-mix.json").read_text("utf-8")


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable"
)
def test_real_narration_only_normalization(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    _tone_wav(
        inputs.project_directory / "narration.wav",
        frequency=620,
        seconds=2,
        amplitude=0.02,
        channels=1,
        sample_rate=16000,
    )
    channel = load_channel_config("engineering-es")
    narration_only = _audio_config()
    artifact = RenderProjectUseCase(
        store, FFmpegRenderer(), channel.render, audio=narration_only
    ).execute(project_id)
    assert artifact.audio_mix is not None
    assert artifact.audio_mix.normalization_enabled
    assert not artifact.audio_mix.music_enabled
    assert artifact.audio_mix.final_integrated_lufs is not None
    assert abs(artifact.audio_mix.final_integrated_lufs + 16) <= 2
    assert artifact.audio_mix.final_true_peak_db is not None
    assert artifact.audio_mix.final_true_peak_db <= -1.25
    assert artifact.audio_codec == "aac"
