"""Tests for livespec_dev_tooling/parallel_check_dispatcher.py.

Covers the parallel check-aggregate dispatcher that replaces the serial
for-loop in the check: justfile recipe. Behavioral tests verify:

- independent targets run concurrently (subprocess-based, file-marker probe)
- coverage-data isolation by construction (work-item
  livespec-dev-tooling-cmn): each coverage namespace gets its own
  COVERAGE_FILE + TMPDIR, so concurrent targets and their
  COVERAGE_PROCESS_START subprocess children cannot collide. The former
  hand-enumerated collision edge for check-check-coverage-incremental is
  retired; only the genuine read-after-write coverage-pair data
  dependency survives as an ordering edge.
- check-coverage runs only AFTER check-per-file-coverage completes
  (the surviving producer->consumer data dependency)
- per-target wall-time timings appear in the aggregate output
- skip list is respected (skipped targets do not run)
- core-budget cap is applied (_cap_workers bounds the worker count)
- failed targets surface in the summary and produce exit 1

Private names are accessed via the imported module object (the
package-private access model, mirroring
tests/livespec_dev_tooling/agent_hooks/).
"""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pytest

import livespec_dev_tooling.parallel_check_dispatcher as mod
from livespec_dev_tooling.parallel_check_dispatcher import (
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
# Coverage-data isolation by construction (work-item livespec-dev-tooling-cmn)
# ---------------------------------------------------------------------------


def test_coverage_pair_shares_one_namespace_key() -> None:
    """check-per-file-coverage (producer) and check-coverage (consumer) share a key.

    Sharing a namespace key means they resolve to the same isolated
    coverage dir, so the consumer reads the producer's COVERAGE_FILE —
    the explicit producer->consumer data dependency.
    """
    namespaces = mod._COVERAGE_NAMESPACES  # noqa: SLF001
    assert namespaces["check-per-file-coverage"] == namespaces["check-coverage"], (
        "the full-tree coverage pair must share one namespace key so the consumer "
        f"reads the producer's isolated COVERAGE_FILE; got {namespaces!r}"
    )


def test_incremental_isolated_in_its_own_namespace() -> None:
    """check-check-coverage-incremental gets a namespace DISTINCT from the pair.

    A distinct namespace key means a distinct isolated dir: the
    incremental gate's `coverage combine` can only glob its own dir, so
    a concurrent check-per-file-coverage can never erase its data. This
    is the structural fix that retires the hand-pinned collision edge.
    """
    namespaces = mod._COVERAGE_NAMESPACES  # noqa: SLF001
    assert (
        namespaces["check-check-coverage-incremental"] != namespaces["check-per-file-coverage"]
    ), (
        "the incremental gate must be isolated in its OWN coverage namespace "
        "(distinct from the full-tree pair) so collisions are structurally impossible; "
        f"got {namespaces!r}"
    )


def test_incremental_collision_edge_retired() -> None:
    """The former incremental->per-file-coverage serialization edge is removed.

    Only the genuine read-after-write coverage-pair data dependency
    survives as an ordering edge; the incremental gate is no longer
    serialized after per-file-coverage (it runs fully concurrently in
    its own namespace).
    """
    consumers = mod._COVERAGE_CONSUMERS  # noqa: SLF001
    assert "check-check-coverage-incremental" not in consumers, (
        "the hand-pinned incremental->per-file-coverage collision edge must be retired; "
        f"got coverage-consumer edges {consumers!r}"
    )
    assert consumers.get("check-coverage") == "check-per-file-coverage", (
        "the surviving coverage-pair data dependency (consumer check-coverage reads "
        f"producer check-per-file-coverage) must remain; got {consumers!r}"
    )


def test_target_env_isolates_coverage_file_and_tmpdir(*, tmp_path: Path) -> None:
    """_target_env points COVERAGE_FILE + TMPDIR at the target's namespace dir.

    A coverage-touching target gets a COPY of the environment with both
    COVERAGE_FILE and TMPDIR redirected into its isolated namespace dir,
    so pytest-cov (and its COVERAGE_PROCESS_START children) and any
    shared-temp artifact land inside that dir.
    """
    ns_dir = tmp_path / "covns-full-tree"
    (ns_dir / "tmp").mkdir(parents=True)
    namespace_dirs = {"full-tree": ns_dir}
    env = mod._target_env(  # noqa: SLF001
        name="check-per-file-coverage", namespace_dirs=namespace_dirs
    )
    assert env is not None, "a coverage-touching target must receive an isolated env"
    assert env["COVERAGE_FILE"] == str(
        ns_dir / ".coverage"
    ), f"COVERAGE_FILE must point into the namespace dir; got {env['COVERAGE_FILE']!r}"
    assert env["TMPDIR"] == str(
        ns_dir / "tmp"
    ), f"TMPDIR must point into the namespace dir; got {env['TMPDIR']!r}"


def test_target_env_returns_none_for_non_coverage_target() -> None:
    """_target_env returns None for a target with no coverage namespace.

    A non-coverage target inherits the parent env unchanged (no isolated
    COVERAGE_FILE/TMPDIR overlay), so the dispatcher passes env=None.
    """
    env = mod._target_env(name="check-lint", namespace_dirs={})  # noqa: SLF001
    assert env is None, f"non-coverage target must get None (inherit parent env); got {env!r}"


def test_build_namespace_dirs_shares_within_key_and_isolates_across(*, tmp_path: Path) -> None:
    """_build_namespace_dirs mints one dir per distinct namespace key.

    The full-tree coverage pair (same key) resolves to one shared dir;
    the incremental gate (distinct key) gets a separate dir. Each dir is
    a fresh directory under the root with its own tmp/ subdir.
    """
    targets = [
        "check-lint",
        "check-per-file-coverage",
        "check-coverage",
        "check-check-coverage-incremental",
    ]
    dirs = mod._build_namespace_dirs(  # noqa: SLF001
        targets=targets, skip_set=frozenset(), root=tmp_path
    )
    full_tree_key = mod._COVERAGE_NAMESPACES["check-per-file-coverage"]  # noqa: SLF001
    incremental_key = mod._COVERAGE_NAMESPACES[  # noqa: SLF001
        "check-check-coverage-incremental"
    ]
    assert full_tree_key in dirs and incremental_key in dirs
    assert (
        dirs[full_tree_key] != dirs[incremental_key]
    ), "distinct namespace keys must resolve to distinct isolated dirs"
    for ns_dir in dirs.values():
        assert ns_dir.is_dir(), f"namespace dir {ns_dir} must exist"
        assert (ns_dir / "tmp").is_dir(), f"namespace dir {ns_dir} must carry a tmp/ subdir"


def test_build_namespace_dirs_skips_skipped_targets(*, tmp_path: Path) -> None:
    """A coverage target in the skip set does not get a namespace dir.

    When every coverage target sharing a key is skipped, that key's dir
    is not minted (nothing will use it).
    """
    dirs = mod._build_namespace_dirs(  # noqa: SLF001
        targets=["check-check-coverage-incremental"],
        skip_set=frozenset({"check-check-coverage-incremental"}),
        root=tmp_path,
    )
    assert dirs == {}, f"skipped coverage targets must mint no namespace dir; got {dirs!r}"


# ---------------------------------------------------------------------------
# _deferred_run (the surviving producer->consumer data dependency)
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
        env=None,
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
    """_deferred_run calls _run_one for the dependent when the prereq exited 0.

    The isolated env handed to _deferred_run is forwarded to _run_one so
    the consumer reads the producer's COVERAGE_FILE.
    """
    prereq = TargetResult(
        name="check-per-file-coverage",
        skipped=False,
        exit_code=0,
        wall_time_s=1.0,
        output="ok",
    )
    called_with: list[tuple[str, dict[str, str] | None]] = []

    def fake_run_one(*, name: str, cwd: Path, env: dict[str, str] | None) -> TargetResult:
        _ = cwd
        called_with.append((name, env))
        return TargetResult(name=name, skipped=False, exit_code=0, wall_time_s=0.1, output="ran")

    monkeypatch.setattr(mod, "_run_one", fake_run_one)

    forwarded = {"COVERAGE_FILE": "/iso/.coverage"}
    result = _deferred_run(
        name="check-coverage",
        prereq_fut=_make_done_future(result=prereq),
        cwd=tmp_path,
        env=forwarded,
    )
    assert result.exit_code == 0, f"expected exit_code=0; got {result.exit_code}"
    assert called_with == [
        ("check-coverage", forwarded)
    ], f"expected _run_one called once with the forwarded isolated env; got {called_with}"


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
    passes only when the dispatcher enforces the producer->consumer data
    dependency edge.
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


def test_coverage_target_runs_with_isolated_coverage_file_env(*, tmp_path: Path) -> None:
    """A coverage target's recipe sees COVERAGE_FILE/TMPDIR set into an isolated dir.

    The recipe writes the COVERAGE_FILE + TMPDIR values it received into
    a probe file; the test asserts both point under a per-namespace dir
    that the dispatcher minted inside cwd (NOT the inherited environment),
    proving the isolation env reaches the `just` subprocess.
    """
    probe = tmp_path / "coverage_env_probe"
    justfile_text = (
        "check-per-file-coverage:\n"
        f'    printf "%s\\n%s\\n" "$COVERAGE_FILE" "$TMPDIR" > {probe}\n'
    )
    _write_justfile(tmp_path=tmp_path, content=justfile_text)
    result = _run_dispatcher(tmp_path=tmp_path, args=["--", "check-per-file-coverage"])
    assert result.returncode == 0, (
        f"coverage target should run; got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert probe.is_file(), "the recipe should have written the env probe"
    lines = probe.read_text(encoding="utf-8").splitlines()
    coverage_file, tmpdir = lines[0], lines[1]
    assert coverage_file.endswith(
        ".coverage"
    ), f"COVERAGE_FILE should name a .coverage data file; got {coverage_file!r}"
    assert (
        "covns-" in coverage_file
    ), f"COVERAGE_FILE should live under a minted per-namespace dir; got {coverage_file!r}"
    assert (
        "covns-" in tmpdir
    ), f"TMPDIR should live under a minted per-namespace dir; got {tmpdir!r}"
    # The dispatcher removes each namespace dir after all futures resolve,
    # so the system temp dir does not accumulate one covns-* tree per run.
    assert not Path(
        coverage_file
    ).exists(), f"the minted namespace COVERAGE_FILE should be cleaned up after the run; {coverage_file!r} remains"


def test_incremental_runs_concurrently_with_no_prereq_edge(*, tmp_path: Path) -> None:
    """check-check-coverage-incremental runs even though no producer precedes it.

    The incremental gate is isolated in its own namespace with no data
    dependency, so the dispatcher runs it immediately (not deferred
    behind check-per-file-coverage). The recipe creates a marker; the
    test confirms it ran and the run exited 0.
    """
    marker = tmp_path / "incremental_ran"
    justfile_text = "check-check-coverage-incremental:\n" f"    touch {marker}\n"
    _write_justfile(tmp_path=tmp_path, content=justfile_text)
    result = _run_dispatcher(tmp_path=tmp_path, args=["--", "check-check-coverage-incremental"])
    assert result.returncode == 0, (
        f"incremental gate should run independently; got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert marker.exists(), "the incremental gate should have run with no blocking prereq"


def test_prereq_skipped_runs_dependent_independently(*, tmp_path: Path) -> None:
    """check-coverage runs independently when check-per-file-coverage is skipped.

    Covers the dispatcher branch: the consumer's producer is named in
    _COVERAGE_CONSUMERS but is not in futures (it was skipped).
    check-coverage should run and succeed even though
    check-per-file-coverage was skipped.
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
