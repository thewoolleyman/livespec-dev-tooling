"""Outside-in test for `dev-tooling/checks/no_lloc_soft_warnings.py` — 201-250 LLOC soft-band severity lever.

Per `SPECIFICATION/constraints.md` section "File LLOC ceiling" (post-v008):
files in the 201-250 LLOC soft band are flagged. Files at or below
200 LLOC pass; files above 250 LLOC are NOT this check's concern
(the per-commit `file_lloc.py` hard-fails them).

Epic li-cvaudit (cvtodo) replaced the `LIVESPEC_RELEASE_GATE` skip
carve-out with a per-check severity lever: the soft-band scan ALWAYS
runs; `LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST` (non-empty) makes
soft-band offenders fail (exit 1, error level), unset downgrades the
SAME findings to warning + exit 0.

The check is driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` +
`capsys` + `rc = main()`) rather than via a `sys.executable`
subprocess (work-item livespec-dev-tooling-py9): no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*`
race under the parallel dispatcher, and materially faster.
`main()` reads `Path.cwd()` and `os.environ`, so the
monkeypatched cwd is the fixture root and the fail-lever is
toggled via `monkeypatch.setenv`/`delenv`.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_LLOC_SOFT_WARNINGS = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_lloc_soft_warnings.py"

_FAIL_VAR = "LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST"


def _git(*, cwd: Path, args: list[str]) -> None:
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

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and
    so `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "no_lloc_soft_warnings_under_test", str(_NO_LLOC_SOFT_WARNINGS)
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
    *,
    cwd: Path,
    fail_var: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd`, toggling the fail-lever.

    `fail_var=None` removes the lever from the environment (the
    warn-only state); any string sets it to that value via
    `monkeypatch.setenv`.
    """
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    monkeypatch.chdir(cwd)
    if fail_var is None:
        monkeypatch.delenv(_FAIL_VAR, raising=False)
    else:
        monkeypatch.setenv(_FAIL_VAR, fail_var)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write_py_with_lloc(*, tmp_path: Path, rel_path: str, n_statements: int) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    body_lines = "\n".join(f"x_{i} = {i}" for i in range(n_statements))
    full.write_text(
        "from __future__ import annotations\n\n__all__: list[str] = []\n\n" + body_lines + "\n",
        encoding="utf-8",
    )


def test_fails_on_soft_band_file_when_fail_var_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 201-250 LLOC file + fail-lever set → exit 1, error-level diagnostic."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
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


def test_warns_on_soft_band_file_when_fail_var_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A 201-250 LLOC file + fail-lever unset → exit 0, SAME finding at warning level."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    result = _run_check(cwd=tmp_path, fail_var=None, monkeypatch=monkeypatch, capsys=capsys)
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


def test_empty_fail_var_treated_as_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty-string fail-lever value counts as unset → warn + exit 0."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    result = _run_check(cwd=tmp_path, fail_var="", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"empty fail-lever should be treated as unset (warn + exit 0); "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        '"level": "warning"' in combined
    ), f"empty fail-lever should downgrade finding to warning; stderr={result.stderr!r}"


