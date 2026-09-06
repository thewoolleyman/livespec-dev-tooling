"""ci_gate_parity — PR gate ≡ master gate: no gating job may skip its steps on a PR.

The companion to `ci_matrix_completeness`. Where that check proves every
canonical slug is PRESENT in CI and wired into the `ci-green` gate's
`needs:`, this check proves each such gating job actually RUNS on a
`pull_request` rather than being conditionally skipped or reduced relative to
a `push` to master. Together they enforce the livespec CI-as-a-merge-gate
(branch protection) invariant stated in
`livespec/SPECIFICATION/non-functional-requirements.md`:

    **PR gate ≡ master gate.** For every fleet member, the set of GATING
    checks a `pull_request` must pass is identical to the set that runs on a
    `push` to master. A PR MAY run ADDITIONAL checks master does not; what is
    forbidden is a PR running FEWER gating checks than master.

The exact hole this closes shipped as the retired `.py`-skip mechanism: a
`setup` job named `detect-py-changes` exported `py_changed` (true on push,
false on a doc-only PR), and the python jobs gated their real steps on
`if: needs.setup.outputs.py_changed == 'true'` (with a paired "Skip when no
.py changes" step gated `!= 'true'`). That made a doc-only PR run FEWER
checks than master — the seam that let a workflow-only PR merge green and
redden master on 2026-09-04.

What it flags, precisely:

- **Gating job** = a job listed in the `ci-green` job's `needs:`. `ci-green`
  itself is not gating; a non-gating job (telemetry export, the `setup`
  detector) absent from `ci-green.needs` is exempt.
- **Violation** = a gating job that carries a job- or step-level `if:` whose
  expression references the changeset `.py`-detection token `py_changed` (see
  `_ci_matrix_parse._IF_CHANGESET_PY`). That token is the DIRECTIONAL
  discriminator "runs on push, skipped on doc-only PR".
- **NOT flagged** — additional PR strictness, which is one-directional-safe:
  an `if:` on `github.event_name == 'pull_request'` /
  `startsWith(github.head_ref, 'release-please--')` (e.g.
  `release-gate-pre-tag`) carries no `py_changed` token; `runs-on` runner
  routing on `vars.CI_RUNNER_LABELS` is not an `if:` gate at all; and a
  non-gating job (absent from `ci-green.needs`) is out of scope even if it
  event-conditions its steps.

Warn-vs-fail severity lever (mirrors `ci_matrix_completeness` /
`no_todo_registry`): the scan ALWAYS runs. When
`LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST` is set to a non-empty value,
findings fail the check (exit 4, error-level diagnostics); when it is unset
(or empty) the SAME findings log at WARNING and the check exits 0 — so the
slug propagates fleet-wide and warns each not-yet-fixed repo about its own
gate skew without reddening it. Each repo flips to fail in the PR that
retires its skip.

Exit codes: `0` — no findings, OR findings with the lever unset; `2` — usage
error (argparse-driven); `4` — findings with the lever set.

Graceful absence: no `.github/workflows/ci.yml`, or a ci.yml with no
`ci-green` gate job (hence no gating jobs), means there is no merge gate whose
parity could be violated → no findings (exit 0). An absent `ci-green` gate is
`ci_matrix_completeness`'s assertion (b) finding, deliberately not duplicated
here.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`. The ci.yml parser (and the rule-encoding `py_changed`
recogniser) live in the shared private sibling `_ci_matrix_parse`, imported by
both this check and `ci_matrix_completeness`, so the two cannot drift about
what the invariant means.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._ci_matrix_parse import (  # noqa: E402
    CiJob,
    parse_ci_jobs,
)

__all__: list[str] = []


_CI_YML_PATH = Path(".github") / "workflows" / "ci.yml"
_CI_GREEN_JOB = "ci-green"
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST"
_CHECK_ID = "ci_gate_parity"
_EXIT_VIOLATIONS = 4

_MSG_GATE_SKEW = (
    "gating job conditions its steps on a changeset `.py`-detection output "
    "(`py_changed`): it runs on a `push` to master but is skipped/reduced on a "
    "doc-only `pull_request`, so the PR gate is weaker than the master gate"
)


@dataclass(frozen=True, kw_only=True)
class _Finding:
    """One structured finding: a failure mode plus its diagnostic fields."""

    failure_mode: str
    message: str
    fields: dict[str, object]


def _finding(*, mode: str, message: str, **fields: object) -> _Finding:
    return _Finding(failure_mode=mode, message=message, fields=dict(fields))


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="ci-gate-parity",
        description=(
            "Enforce PR gate ≡ master gate: no CI gating job (one in "
            "`ci-green.needs`) may condition its real steps on a changeset "
            "`.py`-detection output (`py_changed`), which would run it on a "
            "push to master but skip it on a doc-only pull request. "
            "Warn-default companion to check-ci-matrix-completeness."
        ),
    )


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("ci_gate_parity")


def _evaluate(*, jobs: list[CiJob]) -> list[_Finding]:
    """Flag each GATING job (one in `ci-green.needs`) that `.py`-conditions its steps."""
    ci_green: CiJob | None = None
    for job in jobs:
        if job.name == _CI_GREEN_JOB:
            ci_green = job
            break
    if ci_green is None:
        # No all-green gate ⇒ no gating jobs ⇒ no parity to violate. An absent
        # `ci-green` is `ci_matrix_completeness`'s assertion (b) finding, not
        # this check's to re-report.
        return []
    gating = ci_green.needs
    return [
        _finding(mode="ci-gate-py-conditioned-skip", message=_MSG_GATE_SKEW, job=job.name)
        for job in jobs
        if job.name in gating and job.changeset_py_conditioned
    ]


def _collect_findings(*, cwd: Path) -> list[_Finding]:
    """Parse the repo's OWN ci.yml and evaluate; absent workflow ⇒ no findings."""
    ci_yml_path = cwd / _CI_YML_PATH
    if not ci_yml_path.is_file():
        # No workflow ⇒ no merge gate whose parity could be violated.
        return []
    jobs = parse_ci_jobs(source=ci_yml_path.read_text(encoding="utf-8"))
    return _evaluate(jobs=jobs)


def _report(*, log: structlog.stdlib.BoundLogger, findings: list[_Finding]) -> int:
    """Emit findings under the severity lever; return the lever-scoped exit code."""
    if not findings:
        return 0
    fail = bool(os.environ.get(_FAIL_ENV_VAR))
    for finding in findings:
        emit = log.error if fail else log.warning
        emit(
            finding.message,
            check_id=_CHECK_ID,
            failure_mode=finding.failure_mode,
            fail_env_var=_FAIL_ENV_VAR,
            failing=fail,
            **finding.fields,
        )
    return _EXIT_VIOLATIONS if fail else 0


def main() -> int:
    _ = _build_parser().parse_args()
    log = _configure_logger()
    findings = _collect_findings(cwd=Path.cwd())
    return _report(log=log, findings=findings)


if __name__ == "__main__":
    raise SystemExit(main())
