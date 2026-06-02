"""Outside-in test for `dev-tooling/checks/no_lloc_soft_warnings.py` — 201-250 LLOC soft-band severity lever.

Per `SPECIFICATION/constraints.md` §"File LLOC ceiling" (post-v008):
files in the 201-250 LLOC soft band are flagged. Files at or below
200 LLOC pass; files above 250 LLOC are NOT this check's concern
(the per-commit `file_lloc.py` hard-fails them).

Epic li-cvaudit (cvtodo) replaced the `LIVESPEC_RELEASE_GATE` skip
carve-out with a per-check severity lever: the soft-band scan ALWAYS
runs; `LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST` (non-empty) makes
soft-band offenders fail (exit 1, error level), unset downgrades the
SAME findings to warning + exit 0.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_LLOC_SOFT_WARNINGS = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_lloc_soft_warnings.py"

_FAIL_VAR = "LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST"


def _run_check(*, cwd: Path, fail_var: str | None) -> subprocess.CompletedProcess[str]:
    """Invoke the check in `cwd`, optionally setting the fail-lever env var.

    `fail_var=None` removes the lever from the inherited environment
    (the warn-only state); any string sets it to that value.
    """
    env = {k: v for k, v in os.environ.items() if k != _FAIL_VAR}
    if fail_var is not None:
        env[_FAIL_VAR] = fail_var
    return subprocess.run(
        [sys.executable, str(_NO_LLOC_SOFT_WARNINGS)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _write_py_with_lloc(*, tmp_path: Path, rel_path: str, n_statements: int) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    body_lines = "\n".join(f"x_{i} = {i}" for i in range(n_statements))
    full.write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n" + body_lines + "\n",
        encoding="utf-8",
    )


def test_fails_on_soft_band_file_when_fail_var_set(*, tmp_path: Path) -> None:
    """A 201-250 LLOC file + fail-lever set → exit 1, error-level diagnostic."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode != 0, (
        f"fail-lever set + soft-band file should exit non-zero; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "soft band" in combined
    assert ".claude-plugin/scripts/livespec/medium.py" in combined
    assert (
        '"level": "error"' in combined
    ), f"fail-lever set should emit error-level finding; stderr={result.stderr!r}"


def test_warns_on_soft_band_file_when_fail_var_unset(*, tmp_path: Path) -> None:
    """A 201-250 LLOC file + fail-lever unset → exit 0, SAME finding at warning level."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    result = _run_check(cwd=tmp_path, fail_var=None)
    assert result.returncode == 0, (
        f"fail-lever unset + soft-band file should warn + exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "soft band" in combined
    assert ".claude-plugin/scripts/livespec/medium.py" in combined
    assert (
        '"level": "warning"' in combined
    ), f"fail-lever unset should downgrade finding to warning; stderr={result.stderr!r}"


def test_empty_fail_var_treated_as_unset(*, tmp_path: Path) -> None:
    """An empty-string fail-lever value counts as unset → warn + exit 0."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
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


def test_accepts_file_at_or_below_soft_ceiling(*, tmp_path: Path) -> None:
    """A `.py` file with ≤ 200 LLOC passes (exit 0) regardless of lever."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/small.py",
        n_statements=50,
    )
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode == 0


def test_ignores_file_above_hard_ceiling(*, tmp_path: Path) -> None:
    """A `.py` file with > 250 LLOC is NOT this check's concern (per-commit file_lloc.py handles it)."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/big.py",
        n_statements=300,
    )
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode == 0


def test_emits_each_offender_when_fail_var_set(*, tmp_path: Path) -> None:
    """Multiple soft-band files produce one diagnostic each; check still exits non-zero."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium_a.py",
        n_statements=210,
    )
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium_b.py",
        n_statements=240,
    )
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "medium_a.py" in combined
    assert "medium_b.py" in combined


def test_excludes_blank_lines_and_comments_and_docstrings(*, tmp_path: Path) -> None:
    """LLOC counting matches file_lloc.py: blank/comment/docstring lines don't count."""
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "padded.py"
    blanks = "\n" * 250
    comments = "\n".join(f"# comment {i}" for i in range(250))
    docstring_lines = "\n".join(f"docstring line {i}" for i in range(250))
    source.write_text(
        f'"""\n{docstring_lines}\n"""\n'
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        f"{blanks}\n"
        f"{comments}\n"
        "\n"
        "x = 0\ny = 1\nz = 2\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode == 0


def test_accepts_empty_tree(*, tmp_path: Path) -> None:
    """An empty repo cwd passes (exit 0)."""
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode == 0


def test_no_op_when_covered_trees_absent(*, tmp_path: Path) -> None:
    """A config with an empty `covered_trees` role key → no-op exit 0.

    Writing a `pyproject.toml` with a `[tool.livespec_dev_tooling]`
    block that explicitly empties `covered_trees` drives the
    `if not config.covered_trees:` branch. (A bare block present with
    the key omitted would also work — both resolve `covered_trees`
    to the empty flat baseline rather than the livespec-core fallback.)
    """
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ncovered_trees = []\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, fail_var="true")
    assert result.returncode == 0, (
        f"empty covered_trees should no-op exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "role key absent" in combined


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_lloc_soft_warnings_for_import_test",
        str(_NO_LLOC_SOFT_WARNINGS),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
