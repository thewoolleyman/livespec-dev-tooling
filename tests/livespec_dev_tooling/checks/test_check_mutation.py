"""Tests for dev-tooling/checks/check_mutation.py.

Per SPECIFICATION/constraints.md section "Enforcement suite — Release-gate targets":
check_mutation runs mutmut against livespec/parse/ + validate/ and compares
the kill rate against the .mutmut-baseline.json ratchet (capped at 80%).
First-run mode: when baseline shows total=0 (placeholder), the check runs
mutmut, saves the result as the real baseline, and exits 0.

Epic li-cvaudit (cvtodo) replaced the `LIVESPEC_RELEASE_GATE` skip
carve-out with a RUN/SKIP lever (the blocker is runtime cost, not
severity): `LIVESPEC_RUN_MUTATION` unset → the check logs a "skipped"
diagnostic and exits 0; set to a non-empty value → the suite runs as
before. CI sets `LIVESPEC_RUN_MUTATION=true` for the release context.

mutmut-3.x output (work-item livespec-dev-tooling-q3r): `_parse_mutmut_results`
reads `mutmut results --all True`, which lists every mutant as one
`    <key>: <status>` line. The pre-3.x `Killed:` / `Total:` summary lines
do not exist in mutmut 3.2.3, so the old `Killed:`/`Total:` scanner returned
(0, 0) and the gate stayed a silent no-op even with real verdicts. The
direct-import tests below pin the parser against REAL captured mutmut-3.2.3
output; the subprocess tests use a fake mutmut package that emits the same
mutmut-3.x line format (survivors-only for `results`, every verdict for
`results --all True`).

Nested-layout staging cwd (work-item livespec-dev-tooling-q3r): mutmut runs
from `_resolve_staging_cwd(repo_root=...)` — the configured
`mutation_staging_dir` under `[tool.livespec_dev_tooling]`, or the repo root
when the key is absent. The `.mutmut-baseline.json` ratchet always lives at
the repo root regardless of the staging cwd.

Armed-but-inspected-nothing (work-item livespec-dev-tooling-z45): the check
formerly carried three composing masks that made ANY misconfiguration pass
green — rc-1 tolerance (mutmut's legitimate survivor exit is also what a
crash returns), `total == 0` as an unconditional pass, and a placeholder
baseline rewritten from whatever the run measured (possibly 0, pinning the
ratchet at 0.0% forever). The tests below pin each: an ARMED run
(non-empty `pure_trees`) that enumerates zero mutants FAILS; an rc-1 run
with no parseable verdicts is classified as a CRASH and surfaces mutmut's
stderr; and `_update_baseline` refuses a zero-mutant write outright.

Crashed-with-verdicts (work-item livespec-dev-tooling-6j6): z45 replaced an
unconditional `returncode not in (0, 1)` hard fail with `_is_crashed_run`,
which keys off an EMPTY tally — so a run that died with rc >= 2 AFTER
enumerating some mutants was reclassified as a normal survivors run. mutmut
persists each verdict as it completes, so a killed run leaves a non-empty
tally on disk; the tests below pin that rc 1 is the only non-zero code the
tally may excuse, and that a crashed run's partial measurement never reaches
the ratchet.

rc-1 partial tallies (work-item livespec-dev-tooling-y27): 6j6 left the SAME
harm open at rc 1 itself, because rc 1 is genuinely ambiguous — a legitimate
survivors run and a run that died of an unhandled exception AFTER enumerating
some mutants both exit 1 with a parseable tally, and the exit code carries no
discriminator. The check now requires POSITIVE evidence of completion at rc 1:
mutmut's end-of-run `<N> mutations/second` marker. The three tests below pin
the pair — a COMPLETE rc-1 survivors run still passes (the positive control,
without which every genuine survivor would fail and the ratchet would be
unusable), and a rc-1 run whose partial tally arrives WITHOUT the marker is
rejected, naming the death as the reason and leaving the committed ratchet
byte-identical.

Tests invoke `check_mutation.main()` IN-PROCESS (`monkeypatch.chdir(...)`
+ `capsys` + `rc = main()`) with a fake mutmut package injected through
PYTHONPATH, following the established dev-tooling test pattern: no
`COVERAGE_PROCESS_START`-instrumented child of this test, no `.coverage.*`
race under the parallel dispatcher, and materially faster. `main()` reads
`Path.cwd()`, so the monkeypatched cwd anchors the fixture, and the
assertion targets are unchanged — the int exit code plus the structlog
stderr text, now read off `capsys` instead of `CompletedProcess`.

PYTHONPATH still does exactly what it did: the check's OWN
`python -m mutmut` children are fresh interpreters, so injecting the fake
mutmut package there still lets mutmut substitute the mutated module when
running its own tests. What used to be the child's `env=` mapping is now
`monkeypatch.setenv` / `monkeypatch.delenv` in this process, which those
children inherit identically. Tests that exercise the armed path declare
an explicit `pure_trees` role key and seed a Python file under it, so they
do not depend on a whole-block fallback.

Branch parity with the retired spawn: the `LIVESPEC_RUN_MUTATION`
self-skip and armed arms, the pure-trees gate arms, the first-run
baseline-capture arm, the ratchet arms, and the crashed/unusable-
measurement arms are driven by the same fixtures as before. The
`if __name__ == "__main__": raise SystemExit(main())` line is the one
line the child reached that an in-process call cannot; it is already
excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so it was never measured here and no new
exclusion is introduced.
"""

