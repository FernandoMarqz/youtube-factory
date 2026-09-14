"""Bootstrap command-line interface."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from youtube_factory import __version__
from youtube_factory.adapters.local import (
    FileSystemArtifactStore,
    LocalNarrationGenerator,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.application.exceptions import ContentPipelineError
from youtube_factory.application.services import SceneTimingReconciler
from youtube_factory.application.use_cases import CreateContentUseCase


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser without executing application logic."""
    parser = argparse.ArgumentParser(prog="youtube-factory", description="YouTube Factory CLI")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("status", help="Show bootstrap readiness.")
    create_content = subcommands.add_parser(
        "create-content", help="Create deterministic research, script and scene artifacts."
    )
    create_content.add_argument("--topic", required=True, help="Spanish topic to create.")
    create_content.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/projects"),
        help="Directory where project folders are written (default: data/projects).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the minimal bootstrap CLI."""
    args = build_parser().parse_args(argv)
    if args.command == "status":
        print("youtube-factory bootstrap ready")
    elif args.command == "create-content":
        use_case = CreateContentUseCase(
            research_provider=LocalResearchProvider(),
            script_generator=LocalScriptGenerator(),
            scene_planner=LocalScenePlanner(),
            narration_generator=LocalNarrationGenerator(),
            timing_reconciler=SceneTimingReconciler(),
            artifact_store=FileSystemArtifactStore(args.output_dir),
        )
        try:
            result = use_case.execute(args.topic)
        except ContentPipelineError as error:
            raise SystemExit(f"error: {error}") from error
        print(result.project_directory)
