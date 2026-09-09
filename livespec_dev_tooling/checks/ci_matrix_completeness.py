"""ci_matrix_completeness — CI provably runs AND gates the whole canonical aggregate.

Per epic `livespec-cf4bcu` (fleet-ci-aggregate-coverage) slice 1, this
check is the shared drift-guard that closes the seam
`check-aggregate-completeness` leaves open. `aggregate-completeness`
proves the consumer's `justfile` `check:` aggregate WIRES every canonical
slug; it never proves that CI RUNS them. A canonical check that runs at
pre-push but never in CI gives false coverage — a contributor sees the
aggregate green locally while CI silently skips the check. This
meta-check, reading a repo's OWN committed files only, asserts both:

- **(a) CI runs the whole aggregate.** The set of canonical slugs CI runs
  is a SUPERSET of the canonical slugs the `justfile` `check:` aggregate
  wires. The CI-covered slug set is, per top-level job in
  `.github/workflows/ci.yml`, the union of (i) the job's
  `strategy.matrix.target` entries and (ii) every canonical `check-<slug>`
  its `run:` lines invoke as `just <canonical-slug>` (the matrix leg
  `just ${{ matrix.target }}` contributes via (i), not (ii)). A canonical
  aggregate slug absent from that union fails (a).
- **(a-repo-local) CI runs the REPO-LOCAL members too, or the repo says
  why not** (`livespec-dev-tooling-8o8e.18`). (a) above was canonical-scoped,
  and a repo-local slug — one with no backing `checks/<slug>.py` module, so
  `canonical_check_slugs` never discovers it — was therefore outside its
  universe BY CONSTRUCTION. It could sit in a `just check` aggregate forever
  with no CI job running it: pre-push caught a violation, and every path to
  master that runs no local hook (a web edit, a bot commit, release
  automation, a fan-out pin bump, `--no-verify`) did not. Seventeen such
  gates across six fleet repos were measured in that state. The remedy is
  NOT "wire all seventeen" — some absences are correct, the precedent being
  livespec-overseer's `check-codex-skill-picker`, which can only ever SKIP
  on a hosted runner, and a matrix entry that can only skip manufactures a
  green row that reads as coverage. The defect was that NOTHING SAID WHICH
  WAS WHICH. So a repo-local aggregate slug run by no CI job is a finding
  UNLESS the repo declares it in `[tool.livespec_dev_tooling]
  repo_local_ci_skips` with a reason (`config.RepoLocalCiSkip`), and a
  declaration naming a slug the aggregate no longer wires is ITSELF a
  finding — otherwise the list rots into an unexamined exemption, which is
  the shape this limb exists to remove.
- **(b) `ci-green` gates the whole aggregate.** A job named `ci-green`
  exists and its `needs:` list covers every GATING job — a job that runs
  any `just <target>` command (canonical OR not: `check-doctor-static`,
  `e2e-cli`, `acceptance`) or carries a `strategy.matrix.target` list (whose
  leg runs `just ${{ matrix.target }}`). This is BROADER than (a)'s
  canonical scope on purpose (`livespec-dev-tooling-o6b`): a dedicated
  non-canonical gating job contributes no canonical slug, so scoping (b) to
  canonical jobs would never require it in `ci-green.needs` — a red
  `e2e-cli` / `acceptance` / `doctor-static` could then merge under a
  require-only-`ci-green` branch protection. Telemetry / export / auto-merge
  / setup jobs run no `just` target and carry no matrix, so they are
  excluded automatically (no hardcoded exclude list). When a repo protects
  master by requiring only `ci-green`, an incomplete `needs:` list would
  let a red gating job land on master.

Warn-vs-fail severity lever (mirrors `no_todo_registry` /
`no_lloc_soft_warnings`): the scan ALWAYS runs (no skip carve-out). When
`LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST` is set to a non-empty value (a repo
sets it in its CI job once its matrix + `ci-green` are wired), findings
fail the check (exit 4, error-level diagnostics). When the lever is unset
(or empty), the SAME findings are logged at WARNING level and the check
exits 0 — so the slug can propagate fleet-wide and warn each not-yet-wired
repo about its own CI gaps without reddening it. Each repo flips to fail in
its own wiring PR.

Exit codes: `0` — no findings, OR findings with the lever unset;
`2` — usage error (argparse-driven); `4` — findings with the lever set.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. Two private siblings carry the PURE halves as
LLOC-reduction splits (like `_red_green_replay_modes`): the regex parsers
live in `_ci_matrix_parse`, and the finding model plus the three limb
verdicts in `_ci_matrix_evaluate`. What stays here is the impure middle —
resolving a repo's committed files into those inputs, applying the severity
lever, and emitting every diagnostic — so the check reads as
parse → evaluate → report with the IO confined to the ends.

Self-bootstrapping: because this module lives under
`livespec_dev_tooling/checks/`, its own slug
(`check-ci-matrix-completeness`) is a canonical slug discovered by
`canonical_check_slugs`, so `aggregate-completeness` forces it into every
consumer's `just check` aggregate; this check in turn nudges each
consumer's CI toward running and gating the whole aggregate.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware.
from returns.result import Failure  # noqa: E402  — vendor-path-aware.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware.

from livespec_dev_tooling.canonical_checks import world_gate_check_slugs  # noqa: E402
from livespec_dev_tooling.checks._check_aggregate_failures import (  # noqa: E402
    TargetsArrayFailure,
    TargetsArrayUnterminated,
)
from livespec_dev_tooling.checks._ci_matrix_evaluate import (  # noqa: E402
    Finding,
    evaluate,
    finding,
)
from livespec_dev_tooling.checks._ci_matrix_parse import (  # noqa: E402
    extract_check_recipe_body,
    extract_targets_array_tokens,
    load_canonical,
    parse_ci_jobs,
)
from livespec_dev_tooling.config import (  # noqa: E402  — vendor-path-aware.
    load_repo_local_ci_skips,
)

__all__: list[str] = []


_JUSTFILE_NAME = "justfile"
_TARGET_INVENTORY_NAME = "check-targets.txt"
_CI_YML_PATH = Path(".github") / "workflows" / "ci.yml"
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST"
_CHECK_ID = "ci_matrix_completeness"
_EXIT_VIOLATIONS = 4


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci-matrix-completeness",
        description=(
            "Enforce that CI runs (a) and gates (b) the whole canonical `just check` "
            "aggregate: the CI-covered canonical slug set is a superset of the justfile "
            "aggregate, and a `ci-green` job's `needs:` covers every check-bearing job. "
            "Warn-default drift-guard of epic fleet-ci-aggregate-coverage."
        ),
    )
    _ = parser.add_argument(
        "--canonical-from",
        type=str,
        default=None,
        help=(
            'Path to a JSON file with shape `{"slugs": [...]}` overriding the live '
            "canonical-set discovery. Reserved for hermetic test fixtures; production "
            "callers omit this flag."
        ),
    )
    return parser


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("ci_matrix_completeness")


def _collect_findings(
    *, cwd: Path, canonical: tuple[str, ...], world_gates: frozenset[str]
) -> list[Finding]:
    """Resolve preconditions then evaluate; a precondition returns one finding."""
    justfile_path = cwd / _JUSTFILE_NAME
    if not justfile_path.is_file():
        return [
            _absence(mode="justfile_not_found", message="justfile not found", path=justfile_path)
        ]
    inventory_targets = _inventory_targets(cwd=cwd)
    if inventory_targets is None:
        recipe_body = extract_check_recipe_body(
            justfile_text=justfile_path.read_text(encoding="utf-8")
        )
        if isinstance(recipe_body, Failure):
            return [
                _absence(
                    mode="check_recipe_not_found",
                    message="justfile has no `check:` recipe",
                    path=justfile_path,
                )
            ]
        targets = extract_targets_array_tokens(recipe_body=recipe_body.unwrap())
        if isinstance(targets, Failure):
            return [_targets_absence(failure=targets.failure(), path=justfile_path)]
        justfile_targets = targets.unwrap()
    else:
        justfile_targets = inventory_targets
    ci_yml_path = cwd / _CI_YML_PATH
    if not ci_yml_path.is_file():
        return [
            _absence(
                mode="ci_yml_not_found",
                message="no `.github/workflows/ci.yml`; CI cannot run the aggregate",
                path=ci_yml_path,
            )
        ]
    jobs = parse_ci_jobs(source=ci_yml_path.read_text(encoding="utf-8"))
    return evaluate(
        canonical=canonical,
        world_gates=world_gates,
        justfile_targets=justfile_targets,
        jobs=jobs,
        repo_local_skips=load_repo_local_ci_skips(repo_root=cwd) or (),
    )


def _inventory_targets(*, cwd: Path) -> list[str] | None:
    path = cwd / _TARGET_INVENTORY_NAME
    if not path.is_file():
        return None
    targets: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        token = raw.split("#", 1)[0].strip()
        if token.startswith("check-"):
            targets.append(token)
    return targets


def _absence(*, mode: str, message: str, path: Path) -> Finding:
    """Build a graceful-absence precondition finding."""
    return finding(mode=mode, message=message, path=str(path))


def _targets_absence(*, failure: TargetsArrayFailure, path: Path) -> Finding:
    """Render the targets-array failure, which has TWO arms and used to have one.

    An UNTERMINATED array was reported as `targets_array_not_found` — the
    operator was sent to add an array that is already there, missing only its
    closing paren.
    """
    if isinstance(failure, TargetsArrayUnterminated):
        return _absence(
            mode="targets_array_unterminated",
            message="`check:` recipe opens a `targets=(...)` array and never closes it",
            path=path,
        )
    return _absence(
        mode="targets_array_not_found",
        message="`check:` recipe declares no `targets=(...)` array",
        path=path,
    )


def _report(*, log: structlog.stdlib.BoundLogger, findings: list[Finding]) -> int:
    """Emit findings under the severity lever; return the lever-scoped exit code."""
    if not findings:
        return 0
    fail = bool(os.environ.get(_FAIL_ENV_VAR))
    # `item`, not `finding`: the loop used to own that name, but `finding` is now
    # the imported factory from `_ci_matrix_evaluate` and shadowing it here would
    # be a live F402 rather than a style nit.
    for item in findings:
        emit = log.error if fail else log.warning
        emit(
            item.message,
            check_id=_CHECK_ID,
            failure_mode=item.failure_mode,
            fail_env_var=_FAIL_ENV_VAR,
            failing=fail,
            **item.fields,
        )
    return _EXIT_VIOLATIONS if fail else 0


def main() -> int:
    args = _build_parser().parse_args()
    canonical_from: str | None = args.canonical_from
    log = _configure_logger()
    cwd = Path.cwd()
    loaded = load_canonical(canonical_from=canonical_from, cwd=cwd)
    if isinstance(loaded, IOFailure):
        # NOT lever-scoped, unlike every finding below. A `--canonical-from`
        # the check cannot read or parse is a broken INVOCATION, not a gap in
        # the repo being checked, so the severity lever that decides whether
        # gaps fail has no bearing on it. It raised before this conversion —
        # this only replaces the traceback with a diagnostic.
        failure = loaded.failure()._inner_value  # noqa: SLF001  — IOResult failure unwrap.
        log.error(
            "canonical-slug override could not be loaded",
            check_id=_CHECK_ID,
            failure_mode="canonical_override_unusable",
            path=failure.path,
            detail=failure.detail,
        )
        return _EXIT_VIOLATIONS
    canonical = unsafe_perform_io(loaded.unwrap())
    # `unsafe_perform_io(...unwrap())` is FAIL-CLOSED and deliberate.
    # `world_gate_check_slugs` is `IOResult` since `livespec-dev-tooling-vzwa`,
    # and its failure means the installed `checks/` package is unreadable — a
    # broken install, not a reachable state for a check running out of that same
    # package. A `match` arm here could never be covered under this repo's
    # 100%-per-file gate, so raising beats a dead branch (`#846`'s precedent).
    # ⛔ NOT `value_or(())`: an empty slug set is read as 'no canonical checks'
    # and PASSES — the exact fail-open vzwa removed.
    world_gates = frozenset(unsafe_perform_io(world_gate_check_slugs().unwrap()))
    findings = _collect_findings(cwd=cwd, canonical=canonical, world_gates=world_gates)
    return _report(log=log, findings=findings)


if __name__ == "__main__":
    raise SystemExit(main())
