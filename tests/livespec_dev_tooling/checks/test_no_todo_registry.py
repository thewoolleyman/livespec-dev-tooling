"""Outside-in test for `dev-tooling/checks/no_todo_registry.py` — `tests/heading-coverage.json` no TODO entries.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-no-todo-registry` row), no entry in
`tests/heading-coverage.json` may have `test: "TODO"`.

Epic li-cvaudit (cvtodo) replaced the `LIVESPEC_RELEASE_GATE`
skip carve-out with a per-check severity lever: the scan ALWAYS
runs; the `LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` env var
decides whether discovered offenders fail the check (release
context, var set to a non-empty value) or merely warn (var unset).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_TODO_REGISTRY = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_todo_registry.py"

_FAIL_VAR = "LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST"


def _run_check(*, cwd: Path, fail_var: str | None) -> subprocess.CompletedProcess[str]:
    """Invoke the check in `cwd`, optionally setting the fail-lever env var.

    `fail_var=None` removes the lever from the inherited environment
    (the warn-only state); any string sets it to that value.
    """
    env = {k: v for k, v in os.environ.items() if k != _FAIL_VAR}
    if fail_var is not None:
        env[_FAIL_VAR] = fail_var
    return subprocess.run(
        [sys.executable, str(_NO_TODO_REGISTRY)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _write_coverage(*, tmp_path: Path, body: str) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "heading-coverage.json").write_text(body, encoding="utf-8")


def test_fails_on_todo_entry_when_fail_var_set(*, tmp_path: Path) -> None:
    """`test: "TODO"` + fail-lever set → exit 1, error-level diagnostic."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "TODO"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode != 0, (
        f"fail-lever set + TODO entry should exit non-zero; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "Foo" in combined
    ), f"diagnostic does not surface offending heading; stderr={result.stderr!r}"
    assert (
        '"level": "error"' in combined
    ), f"fail-lever set should emit error-level finding; stderr={result.stderr!r}"


def test_warns_on_todo_entry_when_fail_var_unset(*, tmp_path: Path) -> None:
    """`test: "TODO"` + fail-lever unset → exit 0, SAME finding at warning level."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "TODO"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var=None)
    assert result.returncode == 0, (
        f"fail-lever unset + TODO entry should warn + exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "Foo" in combined
    ), f"warning should still surface offending heading; stderr={result.stderr!r}"
    assert (
        '"level": "warning"' in combined
    ), f"fail-lever unset should downgrade finding to warning; stderr={result.stderr!r}"


def test_empty_fail_var_treated_as_unset(*, tmp_path: Path) -> None:
    """An empty-string fail-lever value counts as unset → warn + exit 0."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "TODO"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var="")
    assert result.returncode == 0, (
        f"empty fail-lever should be treated as unset (warn + exit 0); "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        '"level": "warning"' in combined
    ), f"empty fail-lever should downgrade finding to warning; stderr={result.stderr!r}"


def test_accepts_no_todo_entries_with_fail_var_set(*, tmp_path: Path) -> None:
    """No offenders + fail-lever set → exit 0 (nothing to gate on)."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "tests/foo.py"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode == 0, (
        f"TODO-free coverage should exit 0 even with fail-lever set; "
        f"got returncode={result.returncode}"
    )


def test_accepts_no_todo_entries_with_fail_var_unset(*, tmp_path: Path) -> None:
    """No offenders + fail-lever unset → exit 0, no warning emitted."""
    _write_coverage(
        tmp_path=tmp_path,
        body='[{"heading": "## Foo", "spec_root": "/", "test": "tests/foo.py"}]',
    )
    result = _run_check(cwd=tmp_path, fail_var=None)
    assert (
        result.returncode == 0
    ), f"TODO-free coverage should exit 0; got returncode={result.returncode}"


def test_accepts_object_top_level(*, tmp_path: Path) -> None:
    """Coverage JSON whose top-level is not a list passes (exit 0).

    Closes the `if isinstance(parsed, list):` False branch.
    """
    _write_coverage(tmp_path=tmp_path, body="{}")
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert (
        result.returncode == 0
    ), f"object top-level should exit 0; got returncode={result.returncode}"


def test_accepts_missing_coverage_file(*, tmp_path: Path) -> None:
    """Repo without `tests/heading-coverage.json` passes (exit 0)."""
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert (
        result.returncode == 0
    ), f"missing coverage file should exit 0; got returncode={result.returncode}"


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_todo_registry_for_import_test",
        str(_NO_TODO_REGISTRY),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"
