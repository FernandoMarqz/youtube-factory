"""Tests for the bootstrap CLI."""

import subprocess
import sys


def test_module_status_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "youtube_factory", "status"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "youtube-factory bootstrap ready"
