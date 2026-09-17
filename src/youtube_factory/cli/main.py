"""Bootstrap command-line interface."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from youtube_factory import __version__
from youtube_factory.adapters.ffmpeg import FFmpegRenderer
from youtube_factory.adapters.local import (
    FileSystemArtifactStore,
    LocalCaptionAlignmentProvider,
    LocalNarrationGenerator,
    LocalPlaceholderVisualAssetProvider,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.adapters.openai import (
    OpenAICaptionAlignmentConfig,
    OpenAICaptionAlignmentProvider,
    OpenAINarrationGenerator,
    OpenAIResearchConfig,
    OpenAIResearchProvider,
    OpenAIScenePlanner,
    OpenAIScenePlannerConfig,
    OpenAIScriptConfig,
    OpenAIScriptGenerator,
    OpenAITTSConfig,
    OpenAIVisualAssetProvider,
    OpenAIVisualConfig,
)
from youtube_factory.application.config import (
    ChannelConfig,
    get_openai_api_key,
    get_output_directory,
    load_channel_config,
    load_local_environment,
)
from youtube_factory.application.exceptions import ContentPipelineError
from youtube_factory.application.services import (
    DeterministicVisualPromptBuilder,
    SceneTimingReconciler,
)
from youtube_factory.application.use_cases import (
    CaptionProjectUseCase,
    CreateContentUseCase,
    RenderProjectUseCase,
)
from youtube_factory.ports import (
    CaptionAlignmentProvider,
    NarrationGenerator,
    Renderer,
    ResearchProvider,
    ScenePlanner,
    ScriptGenerator,
    VisualAssetProvider,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser without executing application logic."""
    parser = argparse.ArgumentParser(prog="youtube-factory", description="YouTube Factory CLI")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("status", help="Show bootstrap readiness.")
    create_content = subcommands.add_parser(
        "create-content", help="Create content, narration, timing and visual artifacts."
    )
    create_content.add_argument("--topic", required=True, help="Spanish topic to create.")
    create_content.add_argument(
        "--channel",
        default="engineering-es",
        help="Channel configuration id (default: engineering-es).",
    )
    create_content.add_argument(
        "--research-provider",
        choices=("local", "openai"),
        default=None,
        help="Optional research override; otherwise the selected channel decides.",
    )
    create_content.add_argument(
        "--script-generator",
        choices=("local", "openai"),
        default=None,
        help="Optional script-generator override; otherwise the selected channel decides.",
    )
    create_content.add_argument(
        "--scene-planner",
        choices=("local", "openai"),
        default=None,
        help="Optional scene-planner override; otherwise the selected channel decides.",
    )
    create_content.add_argument(
        "--narration-provider",
        choices=("local", "openai"),
        default=None,
        help="Optional narration override; otherwise the selected channel decides.",
    )
    create_content.add_argument(
        "--visual-provider",
        choices=("local-placeholder", "openai"),
        default=None,
        help="Optional visual override; otherwise the selected channel decides.",
    )
    create_content.add_argument(
        "--renderer",
        choices=("ffmpeg",),
        default=None,
        help="Optional renderer override; otherwise the selected channel decides.",
    )
    create_content.add_argument(
        "--caption-alignment",
        choices=("local", "openai"),
        default=None,
        help="Optional word-alignment provider override.",
    )
    create_content.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where project folders are written; overrides YOUTUBE_FACTORY_OUTPUT_DIR.",
    )
    render_project = subcommands.add_parser(
        "render-project", help="Render persisted narration, timed scenes and PNGs only."
    )
    render_project.add_argument("--project-id", required=True)
    render_project.add_argument("--channel", default="engineering-es")
    render_project.add_argument("--renderer", choices=("ffmpeg",), default=None)
    render_project.add_argument(
        "--reselect-music", action="store_true", help="Choose a new catalog track for this project."
    )
    render_project.add_argument("--output-dir", type=Path, default=None)
    caption_project = subcommands.add_parser(
        "caption-project", help="Align and caption existing narration without upstream generation."
    )
    caption_project.add_argument("--project-id", required=True)
    caption_project.add_argument("--channel", default="engineering-es")
    caption_project.add_argument("--caption-alignment", choices=("local", "openai"), default=None)
    caption_project.add_argument("--output-dir", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the minimal bootstrap CLI."""
    args = build_parser().parse_args(argv)
    if args.command == "status":
        print("youtube-factory bootstrap ready")
    elif args.command == "create-content":
        load_local_environment()
        try:
            channel = load_channel_config(args.channel)
            research_provider = build_research_provider(channel, args.research_provider)
            script_generator = build_script_generator(channel, args.script_generator)
            scene_planner = build_scene_planner(channel, args.scene_planner)
            narration_generator = build_narration_generator(channel, args.narration_provider)
            visual_asset_provider = build_visual_asset_provider(channel, args.visual_provider)
            renderer = build_renderer(channel, args.renderer)
            caption_settings = (
                channel.captions.model_copy(update={"enabled": True})
                if args.caption_alignment
                else channel.captions
            )
            aligner = (
                build_caption_alignment_provider(channel, args.caption_alignment)
                if caption_settings.enabled
                else None
            )
            if isinstance(renderer, FFmpegRenderer):
                renderer.check_available()
            store = FileSystemArtifactStore(
                args.output_dir or get_output_directory(Path("data/projects"))
            )
            use_case = CreateContentUseCase(
                research_provider=research_provider,
                script_generator=script_generator,
                scene_planner=scene_planner,
                narration_generator=narration_generator,
                timing_reconciler=SceneTimingReconciler(),
                channel_config=channel,
                visual_prompt_builder=DeterministicVisualPromptBuilder(),
                visual_asset_provider=visual_asset_provider,
                artifact_store=store,
            )
            result = use_case.execute(args.topic)
            if aligner is not None:
                CaptionProjectUseCase(store, aligner, channel).execute(str(result.project_id))
            render_use_case = RenderProjectUseCase(
                store,
                renderer,
                channel.render,
                caption_settings,
                channel.audio,
                visual_motion=channel.visual_motion,
                visual_pacing=channel.visual_pacing,
            )
            render_use_case.execute(str(result.project_id))
        except ContentPipelineError as error:
            raise SystemExit(f"error: {error}") from error
        print(result.project_directory)
    elif args.command == "render-project":
        load_local_environment()
        try:
            channel = load_channel_config(args.channel)
            output_root = args.output_dir or get_output_directory(Path("data/projects"))
            store = FileSystemArtifactStore(output_root)
            renderer = build_renderer(channel, args.renderer)
            render_use_case = RenderProjectUseCase(
                store,
                renderer,
                channel.render,
                channel.captions,
                channel.audio,
                visual_motion=channel.visual_motion,
                visual_pacing=channel.visual_pacing,
            )
            artifact = render_use_case.execute(args.project_id, reselect_music=args.reselect_music)
        except ContentPipelineError as error:
            raise SystemExit(f"error: {error}") from error
        print(output_root / args.project_id / artifact.file_path)
    elif args.command == "caption-project":
        load_local_environment()
        try:
            channel = load_channel_config(args.channel)
            output_root = args.output_dir or get_output_directory(Path("data/projects"))
            store = FileSystemArtifactStore(output_root)
            aligner = build_caption_alignment_provider(channel, args.caption_alignment)
            CaptionProjectUseCase(store, aligner, channel).execute(args.project_id)
        except ContentPipelineError as error:
            raise SystemExit(f"error: {error}") from error
        print(output_root / args.project_id / "captions.json")


def build_caption_alignment_provider(
    channel: ChannelConfig, override: str | None = None
) -> CaptionAlignmentProvider:
    provider = override or channel.captions.alignment.provider
    if provider == "local":
        return LocalCaptionAlignmentProvider()
    if provider == "openai":
        model = channel.captions.alignment.model
        if not model:
            raise ContentPipelineError("OpenAI caption alignment model is not configured")
        return OpenAICaptionAlignmentProvider(
            OpenAICaptionAlignmentConfig(get_openai_api_key("caption_alignment"), model)
        )
    raise ContentPipelineError(f"unsupported caption alignment provider: {provider}")


def build_renderer(channel: ChannelConfig, renderer_override: str | None = None) -> Renderer:
    """Select the configured renderer without an implicit fallback."""
    provider = renderer_override or channel.render.provider
    if provider == "ffmpeg":
        return FFmpegRenderer()
    raise ContentPipelineError(f"unsupported renderer: {provider}")


def build_research_provider(
    channel: ChannelConfig, research_provider_override: str | None = None
) -> ResearchProvider:
    """Compose research from channel settings with an optional CLI override."""
    provider = research_provider_override or channel.research.provider
    if provider == "local":
        return LocalResearchProvider()
    if provider == "openai":
        research = channel.research
        if research.model is None:
            raise ContentPipelineError("OpenAI channel research model is not configured")
        return OpenAIResearchProvider(
            OpenAIResearchConfig(
                api_key=get_openai_api_key("research"),
                model=research.model,
                language=channel.language,
                channel_id=channel.id,
                max_sources=research.max_sources,
            )
        )
    raise ContentPipelineError(f"unsupported research provider: {provider}")


def build_script_generator(
    channel: ChannelConfig, script_generator_override: str | None = None
) -> ScriptGenerator:
    """Compose script generation from channel settings with an optional CLI override."""
    provider = script_generator_override or channel.script.provider
    if provider == "local":
        return LocalScriptGenerator()
    if provider == "openai":
        script = channel.script
        if script.model is None:
            raise ContentPipelineError("OpenAI channel script model is not configured")
        content = channel.content
        return OpenAIScriptGenerator(
            OpenAIScriptConfig(
                api_key=get_openai_api_key("script"),
                model=script.model,
                language=channel.language,
                channel_id=channel.id,
                niche=content.niche,
                target_duration_seconds=content.target_duration_seconds,
                min_duration_seconds=content.min_duration_seconds,
                max_duration_seconds=content.max_duration_seconds,
            )
        )
    raise ContentPipelineError(f"unsupported script generator: {provider}")


def build_narration_generator(
    channel: ChannelConfig, narration_provider_override: str | None = None
) -> NarrationGenerator:
    """Compose narration from channel settings with an optional explicit provider override."""
    provider = narration_provider_override or channel.narration.provider
    if provider == "local":
        return LocalNarrationGenerator()
    if provider == "openai":
        narration = channel.narration
        if narration.model is None or narration.voice is None or narration.instructions is None:
            raise ValueError("OpenAI channel narration settings are incomplete")
        return OpenAINarrationGenerator(
            OpenAITTSConfig(
                api_key=get_openai_api_key(),
                model=narration.model,
                voice=narration.voice,
                instructions=narration.instructions,
            )
        )
    raise ValueError(f"unsupported narration provider: {provider}")


def build_scene_planner(
    channel: ChannelConfig, scene_planner_override: str | None = None
) -> ScenePlanner:
    """Compose scene planning from channel settings with an optional CLI override."""
    provider = scene_planner_override or channel.scene_planning.provider
    if provider == "local":
        return LocalScenePlanner()
    if provider == "openai":
        planning = channel.scene_planning
        if planning.model is None:
            raise ContentPipelineError("OpenAI channel scene-planning model is not configured")
        return OpenAIScenePlanner(
            OpenAIScenePlannerConfig(
                api_key=get_openai_api_key("scene_planning"),
                model=planning.model,
                language=channel.language,
                channel_id=channel.id,
                min_scenes=planning.min_scenes,
                max_scenes=planning.max_scenes,
                target_scene_duration_seconds=planning.target_scene_duration_seconds,
                visual_style=channel.visuals.style,
            )
        )
    raise ContentPipelineError(f"unsupported scene planner: {provider}")


def build_visual_asset_provider(
    channel: ChannelConfig, visual_provider_override: str | None = None
) -> VisualAssetProvider:
    """Compose visuals from channel settings with an optional explicit provider override."""
    provider = visual_provider_override or channel.visuals.provider
    if provider == "local-placeholder":
        return LocalPlaceholderVisualAssetProvider()
    if provider == "openai":
        model = channel.visuals.model
        if model is None:
            raise ContentPipelineError("OpenAI channel visual model is not configured")
        return OpenAIVisualAssetProvider(
            OpenAIVisualConfig(api_key=get_openai_api_key("visuals"), model=model)
        )
    raise ContentPipelineError(f"unsupported visual provider: {provider}")
