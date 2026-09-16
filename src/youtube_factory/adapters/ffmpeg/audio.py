"""Deterministic FFmpeg audio-filter construction and loudness report parsing."""

import json
import math
from dataclasses import dataclass

from youtube_factory.application.config import AudioConfig
from youtube_factory.application.exceptions import AudioProcessingError

AUDIO_SAMPLE_RATE = 48000
LOUDNESS_RANGE = 11
LOUDNESS_TOLERANCE_LU = 2.0
PEAK_TOLERANCE_DB = 0.25


@dataclass(frozen=True, slots=True)
class LoudnessMeasurement:
    integrated_lufs: float | None
    true_peak_db: float | None
    loudness_range: float | None
    threshold_lufs: float | None
    target_offset_db: float | None

    @property
    def silent(self) -> bool:
        return self.integrated_lufs is None and self.true_peak_db is None


def parse_loudnorm_report(stderr: str) -> LoudnessMeasurement:
    """Decode loudnorm's JSON object while rejecting partial or non-finite measurements."""
    marker = stderr.rfind('"input_i"')
    start = stderr.rfind("{", 0, marker) if marker >= 0 else -1
    if start < 0:
        raise AudioProcessingError("loudnorm did not return measurement JSON")
    try:
        payload, _ = json.JSONDecoder().raw_decode(stderr[start:])
        integrated = float(payload["input_i"])
        peak = float(payload["input_tp"])
        if integrated == -math.inf and peak == -math.inf:
            return LoudnessMeasurement(None, None, None, None, None)
        lra = float(payload["input_lra"])
        threshold = float(payload["input_thresh"])
        offset = float(payload["target_offset"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise AudioProcessingError("loudnorm returned malformed measurement JSON") from error
    if not all(math.isfinite(value) for value in (integrated, peak, lra, threshold, offset)):
        raise AudioProcessingError("loudnorm returned non-finite measurements")
    return LoudnessMeasurement(integrated, peak, lra, threshold, offset)


def analysis_filter(config: AudioConfig, *, dual_mono: bool) -> str:
    narration = config.narration
    return (
        f"loudnorm=I={narration.target_lufs}:TP={narration.true_peak_db}:"
        f"LRA={LOUDNESS_RANGE}:dual_mono={'true' if dual_mono else 'false'}:"
        "print_format=json"
    )


def audio_filters(
    config: AudioConfig,
    narration_index: int,
    duration_seconds: float,
    narration_measurement: LoudnessMeasurement | None,
    music_index: int | None,
    music_duration_seconds: float | None,
) -> list[str]:
    """Translate semantic audio intent into a bounded, stereo 48 kHz filter graph."""
    narration = config.narration
    voice_filters = []
    if narration.normalize and narration_measurement is None:
        raise AudioProcessingError("narration normalization requires a loudnorm analysis pass")
    if (
        narration.normalize
        and narration_measurement is not None
        and not narration_measurement.silent
    ):
        measured = narration_measurement
        voice_filters.append(
            f"loudnorm=I={narration.target_lufs}:TP={narration.true_peak_db}:"
            f"LRA={LOUDNESS_RANGE}:measured_I={measured.integrated_lufs}:"
            f"measured_TP={measured.true_peak_db}:measured_LRA={measured.loudness_range}:"
            f"measured_thresh={measured.threshold_lufs}:offset={measured.target_offset_db}:"
            "linear=true:dual_mono=true:print_format=none"
        )
    voice_filters.extend(
        [
            f"aresample={AUDIO_SAMPLE_RATE}",
            "pan=stereo|c0=c0|c1=c0",
            "asetpts=PTS-STARTPTS",
        ]
    )
    filters = [f"[{narration_index}:a:0]{','.join(voice_filters)}[voice]"]
    if music_index is not None:
        music = config.music
        music_end = (
            duration_seconds
            if music.loop or music_duration_seconds is None
            else min(duration_seconds, music_duration_seconds)
        )
        music_filters = [
            f"aresample={AUDIO_SAMPLE_RATE}",
            "aformat=channel_layouts=stereo",
            f"volume={music.gain_db}dB",
            f"atrim=duration={duration_seconds:.6f}",
            "asetpts=PTS-STARTPTS",
        ]
        fade_in = min(music.fade_in_seconds, music_end)
        fade_out = min(music.fade_out_seconds, music_end)
        if fade_in > 0:
            music_filters.append(f"afade=t=in:st=0:d={fade_in:.6f}")
        if fade_out > 0:
            music_filters.append(f"afade=t=out:st={music_end - fade_out:.6f}:d={fade_out:.6f}")
        filters.append(f"[{music_index}:a:0]{','.join(music_filters)}[music]")
        if config.ducking.enabled:
            ducking = config.ducking
            filters.append("[voice]asplit=2[voice_mix][voice_sidechain]")
            filters.append(
                "[music][voice_sidechain]sidechaincompress="
                f"threshold={ducking.threshold}:ratio={ducking.ratio}:"
                f"attack={ducking.attack_ms}:release={ducking.release_ms}:"
                "makeup=1:mix=1[ducked_music]"
            )
            mix_inputs = "[voice_mix][ducked_music]"
        else:
            mix_inputs = "[voice][music]"
        filters.append(
            f"{mix_inputs}amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mixed]"
        )
    else:
        filters.append("[voice]anull[mixed]")
    # Leave 1 dB of AAC encoder headroom below the configured true-peak ceiling.
    limiter_level = 10 ** ((narration.true_peak_db - 1.0) / 20)
    filters.append(
        f"[mixed]alimiter=limit={limiter_level:.8f}:level=disabled:latency=1,"
        f"apad,atrim=duration={duration_seconds:.6f},"
        f"aresample={AUDIO_SAMPLE_RATE}[aout]"
    )
    return filters
