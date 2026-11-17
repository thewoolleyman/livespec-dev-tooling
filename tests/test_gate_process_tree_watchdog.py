"""A quiet gate container prints its own process tree, bounded, so an abandoned Job's logs name the hung step.

`ci-runner/k3s/phase2/gates/gate-process-tree-watchdog.sh` is inlined by
render-gate-job.sh into the gate container's script (livespec-dev-tooling-yrjatv).
The delegated client holds no pods/exec credential, so the POD prints the tree and
the client's saved last-200-lines file carries it. These tests run the shipped
functions in a real bash with a fake `ps` first on PATH, and run the real renderer
to prove the functions and their start reach the manifest.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[1]
_GATES = _REPO / "ci-runner" / "k3s" / "phase2" / "gates"
_WATCHDOG = _GATES / "gate-process-tree-watchdog.sh"
_RENDERER = _GATES / "render-gate-job.sh"
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_HEADER = ":: gate: process tree at"
_MARKER = "FAKE-PS-ROW"
_ROWS = 500
_BOUND = 7


def _fake_ps(*, tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "ps"
    body = f'#!/bin/bash\nfor i in $(seq 1 {_ROWS}); do echo "{_MARKER} $i"; done\n'
    _ = script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    return bin_dir


def _watch(*, tmp_path: Path, log_age_seconds: int, quiet: int, watch_seconds: str) -> str:
    """Run the watchdog over a recipe log of the given age and return what it printed."""
    bin_dir = _fake_ps(tmp_path=tmp_path)
    log = tmp_path / "recipe.log"
    _ = log.write_text("", encoding="utf-8")
    stamp = log.stat().st_mtime - log_age_seconds
    os.utime(log, (stamp, stamp))
    runner = tmp_path / "run.sh"
    lines = [
        "#!/bin/bash",
        f"source '{_WATCHDOG}'",
        f"gate_process_tree_watchdog '{log}' &",
        "pid=$!",
        f"sleep {watch_seconds}",
        'kill "$pid"',
        'wait "$pid" 2>/dev/null',
        "true",
    ]
    _ = runner.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),
        "GATE_PROCESS_TREE_QUIET_SECONDS": str(quiet),
        "GATE_PROCESS_TREE_TICK_SECONDS": "0.2",
        "GATE_PROCESS_TREE_MAX_LINES": str(_BOUND),
    }
    done = subprocess.run(
        ["bash", str(runner)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    return done.stdout


@pytest.mark.integration
def test_a_quiet_container_prints_a_bounded_process_tree_again_and_again(*, tmp_path: Path) -> None:
    """Once the recipe log is quiet, the tree repeats every quiet interval, each dump bounded."""
    out = _watch(tmp_path=tmp_path, log_age_seconds=3600, quiet=1, watch_seconds="3.5")
    assert out.count(_HEADER) >= 2
    assert out.count(_MARKER) <= out.count(_HEADER) * _BOUND
    assert _MARKER in out
    assert len(out.splitlines()) <= out.count(_HEADER) * (_BOUND + 1)


@pytest.mark.integration
def test_a_container_still_producing_output_prints_no_tree(*, tmp_path: Path) -> None:
    """A recipe log written moments ago is not quiet, so no tree is printed."""
    out = _watch(tmp_path=tmp_path, log_age_seconds=0, quiet=3600, watch_seconds="1")
    assert _HEADER not in out


@pytest.mark.integration
def test_the_rendered_manifest_starts_the_watchdog_and_prints_a_last_tree_before_the_kill(
    *, tmp_path: Path
) -> None:
    """The renderer inlines the functions, starts them, and the pod prints one more tree at preStop."""
    done = subprocess.run(
        [str(_RENDERER), "--repo-root", str(_REPO), "--tree-hash", _TREE],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert "gate_process_tree_watchdog() {" in done.stdout
    assert 'gate_process_tree_watchdog "${recipe_log}" &' in done.stdout
    assert "@@" not in done.stdout
    assert "preStop:" in done.stdout
