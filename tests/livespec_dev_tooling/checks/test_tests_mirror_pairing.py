"""Outside-in test for `dev-tooling/checks/tests_mirror_pairing.py` — v033 D1 mirror-pairing enforcement.

Per `SPECIFICATION/spec.md` section "Testing approach" (post-v006), every
covered `.py` file MUST have a paired test file at the mirror path
EXCEPT (a) private-helper modules (filename starts with `_`, NOT
`__init__.py`); (b) boilerplate `__init__.py` files (only docstring +
`from __future__ import annotations` + `__all__: list[str] = []`);
(c) `bin/_bootstrap.py` (covered by `tests/bin/test_bootstrap.py`).

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. `main()` reads
`Path.cwd()`, so the monkeypatched cwd anchors the fixture, and the
assertion targets are unchanged — the int exit code plus the structlog
stderr text, now read off `capsys` instead of `CompletedProcess`.

Branch parity with the retired spawn: the check's `main()` and every
helper it reaches are exercised by the same fixtures as before (the
`config.mirror_pairings` short-circuit AND its
`_derived_pairings_from_prefixes` fallback arm, the missing-source-tree
`continue`, both exemption arms, and the offender/clean exits). The two
lines the child process reached that an in-process call cannot are the
module's vendored-path guard (`sys.path.insert`) and its
`if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so neither was ever measured here and no new
exclusion is introduced.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from tests.livespec_dev_tooling.checks.config_parse_rendering import (
    assert_main_renders_the_parse_failure,
)

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_TESTS_MIRROR_PAIRING = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "tests_mirror_pairing.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "tests_mirror_pairing_under_test", str(_TESTS_MIRROR_PAIRING)
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
    """Invoke the check's `main()` in-process under `cwd` and capture output."""
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_py(*, tmp_path: Path, rel_path: str, body: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body, encoding="utf-8")


def test_tests_mirror_pairing_rejects_livespec_source_without_paired_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `livespec/foo/bar.py` source file (with a function definition) without `tests/livespec/foo/test_bar.py` fails."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo/bar.py",
        body="from __future__ import annotations\n\n__all__: list[str] = []\n\n"
        "def do_thing() -> int:\n    return 0\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/livespec/foo/bar.py" in combined
    assert "tests/livespec/foo/test_bar.py" in combined


def test_tests_mirror_pairing_accepts_paired_source_and_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two source files with paired tests pass (exit 0); covers the pair-found loop continuation."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo/bar.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n\n"
        "def do_thing() -> int:\n    return 0\n",
    )
    _write_py(
        tmp_path=tmp_path,
        rel_path="tests/livespec/foo/test_bar.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n"
        "def test_bar() -> None:\n    assert True\n",
    )
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo/baz.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n\n"
        "def other() -> int:\n    return 1\n",
    )
    _write_py(
        tmp_path=tmp_path,
        rel_path="tests/livespec/foo/test_baz.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n"
        "def test_baz() -> None:\n    assert True\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_tests_mirror_pairing_derives_pairing_from_source_tree_prefix(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'source_tree_prefixes = ["pkg/"]\n'
        'tests_tree_prefix = "tests/"\n',
        encoding="utf-8",
    )
    _write_py(
        tmp_path=tmp_path,
        rel_path="pkg/foo.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n\n"
        "def do_thing() -> int:\n    return 0\n",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert "tests/pkg/test_foo.py" in result.stdout + result.stderr


def test_tests_mirror_pairing_skips_vendor_subtrees(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'source_tree_prefixes = ["pkg/"]\n'
        'tests_tree_prefix = "tests/"\n',
        encoding="utf-8",
    )
    _write_py(
        tmp_path=tmp_path,
        rel_path="pkg/_vendor/upstream.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n\n"
        "def vendored() -> int:\n    return 0\n",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0


def test_tests_mirror_pairing_exempts_private_helper_module(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `_helper.py` private-helper module (not `__init__.py`) does NOT need a paired test."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/commands/_helper.py",
        body="from __future__ import annotations\n__all__: list[str] = []\nx = 0\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_tests_mirror_pairing_exempts_private_helper_with_function_def(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `_helper.py` WITH a FunctionDef (not `__init__.py`) is exempt via `_is_private_helper_module`.

    The existing `test_tests_mirror_pairing_exempts_private_helper_module` uses a
    body with no functions (`x = 0`), which is ALSO caught by `_is_pure_declaration_module`.
    This test uses a body with a `def` so the exemption is only reachable via
    `_is_private_helper_module` — pinning the rule for the realistic case of
    `_red_green_replay_modes.py`-style helpers that do contain functions.
    """
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/commands/_helper.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n\n"
        "def do_thing() -> int:\n    return 0\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_tests_mirror_pairing_exempts_pure_declaration_init(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An `__init__.py` whose body has no FunctionDef is exempt under the pure-declaration rule."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/commands/__init__.py",
        body='"""commands package."""\nfrom __future__ import annotations\n__all__: list[str] = []\n',
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_tests_mirror_pairing_exempts_pure_dataclass_module(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pure dataclass module (decorated class, no FunctionDef anywhere) is exempt."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/schemas/dataclasses/finding.py",
        body='"""Finding dataclass."""\nfrom __future__ import annotations\n'
        "from dataclasses import dataclass\n"
        '__all__: list[str] = ["Finding"]\n\n'
        "@dataclass(frozen=True, kw_only=True, slots=True)\n"
        "class Finding:\n"
        '    """The Finding wire dataclass."""\n'
        "    check_id: str\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_tests_mirror_pairing_rejects_non_pure_init_without_paired_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An `__init__.py` with a FunctionDef requires a paired test."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/__init__.py",
        body='"""livespec package."""\nfrom __future__ import annotations\n'
        "__all__: list[str] = []\n\n"
        "def configure() -> int:\n    return 0\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "__init__.py" in combined


def test_tests_mirror_pairing_exempts_bootstrap(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`bin/_bootstrap.py` is special-cased (covered by tests/bin/test_bootstrap.py)."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/bin/_bootstrap.py",
        body="from __future__ import annotations\n__all__: list[str] = []\nx = 0\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_tests_mirror_pairing_rejects_module_with_function_def_without_paired_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A module with a `def` (any function definition) requires a paired test."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo/has_logic.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n\n"
        "def f() -> int:\n    return 1\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0


def test_tests_mirror_pairing_rejects_module_with_async_function_def_without_paired_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A module with an `async def` requires a paired test."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo/has_async.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n\n"
        "async def f() -> int:\n    return 1\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0


def test_tests_mirror_pairing_rejects_class_with_method_def_without_paired_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A class definition containing a method (FunctionDef inside ClassDef) is NOT exempt."""
    _write_py(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo/with_class.py",
        body="from __future__ import annotations\n__all__: list[str] = []\n\n"
        "class Foo:\n    def bar(self) -> int:\n        return 1\n",
    )
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0


def test_tests_mirror_pairing_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "tests_mirror_pairing_for_import_test",
        str(_TESTS_MIRROR_PAIRING),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


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
        module_slug="tests_mirror_pairing",
        check_id="tests_mirror_pairing",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
