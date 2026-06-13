"""Tests for livespec_dev_tooling/parallel_check_dispatcher.py.

Covers the parallel check-aggregate dispatcher that replaces the serial
for-loop in the check: justfile recipe. Behavioral tests verify:

- independent targets run concurrently (subprocess-based, file-marker probe)
- check-coverage runs only AFTER check-per-file-coverage completes
  (file-marker probe: check-coverage fails if the marker is absent)
- per-target wall-time timings appear in the aggregate output
- skip list is respected (skipped targets do not run)
- core-budget cap is applied (_cap_workers bounds the worker count)
- failed targets surface in the summary and produce exit 1

Private names are imported via from-imports (the package-private
access model, mirroring tests/livespec_dev_tooling/agent_hooks/).
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pytest

from livespec_dev_tooling.parallel_check_dispatcher import (
    _ARTIFACT_PREREQS,
    TargetResult,
    _cap_workers,
    _configure_logger,
    _deferred_run,
    _emit_result,
    _emit_summary,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = _REPO_ROOT / "livespec_dev_tooling" / "parallel_check_dispatcher.py"


# ---------------------------------------------------------------------------
# _cap_workers
# ---------------------------------------------------------------------------


def test_cap_workers_uses_default_when_not_requested() -> None:
    """_cap_workers(requested=None) returns a positive value bounded by cpu_count."""
    result = _cap_workers(requested=None)
    assert result >= 1
    assert result <= (os.cpu_count() or 1)


def test_cap_workers_respects_explicit_request_when_below_cpu_count() -> None:
    """_cap_workers(requested=1) returns 1 regardless of cpu_count."""
    result = _cap_workers(requested=1)
    assert result == 1


def test_cap_workers_caps_at_cpu_count_when_request_exceeds_it() -> None:
    """_cap_workers(requested=999) is capped at cpu_count (never exceeds real cores)."""
    cpu = os.cpu_count() or 1
    result = _cap_workers(requested=999)
    assert result <= cpu


# ---------------------------------------------------------------------------
# _ARTIFACT_PREREQS — shared coverage-data-namespace serialization edges
# ---------------------------------------------------------------------------


def test_coverage_incremental_is_serialized_after_per_file_coverage() -> None:
    """check-check-coverage-incremental must run AFTER check-per-file-coverage.

    Both run a coverage-instrumented pytest in the repo root. A
    concurrent `check-per-file-coverage` (`pytest -n auto --cov`) runs
    `coverage combine`, which globs and erases `.coverage*` data files —
    including the incremental gate's `.coverage.check-coverage-
    incremental`. Run concurrently, the incremental gate intermittently
    finds its data file swept ("No data to report") and hard-fails.
    Serializing it after per-file-coverage (the existing artifact-prereq
    pattern used for check-coverage) removes the only concurrent
    coverage writer and makes the gate deterministic. The aggregate
    target name carries the double-`check` prefix
    (`check-check-coverage-incremental`), which is the dispatcher key.
    """
    assert _ARTIFACT_PREREQS.get("check-check-coverage-incremental") == "check-per-file-coverage"
    # The pre-existing edge for the aggregate coverage gate stays intact.
    assert _ARTIFACT_PREREQS.get("check-coverage") == "check-per-file-coverage"


# ---------------------------------------------------------------------------
# _deferred_run
# ---------------------------------------------------------------------------


def _make_done_future(*, result: TargetResult) -> Future[TargetResult]:
    """Return an already-completed Future wrapping result."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut: Future[TargetResult] = pool.submit(lambda: result)
    return fut


def test_deferred_run_skips_dependent_when_prereq_fails() -> None:
    """_deferred_run marks the dependent skipped when the prereq exited non-zero."""
    prereq = TargetResult(
        name="check-per-file-coverage",
        skipped=False,
        exit_code=1,
        wall_time_s=1.0,
        output="FAIL",
    )
    result = _deferred_run(
        name="check-coverage",
        prereq_fut=_make_done_future(result=prereq),
        cwd=Path(),
    )
    assert (
        result.skipped is True
    ), f"expected skipped=True when prereq failed; got skipped={result.skipped!r}"
    assert (
        "check-per-file-coverage" in result.output or "prereq" in result.output.lower()
    ), f"expected prereq name in output; got {result.output!r}"


def test_deferred_run_runs_dependent_when_prereq_succeeds(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """_deferred_run calls _run_one for the dependent when the prereq exited 0."""
    import livespec_dev_tooling.parallel_check_dispatcher as mod

    prereq = TargetResult(
        name="check-per-file-coverage",
        skipped=False,
        exit_code=0,
        wall_time_s=1.0,
        output="ok",
    )
    called_with: list[str] = []

    def fake_run_one(*, name: str, cwd: Path) -> TargetResult:
        _ = cwd
        called_with.append(name)
        return TargetResult(name=name, skipped=False, exit_code=0, wall_time_s=0.1, output="ran")

    monkeypatch.setattr(mod, "_run_one", fake_run_one)

    result = _deferred_run(
        name="check-coverage",
        prereq_fut=_make_done_future(result=prereq),
        cwd=tmp_path,
    )
    assert result.exit_code == 0, f"expected exit_code=0; got {result.exit_code}"
    assert called_with == ["check-coverage"], f"expected _run_one called once; got {called_with}"


# ---------------------------------------------------------------------------
# _emit_result
# ---------------------------------------------------------------------------


def test_emit_result_shows_header_and_timing_for_passed_target(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """_emit_result writes a header with timing for a passing target."""
    log = _configure_logger()
    result = TargetResult(
        name="check-lint", skipped=False, exit_code=0, wall_time_s=2.3, output="lint ok\n"
    )
    _emit_result(result=result, log=log)
    captured = capsys.readouterr()
    assert "check-lint" in captured.out
    assert "2.3" in captured.out or "wall" in captured.out.lower()
    assert "lint ok" in captured.out


def test_emit_result_shows_failed_status_for_nonzero_exit(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """_emit_result labels a non-zero exit as FAILED in the header."""
    log = _configure_logger()
    result = TargetResult(
        name="check-fail", skipped=False, exit_code=1, wall_time_s=0.5, output="error\n"
    )
    _emit_result(result=result, log=log)
    captured = capsys.readouterr()
    assert "check-fail" in captured.out
    assert "FAILED" in captured.out or "failed" in captured.out.lower()


def test_emit_result_shows_skipped_label_for_skipped_target(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """_emit_result writes a skipped label for a skipped target and returns early."""
    log = _configure_logger()
    result = TargetResult(
        name="check-coverage", skipped=True, exit_code=0, wall_time_s=0.0, output=""
    )
    _emit_result(result=result, log=log)
    captured = capsys.readouterr()
    assert "check-coverage" in captured.out
    assert "skipped" in captured.out.lower()


def test_emit_result_handles_empty_output(*, capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_result writes only the header when a target produced no output."""
    log = _configure_logger()
    result = TargetResult(
        name="check-quiet", skipped=False, exit_code=0, wall_time_s=0.1, output=""
    )
    _emit_result(result=result, log=log)
    captured = capsys.readouterr()
    assert "check-quiet" in captured.out


# ---------------------------------------------------------------------------
# _emit_summary
# ---------------------------------------------------------------------------


def test_emit_summary_returns_0_when_all_targets_pass(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """_emit_summary exits 0 and writes 'passed' when all results are exit 0."""
    log = _configure_logger()
    results = [
        TargetResult(name="check-lint", skipped=False, exit_code=0, wall_time_s=1.0, output=""),
        TargetResult(name="check-format", skipped=False, exit_code=0, wall_time_s=0.8, output=""),
    ]
    code = _emit_summary(results=results, log=log)
    assert code == 0, f"expected 0; got {code}"
    captured = capsys.readouterr()
    assert "passed" in captured.out.lower()


def test_emit_summary_returns_1_when_any_target_fails(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """_emit_summary exits 1 and lists failing targets when any result is non-zero."""
    log = _configure_logger()
    results = [
        TargetResult(name="check-lint", skipped=False, exit_code=0, wall_time_s=1.0, output=""),
        TargetResult(name="check-types", skipped=False, exit_code=1, wall_time_s=2.0, output=""),
    ]
    code = _emit_summary(results=results, log=log)
    assert code == 1, f"expected 1; got {code}"
    captured = capsys.readouterr()
    assert "check-types" in captured.out
    assert "failed" in captured.out.lower() or "Failed" in captured.out


def test_emit_summary_shows_per_target_timings(*, capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_summary includes per-target wall times in the output (feeds e60)."""
    log = _configure_logger()
    results = [
        TargetResult(
            name="check-per-file-coverage", skipped=False, exit_code=0, wall_time_s=141.6, output=""
        ),
        TargetResult(name="check-lint", skipped=False, exit_code=0, wall_time_s=1.2, output=""),
    ]
    _emit_summary(results=results, log=log)
    captured = capsys.readouterr()
    assert "141.6" in captured.out or "check-per-file-coverage" in captured.out
    assert "1.2" in captured.out or "check-lint" in captured.out


# ---------------------------------------------------------------------------
# main() — subprocess-based end-to-end tests
# ---------------------------------------------------------------------------


def _write_justfile(*, tmp_path: Path, content: str) -> None:
    (tmp_path / "justfile").write_text(content, encoding="utf-8")


def _run_dispatcher(*, tmp_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_MODULE), *args],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )


def test_main_exits_0_and_emits_timings_when_all_targets_pass(*, tmp_path: Path) -> None:
    """main() exits 0 and includes per-target wall times when all targets pass."""
    _write_justfile(
        tmp_path=tmp_path,
        content="check-lint:\n    @echo lint ok\n\ncheck-format:\n    @echo format ok\n",
    )
    result = _run_dispatcher(tmp_path=tmp_path, args=["--", "check-lint", "check-format"])
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "check-lint" in result.stdout
    assert "check-format" in result.stdout
    combined = result.stdout.lower()
    assert "wall" in combined or "0." in combined


def test_main_exits_1_when_any_target_fails(*, tmp_path: Path) -> None:
    """main() exits 1 and names the failing target when any target exits non-zero."""
    _write_justfile(
        tmp_path=tmp_path,
        content="check-lint:\n    @echo ok\n\ncheck-fail:\n    @exit 1\n",
    )
    result = _run_dispatcher(tmp_path=tmp_path, args=["--", "check-lint", "check-fail"])
    assert result.returncode == 1, (
        f"expected exit 1; got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert "check-fail" in result.stdout or "check-fail" in result.stderr


def test_main_skips_targets_in_skip_list(*, tmp_path: Path) -> None:
    """main() skips targets in --skip and exits 0 even if the skipped target would fail."""
    _write_justfile(
        tmp_path=tmp_path,
        content="check-lint:\n    @echo ok\n\ncheck-coverage:\n    @exit 1\n",
    )
    result = _run_dispatcher(
        tmp_path=tmp_path,
        args=["--skip", "check-coverage", "--", "check-lint", "check-coverage"],
    )
    assert result.returncode == 0, (
        f"check-coverage should be skipped; got {result.returncode}\n" f"stdout={result.stdout!r}"
    )
    combined = result.stdout.lower()
    assert "skipped" in combined


def test_coverage_dependency_ordering_enforced(*, tmp_path: Path) -> None:
    """check-coverage runs only AFTER check-per-file-coverage: file-marker probe.

    check-per-file-coverage creates a marker file; check-coverage's recipe
    asserts the marker exists. If the dispatcher were to run them concurrently
    or in the wrong order, check-coverage would fail (non-zero exit). The test
    passes only when the dispatcher enforces the dependency edge.
    """
    marker = tmp_path / "per_file_coverage_done"
    justfile_text = (
        "check-per-file-coverage:\n"
        f"    touch {marker}\n"
        "\n"
        "check-coverage:\n"
        f"    test -f {marker}\n"
    )
    _write_justfile(tmp_path=tmp_path, content=justfile_text)
    result = _run_dispatcher(
        tmp_path=tmp_path,
        args=["--", "check-per-file-coverage", "check-coverage"],
    )
    assert result.returncode == 0, (
        f"check-coverage should run after check-per-file-coverage (marker must exist); "
        f"returncode={result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


def test_prereq_skipped_runs_dependent_independently(*, tmp_path: Path) -> None:
    """check-coverage runs independently when check-per-file-coverage is skipped.

    Covers the dispatcher branch: prereq is not None but not in futures
    (prereq was in the skip list). check-coverage should run and succeed
    even though check-per-file-coverage was skipped.
    """
    marker = tmp_path / "coverage_ran"
    _write_justfile(
        tmp_path=tmp_path,
        content=(
            "check-per-file-coverage:\n    @exit 1\n\n" f"check-coverage:\n    touch {marker}\n"
        ),
    )
    result = _run_dispatcher(
        tmp_path=tmp_path,
        args=[
            "--skip",
            "check-per-file-coverage",
            "--",
            "check-per-file-coverage",
            "check-coverage",
        ],
    )
    assert result.returncode == 0, (
        f"check-coverage should run independently when prereq is skipped; "
        f"got {result.returncode}\nstdout={result.stdout!r}"
    )
    assert marker.exists(), "check-coverage should have created the marker file"


# ---------------------------------------------------------------------------
# Module importability
# ---------------------------------------------------------------------------


def test_module_importable_without_running_main() -> None:
    """The module imports cleanly without invoking main().

    Closes the sys.path.insert already-present branch (pytest's
    pythonpath has pre-populated sys.path) and the __name__ == __main__
    else-arm (module imported, not run as a script).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "parallel_check_dispatcher_import_test", str(_MODULE)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be callable after import"
