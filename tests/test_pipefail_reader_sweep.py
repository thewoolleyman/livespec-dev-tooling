"""Regression guard for readers that can SIGPIPE a pipefail pipeline."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SHELL_TREES = ("ansible/", "ci-runner/", "dev-tooling/", "scripts/")
_AGENT_JOIN_TOKEN_EXIT_TEST = _REPO_ROOT / (
    "ci-runner/k3s/secret-reinjection/seed-k3s-agent-join-token-exit-tests.sh"
)
_EARLY_READER = re.compile(
    r"""\|\s*(?:
        grep\b(?:\s+-[^\s'\"]*)*?\s+(?:-[A-Za-z]*q[A-Za-z]*\b|--quiet\b|-m\s*1\b|-m1\b)
        |head\b\s+(?:-1\b|-n\s*1\b|-n1\b|-c\s*1\b|-c1\b)
        |awk\b[^\n]*\bexit\b
    )""",
    re.VERBOSE,
)


def _tracked_shell_paths() -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "ansible", "ci-runner", "dev-tooling", "scripts"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths: list[Path] = []
    for raw_path in completed.stdout.splitlines():
        path = _REPO_ROOT / raw_path
        if (
            raw_path.startswith(_SHELL_TREES)
            and path.is_file()
            and (path.suffix == ".sh" or path.read_text(encoding="utf-8").startswith("#!"))
        ):
            paths.append(path)
    return tuple(paths)


def _non_comment_lines(*, text: str) -> tuple[str, ...]:
    return tuple(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_pipefail_scripts_do_not_use_early_exiting_pipeline_readers() -> None:
    """A match must retain its verdict after the writer exceeds a pipe buffer."""
    violations: list[str] = []
    for path in _tracked_shell_paths():
        text = path.read_text(encoding="utf-8")
        if "pipefail" not in text:
            continue
        for line_number, line in enumerate(_non_comment_lines(text=text), start=1):
            if _EARLY_READER.search(line):
                violations.append(f"{path.relative_to(_REPO_ROOT)}:{line_number}: {line.strip()}")

    assert not violations, "\n".join(violations)


def test_pipefail_sweep_detects_an_unsafe_reader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The sweep rejects the reader shape that loses pipefail's verdict."""
    script = tmp_path / "unsafe-reader.sh"
    script.write_text("set -o pipefail\nproducer | grep -q needle\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "_tracked_shell_paths", lambda: (script,))
    monkeypatch.setitem(globals(), "_REPO_ROOT", tmp_path)

    with pytest.raises(AssertionError, match=r"unsafe-reader\.sh:2:"):
        test_pipefail_scripts_do_not_use_early_exiting_pipeline_readers()


def test_agent_join_token_exit_test_retains_its_original_verdict() -> None:
    """Replacing `grep -q` must not relax aligned-output assertions."""
    completed = subprocess.run(
        [_AGENT_JOIN_TOKEN_EXIT_TEST],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
