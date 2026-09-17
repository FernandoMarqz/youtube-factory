"""Deterministic, provider-neutral motion choices for persisted still images."""

from hashlib import sha256

from youtube_factory.application.config.models import VisualMotionConfig
from youtube_factory.application.exceptions import RenderValidationError
from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import (
    SceneMotion,
    TimedScenePlan,
    VisualAssetManifest,
    VisualMotionPlan,
)
from youtube_factory.domain.models.contracts import MotionType


class DeterministicVisualMotionPlanner:
    identifier = "deterministic-visual-motion-v1"

    def plan(
        self,
        timed: TimedScenePlan,
        assets: VisualAssetManifest,
        config: VisualMotionConfig,
        fps: int,
    ) -> VisualMotionPlan:
        if timed.topic_id != assets.topic_id or len(timed.scenes) != len(assets.assets):
            raise RenderValidationError("motion inputs do not match timed scenes and visual assets")
        motions: list[SceneMotion] = []
        previous: str | None = None
        for scene, asset in zip(timed.scenes, assets.assets, strict=True):
            if scene.sequence != asset.scene_sequence:
                raise RenderValidationError("motion scene and asset sequences do not match")
            choices: list[MotionType] = (
                ["static"] if not config.enabled else list(config.allowed_motion_types)
            )
            description = f"{scene.visual_intent} {scene.visual_description}".casefold()
            preferred: tuple[MotionType, ...]
            if scene.asset_type == AssetType.DIAGRAM or "comparaci" in description:
                preferred = ("static", "slow_zoom_out", "slow_zoom_in")
            elif "primer plano" in description:
                preferred = ("slow_zoom_in", "pan_zoom_in")
            elif "sección" in description or "seccion" in description:
                preferred = ("pan_down", "slow_zoom_in")
            elif scene.asset_type == AssetType.ANIMATION:
                preferred = ("pan_zoom_in", "pan_zoom_out", "pan_left", "pan_right")
            else:
                preferred = ("slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right")
            pool = [name for name in preferred if name in choices] or choices
            if config.avoid_adjacent_repeat and len(pool) > 1:
                pool = [name for name in pool if name != previous]
            digest = sha256(f"{timed.topic_id}:{scene.sequence}".encode()).digest()
            motion = pool[int.from_bytes(digest[:4], "big") % len(pool)]
            previous = motion
            fraction = (digest[4] % 4 + 4) / 7
            strength = (config.zoom_max - config.zoom_min) * fraction
            low = config.zoom_min
            high = low + strength
            # Available zoom bounds the effective pan; requested pan is an upper limit.
            pan_zoom = high
            pan_range = min(config.pan_max_percent, (pan_zoom - 1) / (2 * pan_zoom))
            delta = pan_range / max((pan_zoom - 1) / pan_zoom, 1e-9)
            start_zoom, end_zoom = low, high
            x0 = x1 = y0 = y1 = 0.5
            if motion == "slow_zoom_out":
                start_zoom, end_zoom = high, low
            elif motion in ("pan_left", "pan_right", "pan_up", "pan_down"):
                start_zoom = end_zoom = pan_zoom
            elif motion == "pan_zoom_in":
                start_zoom, end_zoom = max(low, pan_zoom - strength / 3), pan_zoom
            elif motion == "pan_zoom_out":
                start_zoom, end_zoom = pan_zoom, max(low, pan_zoom - strength / 3)
            elif motion == "static":
                start_zoom = end_zoom = 1.0
            if motion in ("pan_left", "pan_zoom_out"):
                x0, x1 = 0.5 + delta, 0.5 - delta
            elif motion in ("pan_right", "pan_zoom_in"):
                x0, x1 = 0.5 - delta, 0.5 + delta
            elif motion == "pan_up":
                y0, y1 = 0.5 + delta, 0.5 - delta
            elif motion == "pan_down":
                y0, y1 = 0.5 - delta, 0.5 + delta
            motions.append(
                SceneMotion(
                    scene_sequence=scene.sequence,
                    motion_type=motion,
                    duration_seconds=scene.duration_seconds,
                    start_zoom=round(start_zoom, 6),
                    end_zoom=round(end_zoom, 6),
                    pan_x_start=round(x0, 6),
                    pan_x_end=round(x1, 6),
                    pan_y_start=round(y0, 6),
                    pan_y_end=round(y1, 6),
                )
            )
        return VisualMotionPlan(
            identifier=self.identifier,
            topic_id=timed.topic_id,
            fps=fps,
            enabled=config.enabled,
            scenes=motions,
        )
