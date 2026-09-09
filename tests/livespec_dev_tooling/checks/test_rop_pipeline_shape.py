"""Outside-in test for `dev-tooling/checks/rop_pipeline_shape.py` — `@rop_pipeline` class shape.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-rop-pipeline-shape` row), every class
decorated with `@rop_pipeline` carries exactly one public
method (the entry point); other methods are `_`-prefixed;
dunders aren't counted. Enforces the Command / Use Case
Interactor pattern at the class level.

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. `main()` reads
`Path.cwd()`, so the monkeypatched cwd anchors the fixture exactly as the
child's `cwd=` argument did, and the assertion targets are unchanged —
the int exit code plus the diagnostic text, now read off `capsys` instead
of `CompletedProcess`.

The `git` spawn in `_git` STAYS: this check resolves its file universe
from the git index, so a real `git init` + `git add -A` is the behaviour
the fixture exists to produce, and replacing it with an in-process call
would be a test that no longer tests what it claims. Its hardcoded 3-key
env keeps `COVERAGE_PROCESS_START` / `COV_CORE_*` out of that child,
which is the standing requirement on an allowlisted spawn — so this file
KEEPS its `subprocess_spawn_allowlist` entry.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the two-public-method rejection, the `@rop_pipeline()` Call-form
acceptance (one public method plus a private helper), the bare-Name
decorator carrying a class attribute alongside its method, the
undecorated class that is ignored outright, and the empty tree. The two
lines the child reached that an in-process call cannot are the module's
vendored-path guard (`sys.path.insert`) and its
`if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so neither was ever measured here and no new
exclusion is introduced.
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
_ROP_PIPELINE_SHAPE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "rop_pipeline_shape.py"


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    `git` is not a Python spawn, so `tests_no_subprocess_spawn` permits it;
    the hardcoded env is a REPLACEMENT rather than a filtered copy of
    `os.environ`, so `COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach
    this child, and the developer's own git config cannot reach the fixture.
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
        "rop_pipeline_shape_under_test",
        str(_ROP_PIPELINE_SHAPE),
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


def test_rop_pipeline_shape_rejects_class_with_two_public_methods(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `@rop_pipeline` class with two non-underscore methods fails the check."""
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from livespec.types import rop_pipeline\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "@rop_pipeline\n"
        "class Pipeline:\n"
        "    def run(self) -> int:\n"
        "        return 0\n"
        "\n"
        "    def also_run(self) -> int:\n"
        "        return 1\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"rop_pipeline_shape should reject two-public-methods class; "
        f"got returncode={result.returncode}"
    )
    combined = result.stdout + result.stderr
    assert "Pipeline" in combined, (
        f"diagnostic does not surface offending class `Pipeline`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rop_pipeline_shape_accepts_class_with_one_public_method(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `@rop_pipeline()` class with one public method + private helpers passes (exit 0).

    Uses the `@rop_pipeline()` Call form (decorator with
    parens) to exercise the `if isinstance(decorator, ast.
    Call):` True arm of `_decorator_terminal_name`.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from livespec.types import rop_pipeline\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "@rop_pipeline()\n"
        "class Pipeline:\n"
        "    def __init__(self) -> None:\n"
        "        pass\n"
        "\n"
        "    def run(self) -> int:\n"
        "        return self._helper()\n"
        "\n"
        "    def _helper(self) -> int:\n"
        "        return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"rop_pipeline_shape should accept one-public-method class with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rop_pipeline_shape_accepts_bare_decorator_and_class_attributes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `@rop_pipeline` class with class attributes (not methods) and bare decorator passes.

    Closes the `_decorator_terminal_name` non-Call branch
    (decorator is a bare Name, not a Call) and the
    `_count_public_methods` non-FunctionDef body-stmt branch
    (the class has an `Assign` body member alongside its
    methods).
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from livespec.types import rop_pipeline\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "@rop_pipeline\n"
        "class Pipeline:\n"
        "    CONST: int = 0\n"
        "\n"
        "    def run(self) -> int:\n"
        "        return 0\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"rop_pipeline_shape should accept class with attributes; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_rop_pipeline_shape_ignores_undecorated_classes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A class without the `@rop_pipeline` decorator is ignored."""
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "class Plain:\n"
        "    def m1(self) -> int:\n"
        "        return 0\n"
        "\n"
        "    def m2(self) -> int:\n"
        "        return 1\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"rop_pipeline_shape should ignore undecorated classes; "
        f"got returncode={result.returncode}"
    )


def test_rop_pipeline_shape_accepts_empty_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty repo cwd passes (exit 0)."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert (
        result.returncode == 0
    ), f"rop_pipeline_shape should accept empty tree; got returncode={result.returncode}"


def test_rop_pipeline_shape_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "rop_pipeline_shape_for_import_test",
        str(_ROP_PIPELINE_SHAPE),
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
        module_slug="rop_pipeline_shape",
        check_id="rop_pipeline_shape",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
