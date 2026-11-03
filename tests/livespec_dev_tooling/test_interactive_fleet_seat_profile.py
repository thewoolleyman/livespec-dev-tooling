"""Integration coverage for the committed interactive fleet seat profile.

The profile is intentionally data rather than launcher-local defaults: changing a
seat class must be one profile edit, and the launcher must pass the selected
class's values to Claude exactly.  A stand-in ``claude`` records the real
launcher invocation without starting a session on the test host.
"""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

# INTEGRATION TIER: this runs the committed launcher against its committed
# profile through a stand-in Claude executable, including its refusal path.
pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAUNCHER = _REPO_ROOT / "scripts" / "launch-interactive-fleet-seat.sh"
_PROFILE = _REPO_ROOT / "config" / "interactive-fleet-seat-profile.tsv"

_CLAUDE_STAND_IN = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$@" > "$SEAT_ARGS_FILE"
printf '%s\\n' "$CLAUDE_CODE_AUTO_COMPACT_WINDOW" > "$SEAT_COMPACT_WINDOW_FILE"
printf '%s\\n' "$LIVESPEC_INTERACTIVE_SEAT_LIFETIME_SECONDS" > "$SEAT_LIFETIME_FILE"
"""


def test_launcher_reads_each_committed_class_and_refuses_unknown_class(*, tmp_path: Path) -> None:
    """Every profile row drives Claude; an absent row never starts it."""
    assert _LAUNCHER.is_file(), "the committed interactive fleet seat launcher must exist"
    assert _PROFILE.is_file(), "the committed interactive fleet seat profile must exist"

    with _PROFILE.open(encoding="utf-8", newline="") as profile_file:
        rows = list(csv.DictReader(profile_file, delimiter="\t"))
    assert rows, "the fleet seat profile must define at least one class"
    assert {"coordinator", "monitor", "implementer"} <= {row["class"] for row in rows}

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    _ = claude.write_text(_CLAUDE_STAND_IN, encoding="utf-8")
    claude.chmod(0o755)
    args_file = tmp_path / "claude-args"
    compact_window_file = tmp_path / "compact-window"
    lifetime_file = tmp_path / "lifetime"
    environment = os.environ | {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "SEAT_ARGS_FILE": str(args_file),
        "SEAT_COMPACT_WINDOW_FILE": str(compact_window_file),
        "SEAT_LIFETIME_FILE": str(lifetime_file),
    }

    for row in rows:
        name = f"profile-test-{row['class']}"
        started = subprocess.run(
            [str(_LAUNCHER), row["class"], name],
            capture_output=True,
            check=False,
            env=environment,
            text=True,
        )
        assert started.returncode == 0, started.stderr
        assert args_file.read_text(encoding="utf-8").splitlines() == [
            "--model",
            row["model"],
            "--effort",
            row["effort"],
            "--dangerously-skip-permissions",
            "-n",
            name,
        ]
        assert (
            compact_window_file.read_text(encoding="utf-8").strip() == row["auto_compact_threshold"]
        )
        assert lifetime_file.read_text(encoding="utf-8").strip() == row["lifetime_seconds"]
        assert int(row["auto_compact_threshold"]) < int(row["model_context_ceiling"])

    args_file.unlink()
    refused = subprocess.run(
        [str(_LAUNCHER), "undefined-class", "must-not-start"],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )
    assert refused.returncode != 0
    assert "undefined-class" in refused.stderr
    assert not args_file.exists(), "an undefined class must be refused before Claude starts"
