"""Tests for dev-tooling/checks/check_mutation.py.

Per SPECIFICATION/constraints.md §"Enforcement suite — Release-gate targets":
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

Tests invoke check_mutation.py via subprocess with a fake mutmut package
injected through PYTHONPATH, following the established dev-tooling test
pattern. This approach lets mutmut properly substitute the mutated module
when running its own tests. A bare `tmp_path` carries no
`[tool.livespec_dev_tooling]` block, so `load_config` returns the
livespec-core fallback whose `pure_trees` is non-empty — every subprocess
test below therefore runs the check ARMED.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import FunctionType

import pytest

from livespec_dev_tooling.checks.check_mutation import (
    _derive_exit_code,
    _is_crashed_run,
    _parse_mutmut_results,
    _resolve_staging_cwd,
    _update_baseline,
)

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_MUTATION_SCRIPT = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "check_mutation.py"

_RUN_VAR = "LIVESPEC_RUN_MUTATION"


def _make_fake_mutmut(
    *,
    tmp_path: Path,
    killed: int,
    total: int,
    run_rc: int = 0,
    run_stderr: str = "",
) -> Path:
    """Write a fake mutmut package into tmp_path that emits mutmut-3.x results.

    The fake mirrors mutmut 3.2.3's actual surface:

    - `run` writes `run_stderr` to its stderr (empty by default), exits with
      `run_rc`, and writes a `MUTMUT_RAN_IN.txt` marker into its own cwd (the
      staging-cwd test reads it to prove WHERE mutmut ran). `run_stderr` lets
      a test reproduce a real mutmut CRASH — an rc-1 exit carrying a traceback
      on stderr and enumerating no mutants — as opposed to mutmut's legitimate
      rc-1 survivor exit.
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


def _run_check(
    *,
    tmp_path: Path,
    fake_mutmut_dir: Path,
    baseline: dict[str, object] | None = None,
    run_var: str | None = "true",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run check_mutation.py in `cwd` (default `tmp_path`) with a fake mutmut.

    `run_var` controls the `LIVESPEC_RUN_MUTATION` lever: the default
    `"true"` exercises the run-the-suite path (the behavior every
    existing assertion below depends on); `None` removes the lever to
    exercise the self-skip path.

    The repo package must be importable in the subprocess (the script now
    imports `livespec_dev_tooling.config`), so the repo root is appended to
    `PYTHONPATH` alongside the fake-mutmut dir.
    """
    if baseline is not None:
        (tmp_path / ".mutmut-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != _RUN_VAR}
    env["PYTHONPATH"] = os.pathsep.join([str(fake_mutmut_dir), str(_REPO_ROOT)])
    if run_var is not None:
        env[_RUN_VAR] = run_var
    return subprocess.run(
        [sys.executable, str(_CHECK_MUTATION_SCRIPT)],
        cwd=str(cwd if cwd is not None else tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


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


def test_skips_when_run_var_unset(*, tmp_path: Path) -> None:
    """`LIVESPEC_RUN_MUTATION` unset → self-skip: exit 0, no mutmut invocation."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=3, total=20)
    # A baseline that would FAIL if the suite actually ran (3/20 = 15% < 80%
    # floor). The skip path must short-circuit before any kill-rate gate, so
    # exit 0 here proves the suite did not run.
    baseline = {"kill_rate_percent": 0.0, "mutants_surviving": 0, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline, run_var=None)
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


def test_empty_run_var_treated_as_unset(*, tmp_path: Path) -> None:
    """An empty-string `LIVESPEC_RUN_MUTATION` counts as unset → self-skip + exit 0."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=3, total=20)
    baseline = {"kill_rate_percent": 0.0, "mutants_surviving": 0, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline, run_var="")
    assert result.returncode == 0, (
        f"empty run-var should self-skip + exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "skipped" in combined


def test_baseline_is_placeholder_first_run(*, tmp_path: Path) -> None:
    """total=0 in baseline → first-run mode: saves baseline, exits 0."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    baseline = {"kill_rate_percent": 0, "mutants_surviving": 0, "mutants_total": 0}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    written = json.loads((tmp_path / ".mutmut-baseline.json").read_text())
    assert written["mutants_total"] == 20
    assert written["kill_rate_percent"] == pytest.approx(85.0)


def test_no_baseline_file_treated_as_placeholder(*, tmp_path: Path) -> None:
    """Missing .mutmut-baseline.json → treated as placeholder → first-run mode."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert (tmp_path / ".mutmut-baseline.json").is_file()


def test_parse_mutmut_results_parses_killed_total(*, tmp_path: Path) -> None:
    """Killed and total are tallied end-to-end from a mutmut-3.x results block."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=18, total=20)
    baseline = {"kill_rate_percent": 80.0, "mutants_surviving": 4, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 0, f"stderr={result.stderr!r}"


def test_derive_exit_code_passes_at_floor(*, tmp_path: Path) -> None:
    """Kill rate at exactly 80% floor passes."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=16, total=20)
    baseline = {"kill_rate_percent": 80.0, "mutants_surviving": 4, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 0, f"stderr={result.stderr!r}"


def test_derive_exit_code_fails_below_80_percent(*, tmp_path: Path) -> None:
    """Kill rate below 80% always fails — proving the gate is no longer a no-op."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=3, total=20)
    baseline = {"kill_rate_percent": 0.0, "mutants_surviving": 0, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 1, "unexpected pass"


def test_derive_exit_code_fails_on_regression(*, tmp_path: Path) -> None:
    """Kill rate above floor but below baseline fails (regression)."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    baseline = {"kill_rate_percent": 90.0, "mutants_surviving": 2, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 1, "unexpected pass"


def test_update_baseline_on_improvement(*, tmp_path: Path) -> None:
    """Improved kill rate updates baseline."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=20, total=20)
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 3, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 0
    written = json.loads((tmp_path / ".mutmut-baseline.json").read_text())
    assert written["kill_rate_percent"] == pytest.approx(100.0)


def test_no_baseline_update_when_equal(*, tmp_path: Path) -> None:
    """Kill rate == baseline: passes but does not update baseline."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=16, total=20)
    baseline = {"kill_rate_percent": 80.0, "mutants_surviving": 4, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 0
    written = json.loads((tmp_path / ".mutmut-baseline.json").read_text())
    assert written["kill_rate_percent"] == pytest.approx(80.0)


def test_mutmut_run_failure_returns_1(*, tmp_path: Path) -> None:
    """Mutmut run returning non-0/1 exit code causes check to fail."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=0, total=0, run_rc=2)
    baseline = {"kill_rate_percent": 0, "mutants_surviving": 0, "mutants_total": 0}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 1


# --- armed-but-inspected-nothing (work-item livespec-dev-tooling-z45) ---


def test_armed_zero_mutants_fails(*, tmp_path: Path) -> None:
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
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 1, (
        f"an armed run enumerating zero mutants must FAIL, not pass; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "zero mutants" in combined
    ), f"the failure must name the zero-mutant cause; stderr={result.stderr!r}"


def test_armed_zero_mutants_refuses_to_write_baseline(*, tmp_path: Path) -> None:
    """A zero-mutant run never promotes its garbage measurement into the ratchet.

    Mask 3 of work-item livespec-dev-tooling-z45: first-run mode recorded
    whatever it had just measured — possibly 0 — pinning the committed ratchet
    at 0.0%, after which the 80% hard floor fails every subsequent release with
    no obvious cause. No baseline file exists here, which is treated as the
    placeholder, so this is exactly the first-run path.
    """
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=0, total=0, run_rc=0)
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake)
    assert result.returncode == 1, (
        f"a zero-mutant first run must FAIL rather than capture a baseline; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert not (
        tmp_path / ".mutmut-baseline.json"
    ).is_file(), "a zero-mutant run must not write the ratchet"


def test_crashed_mutmut_rc1_fails_and_surfaces_stderr(*, tmp_path: Path) -> None:
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
        run_stderr="FileNotFoundError: [Errno 2] No such file or directory: 'pyproject.toml'\n",
    )
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 3, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 1, (
        f"a crashed mutmut must FAIL rather than be absorbed as rc 1; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "FileNotFoundError" in combined
    ), f"the crash must surface mutmut's stderr; stderr={result.stderr!r}"