from __future__ import annotations

import json
import os
from importlib import import_module
from pathlib import Path
from types import FunctionType
from typing import NamedTuple

import pytest
import structlog

from livespec_dev_tooling.checks.check_mutation import (
    _derive_exit_code,
    _parse_mutmut_results,
    _pure_trees_gate_exit_code,
    _resolve_staging_cwd,
    _update_baseline,
    main,
)

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]

_RUN_VAR = "LIVESPEC_RUN_MUTATION"


_COMPLETION_LINE = "24.76 mutations/second\n"


def _make_fake_mutmut(
    *,
    tmp_path: Path,
    killed: int,
    total: int,
    run_rc: int = 0,
    run_stderr: str = "",
    run_stdout: str = _COMPLETION_LINE,
) -> Path:
    """Write a fake mutmut package into tmp_path that emits mutmut-3.x results.

    The fake mirrors mutmut 3.2.3's actual surface:

    - `run` writes `run_stdout` to its stdout and `run_stderr` to its stderr,
      exits with `run_rc`, and writes a `MUTMUT_RAN_IN.txt` marker into its
      own cwd (the staging-cwd test reads it to prove WHERE mutmut ran).
      `run_stdout` defaults to mutmut's real end-of-run `<N> mutations/second`
      line, which every COMPLETED `mutmut run` prints unconditionally; a test
      reproducing a run that DIED mid-flight passes `run_stdout=""`, because a
      process that never reached the end of `run()` never printed it.
      `run_stderr` lets a test reproduce a real mutmut CRASH — an rc-1 exit
      carrying a traceback on stderr — as opposed to mutmut's legitimate rc-1
      survivor exit.
    - `results` (no flag) prints ONLY the surviving mutants, one
      `    <key>: survived` line each (mutmut 3.x suppresses killed verdicts
      unless `--all True` is passed).
    - `results --all True` prints EVERY mutant: `killed` lines first, then
      `survived` lines, each `    <key>: <status>` with mutmut's 4-space
      indent.

    `killed` killed + `(total - killed)` survived mutants are emitted.
    """
    pkg = tmp_path / "mutmut"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__main__.py").write_text(
        f"""\
import os
import sys

KILLED = {killed}
SURVIVED = {total - killed}


def _killed_lines():
    return [f"    pkg.x_mut_killed_{{i}}: killed" for i in range(KILLED)]


def _survived_lines():
    return [f"    pkg.x_mut_survived_{{i}}: survived" for i in range(SURVIVED)]


cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if cmd == "run":
    with open("MUTMUT_RAN_IN.txt", "w", encoding="utf-8") as fh:
        fh.write(os.getcwd())
    sys.stdout.write({run_stdout!r})
    sys.stderr.write({run_stderr!r})
    sys.exit({run_rc})
elif cmd == "results":
    all_flag = sys.argv[2:] == ["--all", "True"]
    if all_flag:
        for line in _killed_lines() + _survived_lines():
            print(line)
    else:
        for line in _survived_lines():
            print(line)
    sys.exit(0)
sys.exit(2)
""",
        encoding="utf-8",
    )
    return tmp_path


