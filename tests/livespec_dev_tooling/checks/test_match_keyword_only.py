"""Outside-in test for `livespec_dev_tooling/checks/match_keyword_only.py` — keyword-pattern destructuring.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-match-keyword-only` row), every `match`
statement's class pattern resolving to a livespec-authored class
binds via keyword sub-patterns (`Foo(x=x)`), not positional
(`Foo(x)`). Third-party `returns`-package types (`Success`,
`Failure`, `IOSuccess`, `IOFailure`) are permitted positionally
because their `__match_args__` is upstream-fixed.

The check now resolves the files it inspects from the git-derived
first-party `.py` universe (`config.resolve_check_universe`),
root-anchored via `config.resolve_repo_root`, rather than a
`config.source_trees` walk — so each fixture is a real git repo
(`git init` + `git add -A`) before the check subprocess runs.
Phase-0 delta-WARN severity: `config.source_trees` is retained as
a classifier — a positional class pattern in a `source_trees` file
keeps today's hard gate (`error`, exit 1); the identical violation
in a NEWLY-covered file emits at WARN (`newly_covered` /
`phase="0-warn"`, exit 0).

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than through a `sys.executable` subprocess: there is
no `COVERAGE_PROCESS_START`-instrumented child, so no per-fixture
`.coverage.*` data file is written and none can race under the parallel
dispatcher — and the fixture runs materially faster without an interpreter
start per case. `main()` anchors itself on `Path.cwd()`, so the
monkeypatched cwd places the fixture exactly where the child's `cwd=`
argument did, and every assertion target is unchanged: the same int exit
code and the same diagnostic text, now read off `capsys` rather than off a
`CompletedProcess`.

The `git` spawn in `_git` STAYS. This check resolves the files it inspects
from the git-derived first-party `.py` universe, so a real `git init` +
`git add -A` is the behaviour the fixture exists to produce; replacing it
would leave the git-index universe untested. Its hardcoded 3-key env keeps
`COVERAGE_PROCESS_START` / `COV_CORE_*` out of that child, which is the
standing requirement on an allowlisted spawn — so this file KEEPS its
`subprocess_spawn_allowlist` entry.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the hard rejection of a positional class pattern on a
livespec-authored class inside `source_trees`, the keyword sub-pattern
acceptance, the upstream-fixed `returns` positional acceptance across all
four of `Success` / `Failure` / `IOSuccess` / `IOFailure`, the Phase-0
WARN-only newly-covered offender outside `source_trees`, and the codeless
repo. The two lines the child reached that an in-process call cannot are
the module's vendored-path guard (`sys.path.insert`) and its
`if __name__ == "__main__":` line; both are already excluded repo-wide by
the PRE-EXISTING `exclude_also` patterns in `[tool.coverage.report]`, so
neither was ever measured here and no new exclusion is introduced.
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


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MATCH_KEYWORD_ONLY = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "match_keyword_only.py"

_POSITIONAL_PATTERN_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "from typing_extensions import assert_never\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "class Foo:\n"
    "    pass\n"
    "\n"
    "\n"
    "def handle(val: object) -> int:\n"
    "    match val:\n"
    "        case Foo(x):\n"
    "            return x\n"
    "        case _:\n"
    "            assert_never(val)\n"
)


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env (no os.environ).

    The env is a REPLACEMENT, not a filtered copy of `os.environ`, so
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


def _init_repo_with_files(*, tmp_path: Path) -> None:
    """`git init` the fixture and stage every file already written under it."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red-Green-Replay hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "match_keyword_only_under_test",
        str(_MATCH_KEYWORD_ONLY),
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
    """`git init` + stage the fixture, then invoke the check's `main()` in-process."""
    _init_repo_with_files(tmp_path=cwd)
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def test_match_keyword_only_rejects_positional_class_pattern_for_livespec_class(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `case Foo(x):` (positional) in a `source_trees` file fails hard (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_POSITIONAL_PATTERN_SOURCE,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"match_keyword_only should reject positional class pattern; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo.py"
    assert expected_path in combined, (
        f"match_keyword_only diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_match_keyword_only_accepts_keyword_class_pattern(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `case Foo(x=x):` (keyword) on a livespec class passes (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "from typing_extensions import assert_never\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "class Foo:\n"
            "    pass\n"
            "\n"
            "\n"
            "def handle(val: object) -> int:\n"
            "    match val:\n"
            "        case Foo(x=x):\n"
            "            return x\n"
            "        case _:\n"
            "            assert_never(val)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"match_keyword_only should accept keyword class pattern with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_match_keyword_only_accepts_returns_positional_class_pattern(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `case Success(x):` / `case IOSuccess(x):` (positional) is permitted (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "from returns.io import IOFailure, IOSuccess\n"
            "from returns.result import Failure, Success\n"
            "from typing_extensions import assert_never\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def handle(val: object) -> int:\n"
            "    match val:\n"
            "        case Success(x):\n"
            "            return 0\n"
            "        case Failure(x):\n"
            "            return 1\n"
            "        case IOSuccess(x):\n"
            "            return 2\n"
            "        case IOFailure(x):\n"
            "            return 3\n"
            "        case _:\n"
            "            assert_never(val)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"match_keyword_only should accept returns-package positional patterns; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_match_keyword_only_warns_newly_covered_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A positional class pattern OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_POSITIONAL_PATTERN_SOURCE)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_match_keyword_only_accepts_codeless_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0)."""
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"match_keyword_only should accept a codeless repo with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_match_keyword_only_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "match_keyword_only_for_import_test",
        str(_MATCH_KEYWORD_ONLY),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


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
        module_slug="match_keyword_only",
        check_id="match_keyword_only",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
