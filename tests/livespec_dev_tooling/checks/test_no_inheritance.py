"""Outside-in test for `dev-tooling/checks/no_inheritance.py` — direct-parent allowlist enforcement.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-no-inheritance` row), `class X(Y):` in
`.claude-plugin/scripts/livespec/**` is forbidden when `Y` is
not in the direct-parent allowlist `{Exception, BaseException,
LivespecError, Protocol, NamedTuple, TypedDict}`. Codifies
flat-composition direction; `LivespecError` itself remains an
open extension point. `LivespecError` subclasses are NOT
acceptable bases (v013 M5 tightening — `class
RateLimitError(UsageError):` is rejected even though
`UsageError` is itself a `LivespecError` subclass).

The check is driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` +
`capsys` + `rc = main()`) rather than via a `sys.executable`
subprocess (work-item livespec-dev-tooling-py9): no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*`
race under the parallel dispatcher, and materially faster.
`main()` reads `Path.cwd()`, so the monkeypatched cwd is the
fixture root.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_INHERITANCE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_inheritance.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and
    so `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location("no_inheritance_under_test", str(_NO_INHERITANCE))
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


def test_no_inheritance_rejects_disallowed_base_class(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `class Foo(Bar):` with `Bar` outside the allowlist fails the check.

    Fixture: `.claude-plugin/scripts/livespec/foo.py` defines
    `class Foo(Bar):` where `Bar` is a hand-rolled application
    class (not in the closed allowlist). The check, invoked
    with cwd monkeypatched to tmp_path, must walk the livespec
    subtree, parse the file, detect the disallowed base, exit
    non-zero, and surface the offending file plus line number.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "class Bar:\n"
        "    pass\n"
        "\n"
        "\n"
        "class Foo(Bar):\n"
        "    pass\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"no_inheritance should reject `class Foo(Bar):` with non-zero exit; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo.py"
    assert expected_path in combined, (
        f"no_inheritance diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # is the `class Foo(Bar):` line in the fixture.
    assert "10" in combined, (
        f"no_inheritance diagnostic does not surface offending line number 10; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_inheritance_accepts_allowlisted_base_classes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Classes deriving from `Exception`, `Protocol`, etc., pass the check (exit 0).

    Pass-case: each of the allowlist entries (Exception,
    BaseException, LivespecError, Protocol, NamedTuple,
    TypedDict) is a permitted direct parent. Fixture writes a
    file using `class FooError(Exception):` and `class
    FooProto(Protocol):`. The check walks the file and exits 0.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from typing import Protocol\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "class FooError(Exception):\n"
        "    pass\n"
        "\n"
        "\n"
        "class FooProto(Protocol):\n"
        "    def bar(self) -> None: ...\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_inheritance should accept allowlist parents with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_inheritance_accepts_tree_without_livespec_directory(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo cwd without `.claude-plugin/scripts/livespec/` passes the check (exit 0).

    Closes the `if livespec_root.is_dir():` False arm: tmp_path
    is empty, so main() short-circuits without walking.
    """
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"no_inheritance should accept empty tree with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_inheritance_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main().

    Closes the `_VENDOR_DIR` already-present branch and the
    `if __name__ == "__main__":` else-arm for per-file 100%.
    """
    module = _load_check_module()
    assert callable(module.main), "main should be importable without invocation"
