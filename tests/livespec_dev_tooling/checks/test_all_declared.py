"""Outside-in test for `livespec_dev_tooling/checks/all_declared.py` — `__all__` declaration discipline.

Per `python-skill-script-style-requirements.md` §"Canonical
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

The check is invoked as a `sys.executable` subprocess (this file is
in the documented `subprocess_spawn_allowlist`); pytest-cov's
pth-installed startup hook instruments the child so per-file
coverage is measured.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env (no os.environ)."""
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


def _run_all_declared(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    """`git init` + stage the fixture, then run the check as a consumer would."""
    _init_repo_with_files(tmp_path=cwd)
    return subprocess.run(
        [sys.executable, str(_ALL_DECLARED)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def test_all_declared_rejects_module_missing_all_declaration(*, tmp_path: Path) -> None:
    """A `source_trees` module without `__all__` fails hard (error, exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_MISSING_ALL_SOURCE,
    )

    result = _run_all_declared(cwd=tmp_path)

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


def test_all_declared_rejects_undefined_name_in_all(*, tmp_path: Path) -> None:
    """An `__all__` entry not defined in a `source_trees` module fails (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_UNDEFINED_NAME_SOURCE,
    )

    result = _run_all_declared(cwd=tmp_path)

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


def test_all_declared_accepts_module_with_complete_all_declaration(*, tmp_path: Path) -> None:
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

    result = _run_all_declared(cwd=tmp_path)

    assert result.returncode == 0, (
        f"all_declared should accept valid module with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_all_declared_warns_newly_covered_missing_all(*, tmp_path: Path) -> None:
    """A missing-`__all__` module OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_MISSING_ALL_SOURCE)

    result = _run_all_declared(cwd=tmp_path)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_all_declared_warns_newly_covered_undefined_name(*, tmp_path: Path) -> None:
    """An undefined-`__all__`-name module OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_UNDEFINED_NAME_SOURCE)

    result = _run_all_declared(cwd=tmp_path)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "bogus" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_all_declared_ignores_bin_wrapper_without_all(*, tmp_path: Path) -> None:
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

    result = _run_all_declared(cwd=tmp_path)

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


def test_all_declared_still_flags_bootstrap_bin_file(*, tmp_path: Path) -> None:
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

    result = _run_all_declared(cwd=tmp_path)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/bin/_bootstrap.py" in combined, (
        f"_bootstrap.py is not a wrapper and must still be flagged; " f"stderr={result.stderr!r}"
    )
    assert "newly_covered" in combined


def test_all_declared_accepts_codeless_repo(*, tmp_path: Path) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0)."""
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run_all_declared(cwd=tmp_path)

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
