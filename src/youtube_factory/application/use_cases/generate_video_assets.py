"""Explicit, budgeted image-to-video generation from persisted project media."""

from hashlib import sha256
from io import BytesIO
from warnings import warn

from PIL import Image, ImageOps

from youtube_factory.application.config import (
    GenerativeVideoConfig,
    VisualMotionConfig,
    VisualPacingConfig,
)
from youtube_factory.application.exceptions import (
    GenerativeVideoConfigurationError,
    GenerativeVideoError,
)
from youtube_factory.application.services.generative_video import GenerativeVideoEligibilityPolicy
from youtube_factory.application.services.visual_motion import DeterministicVisualMotionPlanner
from youtube_factory.application.services.visual_pacing import DeterministicVisualPacingPlanner
from youtube_factory.domain.models import GeneratedVideoAsset, GenerativeVideoPlan
from youtube_factory.ports.artifact_store import ProjectArtifactStore
from youtube_factory.ports.video_assets import (
    VideoAssetProvider,
    VideoGenerationRequest,
    VideoMediaInspector,
)


class GenerateVideoAssetsUseCase:
    """Plan for free; generate only through this explicitly invoked use case."""

    def __init__(
        self,
        store: ProjectArtifactStore,
        config: GenerativeVideoConfig,
        motion: VisualMotionConfig,
        pacing: VisualPacingConfig,
        fps: int,
        inspector: VideoMediaInspector,
        provider: VideoAssetProvider | None = None,
    ) -> None:
        self._store = store
        self._config = config
        self._motion = motion
        self._pacing = pacing
        self._fps = fps
        self._inspector = inspector
        self._provider = provider

    def execute(
        self, project_id: str, *, dry_run: bool, regenerate: bool = False
    ) -> GenerativeVideoPlan:
        inputs = self._store.load_render_inputs(project_id)
        semantic = self._store.load_scene_plan(project_id)
        motion = DeterministicVisualMotionPlanner().plan(
            inputs.timed_scene_plan, inputs.visual_assets, self._motion, self._fps
        )
        pacing = DeterministicVisualPacingPlanner().plan(
            inputs.timed_scene_plan, motion, inputs.visual_assets, self._pacing, self._motion
        )
        plan = GenerativeVideoEligibilityPolicy().plan(
            inputs.timed_scene_plan, semantic, inputs.visual_assets, pacing, self._config
        )
        self._store.save_generative_video_plan(project_id, plan)
        if dry_run:
            return plan
        if not self._config.enabled or self._provider is None:
            raise GenerativeVideoConfigurationError(
                "paid video generation is disabled; set generative_video.enabled: true"
            )
        if self._provider.provider != self._config.provider:
            raise GenerativeVideoConfigurationError(
                "video provider differs from channel configuration"
            )
        existing = self._store.load_generated_videos(project_id)
        for planned in plan.scenes:
            if not planned.selected:
                continue
            old = (
                next(
                    (
                        item
                        for item in existing.assets
                        if item.scene_sequence == planned.scene_sequence
                    ),
                    None,
                )
                if existing
                else None
            )
            if old is not None and not regenerate:
                path = inputs.project_directory / old.file_path
                self._inspector.inspect(path)
                source = inputs.project_directory / planned.source_asset
                if sha256(source.read_bytes()).hexdigest() != old.source_image_sha256 or (
                    planned.prompt is not None
                    and sha256(planned.prompt.encode("utf-8")).hexdigest() != old.prompt_sha256
                ):
                    warn(
                        f"scene {planned.scene_sequence} generated video has stale source or "
                        "prompt hashes; reusing it (pass --regenerate to replace)",
                        stacklevel=2,
                    )
                continue
            source = inputs.project_directory / planned.source_asset
            original = source.read_bytes()
            with Image.open(BytesIO(original)) as image:
                reference = ImageOps.fit(
                    image.convert("RGB"),
                    (720, 1280),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
                buffer = BytesIO()
                reference.save(buffer, format="JPEG", quality=88, optimize=True)
            reference_path = self._store.save_video_reference(
                project_id, planned.scene_sequence, buffer.getvalue()
            )
            if planned.prompt is None:
                raise GenerativeVideoError("selected scene has no video prompt")
            result = self._provider.generate(
                VideoGenerationRequest(
                    scene_sequence=planned.scene_sequence,
                    reference_image=reference_path,
                    prompt=planned.prompt,
                    model=self._config.model,
                    duration_seconds=planned.target_duration_seconds,
                    timeout_seconds=self._config.timeout_seconds,
                )
            )
            path = self._store.save_generated_video_bytes(
                project_id, planned.scene_sequence, result.video_bytes
            )
            media = self._inspector.inspect(path)
            if (
                media.duration_seconds + 1 / self._fps
                < pacing.scenes[planned.scene_sequence - 1].beats[-1].frame_count / self._fps
            ):
                raise GenerativeVideoError("generated clip is shorter than its target visual beat")
            asset = GeneratedVideoAsset(
                scene_sequence=planned.scene_sequence,
                provider=self._provider.provider,
                model=self._config.model,
                file_path=f"generated-video/scene-{planned.scene_sequence:02d}.mp4",
                source_image=planned.source_asset,
                reference_image=reference_path.relative_to(inputs.project_directory).as_posix(),
                duration_seconds=media.duration_seconds,
                width=media.width,
                height=media.height,
                fps=media.fps,
                video_codec=media.video_codec,
                has_audio=media.has_audio,
                requested_seconds=planned.target_duration_seconds,
                provider_task_id=result.task_id,
                prompt_sha256=sha256(planned.prompt.encode("utf-8")).hexdigest(),
                source_image_sha256=sha256(original).hexdigest(),
                requested_at=result.requested_at,
                completed_at=result.completed_at,
            )
            self._store.save_generated_video_asset(project_id, asset)
        return plan
