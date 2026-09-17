"""Frame-exact visual beats derived from existing scene-level motion."""

from hashlib import sha256
from math import ceil

from youtube_factory.application.config import VisualMotionConfig, VisualPacingConfig
from youtube_factory.application.exceptions import RenderValidationError
from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import (
    SceneMotion,
    SceneVisualPacing,
    TimedScenePlan,
    VisualAssetManifest,
    VisualBeat,
    VisualMotionPlan,
    VisualPacingPlan,
)


class DeterministicVisualPacingPlanner:
    identifier = "deterministic-visual-pacing-v1"

    def plan(
        self,
        timed: TimedScenePlan,
        motion: VisualMotionPlan,
        assets: VisualAssetManifest,
        pacing: VisualPacingConfig,
        bounds: VisualMotionConfig,
    ) -> VisualPacingPlan:
        if (
            timed.topic_id != motion.topic_id
            or timed.topic_id != assets.topic_id
            or len(timed.scenes) != len(motion.scenes)
            or len(timed.scenes) != len(assets.assets)
        ):
            raise RenderValidationError("visual pacing inputs do not share scenes and topic")
        planned: list[SceneVisualPacing] = []
        minimum_frames = ceil(pacing.min_beat_duration_seconds * motion.fps)
        for scene, scene_motion, asset in zip(
            timed.scenes, motion.scenes, assets.assets, strict=True
        ):
            if (
                scene.sequence != scene_motion.scene_sequence
                or scene.sequence != asset.scene_sequence
                or abs(scene.duration_seconds - scene_motion.duration_seconds) > 0.001
            ):
                raise RenderValidationError("visual pacing scene, motion and asset differ")
            start = round(scene.start_seconds * motion.fps)
            end = round(scene.end_seconds * motion.fps)
            frames = end - start
            if frames < 1:
                raise RenderValidationError(f"scene {scene.sequence} has no video frames")
            split = self._should_split(scene.asset_type, frames, motion, pacing, minimum_frames)
            if scene_motion.motion_type == "static":
                split = False
            if split:
                digest = sha256(f"{timed.topic_id}:{scene.sequence}:beat".encode()).digest()
                ratio = pacing.split_ratios[digest[0] % len(pacing.split_ratios)]
                first_frames = round(frames * ratio)
                if min(first_frames, frames - first_frames) < minimum_frames:
                    split = False
            if split:
                mid = start + first_frames
                first, second = self._split_motion(
                    scene_motion, start, mid, end, motion.fps, bounds, pacing, digest
                )
                beats = [first, second]
            else:
                beats = [self._beat(scene_motion, 1, start, end, motion.fps)]
            planned.append(
                SceneVisualPacing(
                    scene_sequence=scene.sequence,
                    start_frame=start,
                    end_frame=end,
                    beats=beats,
                )
            )
        return VisualPacingPlan(
            identifier=self.identifier,
            topic_id=timed.topic_id,
            fps=motion.fps,
            enabled=pacing.enabled,
            scenes=planned,
        )

    @staticmethod
    def _should_split(
        asset_type: AssetType,
        frames: int,
        motion: VisualMotionPlan,
        pacing: VisualPacingConfig,
        minimum_frames: int,
    ) -> bool:
        if (
            not pacing.enabled
            or not motion.enabled
            or pacing.max_beats_per_scene < 2
            or frames < 2 * minimum_frames
            or asset_type == AssetType.DIAGRAM
        ):
            return False
        duration = frames / motion.fps
        if asset_type == AssetType.ANIMATION:
            return duration >= pacing.second_beat_seconds
        return duration >= pacing.strongly_prefer_second_beat_seconds

    @staticmethod
    def _beat(
        source: SceneMotion,
        sequence: int,
        start: int,
        end: int,
        fps: int,
        **geometry: object,
    ) -> VisualBeat:
        return VisualBeat.model_validate(
            {
                **source.model_dump(),
                **geometry,
                "beat_sequence": sequence,
                "start_frame": start,
                "end_frame": end,
                "frame_count": end - start,
                "duration_seconds": (end - start) / fps,
            }
        )

    def _split_motion(
        self,
        source: SceneMotion,
        start: int,
        mid: int,
        end: int,
        fps: int,
        bounds: VisualMotionConfig,
        pacing: VisualPacingConfig,
        digest: bytes,
    ) -> tuple[VisualBeat, VisualBeat]:
        # A small midpoint detour creates a second camera intent without a framing reset.
        midpoint_zoom = (source.start_zoom + source.end_zoom) / 2
        if source.motion_type in ("pan_left", "pan_right", "pan_up", "pan_down"):
            midpoint_zoom = max(bounds.zoom_min, midpoint_zoom - 0.012)
        midpoint_zoom = round(min(bounds.zoom_max, max(bounds.zoom_min, midpoint_zoom)), 6)
        sideways = 0.08 if digest[1] % 2 else -0.08
        middle_x = round(
            max(0.0, min(1.0, (source.pan_x_start + source.pan_x_end) / 2 + sideways)), 6
        )
        middle_y = round((source.pan_y_start + source.pan_y_end) / 2, 6)
        if not pacing.preserve_continuity:
            second_x = round(max(0.0, min(1.0, middle_x + sideways)), 6)
        else:
            second_x = middle_x
        second_type = "pan_zoom_in" if source.end_zoom >= midpoint_zoom else "pan_zoom_out"
        if second_type == source.motion_type:
            second_type = "pan_left" if source.pan_x_end < middle_x else "pan_right"
        first = self._beat(
            source,
            1,
            start,
            mid,
            fps,
            end_zoom=midpoint_zoom,
            pan_x_end=middle_x,
            pan_y_end=middle_y,
        )
        second = self._beat(
            source,
            2,
            mid,
            end,
            fps,
            motion_type=second_type,
            start_zoom=midpoint_zoom,
            pan_x_start=second_x,
            pan_y_start=middle_y,
        )
        return first, second
