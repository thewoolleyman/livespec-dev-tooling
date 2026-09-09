"""Tests for dev-tooling/checks/comment_line_anchors.

The check bans line-number anchors (the `[Ll]ines?\\s+\\d+...`
pattern) in Python docstrings and `#` comments. Such anchors
silently rot on any edit to the referenced file: a single
inserted paragraph above shifts every downstream reference
without any compiler / linter / test signal. Comments should
explain WHY (non-obvious constraints, hidden invariants,
surprising behavior) — not WHAT (already obvious from
well-named identifiers + signatures). Cross-references to specs
or other code should use section names or symbol names only.

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. `main()` root-anchors
itself from `Path.cwd()`, so the monkeypatched cwd stands in for the
child's `cwd=` argument exactly, and the assertion targets are unchanged
— the int exit code plus the diagnostic text. `capsys` keeps the two
streams separate exactly as `CompletedProcess` did, so the tests that
assert specifically on `stderr` (the offending filename, the WHY/WHAT
reminder) still read the stream the check actually writes findings to.

The `git` spawn in `_git` STAYS. This check resolves the files it
inspects from the git index, so the `git init` + `git add -A` pair is
what puts the fixture inside the check's universe at all — replacing it
with an in-process stand-in would delete the behaviour under test. Its
hardcoded 3-key env is a REPLACEMENT for `os.environ`, so
`COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach that child; because
a spawn remains, this file KEEPS its `subprocess_spawn_allowlist` entry.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the clean-docstring pass, the multi-line anchor in a docstring,
the single-line anchor in a `#` comment, the string-literal fixture that
proves the scope is docstrings and comments only, the `_vendor/` skip,
and the WHY-not-WHAT reminder in the failure diagnostic. The two lines
the child reached that an in-process call cannot are the module's
vendored-path guard (`sys.path.insert`) and its
`if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns
in `[tool.coverage.report]`, so neither was ever measured here and no
new exclusion is introduced. `test_module_importable_without_running_main`
still exercises the module-load path independently.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from tests.livespec_dev_tooling.checks.config_parse_rendering import (
    assert_main_renders_the_parse_failure,
)

__all__: list[str] = []


_CHECK_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "comment_line_anchors.py"
)


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env (no os.environ).

    The env is a REPLACEMENT rather than a filtered copy of `os.environ`, so
    `COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach this child and the
    developer's own git config cannot reach the fixture.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red-Green-Replay hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "comment_line_anchors_under_test",
        str(_CHECK_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Seed the git fixture, then invoke the check's `main()` in-process under `cwd`."""
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _scaffold_target_dirs(*, root: Path) -> Path:
    target = root / ".claude-plugin" / "scripts" / "livespec"
    target.mkdir(parents=True)
    return target


def test_passes_on_clean_docstrings(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fixture with no line-number anchors → exit 0, empty stderr."""
    target = _scaffold_target_dirs(root=tmp_path)
    _ = (target / "clean.py").write_text(
        '"""A clean module docstring with no anchors."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_fails_on_line_anchor_in_docstring(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fixture with a multi-line anchor in a docstring → exit non-zero."""
    target = _scaffold_target_dirs(root=tmp_path)
    _ = (target / "polluted.py").write_text(
        '"""Per spec.md lines 100-200, this module exists."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    assert "polluted.py" in result.stderr


def test_fails_on_line_anchor_in_comment(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fixture with a single-line anchor in a `#` comment → exit non-zero."""
    target = _scaffold_target_dirs(root=tmp_path)
    _ = (target / "polluted.py").write_text(
        "from __future__ import annotations\n"
        "\n"
        "# Per spec.md line 42, this constant exists.\n"
        "_K = 1\n"
        "\n"
        "__all__: list[str] = []\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    assert "polluted.py" in result.stderr


def test_passes_when_anchor_is_in_string_literal(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fixture with an anchor inside a non-docstring string literal → exit 0.

    String literals are not comments. The check must scope to
    docstrings + `#` comments only.
    """
    target = _scaffold_target_dirs(root=tmp_path)
    _ = (target / "literal.py").write_text(
        "from __future__ import annotations\n"
        "\n"
        '_LABEL = "line 42 of the upstream file"\n'
        "\n"
        "__all__: list[str] = []\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_skips_vendored_library_files(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Anchors inside `_vendor/` are out of scope."""
    vendor_dir = tmp_path / ".claude-plugin" / "scripts" / "_vendor" / "upstream"
    vendor_dir.mkdir(parents=True)
    _ = (vendor_dir / "shipped.py").write_text(
        '"""Per upstream README lines 100-200, this lib is vendored."""\n'
        "\n"
        "__all__: list[str] = []\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main().

    Required to exercise the false arms of (a) the vendor
    `sys.path` guard at module-load time and (b) the
    `if __name__ == "__main__"` guard at the bottom — both
    untaken under subprocess invocation. Mirrors the pattern in
    `test_no_todo_registry_module_importable_without_running_main`.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "comment_line_anchors_for_import_test",
        str(_CHECK_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_failure_output_includes_why_not_what_reminder(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The failure diagnostic must include a WHY-not-WHAT reminder.

    Per the user's directive: when the check fails, the output
    should remind the author that comments should explain WHY
    (non-obvious constraints, hidden invariants), not WHAT
    (already obvious from well-named identifiers).
    """
    target = _scaffold_target_dirs(root=tmp_path)
    _ = (target / "polluted.py").write_text(
        '"""Per spec.md lines 100-200, this module exists."""\n' "\n" "__all__: list[str] = []\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    assert "WHY" in result.stderr
    assert "WHAT" in result.stderr


def test_main_renders_the_consumer_config_parse_failure(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed consumer config is a structured diagnostic, never a traceback.

    `SPECIFICATION/contracts.md` section "Configuration loader" puts the catch
    at this check's `main()` supervisor; before `livespec-dev-tooling-efxa`
    the `ConfigParseError` escaped from here as an uncaught traceback, which
    reaches stderr through the interpreter rather than through structlog and
    so broke the very output discipline this package exists to enforce.
    """
    assert_main_renders_the_parse_failure(
        module_slug="comment_line_anchors",
        check_id="comment_line_anchors",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
