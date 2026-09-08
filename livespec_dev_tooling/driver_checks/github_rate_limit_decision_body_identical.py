"""github_rate_limit_decision_body_identical — verify a Driver's decision-body copy.

Byte-identity Verifier for the GitHub rate-limit DECISION body, mirroring
`checks/no_shadow_ledger_body_identical` (Conformance-Pattern concern #1): the
file a Driver bundle ships MUST be byte-identical to the single packaged
carrier constant
`livespec_dev_tooling.install_github_rate_limit_decision.CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY`,
imported here — this module is NOT a second copy of the body.

WHY BYTE-IDENTITY IS THE RIGHT BAR HERE. The decision function's verdicts were
measured, not reasoned: the rollout verification re-measured a 0.0%
false-positive rate from v0.6.0 onward against 40.5% before. Every constant in
that body is load-bearing to a number somebody counted, and a well-meant local
edit in one Driver — widening a regex, relaxing the literal-loop threshold —
would silently un-measure the guard in that runtime alone. Identity is what
makes the measurement transferable.

It lives under `driver_checks/` rather than `checks/` deliberately, and the
placement is the same judgement livespec-2exa recorded for `plugin_structure`:
this body lands only in a Driver bundle, so making its Verifier a CANONICAL
slug would force every aggregate-enforced consumer — livespec core, the
orchestrator plugins, livespec-runtime — to wire a recipe for a check that can
only ever self-skip there.

Self-skip: a tree carrying no Driver manifest resolves to no destination at
all (`driver_decision_body_path` returns None), which is exit 0. The installer
reads the SAME function, so the pair cannot disagree about which file is under
discussion.

Exit codes:
- `0` — this tree is not a Driver bundle (no-op), or the bundle's copy is
  present and byte-identical to the canonical body.
- `1` — the bundle carries no copy (or the path is not a regular file), or its
  bytes differ from the canonical body. Corrective action: run the
  from-package installer, which is the single source of the body.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stdout.write` / `sys.stderr.write`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

# The canonical body is the SINGLE source of truth, shipped as a module
# constant in the installer so it travels in the wheel. The check imports it
# (rather than carrying a second copy) so byte-identity is verified against the
# exact bytes the installer writes — there is no drift seam.
from livespec_dev_tooling.install_github_rate_limit_decision import (  # noqa: E402
    CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY,
    driver_decision_body_path,
)

__all__: list[str] = []


_CHECK_ID = "github_rate_limit_decision_body_identical"
_FAIL_EXIT = 1

_MISSING_FAILURE_MODE = "missing"
_BODY_MISMATCH_FAILURE_MODE = "body_mismatch"
_REMEDY = (
    "run `python -m livespec_dev_tooling.install_github_rate_limit_decision` "
    "(the from-package installer that writes the single canonical github "
    "rate-limit decision body byte-for-byte into this Driver bundle)"
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
    return structlog.get_logger(_CHECK_ID)


def verify_decision_body(*, project_root: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Compare this tree's Driver copy of the decision body to the canonical bytes."""
    path = driver_decision_body_path(project_root=project_root)
    if path is None:
        log.info(
            "no Driver plugin bundle at this root — nothing to verify",
            check_id=_CHECK_ID,
            status="skip",
            project_root=str(project_root),
        )
        return 0
    if not path.is_file():
        log.error(
            "Driver bundle carries no github rate-limit decision body",
            check_id=_CHECK_ID,
            status="fail",
            failure_mode=_MISSING_FAILURE_MODE,
            path=str(path),
            hint=_REMEDY,
        )
        return _FAIL_EXIT
    if path.read_text(encoding="utf-8") != CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY:
        log.error(
            "github_rate_limit_decision_body_identical: decision body drifted from canonical",
            check_id=_CHECK_ID,
            status="fail",
            failure_mode=_BODY_MISMATCH_FAILURE_MODE,
            path=str(path),
            hint=_REMEDY,
        )
        return _FAIL_EXIT
    return 0


def main() -> int:
    log = _configure_logger()
    return verify_decision_body(project_root=Path.cwd(), log=log)


if __name__ == "__main__":
    raise SystemExit(main())
