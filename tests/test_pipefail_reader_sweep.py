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


def _early_reader_violations(*, paths: tuple[Path, ...], repo_root: Path) -> tuple[str, ...]:
    violations: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if "pipefail" not in text:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if _EARLY_READER.search(line):
                violations.append(f"{path.relative_to(repo_root)}:{line_number}: {line.strip()}")
    return tuple(violations)


def _quoted_reader_redirection_violations(
    *, paths: tuple[Path, ...], repo_root: Path
) -> tuple[str, ...]:
    """Find rewrites that accidentally turn a grep pattern into a redirection."""
    violations: list[str] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            grep = re.search(r"\|\s*grep\b", line)
            if grep and _has_quoted_redirection(line[grep.end() :]):
                violations.append(f"{path.relative_to(repo_root)}:{line_number}: {line.strip()}")
    return tuple(violations)


def _has_quoted_redirection(arguments: str) -> bool:
    """Return whether a quoted shell word contains a grep output redirection."""
    quote: str | None = None
    escaped = False
    quoted_word: list[str] = []
    for character in arguments:
        if quote is None:
            if character in "'\"":
                quote = character
                quoted_word = []
            continue
        if escaped:
            quoted_word.append(character)
            escaped = False
        elif character == "\\":
            quoted_word.append(character)
            escaped = True
        elif character == quote:
            if re.search(r">\s*/dev/null", "".join(quoted_word)):
                return True
            quote = None
        else:
            quoted_word.append(character)
    return False


def test_pipefail_reader_forms_keep_their_small_input_verdict_on_large_input() -> None:
    """Each approved rewrite preserves its match verdict past a pipe buffer."""
    for form in ("here-string", "draining-reader", "writer-status-excluded"):
        for matched in (False, True):
            expected = 0 if matched else 1

            assert _run_reader_form(form=form, matched=matched, large=False) == expected
            assert _run_reader_form(form=form, matched=matched, large=True) == expected


def test_pipefail_scripts_do_not_use_early_exiting_pipeline_readers() -> None:
    """Every sweep rewrite uses an approved whole-input or status-isolating form."""
    violations = _early_reader_violations(paths=_tracked_shell_paths(), repo_root=_REPO_ROOT)

    assert not violations, "\n".join(violations)


def test_pipefail_sweep_keeps_reader_redirections_outside_quoted_patterns() -> None:
    """A whole-input grep rewrite must not alter its pattern while adding redirection."""
    violations = _quoted_reader_redirection_violations(
        paths=_tracked_shell_paths(), repo_root=_REPO_ROOT
    )

    assert not violations, "\n".join(violations)


def test_pipefail_sweep_reports_an_early_exiting_reader(tmp_path: Path) -> None:
    """The sweep must make unsafe readers actionable rather than silently skipping them."""
    unsafe_script = tmp_path / "scripts" / "unsafe.sh"
    unsafe_script.parent.mkdir()
    unsafe_script.write_text(
        "#!/usr/bin/env bash\nset -o pipefail\nprintf 'needle\\n' | grep -q needle\n",
        encoding="utf-8",
    )

    assert _early_reader_violations(paths=(unsafe_script,), repo_root=tmp_path) == (
        "scripts/unsafe.sh:3: printf 'needle\\n' | grep -q needle",
    )


def test_pipefail_sweep_reports_a_redirection_inside_a_quoted_pattern(tmp_path: Path) -> None:
    """A redirection must follow grep's pattern, rather than becoming part of it."""
    unsafe_script = tmp_path / "scripts" / "unsafe.sh"
    unsafe_script.parent.mkdir()
    unsafe_script.write_text(
        "#!/usr/bin/env bash\nset -o pipefail\nprintf 'needle\\n' | grep 'needle >/dev/null'\n",
        encoding="utf-8",
    )

    assert _quoted_reader_redirection_violations(paths=(unsafe_script,), repo_root=tmp_path) == (
        "scripts/unsafe.sh:3: printf 'needle\\n' | grep 'needle >/dev/null'",
    )
