"""check_mutation — mutation testing against livespec/parse/ + validate/, gated by a RUN/SKIP lever.

Per SPECIFICATION/constraints.md section "Enforcement suite — Release-gate targets"
and: runs mutmut against `.claude-plugin/scripts/
livespec/parse/` and `.claude-plugin/scripts/livespec/validate/`, then
compares the kill rate against `.mutmut-baseline.json` using a ratchet-
with-ceiling mechanism:

  - Hard floor: kill_rate MUST be >= 80.0% (the v1 absolute minimum).
  - Ratchet: kill_rate MUST be >= the recorded baseline kill_rate_percent
    (no regression allowed once established).
  - First-run mode: when the baseline file records `mutants_total: 0`
    (the pre-implementation placeholder), the check runs mutmut, saves
    the result as the new baseline, and exits 0. This allows the very
    first release-tag CI run to capture the baseline without a hard fail.
    A run that enumerated zero mutants is NOT eligible: it captures no
    baseline and fails (see the z45 note below).

RUN/SKIP lever: mutation testing is slow, so the suite is gated behind
the `LIVESPEC_RUN_MUTATION` env var (the blocker is runtime cost, not
severity). When the var is unset (or empty), the check logs a "skipped"
diagnostic and exits 0 without invoking mutmut. When it is set to a
non-empty value (CI sets it to `true` for the release context), the
suite runs as described above. This replaces the prior
`LIVESPEC_RELEASE_GATE` skip carve-out (epic li-cvaudit, cvtodo); the
lever is per-check and self-documenting rather than an external gate
that silently no-op'd the entire target.

mutmut-3.x output (work-item livespec-dev-tooling-q3r): the kill/total
tally is read from `mutmut results --all True`, which lists every mutant
as one `<key>: <status>` line. The pre-3.x `Killed:` / `Total:` summary
this check formerly scanned does not exist in mutmut 3.2.3 (`mutmut
results` with no flag prints only the surviving mutants), so the old
parser returned (0, 0) and the gate stayed a silent no-op even with real
verdicts. See `_parse_mutmut_results`.

Nested-layout staging cwd (work-item livespec-dev-tooling-q3r): mutmut
runs from a configurable import-root staging directory. Nested-layout
repos (livespec + livespec-orchestrator-git-jsonl, source under
`.claude-plugin/scripts/`) declare `mutation_staging_dir` in their
`[tool.livespec_dev_tooling]` block; the check runs `mutmut run` /
`results` with `cwd=<repo_root>/<mutation_staging_dir>` so the
trampoline's module-name-keyed mutants match the file-path-dotted
`paths_to_mutate` (the livespec-mutreal.1 Layer-B finding — otherwise
every mutant is unkillable). Flat-layout repos (livespec-dev-tooling,
livespec-runtime) omit the key, so mutmut runs from the repo root
unchanged. The `.mutmut-baseline.json` ratchet ALWAYS lives at the repo
root regardless of the staging cwd, so the baseline is version-controlled
in the repo, not in the (typically `.gitignore`d) staging tree.

Armed-but-inspected-nothing (work-item livespec-dev-tooling-z45): the
check formerly could not distinguish "mutation testing ran and found
nothing wrong" from "mutation testing never ran". Three independent masks
composed so that no misconfiguration could fail CI — (1) mutmut's rc 1
was tolerated unconditionally, though rc 1 is BOTH the legitimate
survivors-present exit AND what a hard crash returns (a
`FileNotFoundError` out of `guess_paths_to_mutate()` under a
misconfigured staging cwd); (2) a `total == 0` parse was an unconditional
pass; (3) first-run mode promoted whatever it had just measured —
possibly 0 — into the committed ratchet, which would pin it at 0.0%
permanently and then fail the 80% floor forever with no obvious cause.
Each is individually defensible; composed, they made a check that
inspected NOTHING indistinguishable from one that passed.

The three are now closed as follows, with no skip flag or env lever
anywhere in the path:

  - An ARMED check (non-empty `pure_trees`) whose run enumerates zero
    mutants is an ERROR. Nothing legitimately produces zero mutants from
    a non-empty pure tree.
  - `_is_crashed_run` separates mutmut's legitimate rc 1 (survivors
    present, verdicts parseable) from a crash (rc 1 with no parseable
    verdicts); the crash fails and surfaces mutmut's own stderr.
  - `_update_baseline` refuses a zero-mutant write outright, so no failed
    measurement can be promoted over the placeholder.
  - The mutant count and kill rate are logged before any verdict branch,
    so "inspected 0" is visible in CI output rather than silent.

Crashed-with-verdicts (work-item livespec-dev-tooling-6j6): the rc-1
distinction above must not be generalized to every return code. Deciding
crash-vs-survivors by the tally is correct for rc 1 and WRONG for anything
higher, because mutmut persists verdicts as it goes — so a run killed
part-way leaves a non-empty tally that is partial, skews high, and would be
ratcheted in. `_is_crashed_run` therefore restores an unconditional hard
fail for rc >= 2 alongside the rc-1 tally test.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow
through structlog (JSON to stderr).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402 — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._role_key_gate import (  # noqa: E402
    ensure_declared_paths_contain_python,
    role_absence_exit_code,
)
from livespec_dev_tooling.config import (  # noqa: E402
    load_config,
    load_mutation_staging_dir,
    role_trees,
)

__all__: list[str] = [
    "_baseline_is_placeholder",
    "_derive_exit_code",
    "_is_crashed_run",
    "_parse_mutmut_results",
    "_resolve_staging_cwd",
    "_update_baseline",
]

_BASELINE_PATH = Path(".mutmut-baseline.json")
_RUN_ENV_VAR = "LIVESPEC_RUN_MUTATION"
# Paths to mutate are configured in [tool.mutmut] in pyproject.toml;
# mutmut reads them automatically when invoked without explicit path flags.
_KILL_RATE_FLOOR: float = 80.0


class _Baseline(TypedDict, total=False):
    """Shape of `.mutmut-baseline.json`: the recorded kill-rate ratchet state.

    `total=False` mirrors the defensive `.get(..., default)` access — every
    key is optional, so the typed boundary matches runtime semantics exactly
    (no behavior change vs. the prior `dict[str, object]` annotation). Typing
    the value fields lets `int(baseline.get("mutants_total", 0))` and
    `float(baseline.get("kill_rate_percent", 0.0))` resolve from typed `int`/
    `float` rather than `object`.
    """

    mutants_total: int
    kill_rate_percent: float


def _baseline_is_placeholder(*, baseline: _Baseline) -> bool:
    """Return True when the baseline is the pre-implementation placeholder (total=0)."""
    return int(baseline.get("mutants_total", 0)) == 0


def _resolve_staging_cwd(*, repo_root: Path) -> Path:
    """Return the cwd mutmut runs from: the configured staging dir, else repo root.

    Reads `mutation_staging_dir` from the consumer's
    `[tool.livespec_dev_tooling]` block (a single repo-root-relative path).
    When configured, the returned cwd is `repo_root / mutation_staging_dir`
    (the nested-layout import-root staging dir); when absent, the cwd is
    `repo_root` itself, so flat-layout repos are unaffected. The baseline path
    is computed against `repo_root` separately — the staging cwd never moves
    the ratchet file.
    """
    staging = load_mutation_staging_dir(repo_root=repo_root)
    if staging is None:
        return repo_root
    return repo_root / staging


def _pure_trees_gate_exit_code(*, repo_root: Path, log: structlog.stdlib.BoundLogger) -> int | None:
    """Return the early exit for a missing, empty, or misdeclared pure layer."""
    config = load_config(repo_root=repo_root)
    gate_exit = role_absence_exit_code(
        config=config,
        role=config.pure_trees,
        key="pure_trees",
        log=log,
        check_id="check_mutation",
    )
    if gate_exit is not None:
        return gate_exit
    if not ensure_declared_paths_contain_python(
        repo_root=repo_root,
        key="pure_trees",
        paths=role_trees(role=config.pure_trees),
        log=log,
        check_id="check_mutation",
    ):
        return 1
    return None


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("check_mutation")


# mutmut 3.x verdict vocabulary, mirrored from mutmut's own
# `status_by_exit_code` map: every per-mutant `<key>: <status>` line emitted
# by `mutmut results --all True` ends in one of these statuses. `killed`
# counts toward the numerator; every recognized status counts toward the
# denominator. (`mutmut 3.2.3` collapses several exit codes onto these
# labels — `killed`, `survived`, `no tests`, `timeout`, `suspicious`,
# `skipped`, `not checked`, `check was interrupted by user`.)
_KILLED_STATUS = "killed"
_MUTMUT_STATUSES: frozenset[str] = frozenset(
    {
        "killed",
        "survived",
        "no tests",
        "timeout",
        "suspicious",
        "skipped",
        "not checked",
        "check was interrupted by user",
    }
)


def _parse_mutmut_results(*, output: str) -> tuple[int, int]:
    """Parse `mutmut results --all True` output and return (killed, total).

    mutmut 3.x emits one `    <key>: <status>` line per mutant — e.g.
    `    livespec.parse.front_matter.x__split__mutmut_3: killed`. The pre-3.x
    `Killed:` / `Total:` summary lines this check formerly scanned no longer
    exist: `mutmut results` (no flag) prints ONLY the surviving mutants, and
    the killed/total tally lives only in the transient `\\r`-rewritten `run`
    emoji line. Passing `--all True` lists EVERY mutant with its verdict, so
    counting these lines is the robust, complete kill/total source.

    Each line is split on its LAST `": "` so a colon inside a dotted mutant
    key never confuses the status read. A trailing-token match against the
    known mutmut status vocabulary keeps stray output (spinner frames, the
    `N mutations/second` footer, blank lines) from inflating the total.

    `killed` = count of lines whose status is exactly `killed`; `total` =
    count of every recognized verdict line. Returns (killed=0, total=0) when
    no verdict lines are present.
    """
    killed = 0
    total = 0
    for line in output.splitlines():
        stripped = line.strip()
        if ": " not in stripped:
            continue
        _key, _sep, status = stripped.rpartition(": ")
        status = status.strip()
        if status not in _MUTMUT_STATUSES:
            continue
        total += 1
        if status == _KILLED_STATUS:
            killed += 1
    return killed, total


def _is_crashed_run(*, returncode: int, total: int) -> bool:
    """Return True when mutmut's exit is a crash rather than a survivors-present run.

    mutmut exits 1 in two entirely different situations: legitimately, when
    mutants survived the suite; and on a hard crash before it enumerates
    anything (the observed case: a `FileNotFoundError` out of
    `guess_paths_to_mutate()` when the staging cwd has no `pyproject.toml`).
    Tolerating rc 1 unconditionally therefore absorbed every crash as a
    normal result — mask 1 of work-item livespec-dev-tooling-z45.

    The two are told apart by whether the run enumerated any mutant at all:
    a survivors-present run parses to a non-zero `total`, whereas a crash
    produces no parseable verdicts. A non-zero return code with an empty
    tally is therefore a crash, and the caller surfaces mutmut's stderr
    instead of reporting success.

    That tally test applies to rc 1 ALONE, and the first disjunct below is
    what confines it there (work-item livespec-dev-tooling-6j6). rc 1 is the
    only non-zero code mutmut itself returns for a legitimate outcome, so it
    is the only one a non-empty tally may excuse; every other non-zero code
    is a crash whatever the tally says. Judging rc >= 2 by the tally too — as
    this helper did when it replaced an unconditional `not in (0, 1)` hard
    fail — reopened the hole from the other side: mutmut persists each verdict
    as it completes, so a run that DIES part-way (rc 137 is a SIGKILL/OOM
    death, process-level and independent of mutmut's own exit table) leaves
    real verdicts on disk. Its partial tally then reads as a normal survivors
    run, and being partial it skews HIGH — so it is promoted into the
    committed ratchet, and every subsequent legitimate full run fails against
    a rate no complete run can reach.
    """
    return returncode not in (0, 1) or (returncode != 0 and total == 0)


def _derive_exit_code(*, killed: int, total: int, baseline: _Baseline) -> int:
    """Return exit code 0 (pass) or 1 (fail) based on kill rate vs baseline + floor.

    Zero-mutant case (total=0) FAILS. This helper is only ever reached with
    the check armed (`main` returns early when `pure_trees` is empty), and
    nothing legitimately produces zero mutants from a non-empty pure tree —
    so an empty tally means the run inspected nothing, which must never be
    indistinguishable from a run that passed (mask 2 of work-item
    livespec-dev-tooling-z45).
    """
    if total == 0:
        return 1
    kill_rate = (killed / total) * 100.0
    baseline_rate = float(baseline.get("kill_rate_percent", 0.0))
    if kill_rate < _KILL_RATE_FLOOR:
        return 1
    if kill_rate < baseline_rate:
        return 1
    return 0


def _update_baseline(*, baseline_path: Path, killed: int, total: int) -> bool:
    """Write a new baseline JSON file with the current mutation results.

    Returns True when the baseline was written, False when the write was
    REFUSED because the run enumerated zero mutants. A zero-mutant run is a
    failed measurement, and promoting it over the `mutants_total: 0`
    placeholder would pin the committed ratchet at 0.0% permanently — after
    which the 80% hard floor fails every subsequent release with no obvious
    cause (mask 3 of work-item livespec-dev-tooling-z45). The refusal lives
    here, in the writer, so no caller can route around it.
    """
    if total == 0:
        return False
    kill_rate = (killed / total) * 100.0
    payload: dict[str, object] = {
        "kill_rate_percent": round(kill_rate, 2),
        "mutants_surviving": total - killed,
        "mutants_total": total,
    }
    _ = baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True


def _load_baseline(*, baseline_path: Path) -> _Baseline:
    """Read the recorded ratchet, or an empty baseline when the file is absent.

    An absent file reads as `{}`, which `_baseline_is_placeholder` treats as
    the `mutants_total: 0` placeholder — the same first-run regime as an
    explicitly-placeholder file.
    """
    if not baseline_path.is_file():
        return {}
    # The `cast` is the single typed parse boundary: `json.loads` yields
    # `Any`, and the cast asserts the recorded baseline shape so the
    # downstream `int(...)`/`float(...)` reads resolve from typed fields.
    return cast("_Baseline", json.loads(baseline_path.read_text(encoding="utf-8")))


def _invoke_mutmut(
    *, staging_cwd: Path
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    """Run `mutmut run` then `mutmut results --all True`, returning both completions.

    `results` is invoked unconditionally, whatever `run` exited with: the
    return code alone cannot classify the outcome (work-item
    livespec-dev-tooling-z45), so the verdict tally is the evidence, and a
    single guard downstream decides whether the pair yielded a usable
    measurement.

    `--all True` lists EVERY mutant with its verdict; without it `mutmut
    results` prints only survivors, which the parser cannot tally into a
    kill/total. The summary lives only in the transient `run` emoji line.
    """
    run_result = subprocess.run(
        [sys.executable, "-m", "mutmut", "run"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(staging_cwd),
    )
    results_result = subprocess.run(
        [sys.executable, "-m", "mutmut", "results", "--all", "True"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(staging_cwd),
    )
    return run_result, results_result


def _measurement_is_unusable(
    *,
    log: structlog.stdlib.BoundLogger,
    run_result: subprocess.CompletedProcess[str],
    results_result: subprocess.CompletedProcess[str],
    total: int,
) -> bool:
    """Return True, after logging why, when the run yielded no usable measurement.

    The single place an armed run is allowed to be declared a failure of
    MEASUREMENT rather than of kill rate (work-item
    livespec-dev-tooling-z45). Both branches surface mutmut's own stderr,
    which the previous rc-1 tolerance discarded; a caller that reaches past
    this guard is holding a tally of at least one real mutant.
    """
    if _is_crashed_run(returncode=run_result.returncode, total=total):
        log.error(
            "mutmut crashed — non-zero exit with no parseable verdicts, not a survivors run",
            returncode=run_result.returncode,
            run_stderr=run_result.stderr[:500],
            results_stderr=results_result.stderr[:500],
        )
        return True
    if total == 0:
        log.error(
            "armed check enumerated zero mutants — it inspected nothing, so it cannot pass",
            returncode=run_result.returncode,
            run_stderr=run_result.stderr[:500],
            results_stderr=results_result.stderr[:500],
        )
        return True
    return False


def main() -> int:
    log = _configure_logger()
    if not os.environ.get(_RUN_ENV_VAR):
        log.info(
            "skipped (slow; runs in CI when LIVESPEC_RUN_MUTATION=true)",
            run_env_var=_RUN_ENV_VAR,
        )
        return 0
    repo_root = Path.cwd()
    gate_exit = _pure_trees_gate_exit_code(repo_root=repo_root, log=log)
    if gate_exit is not None:
        return gate_exit
    # The ratchet file is version-controlled at the repo root; the staging
    # cwd (nested-layout import-root) only relocates WHERE mutmut runs, never
    # where the baseline lives.
    baseline_path = repo_root / _BASELINE_PATH
    staging_cwd = _resolve_staging_cwd(repo_root=repo_root)
    baseline = _load_baseline(baseline_path=baseline_path)
    first_run = _baseline_is_placeholder(baseline=baseline)

    run_result, results_result = _invoke_mutmut(staging_cwd=staging_cwd)
    killed, total = _parse_mutmut_results(output=results_result.stdout)
    kill_rate = (killed / total) * 100.0 if total > 0 else 0.0

    # Logged BEFORE any verdict branch so the tally a CI reader needs is
    # present on every path, including the failing ones: "inspected 0" must
    # never render the same as "passed".
    log.info(
        "mutation results",
        killed=killed,
        total=total,
        kill_rate_percent=round(kill_rate, 2),
        first_run=first_run,
        staging_cwd=str(staging_cwd),
    )
    if _measurement_is_unusable(
        log=log, run_result=run_result, results_result=results_result, total=total
    ):
        return 1

    if first_run:
        _ = _update_baseline(baseline_path=baseline_path, killed=killed, total=total)
        log.info("baseline captured", baseline_path=str(baseline_path))
        return 0

    exit_code = _derive_exit_code(killed=killed, total=total, baseline=baseline)
    if exit_code == 0:
        baseline_rate = float(baseline.get("kill_rate_percent", 0.0))
        if kill_rate > baseline_rate:
            _ = _update_baseline(baseline_path=baseline_path, killed=killed, total=total)
            log.info("baseline improved and updated", new_rate=round(kill_rate, 2))
    else:
        baseline_rate = float(baseline.get("kill_rate_percent", 0.0))
        log.error(
            "kill rate below threshold",
            kill_rate=round(kill_rate, 2),
            baseline=baseline_rate,
            floor=_KILL_RATE_FLOOR,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
