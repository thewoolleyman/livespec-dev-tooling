"""Outside-in test for `dev-tooling/checks/per_file_coverage.py` — per-file 100% gate.

Every covered `.py` file MUST hit 100% line and 100% branch
coverage independently — not just total. This script supersedes
the totalize-only `[tool.coverage.report].fail_under = 100`
threshold by reading the `.coverage` data file (post-combine, as
produced by `pytest --cov --cov-branch`) and failing the first
time any single covered file drops below 100% on either axis.

This module holds the OUTERMOST behavioral test for that gate.
Cycle 1 pins the missing-line-coverage rejection: a synthetic
`subject.py` with five executable statements has only two
recorded as covered in the synthetic `.coverage` data file; the
check must exit non-zero and surface the offending source file
plus enough information to locate the gap. Subsequent cycles
will pin missing-branch-coverage rejection, the no-data case,
and the all-files-100% accept case.

The fixture builds a synthetic project root at `tmp_path` with
exactly one source file plus a hand-authored `.coverage` data
file produced via `coverage.CoverageData.add_lines` (writing
parallel-mode-disabled, single-file form so `Coverage.load()`
finds it directly without needing a `combine()` step).

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. The six check call sites
spawned identically, so they now share one `_run_check` helper; `main()`
resolves `cwd/.coverage`, so the monkeypatched cwd anchors the fixture
exactly as the child's `cwd=` argument did, and
`monkeypatch.delenv("COVERAGE_FILE")` supplies what the child's `env=`
mapping did. The assertion targets are unchanged — the int exit code
plus the offending-file diagnostic, now read off `capsys` instead of
`CompletedProcess`.

A SEVENTH SPAWN, not a check spawn, went with them: the fixture builder
in `test_per_file_coverage_empty_data_emits_actionable_hint` that
constructs the present-but-empty `.coverage`. It ran in a child because
it built the file via `Coverage.start()` / `stop()` / `save()`, and a
nested `Coverage.start()` would suspend the outer `pytest --cov`
session's tracer and blind it to this fixture's own lines. The child was
a consequence of that construction, not of the fixture: `CoverageData`
— the same public API this file's other fixtures already use — writes
the identical artifact with no tracer involved at all
(`add_lines({})` + `write()` leaves a loadable data file whose
`measured_files()` is empty). Both forms were compared before the swap
and produce a present, loadable, zero-measured-file `.coverage`. So this
file carries NO spawn and its `subprocess_spawn_allowlist` entry is
removed alongside its eleven siblings'.

Branch parity with the retired spawns: the same fixtures drive the same
arms — the below-100%-line rejection, the missing-`.coverage` early
exit, the all-100% accept, the COVERAGE_FILE-env resolution, and the
empty-data actionable hint. The two lines the child process reached that
an in-process call cannot are the module's vendored-path guard
(`sys.path.insert`) and its
`if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, and
`test_per_file_coverage_module_importable_without_running_main` still
closes the already-present arm of the vendored-path branch. No new
exclusion is introduced.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pytest
from coverage import CoverageData

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PER_FILE_COVERAGE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "per_file_coverage.py"


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and capture output.

    `monkeypatch.delenv("COVERAGE_FILE")` supplies in this process exactly
    what the retired child's `env=` mapping did. The parallel check
    dispatcher (work-item livespec-dev-tooling-cmn) sets COVERAGE_FILE for
    the `check-per-file-coverage` pytest run; tests that exercise
    per_file_coverage's DEFAULT `cwd/.coverage` resolution must not see
    that override, or the check would read the outer run's isolated data
    file instead of the fixture's cwd-local `.coverage`.
    """
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("COVERAGE_FILE", raising=False)
    rc = _load_per_file_coverage_module().main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_per_file_coverage_rejects_file_below_100_line_coverage(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A measured file with line coverage below 100% makes the check exit non-zero.

    The fixture writes a synthetic `subject.py` with five
    executable statements (the canonical livespec module preamble
    of `from __future__ import annotations` + `__all__` + three
    trivial assignment statements). A hand-authored `.coverage`
    data file records only two of those statements as covered
    (the import and the `__all__` declaration); the three
    assignment statements are missing.
    The check, invoked with `cwd=tmp_path`, must walk the
    `.coverage` data, detect `subject.py` at <100% line coverage,
    exit non-zero, and surface the offending file path so the
    developer can locate the gap.
    """
    src_file = tmp_path / "subject.py"
    src_file.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "x = 1\n"
        "y = 2\n"
        "z = 3\n",
        encoding="utf-8",
    )

    # Build the synthetic .coverage data file directly via the
    # CoverageData API. suffix=False writes a single
    # `.coverage` (no parallel-mode .coverage.<host>.<pid>.<random>
    # files) so per_file_coverage.py's Coverage.load() finds it
    # immediately without needing a combine() step. add_lines
    # records the set of executed line numbers per file.
    data = CoverageData(basename=str(tmp_path / ".coverage"), suffix=False)
    data.add_lines({str(src_file): [1, 3]})
    data.write()

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"per_file_coverage should reject subject.py at <100% line coverage with non-zero exit; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_token = "subject.py"
    assert expected_token in combined, (
        f"per_file_coverage diagnostic does not surface offending file `{expected_token}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_per_file_coverage_rejects_when_no_coverage_data_file_exists(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No `.coverage` file in cwd makes the check exit non-zero with a clear diagnostic.

    Per `per_file_coverage.py`: the helper inspects
    `cwd / ".coverage"` and, if missing, logs a "no coverage data
    found" error and returns 1. Drives that early-exit branch:
    fixture is a fresh tmp_path with no `.coverage` file. The
    check must exit non-zero and surface the missing path so the
    developer knows pytest --cov was skipped.
    """
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"per_file_coverage should reject missing .coverage file with non-zero exit; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "no coverage data found" in combined, (
        f"per_file_coverage diagnostic does not surface 'no coverage data found' message; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_per_file_coverage_accepts_when_all_files_at_100_percent(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A `.coverage` data file where every measured file is at 100% passes the check.

    Per `per_file_coverage.py`: when the per-file
    walk finds no offenders, the helper returns 0. Fixture: a
    synthetic `subject.py` with exactly two executable statements
    (the import line + the __all__ declaration); the `.coverage`
    data file records both as covered. The check exits 0.

    Drives the success-path return on (`return 0`) and the
    no-offenders branch (86->83 in coverage's report: when the
    loop body's `if line_pct < 100.0` arm is NOT taken, control
    returns to the loop header, and on loop exit the empty
    offenders list short-circuits the if-offenders block,
    returning 0).
    """
    src_file = tmp_path / "subject.py"
    src_file.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\n",
        encoding="utf-8",
    )
    data = CoverageData(basename=str(tmp_path / ".coverage"), suffix=False)
    # Both executable statements covered: the future-import
    # and the __all__ declaration. Coverage's `add_lines`
    # records executed lines per file.
    data.add_lines({str(src_file): [1, 2]})
    data.write()

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"per_file_coverage should accept all-100% data with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def _load_per_file_coverage_module() -> object:
    """Import per_file_coverage.py fresh as a standalone module object.

    Mirrors the importability/constant tests below: load the check via
    `importlib.util.spec_from_file_location` so `main()` can be exercised
    IN-PROCESS (deterministic coverage of its branches, no
    subprocess-coverage fragility — the gate itself runs the check as a
    subprocess, but its branch coverage is pinned here directly).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "per_file_coverage_for_behavior_test", str(_PER_FILE_COVERAGE)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_per_file_coverage_reads_coverage_file_env(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """per_file_coverage reads the data file named by COVERAGE_FILE, not cwd/.coverage.

    Work-item livespec-dev-tooling-cmn: the parallel check dispatcher
    exports COVERAGE_FILE pointed at the target's isolated namespace dir.
    The fixture writes the synthetic `.coverage` into a SUBDIR (not cwd)
    and points COVERAGE_FILE at it; no `.coverage` exists in cwd. The
    check (run in-process with cwd monkeypatched to tmp_path) must read
    the isolated file and reject the <100% subject rather than failing
    with "no coverage data found" for a missing cwd file.
    """
    src_file = tmp_path / "subject.py"
    src_file.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "x = 1\n"
        "y = 2\n"
        "z = 3\n",
        encoding="utf-8",
    )
    iso_dir = tmp_path / "covns-full-tree"
    iso_dir.mkdir()
    iso_data = iso_dir / ".coverage"
    data = CoverageData(basename=str(iso_data), suffix=False)
    data.add_lines({str(src_file): [1, 3]})
    data.write()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COVERAGE_FILE", str(iso_data))
    module = _load_per_file_coverage_module()
    rc = module.main()

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc != 0, (
        f"per_file_coverage should read the COVERAGE_FILE-named data file and reject "
        f"subject.py at <100%; got rc={rc} output={combined!r}"
    )
    assert "subject.py" in combined, (
        f"per_file_coverage should have read the isolated COVERAGE_FILE and surfaced "
        f"subject.py; output={combined!r}"
    )


def test_per_file_coverage_empty_data_emits_actionable_hint(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty coverage data file fails with the actionable Tier-2 diagnostic.

    Work-item livespec-dev-tooling-cmn Tier 2: when the data file is
    PRESENT but measures zero files (the symptom of a concurrent/
    subprocess COVERAGE_FILE collision whose `coverage combine` swept the
    data — on which `json_report` would raise the cryptic "No data to
    report"), the gate must emit an ACTIONABLE message naming the
    isolated-COVERAGE_FILE fix. The fixture writes a present-but-empty
    `.coverage` (zero measured files, file on disk); the check is run
    in-process with cwd monkeypatched to tmp_path and asserts the hint
    mentions isolating COVERAGE_FILE.
    """
    # Write the present-but-empty `.coverage` through `CoverageData`, the
    # same public API this file's other fixtures use. Recording an empty
    # line map is what materializes the data file; the earlier
    # `Coverage.start()` / `stop()` / `save()` form needed a SUBPROCESS
    # only because a nested `Coverage.start()` would suspend the outer
    # pytest-cov session's tracer and blind it to this fixture's own
    # lines. No tracer is started here, so no child is needed, and the
    # artifact is identical: a loadable file whose measured_files() is
    # empty. The `is_file` + `no measured files` assertions below are
    # what hold that — if the write ever stopped materializing the file,
    # this test would fail loudly rather than silently degrade into the
    # missing-file case that `..._missing_data_file_...` already covers.
    empty_db = tmp_path / ".coverage"
    data = CoverageData(basename=str(empty_db), suffix=False)
    data.add_lines({})
    data.write()
    assert empty_db.is_file(), (
        "fixture must leave a present .coverage file so the EMPTY-data branch "
        "is the one under test, not the missing-file branch"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COVERAGE_FILE", raising=False)
    module = _load_per_file_coverage_module()
    rc = module.main()

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert rc != 0, (
        f"per_file_coverage should reject empty coverage data with non-zero exit; "
        f"got rc={rc} output={combined!r}"
    )
    assert "isolated COVERAGE_FILE" in combined, (
        f"empty-data diagnostic must be the actionable isolated-COVERAGE_FILE hint, "
        f"not the cryptic 'No data to report'; output={combined!r}"
    )
    assert "no measured files" in combined, (
        "the empty-data branch (present file, zero measured files) must be the one "
        f"that fired — not the missing-file branch; output={combined!r}"
    )


def test_per_file_coverage_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main().

    Closes branch 48->51 (`if str(_VENDOR_DIR) not in sys.path`
    already-present branch — pytest's pythonpath has pre-populated
    sys.path) and branch 101->exit (`if __name__ == "__main__":`
    else-arm — module imported, not run as a script).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "per_file_coverage_for_import_test",
        str(_PER_FILE_COVERAGE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_full_coverage_pct_constant_pins_v033_d2_threshold() -> None:
    """The `_FULL_COVERAGE_PCT` constant pins the v033 D2 100.0% threshold.

    Per v033 D2: every covered file MUST be at 100% line coverage.
    The threshold is policy-set with no carveout. This test pins
    the policy in code so a future loosening of the threshold
    requires explicit test failure + intentional bump.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "per_file_coverage_for_constant_test",
        str(_PER_FILE_COVERAGE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._FULL_COVERAGE_PCT == 100.0  # noqa: SLF001


def test_per_file_coverage_parses_xdist_combined_data(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """per_file_coverage.py correctly reads `.coverage` data combined from xdist workers.

    Per v039 D2: `check-coverage` invokes `pytest -n auto` so the
    test suite executes across N worker processes. Each worker
    writes its own parallel-mode `.coverage.<host>.<pid>.<rand>`
    data file; pytest-cov's session-end hook calls
    `coverage.Coverage().combine()` to merge them into a single
    `.coverage` file before `per_file_coverage.py` runs. This
    test pins the post-processor's correctness against that
    combined shape: two synthetic worker files (one missing line
    coverage on `subject.py`, one with all lines covered on
    `other.py`) are combined in `tmp_path`; the check must walk
    the merged data and reject `subject.py` while leaving
    `other.py` unflagged.

    The hard `import xdist` at the top guarantees this test fails
    at collection time when pytest-xdist is not installed in the
    dev-environment, which is the Red signal for the v039 D2
    Green amend (which adds pytest-xdist to pyproject.toml
    [dependency-groups.dev]).
    """
    import xdist  # noqa: F401  — Red signal: ImportError if pytest-xdist not in dev-deps.
    from coverage import Coverage

    src_subject = tmp_path / "subject.py"
    src_subject.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "x = 1\n"
        "y = 2\n"
        "z = 3\n",
        encoding="utf-8",
    )
    src_other = tmp_path / "other.py"
    src_other.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\n",
        encoding="utf-8",
    )

    worker_a = CoverageData(basename=str(tmp_path / ".coverage"), suffix="worker-a")
    worker_a.add_lines({str(src_subject): [1, 3]})
    worker_a.write()
    worker_b = CoverageData(basename=str(tmp_path / ".coverage"), suffix="worker-b")
    worker_b.add_lines({str(src_other): [1, 2]})
    worker_b.write()

    combiner = Coverage(data_file=str(tmp_path / ".coverage"))
    combiner.combine(data_paths=[str(tmp_path)])
    combiner.save()

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"per_file_coverage should reject subject.py at <100% coverage in xdist-combined data; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined_output = result.stdout + result.stderr
    assert "subject.py" in combined_output, (
        f"per_file_coverage diagnostic does not surface offending file `subject.py` "
        f"under xdist-combined input; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_per_file_coverage_purges_measured_files_whose_source_vanished(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A measured file whose source no longer exists is purged with a warning, not a crash.

    Work-item livespec-dev-tooling-5xh8: on a cold-cache CI pod, `uv`
    writes its interpreter-probe script (`get_interpreter_info.py` plus a
    vendored `packaging/`) into `~/.cache/uv/.tmpXXXX/python/`, runs it
    with the project's venv interpreter — whose pytest-cov `.pth` hook is
    armed by COVERAGE_PROCESS_START — and deletes the directory. The
    combined `.coverage` therefore records files that no longer exist,
    and `Coverage.json_report` raised `NoSource` on the first of them,
    failing `check-per-file-coverage` on every cold pod while the tree's
    own coverage was 100%. A measured file with no source on disk can
    never be first-party code under test (the check runs in the tree the
    suite just executed), so the fixture records one such path alongside
    a fully-covered `subject.py`; the check must exit 0, surface the
    skipped path, and PURGE it from the data file so the consume-once
    `check-coverage` reuse read of the same file is clean too.
    """
    src_file = tmp_path / "subject.py"
    src_file.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\n",
        encoding="utf-8",
    )
    vanished = tmp_path / ".cache" / "uv" / ".tmp8ktTHl" / "python" / "get_interpreter_info.py"
    assert not vanished.exists(), "fixture precondition: the probe path must not exist on disk"

    data = CoverageData(basename=str(tmp_path / ".coverage"), suffix=False)
    data.add_lines({str(src_file): [1, 2], str(vanished): [1, 2, 3]})
    data.write()

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"per_file_coverage must not fail on a measured file whose source vanished; "
        f"got returncode={result.returncode} output={combined!r}"
    )
    assert (
        str(vanished) in combined
    ), f"the skipped path must be surfaced in the diagnostic output; output={combined!r}"
    reread = CoverageData(basename=str(tmp_path / ".coverage"), suffix=False)
    reread.read()
    remaining = set(reread.measured_files())
    assert str(vanished) not in remaining, (
        f"the vanished file must be PURGED from the data file so check-coverage's "
        f"consume-once read is clean; remaining={sorted(remaining)!r}"
    )
    assert (
        str(src_file) in remaining
    ), f"purging must keep the still-present measured files; remaining={sorted(remaining)!r}"


def test_per_file_coverage_purge_preserves_branch_arcs_of_kept_files(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Purging under branch (`--cov-branch`) data keeps the surviving files' arcs intact.

    The real producer runs `pytest --cov --cov-branch`, so the data file
    holds ARCS, not lines, and the vanished-row rewrite must carry every
    kept file's arcs across unchanged — otherwise a fully covered file
    could read as partially covered, or the 100% gate could pass on
    emptied data. Fixture: a two-statement `subject.py` fully covered as
    arcs, plus a vanished uv-probe path with arcs of its own. After the
    check exits 0 the reread data must still be arc-based, list exactly
    `subject.py`, and hold exactly its original arcs.
    """
    src_file = tmp_path / "subject.py"
    src_file.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\n",
        encoding="utf-8",
    )
    vanished = tmp_path / ".cache" / "uv" / ".tmpEKjZCb" / "python" / "packaging" / "_elffile.py"
    subject_arcs = [(-1, 1), (1, 2), (2, -1)]

    data = CoverageData(basename=str(tmp_path / ".coverage"), suffix=False)
    data.add_arcs({str(src_file): subject_arcs, str(vanished): [(-1, 1), (1, -1)]})
    data.write()

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"per_file_coverage must not fail on a vanished measured file under branch data; "
        f"got returncode={result.returncode} output={combined!r}"
    )
    reread = CoverageData(basename=str(tmp_path / ".coverage"), suffix=False)
    reread.read()
    assert reread.has_arcs(), "the rewritten data file must stay arc-based (branch data)"
    assert set(reread.measured_files()) == {
        str(src_file)
    }, f"exactly the kept file must survive the rewrite; got {sorted(reread.measured_files())!r}"
    assert sorted(reread.arcs(str(src_file)) or []) == sorted(
        subject_arcs
    ), f"the kept file's arcs must be carried across unchanged; got {reread.arcs(str(src_file))!r}"
