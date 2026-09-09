"""Outside-in test for `livespec_dev_tooling/checks/all_declared.py` — `__all__` declaration discipline.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-all-declared` row), every livespec
module MUST declare a module-top `__all__: list[str]` (typed
annotation, list literal). Every name in `__all__` must also be
defined in the module. Two failure modes: a missing `__all__`
declaration, and a name in `__all__` not defined as a module-top
name.

The check now resolves the files it inspects from the git-derived
first-party `.py` universe (`config.resolve_check_universe`),
root-anchored via `config.resolve_repo_root`, rather than a
`config.source_trees` walk — so each fixture is a real git repo
(`git init` + `git add -A`) before the check subprocess runs.
Phase-0 delta-WARN severity: `config.source_trees` is retained as
a classifier — either failure mode in a `source_trees` file keeps
today's hard gate (`error`, exit 1); the identical failure in a
NEWLY-covered file emits at WARN (`newly_covered` /
`phase="0-warn"`, exit 0).

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. `main()` root-anchors
itself from `Path.cwd()`, so the monkeypatched cwd stands in for the
child's `cwd=` argument exactly, and the assertion targets are unchanged
— the int exit code plus the structlog diagnostic text, now read off
`capsys` instead of `CompletedProcess`.

The `git` spawn in `_git` STAYS. This check resolves its universe from
the git index (`config.resolve_check_universe`), so the `git init` +
`git add -A` in `_init_repo_with_files` is what decides which fixture
files the check can see at all — replacing it with an in-process
stand-in would delete the behaviour under test. Its hardcoded 3-key env
is a REPLACEMENT for `os.environ`, so `COVERAGE_PROCESS_START` /
`COV_CORE_*` cannot reach that child; because a spawn remains, this file
KEEPS its `subprocess_spawn_allowlist` entry.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the hard-gate rejections of a missing `__all__` and of an
undefined `__all__` name inside `source_trees`, the complete-declaration
acceptance that walks every recognized definition form, both Phase-0
newly-covered WARN arms (missing `__all__` and undefined name outside
`source_trees`), the `bin/*.py` wrapper exemption paired with a
non-wrapper file proving it does not fail open, the `_bootstrap.py`
counter-case that pins the exemption boundary, and the codeless repo.
The two lines the child reached that an in-process call cannot are the
module's vendored-path guard (`sys.path.insert`) and its
`if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns
in `[tool.coverage.report]`, so neither was ever measured here and no
new exclusion is introduced.
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
_ALL_DECLARED = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "all_declared.py"

_MISSING_ALL_SOURCE = (
    "from __future__ import annotations\n" "\n" "\n" "def main() -> int:\n" "    return 0\n"
)
_UNDEFINED_NAME_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    '__all__: list[str] = ["bogus"]\n'
    "\n"
    "\n"
    "def real_thing() -> int:\n"
    "    return 0\n"
)
# A canonical `bin/*.py` shebang wrapper: the 5-statement shape
# `wrapper_shape` enforces, which by construction carries NO `__all__` (an
# `__all__` statement would break that exact shape). all_declared must SKIP
# such wrappers entirely — they are thin launchers with no public API.
_BIN_WRAPPER_SOURCE = (
    "#!/usr/bin/env python3\n"
    '"""Shebang wrapper for foo. No logic."""\n'
    "\n"
    "from _bootstrap import bootstrap\n"
    "\n"
    "bootstrap()\n"
    "\n"
    "from livespec.commands.foo import main\n"
    "\n"
    "raise SystemExit(main())\n"
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
        "all_declared_under_test",
        str(_ALL_DECLARED),
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


def _run_all_declared(
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


def test_all_declared_rejects_module_missing_all_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `source_trees` module without `__all__` fails hard (error, exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_MISSING_ALL_SOURCE,
    )

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"all_declared should reject module without `__all__` with non-zero exit; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo.py"
    assert expected_path in combined, (
        f"all_declared diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_all_declared_rejects_undefined_name_in_all(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An `__all__` entry not defined in a `source_trees` module fails (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_UNDEFINED_NAME_SOURCE,
    )

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"all_declared should reject undefined name in `__all__` with non-zero exit; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "bogus" in combined, (
        f"all_declared diagnostic does not surface undefined name `bogus`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_all_declared_accepts_module_with_complete_all_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A module with valid `__all__` listing all defined exports passes (exit 0).

    The fixture exercises every recognized definition form (`import os`,
    `from typing import Any`, `CONST = 1`, `x: int = 0`, `def fn`,
    `class Cls`, tuple-unpack assign) so per-file coverage of
    `_module_top_defined_names` holds.
    """
    source = (
        '"""Module docstring exercises the top-level Expr fall-through arm."""\n'
        "from __future__ import annotations\n"
        "\n"
        "import os\n"
        "from typing import Any\n"
        "\n"
        '__all__: list[str] = ["fn", "Cls", "CONST", "x", "os", "Any"]\n'
        "\n"
        "CONST = 1\n"
        "x: int = 0\n"
        "# Tuple-unpacking assign exercises the target-not-Name branch.\n"
        "(a, b) = (1, 2)\n"
        "\n"
        "\n"
        "def fn() -> Any:\n"
        "    return os.getcwd()\n"
        "\n"
        "\n"
        "class Cls:\n"
        "    pass\n"
    )
    _write(tmp_path=tmp_path, rel_path=".claude-plugin/scripts/livespec/foo.py", source=source)

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"all_declared should accept valid module with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_all_declared_warns_newly_covered_missing_all(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing-`__all__` module OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_MISSING_ALL_SOURCE)

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_all_declared_warns_newly_covered_undefined_name(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An undefined-`__all__`-name module OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_UNDEFINED_NAME_SOURCE)

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "bogus" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_all_declared_ignores_bin_wrapper_without_all(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `bin/*.py` shebang wrapper (no `__all__`) is NOT flagged by all_declared.

    The bin-wrapper launchers `wrapper_shape` governs into the canonical
    5-statement form carry NO `__all__` by construction and have no
    meaningful public API to declare. They drop OUT of all_declared's
    universe entirely (neither ERROR nor WARN) via the shared
    `config.is_bin_wrapper` predicate — the SAME wrapper-identity
    `wrapper_shape` uses as its single source of truth. A normal
    non-wrapper module missing `__all__` is still surfaced (a newly-covered
    WARN here), proving the exemption is scoped to the wrapper set and does
    not fail open.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/bin/foo.py",
        source=_BIN_WRAPPER_SOURCE,
    )
    _write(tmp_path=tmp_path, rel_path="pkg/normal.py", source=_MISSING_ALL_SOURCE)

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"a bin-wrapper exemption plus a newly-covered normal file must not "
        f"hard-fail; stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/bin/foo.py" not in combined, (
        f"all_declared must SKIP bin/*.py wrappers entirely (neither ERROR nor "
        f"WARN); the wrapper was surfaced. stderr={result.stderr!r}"
    )
    assert "pkg/normal.py" in combined, (
        f"a normal module missing `__all__` must still be flagged (the exemption "
        f"must not fail open); stderr={result.stderr!r}"
    )
    assert "newly_covered" in combined