def test_accepts_file_at_or_below_soft_ceiling(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.py` file with ≤ 200 LLOC passes (exit 0) regardless of lever."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/small.py",
        n_statements=50,
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_ignores_file_above_hard_ceiling(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `.py` file with > 250 LLOC is NOT this check's concern (per-commit file_lloc.py handles it)."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/big.py",
        n_statements=300,
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_emits_each_offender_when_fail_var_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "medium_a.py" in combined
    assert "medium_b.py" in combined


def test_excludes_blank_lines_and_comments_and_docstrings(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_accepts_empty_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty repo cwd passes (exit 0)."""
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0


def test_warns_when_covered_trees_absent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty `covered_trees` classifier makes offenders newly-covered WARNs."""
    _write_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ncovered_trees = []\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"empty covered_trees should warn as newly-covered without failing; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert ".claude-plugin/scripts/livespec/medium.py" in combined
    assert "newly_covered" in combined
    assert '"level": "warning"' in combined


_MARKER = "# livespec-lloc-soft-band-owner: livespec-915y.1"


def _write_owned_py_with_lloc(
    *, tmp_path: Path, rel_path: str, n_statements: int, marker: str = _MARKER
) -> None:
    """Write a soft-band file carrying an ownership marker comment.

    Deliberately also carries an ORDINARY comment ahead of the marker: a
    real file is full of unrelated commentary, and a marker parser only
    ever exercised against files whose sole comment IS the marker would
    not prove that non-marker comments are skipped rather than misread.
    """
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    body_lines = "\n".join(f"x_{i} = {i}" for i in range(n_statements))
    full.write_text(
        "from __future__ import annotations\n\n"
        "# an ordinary comment that is not the ownership marker\n"
        f"{marker}\n\n"
        "__all__: list[str] = []\n\n" + body_lines + "\n",
        encoding="utf-8",
    )


def _set_probe(*, monkeypatch: pytest.MonkeyPatch, verdict: bool | None) -> None:
    """Replace the liveness seam with a SYNTHETIC probe.

    Swaps the module-level function wholesale, so no tracker, socket, or
    `bd` invocation is reachable — the live ledger is never contacted.
    """
    monkeypatch.setattr(
        _MODULE,
        "_probe_marker_liveness",
        lambda *, work_item: verdict,  # noqa: ARG005
    )


def test_release_tier_passes_owned_soft_band_file_when_liveness_unverifiable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Owned soft-band file + release lever + no reachable tracker → exit 0, UNVERIFIED.

    An owned live soft-band file must not block an unrelated release.
    Absent a configured tracker liveness is UNVERIFIED, which passes — but
    must never be indistinguishable from a verified check, so a structured
    diagnostic is required.
    """
    _write_owned_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"an owned soft-band file must not fail the release tier; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "liveness_unverified" in combined, (
        f"an unreachable tracker must emit an UNVERIFIED diagnostic, never a silent pass; "
        f"stderr={result.stderr!r}"
    )


def test_release_tier_owned_warning_states_the_refactor_is_owed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Carrying the debt is PERMITTED, not blessed — the diagnostic must say so.

    Guards the maintainer's named risk: a blessed escape hatch makes debt
    easy to carry. The accepted-entry diagnostic has to name the owed
    refactor rather than merely note a threshold.
    """
    _write_owned_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert "refactor" in combined.lower(), (
        f"an owned soft-band file's diagnostic must state the refactor is OWED; "
        f"stderr={result.stderr!r}"
    )
    assert (
        "livespec-915y.1" in combined
    ), f"the diagnostic must name the owning work-item; stderr={result.stderr!r}"


def test_release_tier_fails_owned_file_whose_marker_id_is_not_live(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Where liveness IS checkable, a closed/nonexistent marker id fails."""
    _write_owned_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    _set_probe(monkeypatch=monkeypatch, verdict=False)
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a checkable-but-dead marker id must fail the release tier; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert '"level": "error"' in combined


def test_release_tier_passes_owned_file_whose_marker_id_is_live(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Where liveness IS checkable and the marker id is live, the file passes."""
    _write_owned_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    _set_probe(monkeypatch=monkeypatch, verdict=True)
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"an owned live soft-band file must not block a release; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_marker_inside_a_string_literal_does_not_confer_ownership(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ownership is read from COMMENT tokens, so a string cannot forge it.

    A raw text search would accept this file and silently bless unowned
    debt; the marker must be a real comment.
    """
    full = tmp_path / ".claude-plugin/scripts/livespec/medium.py"
    full.parent.mkdir(parents=True, exist_ok=True)
    body_lines = "\n".join(f"x_{i} = {i}" for i in range(220))
    full.write_text(
        "from __future__ import annotations\n\n"
        f'FORGED = "{_MARKER}"\n\n'
        "__all__: list[str] = []\n\n" + body_lines + "\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode != 0, (
        f"a marker inside a string literal must NOT confer ownership; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_per_commit_tier_unchanged_for_owned_soft_band_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """PER-COMMIT IS UNTOUCHED: an owned soft-band file still warns and exits 0.

    Guards the property that makes this change landable — it is a strict
    LOOSENING of the release tier only. The sibling per-commit test covers
    the unowned case with the identical expectation, so together they pin
    per-commit behaviour for BOTH ownership states.
    """
    _write_owned_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/medium.py",
        n_statements=220,
    )
    result = _run_check(cwd=tmp_path, fail_var=None, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"per-commit tier must stay exit 0 for an owned soft-band file; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert '"level": "warning"' in combined


def test_marker_comment_costs_zero_lloc_at_the_band_boundary(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The marker is FREE: it cannot push a file ACROSS the band boundary.

    Measured outside-in rather than reasoned, per the slice's acceptance.
    198 statements is exactly 200 LLOC — one below the band — so if the
    marker comment cost even a single LLOC this file would become 201 and
    be reported. Its silence is the measurement.

    `test_marker_at_the_first_in_band_size_is_reported` is the paired
    control proving this silence is not vacuous.
    """
    _write_owned_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/boundary.py",
        n_statements=198,
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert "boundary.py" not in combined, (
        "a marked 200-LLOC file must not be reported at all; the ownership marker "
        f"appears to have cost LLOC and pushed it into the band. stderr={result.stderr!r}"
    )
    assert result.returncode == 0


def test_marker_at_the_first_in_band_size_is_reported(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Control for the boundary test: one statement more IS in band.

    199 statements is 201 LLOC. Without this pair, the boundary test's
    silence could equally mean the check never looked at the file.
    """
    _write_owned_py_with_lloc(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/boundary.py",
        n_statements=199,
    )
    result = _run_check(cwd=tmp_path, fail_var="true", monkeypatch=monkeypatch, capsys=capsys)
    combined = result.stdout + result.stderr
    assert (
        "boundary.py" in combined
    ), f"a 201-LLOC file must be reported, or the boundary test proves nothing; {combined!r}"


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    module = _load_check_module()
    assert callable(module.main)
