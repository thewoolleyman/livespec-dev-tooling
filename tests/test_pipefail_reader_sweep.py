"""Regression guards for shell readers that can SIGPIPE a pipefail pipeline."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SHELL_TREES = ("ansible/", "ci-runner/", "dev-tooling/", "scripts/")
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


def _run_reader_form(*, form: str, matched: bool, large: bool) -> int:
    value = "needle\n" if matched else "other\n"
    if large:
        value += "padding\n" * 20000
    programs = {
        "here-string": 'value=$(cat); grep -q needle <<<"$value"',
        "draining-reader": 'value=$(cat); printf "%s" "$value" | grep needle >/dev/null',
        "writer-status-excluded": (
            'value=$(cat); first=$({ printf "%s" "$value" || true; } | head -n 1); '
            '[ "$first" = needle ]'
        ),
    }
    completed = subprocess.run(
        ["bash", "-o", "pipefail", "-c", programs[form]],
        check=False,
        input=value,
        text=True,
    )
    return completed.returncode


def test_pipefail_reader_forms_keep_their_small_input_verdict_on_large_input() -> None:
    """Each approved rewrite preserves its match verdict past a pipe buffer."""
    for form in ("here-string", "draining-reader", "writer-status-excluded"):
        for matched in (False, True):
            expected = 0 if matched else 1

            assert _run_reader_form(form=form, matched=matched, large=False) == expected
            assert _run_reader_form(form=form, matched=matched, large=True) == expected


def test_pipefail_scripts_do_not_use_early_exiting_pipeline_readers() -> None:
    """Every sweep rewrite uses an approved whole-input or status-isolating form."""
    violations: list[str] = []
    for path in _tracked_shell_paths():
        text = path.read_text(encoding="utf-8")
        if "pipefail" not in text:
            continue
        for line_number, line in enumerate(_non_comment_lines(text=text), start=1):
            if _EARLY_READER.search(line):
                violations.append(f"{path.relative_to(_REPO_ROOT)}:{line_number}: {line.strip()}")

    assert not violations, "\n".join(violations)
