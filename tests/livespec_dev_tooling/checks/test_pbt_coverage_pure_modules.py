"""Outside-in test for `dev-tooling/checks/pbt_coverage_pure_modules.py` — `@given` PBT in pure-layer tests.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-pbt-coverage-pure-modules` row), each
test module under `tests/livespec/parse/` and `tests/livespec/
validate/` declares at least one `@given(...)`-decorated test
function. Hypothesis property-based testing is the canonical
PBT mechanism for pure layers.

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. The seven call sites
spawned identically, so they now share one `_run_check` helper; `main()`
reads `Path.cwd()`, so the monkeypatched cwd anchors the fixture exactly
as the child's `cwd=` argument did, and the assertion targets are
unchanged — the int exit code plus the offending-path diagnostic, now
read off `capsys` instead of `CompletedProcess`.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the missing-`@given` offender, the `@given`-present pass, the
configured `pure_trees` arms, the first-matching and no-matching
`mirror_pairings` resolutions, and the config-parse failure exit. The
two lines the child process reached that an in-process call cannot are
the module's vendored-path guard (`sys.path.insert`) and its
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
_PBT_COVERAGE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "pbt_coverage_pure_modules.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "pbt_coverage_pure_modules_under_test", str(_PBT_COVERAGE)
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


def test_pbt_coverage_rejects_parse_test_without_given_decorator(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `tests/livespec/parse/test_foo.py` without `@given(...)` fails the check."""
    test_dir = tmp_path / "tests" / "livespec" / "parse"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_foo.py"
    test_file.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def test_foo() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"pbt_coverage should reject parse-layer test without @given; "
        f"got returncode={result.returncode}"
    )
    combined = result.stdout + result.stderr
    expected_path = "tests/livespec/parse/test_foo.py"
    assert expected_path in combined, (
        f"pbt_coverage diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_pbt_coverage_accepts_parse_test_with_given_decorator(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `tests/livespec/parse/test_foo.py` WITH a `@given(...)`-decorated function passes."""
    test_dir = tmp_path / "tests" / "livespec" / "parse"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_foo.py"
    test_file.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from hypothesis import given\n"
        "from hypothesis import strategies as st\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "@given(st.text())\n"
        "def test_foo_property(*, s: str) -> None:\n"
        "    assert isinstance(s, str)\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"pbt_coverage should accept parse-layer test with @given; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_pbt_coverage_accepts_validate_test_with_given_decorator(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `tests/livespec/validate/test_foo.py` WITH a `@given(...)` passes.

    Fixture exercises additional decorator-shape branches:
    - `@pytest.mark.parametrize` (a bare `Attribute` access,
      not a `Call`) on the first function — covers the
      `decorator` non-Call branch of
      `_decorator_terminal_name`.
    - A non-given decorated function comes BEFORE the given-
      decorated one, exercising the loop continuation past a
      non-matching name.
    """
    test_dir = tmp_path / "tests" / "livespec" / "validate"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_foo.py"
    test_file.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from hypothesis import given, strategies\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def helper() -> None:\n"
        "    pass\n"
        "\n"
        "\n"
        "@helper\n"
        "def test_first() -> None:\n"
        "    assert True\n"
        "\n"
        "\n"
        "@given(strategies.text())\n"
        "def test_foo(*, s: str) -> None:\n"
        "    assert s == s\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"pbt_coverage should accept validate-layer test with @given; "
        f"got returncode={result.returncode}"
    )


def test_pbt_coverage_uses_first_matching_configured_mirror_pairing(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'pure_trees = ["consumer_pkg/parse"]\n'
        "mirror_pairings = [\n"
        '  { source_tree = "other_pkg", test_tree = "tests/other_pkg" },\n'
        '  { source_tree = "consumer_pkg", test_tree = "tests/consumer_pkg" },\n'
        "]\n",
        encoding="utf-8",
    )
    test_dir = tmp_path / "tests" / "consumer_pkg" / "parse"
    test_dir.mkdir(parents=True)
    (test_dir / "test_parser.py").write_text(
        "from __future__ import annotations\n"
        "__all__: list[str] = []\n"
        "def test_parser() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert "tests/consumer_pkg/parse/test_parser.py" in result.stdout + result.stderr


def test_pbt_coverage_falls_back_when_no_mirror_pairing_matches(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'pure_trees = ["consumer_pkg/parse"]\n'
        'mirror_pairings = [{ source_tree = "other_pkg", test_tree = "tests/other_pkg" }]\n'
        'tests_tree_prefix = "tests/"\n',
        encoding="utf-8",
    )
    test_dir = tmp_path / "tests" / "consumer_pkg" / "parse"
    test_dir.mkdir(parents=True)
    (test_dir / "test_parser.py").write_text(
        "from __future__ import annotations\n"
        "__all__: list[str] = []\n"
        "def test_parser() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0
    assert "tests/consumer_pkg/parse/test_parser.py" in result.stdout + result.stderr


def test_pbt_coverage_noops_without_configured_pure_trees(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\npure_trees = { not_applicable = "consumer has no pure tree" }\n',
        encoding="utf-8",
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    assert "pure_trees" in result.stdout + result.stderr


def test_pbt_coverage_rejects_declared_tree_with_no_python(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A declared pure test tree containing no Python files is a misdeclaration."""
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 1, (
        f"pbt_coverage should reject a declared tree with no Python files; "
        f"got returncode={result.returncode}"
    )
    assert "declared role key resolves to no Python files" in result.stderr


def test_pbt_coverage_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pbt_coverage_pure_modules_for_import_test",
        str(_PBT_COVERAGE),
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
        module_slug="pbt_coverage_pure_modules",
        check_id="pbt_coverage_pure_modules",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
