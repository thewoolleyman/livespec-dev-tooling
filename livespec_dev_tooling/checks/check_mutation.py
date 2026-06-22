"""check_mutation — mutation testing against livespec/parse/ + validate/, gated by a RUN/SKIP lever.

Per SPECIFICATION/constraints.md §"Enforcement suite — Release-gate targets"
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

from livespec_dev_tooling.config import load_mutation_staging_dir  # noqa: E402

__all__: list[str] = [
    "_baseline_is_placeholder",
    "_derive_exit_code",
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


def _derive_exit_code(*, killed: int, total: int, baseline: _Baseline) -> int:
    """Return exit code 0 (pass) or 1 (fail) based on kill rate vs baseline + floor.

    Zero-mutant case (total=0) passes unconditionally — nothing to kill.
    """
    if total == 0:
        return 0
    kill_rate = (killed / total) * 100.0
    baseline_rate = float(baseline.get("kill_rate_percent", 0.0))
    if kill_rate < _KILL_RATE_FLOOR:
        return 1
    if kill_rate < baseline_rate:
        return 1
    return 0


def _update_baseline(*, baseline_path: Path, killed: int, total: int) -> None:
    """Write a new baseline JSON file with the current mutation results."""
    kill_rate = (killed / total) * 100.0 if total > 0 else 0.0
    payload: dict[str, object] = {
        "kill_rate_percent": round(kill_rate, 2),
        "mutants_surviving": total - killed,
        "mutants_total": total,
    }
    _ = baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("check_mutation")
    if not os.environ.get(_RUN_ENV_VAR):
        log.info(
            "skipped (slow; runs in CI when LIVESPEC_RUN_MUTATION=true)",
            run_env_var=_RUN_ENV_VAR,
        )
        return 0
    repo_root = Path.cwd()
    # The ratchet file is version-controlled at the repo root; the staging
    # cwd (nested-layout import-root) only relocates WHERE mutmut runs, never
    # where the baseline lives.
    baseline_path = repo_root / _BASELINE_PATH
    staging_cwd = _resolve_staging_cwd(repo_root=repo_root)

    baseline: _Baseline = {}
    if baseline_path.is_file():
        # The `cast` is the single typed parse boundary: `json.loads` yields
        # `Any`, and the cast asserts the recorded baseline shape so the
        # downstream `int(...)`/`float(...)` reads resolve from typed fields.
        baseline = cast("_Baseline", json.loads(baseline_path.read_text(encoding="utf-8")))

    first_run = _baseline_is_placeholder(baseline=baseline)

    run_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mutmut",
            "run",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(staging_cwd),
    )
    if run_result.returncode not in (0, 1):
        log.error(
            "mutmut run failed",
            returncode=run_result.returncode,
            stderr=run_result.stderr[:500],
        )
        return 1

    # `--all True` lists EVERY mutant with its verdict; without it `mutmut
    # results` prints only survivors, which the parser cannot tally into a
    # kill/total. The summary lives only in the transient `run` emoji line.
    results_result = subprocess.run(
        [sys.executable, "-m", "mutmut", "results", "--all", "True"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(staging_cwd),
    )
    killed, total = _parse_mutmut_results(output=results_result.stdout)
    kill_rate = (killed / total) * 100.0 if total > 0 else 0.0

    log.info(
        "mutation results",
        killed=killed,
        total=total,
        kill_rate_percent=round(kill_rate, 2),
        first_run=first_run,
        staging_cwd=str(staging_cwd),
    )

    if first_run:
        _update_baseline(baseline_path=baseline_path, killed=killed, total=total)
        log.info("baseline captured", baseline_path=str(baseline_path))
        return 0

    exit_code = _derive_exit_code(killed=killed, total=total, baseline=baseline)
    if exit_code == 0:
        baseline_rate = float(baseline.get("kill_rate_percent", 0.0))
        if kill_rate > baseline_rate:
            _update_baseline(baseline_path=baseline_path, killed=killed, total=total)
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