def test_reports_mutant_count_and_kill_rate(*, tmp_path: Path) -> None:
    """A passing run still emits the tally, so "inspected 0" cannot look like "passed"."""
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    baseline = {"kill_rate_percent": 85.0, "mutants_surviving": 3, "mutants_total": 20}
    result = _run_check(tmp_path=tmp_path, fake_mutmut_dir=fake, baseline=baseline)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    combined = result.stdout + result.stderr
    assert '"total": 20' in combined, f"the mutant count must be visible; got {combined!r}"
    assert '"kill_rate_percent": 85.0' in combined, f"the kill rate must be visible; {combined!r}"


def test_is_crashed_run_separates_survivors_from_crash() -> None:
    """rc 1 + zero verdicts is a crash; rc 1 + a real tally is a survivor run."""
    assert _is_crashed_run(returncode=1, total=0) is True
    assert _is_crashed_run(returncode=1, total=20) is False
    assert _is_crashed_run(returncode=0, total=0) is False


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


def test_runs_mutmut_from_staging_cwd_baseline_at_repo_root(*, tmp_path: Path) -> None:
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
        'pure_trees = [".claude-plugin/scripts/livespec/parse"]\n'
        'mutation_staging_dir = "staging"\n',
        encoding="utf-8",
    )
    fake = _make_fake_mutmut(tmp_path=tmp_path, killed=17, total=20)
    result = _run_check(
        tmp_path=repo_root,
        fake_mutmut_dir=fake,
        baseline={"kill_rate_percent": 0, "mutants_surviving": 0, "mutants_total": 0},
        cwd=repo_root,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    marker = staging / "MUTMUT_RAN_IN.txt"
    assert marker.is_file(), "mutmut should have run from the staging dir"
    assert marker.read_text(encoding="utf-8") == str(staging)
    assert not (repo_root / "MUTMUT_RAN_IN.txt").is_file()
    assert (repo_root / ".mutmut-baseline.json").is_file(), "baseline must land at the repo root"
    assert not (staging / ".mutmut-baseline.json").is_file()