def test_all_declared_still_flags_bootstrap_bin_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_bootstrap.py` under `bin/` is NOT a wrapper — it is still flagged.

    `wrapper_shape` EXEMPTS `_bootstrap.py` from the canonical wrapper shape
    (it carries real bootstrap logic), so it is NOT part of the wrapper set
    `config.is_bin_wrapper` identifies. all_declared therefore does NOT
    exempt it: a `_bootstrap.py` missing `__all__` is still surfaced
    (newly-covered WARN here). This pins the exemption boundary — only true
    bin wrappers drop out, never every file under `bin/`.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/bin/_bootstrap.py",
        source=_MISSING_ALL_SOURCE,
    )

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/bin/_bootstrap.py" in combined, (
        f"_bootstrap.py is not a wrapper and must still be flagged; " f"stderr={result.stderr!r}"
    )
    assert "newly_covered" in combined


def test_all_declared_still_flags_a_declared_non_wrapper_bin_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `bin_non_wrapper_files` declaration reaches THIS check too, and it tightens.

    `livespec-dev-tooling-g28` made the non-wrapper bin set consumer-declared,
    and both checks read it through the one `config.is_bin_wrapper` predicate.
    Declaring `_currency.py` therefore does not buy a blanket exemption: it says
    the file is pre-import MACHINERY rather than a launcher, so `wrapper_shape`
    stops holding it to the 5-statement shape and all_declared starts requiring
    its `__all__` — exactly `_bootstrap.py`'s standing. The undeclared
    `foo.py` wrapper in the same fixture still drops out, which is what
    proves the declaration moved one file rather than disarming the skip.
    """
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nbin_non_wrapper_files = ["_currency.py"]\n',
        encoding="utf-8",
    )
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/bin/_currency.py",
        source=_MISSING_ALL_SOURCE,
    )
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/bin/foo.py",
        source=_BIN_WRAPPER_SOURCE,
    )

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/bin/_currency.py" in combined, (
        f"a DECLARED non-wrapper bin file is module code, not a launcher, and "
        f"must still owe an `__all__`; stderr={result.stderr!r}"
    )
    assert ".claude-plugin/scripts/bin/foo.py" not in combined, (
        f"the declaration must not disarm the wrapper skip for undeclared "
        f"wrappers; stderr={result.stderr!r}"
    )


def test_all_declared_flags_a_declared_name_nested_below_the_bin_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The declaration is NAME-scoped to direct children, never a path glob.

    The nesting half of `livespec-dev-tooling-g28`. `bin/sub/_currency.py`
    carries the declared NAME but is not a direct child of the bin root, so
    the bare name match does not reach it: it is not a wrapper, all_declared
    does not skip it, and the missing `__all__` is surfaced by name. A
    declaration that leaked into subdirectories would silence this finding
    while looking identical from the config file.
    """
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nbin_non_wrapper_files = ["_currency.py"]\n',
        encoding="utf-8",
    )
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/bin/sub/_currency.py",
        source=_MISSING_ALL_SOURCE,
    )

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/bin/sub/_currency.py" in combined, (
        f"a declared name NESTED below the bin root must not be exempted by "
        f"the bare name match; stderr={result.stderr!r}"
    )


def test_all_declared_accepts_codeless_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0)."""
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run_all_declared(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"all_declared should accept a codeless repo with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_all_declared_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "all_declared_for_import_test",
        str(_ALL_DECLARED),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_module_top_defined_names_helpers_cover_each_node_kind() -> None:
    """The five `_names_from_*` helpers each return the expected name set.

    Cycle 4b refactor extracted per-node-kind helpers from
    `_module_top_defined_names` to bring the dispatcher under
    ruff's C901 cyclomatic-complexity threshold. This test
    exercises each helper directly so coverage no longer
    depends solely on the integration test.
    """
    import ast
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "all_declared_for_helpers_test",
        str(_ALL_DECLARED),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    func_node = ast.parse("def foo() -> None: pass").body[0]
    assert isinstance(func_node, ast.FunctionDef)
    assert module._names_from_def(node=func_node) == {"foo"}  # noqa: SLF001

    assign_node = ast.parse("x = 1").body[0]
    assert isinstance(assign_node, ast.Assign)
    assert module._names_from_assign(node=assign_node) == {"x"}  # noqa: SLF001

    annassign_node = ast.parse("y: int = 2").body[0]
    assert isinstance(annassign_node, ast.AnnAssign)
    assert module._names_from_annassign(node=annassign_node) == {"y"}  # noqa: SLF001

    # AnnAssign whose target is NOT an `ast.Name` (e.g.,
    # `self.x: int = 1` parses as Attribute target). The
    # helper returns empty set; this case pins the fall-
    # through branch so per-file coverage stays at 100%.
    annassign_attr_node = ast.parse("self.x: int = 1").body[0]
    assert isinstance(annassign_attr_node, ast.AnnAssign)
    assert module._names_from_annassign(node=annassign_attr_node) == set()  # noqa: SLF001

    importfrom_node = ast.parse("from os import path").body[0]
    assert isinstance(importfrom_node, ast.ImportFrom)
    assert module._names_from_import_from(node=importfrom_node) == {"path"}  # noqa: SLF001

    import_node = ast.parse("import json").body[0]
    assert isinstance(import_node, ast.Import)
    assert module._names_from_import(node=import_node) == {"json"}  # noqa: SLF001


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
        module_slug="all_declared",
        check_id="all_declared",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
