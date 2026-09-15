"""Bootstrap command-line interface."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from youtube_factory import __version__
from youtube_factory.adapters.local import (
    FileSystemArtifactStore,
    LocalNarrationGenerator,
    LocalPlaceholderVisualAssetProvider,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.adapters.openai import (
    OpenAINarrationGenerator,
    OpenAIScenePlanner,
    OpenAIScenePlannerConfig,
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
from youtube_factory.application.use_cases import CreateContentUseCase
from youtube_factory.ports import NarrationGenerator, ScenePlanner, VisualAssetProvider


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
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where project folders are written; overrides YOUTUBE_FACTORY_OUTPUT_DIR.",
    )
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
            use_case = CreateContentUseCase(
                research_provider=LocalResearchProvider(),
                script_generator=LocalScriptGenerator(),
                scene_planner=build_scene_planner(channel, args.scene_planner),
                narration_generator=build_narration_generator(channel, args.narration_provider),
                timing_reconciler=SceneTimingReconciler(),
                channel_config=channel,
                visual_prompt_builder=DeterministicVisualPromptBuilder(),
                visual_asset_provider=build_visual_asset_provider(channel, args.visual_provider),
                artifact_store=FileSystemArtifactStore(
                    args.output_dir or get_output_directory(Path("data/projects"))
                ),
            )
            result = use_case.execute(args.topic)
        except ContentPipelineError as error:
            raise SystemExit(f"error: {error}") from error
        print(result.project_directory)


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