def _ensure_declared_pure_tree(*, repo_root: Path) -> None:
    pyproject = repo_root / "pyproject.toml"
    if "mutation_staging_dir" not in pyproject.read_text(encoding="utf-8"):
        pyproject.write_text(
            '[tool.livespec_dev_tooling]\npure_trees = ["pure"]\n',
            encoding="utf-8",
        )
    pure = repo_root / "pure"
    pure.mkdir(exist_ok=True)
    module = pure / "mod.py"
    if not module.is_file():
        module.write_text("from __future__ import annotations\n\nx = 1\n", encoding="utf-8")


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_check(
    *,
    tmp_path: Path,
    fake_mutmut_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    baseline: dict[str, object] | None = None,
    run_var: str | None = "true",
    cwd: Path | None = None,
) -> _CheckRun:
    """Run `check_mutation.main()` in `cwd` (default `tmp_path`) with a fake mutmut.

    `run_var` controls the `LIVESPEC_RUN_MUTATION` lever: the default
    `"true"` exercises the run-the-suite path (the behavior every
    existing assertion below depends on); `None` removes the lever to
    exercise the self-skip path.

    The repo package must be importable in the check's own `mutmut`
    subprocesses, so the repo root is appended to `PYTHONPATH` alongside
    the fake-mutmut dir. `monkeypatch.setenv` mutates this process's
    `os.environ`, which those children inherit exactly as the retired
    `env=` mapping supplied it.
    """
    if run_var:
        _ensure_declared_pure_tree(repo_root=tmp_path)
    if baseline is not None:
        (tmp_path / ".mutmut-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.delenv(_RUN_VAR, raising=False)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(fake_mutmut_dir), str(_REPO_ROOT)]))
    if run_var is not None:
        monkeypatch.setenv(_RUN_VAR, run_var)
    monkeypatch.chdir(cwd if cwd is not None else tmp_path)
    rc = main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


# --- direct-import parser tests against REAL captured mutmut-3.2.3 output ---


def test_parse_reads_real_mutmut3_results_all_output() -> None:
    """`_parse_mutmut_results` tallies a REAL `mutmut results --all True` block.

    Verbatim from `mutmut==3.2.3` `mutmut results --all True` (4 mutants,
    3 killed, 1 survived). The pre-3.x parser scanned `Killed:` / `Total:`
    lines that mutmut 3.x never emits, so it returned (0, 0) here and the
    gate stayed a silent no-op (the keystone bug, livespec-mutreal.1 +
    work-item livespec-dev-tooling-q3r).
    """
    real_results_all = (
        "    calc.x_add__mutmut_1: killed\n"
        "    calc.x_greet__mutmut_1: survived\n"
        "    calc.x_greet__mutmut_2: killed\n"
        "    calc.x_greet__mutmut_3: killed\n"
    )
    assert _parse_mutmut_results(output=real_results_all) == (3, 4)


def test_parse_handles_dotted_mutant_keys() -> None:
    """A dotted mutant key (multiple `.`/`:`) splits on the LAST `": "` only."""
    output = (
        "    livespec.parse.front_matter.x__split_front_matter__mutmut_3: killed\n"
        "    livespec.validate.livespec_config.x__build_spec_clis__mutmut_1: survived\n"
    )
    assert _parse_mutmut_results(output=output) == (1, 2)


def test_rop_sweep_red_helper_failure_callback_remains_executable() -> None:
    """Execute the byte-locked Red test's nested callback without editing it."""
    from tests.livespec_dev_tooling.checks import test_rop_sweep_library_checks

    test_fn = test_rop_sweep_library_checks.test_check_mutation_noops_without_pure_trees
    helper_code = next(
        const
        for const in test_fn.__code__.co_consts
        if getattr(const, "co_name", "") == "fail_if_mutmut_runs"
    )
    helper = FunctionType(helper_code, test_rop_sweep_library_checks.__dict__)

    with pytest.raises(AssertionError, match="mutmut should not run"):
        helper()


def test_parse_ignores_non_verdict_noise_lines() -> None:
    """Spinner frames, the `mutations/second` footer, and blank lines are skipped."""
    output = (
        "24.76 mutations/second\n"
        "\n"
        "    pkg.x_a__mutmut_1: killed\n"
        "Running mutation testing\n"
        "    pkg.x_b__mutmut_1: survived\n"
    )
    assert _parse_mutmut_results(output=output) == (1, 2)


def test_parse_counts_every_status_in_total() -> None:
    """`survived`, `no tests`, `timeout`, `suspicious`, `skipped` all count toward total."""
    output = (
        "    pkg.x1: killed\n"
        "    pkg.x2: survived\n"
        "    pkg.x3: no tests\n"
        "    pkg.x4: timeout\n"
        "    pkg.x5: suspicious\n"
        "    pkg.x6: skipped\n"
    )
    # 1 killed out of 6 recognized verdicts.
    assert _parse_mutmut_results(output=output) == (1, 6)


def test_parse_old_pre3x_format_yields_zero() -> None:
    """The removed pre-3.x `Killed:`/`Total:` summary no longer parses (yields 0/0).

    This pins the regression direction: the old format must NOT be mistaken
    for a real tally (its numbers are not a recognized `<key>: <status>`
    verdict line), so a stale mutmut that somehow emitted it cannot silently
    masquerade as a real result.
    """
    old_format = "Killed: 17\nSurvived: 3\nTimeout: 0\nTotal: 20\n"
    assert _parse_mutmut_results(output=old_format) == (0, 0)


def test_parse_empty_output_yields_zero() -> None:
    """Empty output (e.g. `mutmut results` with no survivors) yields (0, 0)."""
    assert _parse_mutmut_results(output="") == (0, 0)


# --- staging-cwd resolution tests ---


def test_resolve_staging_cwd_defaults_to_repo_root(*, tmp_path: Path) -> None:
    """No `mutation_staging_dir` key → mutmut runs from the repo root (flat layout)."""
    assert _resolve_staging_cwd(repo_root=tmp_path) == tmp_path


def test_resolve_staging_cwd_uses_configured_dir(*, tmp_path: Path) -> None:
    """A declared `mutation_staging_dir` → `repo_root / <dir>` (nested layout)."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nmutation_staging_dir = ".mutmut-staging"\n',
        encoding="utf-8",
    )
    assert _resolve_staging_cwd(repo_root=tmp_path) == tmp_path / ".mutmut-staging"


# --- subprocess tests (the established dev-tooling pattern) ---


def test_skips_when_run_var_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`LIVESPEC_RUN_MUTATION` unset → self-skip: exit 0, no mutmut invocation."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=3, total=20)
    # A baseline that would FAIL if the suite actually ran (3/20 = 15% < 80%
    # floor). The skip path must short-circuit before any kill-rate gate, so
    # exit 0 here proves the suite did not run.
    baseline = {"kill_rate_percent": 0.0, "mutants_surviving": 0, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        run_var=None,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0, (
        f"run-var unset should self-skip + exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "skipped" in combined
    ), f"skip path should log a 'skipped' diagnostic; stderr={result.stderr!r}"
    assert (
        _RUN_VAR in combined
    ), f"skip diagnostic should name the run-var lever; stderr={result.stderr!r}"


def test_empty_run_var_treated_as_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty-string `LIVESPEC_RUN_MUTATION` counts as unset → self-skip + exit 0."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=3, total=20)
    baseline = {"kill_rate_percent": 0.0, "mutants_surviving": 0, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        run_var="",
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0, (
        f"empty run-var should self-skip + exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "skipped" in combined


def test_baseline_is_placeholder_first_run(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """total=0 in baseline → first-run mode: saves baseline, exits 0."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    baseline = {"kill_rate_percent": 0, "mutants_surviving": 0, "mutants_total": 0}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    written = json.loads((tmp_path / ".mutmut-baseline.json").read_text())
    assert written["mutants_total"] == 20
    assert written["kill_rate_percent"] == pytest.approx(85.0)


def test_no_baseline_file_treated_as_placeholder(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing .mutmut-baseline.json → treated as placeholder → first-run mode."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    result = _run_check(
        tmp_path=tmp_path, fake_mutmut_dir=fake, monkeypatch=monkeypatch, capsys=capsys
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert (tmp_path / ".mutmut-baseline.json").is_file()


def test_parse_mutmut_results_parses_killed_total(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Killed and total are tallied end-to-end from a mutmut-3.x results block."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=18, total=20)
    baseline = {"kill_rate_percent": 80.0, "mutants_surviving": 4, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"


def test_derive_exit_code_passes_at_floor(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Kill rate at exactly 80% floor passes."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=16, total=20)
    baseline = {"kill_rate_percent": 80.0, "mutants_surviving": 4, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"


def test_derive_exit_code_fails_below_80_percent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Kill rate below 80% always fails — proving the gate is no longer a no-op."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=3, total=20)
    baseline = {"kill_rate_percent": 0.0, "mutants_surviving": 0, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 1, "unexpected pass"


def test_derive_exit_code_fails_on_regression(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Kill rate above floor but below baseline fails (regression)."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    baseline = {"kill_rate_percent": 90.0, "mutants_surviving": 2, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 1, "unexpected pass"


def test_update_baseline_on_improvement(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Improved kill rate updates baseline."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=20, total=20)
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 3, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0
    written = json.loads((tmp_path / ".mutmut-baseline.json").read_text())
    assert written["kill_rate_percent"] == pytest.approx(100.0)


def test_no_baseline_update_when_equal(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Kill rate == baseline: passes but does not update baseline."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=16, total=20)
    baseline = {"kill_rate_percent": 80.0, "mutants_surviving": 4, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0
    written = json.loads((tmp_path / ".mutmut-baseline.json").read_text())
    assert written["kill_rate_percent"] == pytest.approx(80.0)


def test_mutmut_run_failure_returns_1(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mutmut run returning a non-0/1 exit code causes the check to fail.

    The tally is deliberately NON-empty (20 mutants, 18 killed, a 90% rate
    that clears both the floor and the 85% baseline), so the ONLY thing that
    can fail this run is the return code itself. The fixture previously set
    `total=0`, which tripped the zero-mutant branch instead — leaving the test
    green no matter what the return code did and hollowing out the very
    assertion its name makes (work-item livespec-dev-tooling-6j6).
    """
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=18, total=20, run_rc=2, run_stdout="")
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 3, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 1, (
        f"a non-0/1 mutmut exit must FAIL even when verdicts are present; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


# --- armed-but-inspected-nothing (work-item livespec-dev-tooling-z45) ---


def test_armed_zero_mutants_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An ARMED run that enumerated zero mutants FAILS — it inspected nothing.

    Mask 2 of work-item livespec-dev-tooling-z45: `total == 0` was an
    unconditional pass, so a misconfigured or crashed mutmut — which produces
    no parseable verdicts — reported success. Nothing legitimately produces
    zero mutants from a non-empty `pure_trees`, so the only honest verdict is
    a failure. The baseline here has `mutants_total > 0`, which puts the check
    in ratchet mode rather than first-run mode.
    """
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=0, total=0, run_rc=0)
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 3, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 1, (
        f"an armed run enumerating zero mutants must FAIL, not pass; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "zero mutants" in combined
    ), f"the failure must name the zero-mutant cause; stderr={result.stderr!r}"


def test_armed_zero_mutants_refuses_to_write_baseline(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A zero-mutant run never promotes its garbage measurement into the ratchet.

    Mask 3 of work-item livespec-dev-tooling-z45: first-run mode recorded
    whatever it had just measured — possibly 0 — pinning the committed ratchet
    at 0.0%, after which the 80% hard floor fails every subsequent release with
    no obvious cause. No baseline file exists here, which is treated as the
    placeholder, so this is exactly the first-run path.
    """
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=0, total=0, run_rc=0)
    result = _run_check(
        tmp_path=tmp_path, fake_mutmut_dir=fake, monkeypatch=monkeypatch, capsys=capsys
    )
    assert result.returncode == 1, (
        f"a zero-mutant first run must FAIL rather than capture a baseline; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert not (
        tmp_path / ".mutmut-baseline.json"
    ).is_file(), "a zero-mutant run must not write the ratchet"


def test_crashed_mutmut_rc1_fails_and_surfaces_stderr(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """rc 1 with no parseable verdicts is a CRASH, not a survivor run.

    Mask 1 of work-item livespec-dev-tooling-z45: exit 1 is legitimate for
    mutmut when mutants survive, but it is also what a hard crash returns — a
    `FileNotFoundError` from `guess_paths_to_mutate()` under a misconfigured
    staging cwd exits 1 and was indistinguishable from a normal survivor run.
    The two are told apart by whether any mutant was enumerated at all, and
    the crash must surface mutmut's own stderr rather than absorbing it.
    """
    fake = _make_fake_mutmut(
        tmp_path=tmp_path,
        killed=0,
        total=0,
        run_rc=1,
        run_stdout="",
        run_stderr="FileNotFoundError: [Errno 2] No such file or directory: 'pyproject.toml'\n",
    )
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 3, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 1, (
        f"a crashed mutmut must FAIL rather than be absorbed as rc 1; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "FileNotFoundError" in combined
    ), f"the crash must surface mutmut's stderr; stderr={result.stderr!r}"


# --- crashed-with-verdicts (work-item livespec-dev-tooling-6j6) ---


def test_killed_mutmut_with_partial_verdicts_does_not_poison_the_ratchet(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An OOM-killed run's PARTIAL tally must never be promoted into the ratchet.

    Work-item livespec-dev-tooling-6j6. `mutmut run` persists each verdict to
    `mutants/mutmut-meta.json` as it completes (mutmut 3.2.3 `register_result`
    calls `save()` per mutant), so a run killed part-way — OOM/SIGKILL is rc
    137, a process-level death independent of mutmut's own exit table — leaves
    a NON-EMPTY tally on disk that `mutmut results --all True` happily reports.
    `_is_crashed_run` keyed only off an EMPTY tally, so that partial
    measurement was classified as a normal survivors run.

    The harm is second-order and is what makes this worse than a stray green:
    the partial tally here (5 of 400 mutants, all killed) reads as a PERFECT
    100% rate, so it is promoted over a healthy 85% ratchet — after which every
    subsequent LEGITIMATE full run fails the ratchet with no obvious cause.
    That is exactly the damage mask 3 of livespec-dev-tooling-z45 exists to
    prevent, reached through the return code instead of through `total == 0`.
    """
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=5, total=5, run_rc=137, run_stdout="")
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 60, "mutants_total": 400}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 1, (
        f"a killed mutmut run must FAIL even though its partial tally parses; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    written = json.loads((tmp_path / ".mutmut-baseline.json").read_text(encoding="utf-8"))
    assert written["kill_rate_percent"] == pytest.approx(85.0), (
        f"a crashed run's partial measurement must not be promoted into the "
        f"ratchet; baseline is now {written!r}"
    )
    assert written["mutants_total"] == 400, f"the ratchet was overwritten: {written!r}"


def test_reports_mutant_count_and_kill_rate(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A passing run still emits the tally, so "inspected 0" cannot look like "passed"."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 3, "mutants_total": 20}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    combined = result.stdout + result.stderr
    assert '"total": 20' in combined, f"the mutant count must be visible; got {combined!r}"
    assert '"kill_rate_percent": 85.0' in combined, f"the kill rate must be visible; {combined!r}"


def test_crash_reason_separates_a_survivors_run_from_a_died_run() -> None:
    """rc 1 is a measurement ONLY with verdicts AND mutmut's completion marker.

    rc 1 is the only non-zero code mutmut itself returns that can mean
    "survivors present", so it alone is a candidate measurement; every other
    non-zero code is a crash whatever the tally says (work-item
    livespec-dev-tooling-6j6) — rc 2 is a hard failure and rc 137 is a
    SIGKILL/OOM death, and neither becomes legitimate just because verdicts
    were persisted before the process died.

    Within rc 1 the tally CANNOT be the discriminator (work-item
    livespec-dev-tooling-y27): a run that dies of an unhandled exception after
    enumerating some mutants leaves a parseable partial tally behind. The
    discriminator is instead POSITIVE evidence that `mutmut run` reached its
    end — the `<N> mutations/second` line it prints unconditionally on the way
    out. rc 1 WITH that marker is a survivors run; rc 1 without it died.

    `_crash_reason` is reached through `getattr` rather than a module-level
    import so this test fails on a genuine ASSERTION at Red rather than dying
    at collection.
    """
    module = import_module("livespec_dev_tooling.checks.check_mutation")
    assert hasattr(module, "_crash_reason"), (
        "check_mutation must expose `_crash_reason`, which reports WHY a run is "
        "a crash rather than merely that it is one"
    )
    crash_reason = getattr(module, "_crash_reason")  # noqa: B009 — keeps Red off collection

    complete = "24.76 mutations/second\n"
    died = "Generating mutants\n    done in 812ms\n"

    assert crash_reason(returncode=1, total=20, run_output=complete) is None
    assert crash_reason(returncode=0, total=0, run_output=complete) is None
    assert crash_reason(returncode=0, total=20, run_output=complete) is None

    partial = crash_reason(returncode=1, total=5, run_output=died)
    assert partial is not None, "rc 1 without the completion marker must be a crash"
    assert "mutations/second" in partial, f"the reason must name the missing marker; {partial!r}"

    assert crash_reason(returncode=1, total=0, run_output=complete) is not None
    assert crash_reason(returncode=2, total=20, run_output=complete) is not None
    assert crash_reason(returncode=137, total=20, run_output=complete) is not None


# --- rc-1 partial tallies (work-item livespec-dev-tooling-y27) ---


def test_rc1_complete_survivors_run_still_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """POSITIVE CONTROL: a COMPLETE rc-1 run with survivors is accepted as before.

    rc 1 is mutmut's legitimate "mutants survived" exit, and it is the common
    case on any repo whose kill rate is under 100%. Requiring completion
    evidence at rc 1 must not regress it: if this run failed, EVERY genuine
    survivor would fail the gate and the ratchet would be unusable — a
    strictly worse outcome than the hole work-item livespec-dev-tooling-y27
    closes. 340 of 400 killed is exactly the 85.0% the baseline records, so
    the run clears both the floor and the ratchet without improving it.
    """
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=340, total=400, run_rc=1)
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 60, "mutants_total": 400}
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0, (
        f"a COMPLETE rc-1 survivors run must still pass; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    written = json.loads((tmp_path / ".mutmut-baseline.json").read_text(encoding="utf-8"))
    assert written["kill_rate_percent"] == pytest.approx(85.0)
    assert written["mutants_total"] == 400


def test_rc1_partial_tally_is_rejected_and_leaves_the_ratchet_byte_identical(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """NEGATIVE CONTROL: an rc-1 run that DIED mid-flight never reaches the ratchet.

    Work-item livespec-dev-tooling-y27, the residual after 6j6. mutmut exits 1
    both when mutants survive and when it dies of an unhandled internal
    exception — that is simply how Python exits on an uncaught exception — and
    a death AFTER enumeration leaves the already-persisted partial verdicts on
    disk, so the tally parses. `_is_crashed_run` excused rc 1 whenever the
    tally was non-empty, so the crashed run passed AND, being partial, skewed
    high enough (5 of 400, all killed, a perfect 100%) to be promoted over a
    healthy 85%/400 ratchet. Every subsequent legitimate full run then failed
    against a rate no complete run can reach, with no obvious cause.

    The ratchet is compared BYTE for byte, not field by field: the property
    this work-item exists to protect is that a rejected run does not write the
    committed baseline at all, and an exit-code assertion alone leaves that
    unproven.
    """
    fake = _make_fake_mutmut(
        tmp_path=tmp_path,
        killed=5,
        total=5,
        run_rc=1,
        run_stdout="Generating mutants\n    done in 812ms\n",
        run_stderr=(
            "Traceback (most recent call last):\n"
            '  File "mutmut/__main__.py", line 1301, in run\n'
            "    print_stats(source_file_mutation_data_by_path)\n"
            "KeyError: 'x_add__mutmut_1'\n"
        ),
    )
    baseline_path = tmp_path / ".mutmut-baseline.json"
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 60, "mutants_total": 400}
    # `_run_check` seeds the file with exactly these bytes; capturing them here
    # makes the post-run comparison a true byte-for-byte identity check.
    before = json.dumps(baseline).encode("utf-8")
    result = _run_check(
        tmp_path=tmp_path,
        fake_mutmut_dir=fake,
        baseline=baseline,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert result.returncode == 1, (
        f"an rc-1 run that died mid-flight must FAIL even though its partial "
        f"tally parses; got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "did not complete" in combined, (
        f"the finding must say the run DIED rather than report a mutation "
        f"score; stderr={result.stderr!r}"
    )
    assert (
        "mutations/second" in combined
    ), f"the finding must name the missing completion marker; stderr={result.stderr!r}"
    assert baseline_path.read_bytes() == before, (
        f"a rejected run must leave the committed ratchet BYTE-IDENTICAL; it is "
        f"now {baseline_path.read_bytes()!r}"
    )


def test_derive_exit_code_fails_on_zero_total() -> None:
    """`total == 0` is a failure, not the former unconditional pass."""
    assert _derive_exit_code(killed=0, total=0, baseline={"kill_rate_percent": 85.0}) == 1


def test_update_baseline_refuses_zero_mutant_write(*, tmp_path: Path) -> None:
    """`_update_baseline` writes nothing and reports False for a zero-mutant run."""
    baseline_path = tmp_path / ".mutmut-baseline.json"
    assert _update_baseline(baseline_path=baseline_path, killed=0, total=0) is False
    assert not baseline_path.exists()


def test_update_baseline_writes_when_mutants_present(*, tmp_path: Path) -> None:
    """`_update_baseline` writes and reports True when the run enumerated mutants."""
    baseline_path = tmp_path / ".mutmut-baseline.json"
    assert _update_baseline(baseline_path=baseline_path, killed=17, total=20) is True
    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written["mutants_total"] == 20
    assert written["kill_rate_percent"] == pytest.approx(85.0)


def test_runs_mutmut_from_staging_cwd_baseline_at_repo_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A configured `mutation_staging_dir` runs mutmut there; the baseline stays at root.

    The repo root declares `mutation_staging_dir` and carries a placeholder
    baseline; the staging dir is a separate subdir. After the check runs,
    mutmut's `MUTMUT_RAN_IN.txt` marker must land in the STAGING dir (proving
    `cwd=staging`), and the captured `.mutmut-baseline.json` must land at the
    REPO ROOT (proving the ratchet ignores the staging cwd).
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    staging = repo_root / "staging"
    staging.mkdir()
    (repo_root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        'pure_trees = ["pure"]\n'
        'mutation_staging_dir = "staging"\n',
        encoding="utf-8",
    )
    pure = repo_root / "pure"
    pure.mkdir()
    (pure / "mod.py").write_text("from __future__ import annotations\n\nx = 1\n", encoding="utf-8")
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    result = _run_check(
        tmp_path=repo_root,
        fake_mutmut_dir=fake,
        baseline={"kill_rate_percent": 0, "mutants_surviving": 0, "mutants_total": 0},
        cwd=repo_root,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    marker = staging / "MUTMUT_RAN_IN.txt"
    assert marker.is_file(), "mutmut should have run from the staging dir"
    assert marker.read_text(encoding="utf-8") == str(staging)
    assert not (repo_root / "MUTMUT_RAN_IN.txt").is_file()
    assert (repo_root / ".mutmut-baseline.json").is_file(), "baseline must land at the repo root"
    assert not (staging / ".mutmut-baseline.json").is_file()


def test_pure_trees_gate_passes_through_when_the_tree_is_declared_and_populated(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A populated `pure_trees` yields NO early exit — the check proceeds to mutmut.

    Pins the pass-through arm of the role-key gate directly. Under the union
    (livespec-dev-tooling-8o8e.1) the gate has three outcomes — undeclared (1),
    declared-absent (0, announced by variant), and populated (None, proceed) —
    and only the third one lets any mutation actually run.
    """
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\npure_trees = ["pure"]\n', encoding="utf-8"
    )
    pure = tmp_path / "pure"
    pure.mkdir()
    _ = (pure / "mod.py").write_text(
        "from __future__ import annotations\n\nx = 1\n", encoding="utf-8"
    )

    gate_exit = _pure_trees_gate_exit_code(
        repo_root=tmp_path,
        log=structlog.get_logger("test_pure_trees_gate"),
    )

    _ = capsys.readouterr()
    assert (
        gate_exit is None
    ), f"a declared, populated `pure_trees` must produce no early exit; got {gate_exit!r}"


def test_pure_trees_gate_fails_when_the_declared_tree_holds_no_python(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A DECLARED but Python-less `pure_trees` is a hard error, not a quiet pass.

    This is the arm that keeps the union honest at the other end. Declaring a real
    path is not enough — if it resolves to no Python, the check would scan zero
    files while looking fully armed, which is the exact manufactured-confidence
    shape `livespec-dev-tooling-8o8e.1` exists to remove. The union makes ABSENCE
    say why; this keeps PRESENCE from lying.
    """
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\npure_trees = ["pure"]\n', encoding="utf-8"
    )
    (tmp_path / "pure").mkdir()

    gate_exit = _pure_trees_gate_exit_code(
        repo_root=tmp_path,
        log=structlog.get_logger("test_pure_trees_gate_empty"),
    )

    _ = capsys.readouterr()
    assert (
        gate_exit == 1
    ), f"a declared `pure_trees` resolving to no Python must fail closed; got {gate_exit!r}"
