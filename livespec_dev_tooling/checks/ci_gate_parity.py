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

The clause names TWO forbidden directions, and this check enforces both. Per
`livespec/SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate
(branch protection)" (v217), the guard FAILS when a gating job — at the job
level or in its real steps — is conditioned on the TRIGGERING EVENT **or** on a
changeset predicate in the FORBIDDEN DIRECTION: so that it runs on a `push` to
master but is skipped, or runs a smaller check set, on a `pull_request`. A job
conditioned to run pull-request-ONLY adds strictness rather than removing it
and is not flagged.

What it flags, precisely:

- **Gating job** = a job listed in the `ci-green` job's `needs:`. `ci-green`
  itself is not gating; a non-gating job (telemetry export, the `setup`
  detector) absent from `ci-green.needs` is exempt.
- **Violation (changeset half)** = a gating job carrying a job- or step-level
  `if:` whose expression references the changeset `.py`-detection token
  `py_changed` (see `_ci_matrix_parse._IF_CHANGESET_PY`) — the DIRECTIONAL
  signal "runs on push, skipped on doc-only PR".
- **Violation (event half)** = a gating job carrying a job- or step-level `if:`
  that references `github.event_name`, `github.ref`, or `github.ref_name` in
  any shape that is not ENUMERATED as stricter-only (see
  `_ci_matrix_parse._STRICTER_ONLY_SHAPES`): `github.event_name ==
  'pull_request'` and `startsWith(github.head_ref, …)`, including a conjunction
  of the two. `if: github.event_name == 'push'`, `!= 'pull_request'`,
  `== 'merge_group'`, and `github.ref == 'refs/heads/master'` are all findings.
- ⛔ **Exact direction analysis of arbitrary expressions is NOT attempted, and
  must not be added.** Any surviving event/ref reference on a gating job is a
  finding, because a legitimately push-only job belongs OUTSIDE
  `ci-green.needs` — which is where every fleet member's `export-telemetry`
  already sits. Widening the enumeration is how a genuinely stricter-only shape
  earns its exemption; inferring direction from an expression tree is not.
- **NOT flagged** — additional PR strictness, which is one-directional-safe:
  `release-gate-pre-tag`'s `github.event_name == 'pull_request' &&
  startsWith(github.head_ref, 'release-please--')` is a conjunction of both
  enumerated shapes and it IS a gating job on livespec's master, so this
  exemption is load-bearing rather than hypothetical; `runs-on` runner routing
  on `vars.CI_RUNNER_LABELS` is not an `if:` gate at all; and a non-gating job
  (absent from `ci-green.needs`) is out of scope even if it event-conditions
  its steps.

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
`sys.stderr.write`. The ci.yml parser (and BOTH rule-encoding recognisers, the
`py_changed` one and the event/ref one) live in the shared private sibling
`_ci_matrix_parse`, imported by both this check and `ci_matrix_completeness`,
so the two cannot drift about what the invariant means.
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

_MSG_EVENT_SKEW = (
    "gating job conditions its steps on the triggering event or ref "
    "(`github.event_name` / `github.ref` / `github.ref_name`) in a shape that is "
    "not pull-request-only, so it can run on a `push` to master while being "
    "skipped/reduced on a `pull_request` — the PR gate is then weaker than the "
    "master gate. A legitimately push-only job belongs OUTSIDE `ci-green.needs` "
    "(where `export-telemetry` already sits) rather than conditioned inside it"
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
            "`ci-green.needs`) may condition its real steps on the triggering "
            "event or ref (`github.event_name` / `github.ref` / "
            "`github.ref_name`, outside the pull-request-only shapes) or on a "
            "changeset `.py`-detection output (`py_changed`) — either would run "
            "it on a push to master but skip it on a pull request. "
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


def _job_findings(*, job: CiJob) -> list[_Finding]:
    """The findings a single GATING job earns — one per forbidden direction it carries.

    A job can carry BOTH halves of the clause, and each is reported under its
    own failure mode so the diagnostic names which direction was found rather
    than collapsing two different defects into one message.
    """
    findings: list[_Finding] = []
    if job.changeset_py_conditioned:
        findings.append(
            _finding(mode="ci-gate-py-conditioned-skip", message=_MSG_GATE_SKEW, job=job.name)
        )
    if job.event_conditioned:
        findings.append(
            _finding(mode="ci-gate-event-conditioned-skip", message=_MSG_EVENT_SKEW, job=job.name)
        )
    return findings


def _evaluate(*, jobs: list[CiJob]) -> list[_Finding]:
    """Flag each GATING job (one in `ci-green.needs`) conditioned in a forbidden direction."""
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
    return [finding for job in jobs if job.name in gating for finding in _job_findings(job=job)]


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
