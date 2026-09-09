"""shell_quality — canonical shell-quality policy gate."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402

from livespec_dev_tooling.checks._shell_quality_finding import Finding  # noqa: E402
from livespec_dev_tooling.checks._shell_quality_recipes import recipe_findings  # noqa: E402
from livespec_dev_tooling.config import assert_never  # noqa: E402
from livespec_dev_tooling.shellcheck import (  # noqa: E402
    ShellCheckRunFailure,
    ShellCheckUnavailable,
    ShellCorpusEmpty,
    ShellFinding,
    run_shellcheck,
)

__all__: list[str] = []

_CHECK_ID = "shell-quality"
_EXIT_VIOLATIONS = 1


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("shell_quality")


def _shellcheck_findings(*, repo_root: Path) -> list[Finding]:
    run_result = run_shellcheck(repo_root=repo_root)
    if not is_successful(run_result):
        return _findings_for_run_failure(repo_root=repo_root, failure=run_result.failure())
    shell_findings = run_result.unwrap()
    findings: list[Finding] = []
    for item in shell_findings:
        findings.extend(_finding_for_shellcheck_severity(item=item))
    return findings


def _findings_for_run_failure(*, repo_root: Path, failure: ShellCheckRunFailure) -> list[Finding]:
    """Render the run's failure track, TOTALLY — every member gets an arm.

    ⛔ The `case _: assert_never(failure)` terminator is the POINT, not
    ceremony. This arm previously read `if isinstance(failure,
    ShellCheckUnavailable): return [...]` inside the caller and then fell
    through to `.unwrap()` on an already-failed `Result` for every OTHER
    member — so `ShellCorpusEmpty`, the other half of `ShellCheckRunFailure`,
    crashed `check-shell-quality` with `UnwrapFailedError` on any repo with no
    tracked shell files. An `isinstance` guard cannot fail when a member is
    added; a `match` over the declared union does, at the type gate.

    The two members mean genuinely different things and that is why neither
    can be folded into the other:

    - `ShellCorpusEmpty` is NOT an error. Zero tracked shell files is the
      correct state for a shell-free repo, so it yields no findings and the
      check passes. What must never come back with it is the blanket
      `if isinstance(result, Failure): return []` this function replaced in
      `cddb989e` — that swallowed BOTH members, which is what made a missing
      ShellCheck binary read as a clean repo.
    - `ShellCheckUnavailable` IS an error, and stays one: the check cannot
      have looked at any shell file, so it reports the unavailability as a
      finding carrying the remedy rather than passing blind.
    """
    match failure:
        case ShellCorpusEmpty():
            return []
        case ShellCheckUnavailable():
            return [_finding_for_shellcheck_unavailable(repo_root=repo_root, failure=failure)]
        case _:
            assert_never(failure)


def _finding_for_shellcheck_unavailable(
    *, repo_root: Path, failure: ShellCheckUnavailable
) -> Finding:
    return Finding(
        reason="shellcheck-unavailable",
        path=repo_root,
        line=1,
        binary_name=failure.binary_name,
        required_version=failure.required_version,
        remedy=failure.remedy,
    )


def _finding_for_shellcheck_severity(*, item: ShellFinding) -> list[Finding]:
    finding = _from_shellcheck(item=item)
    findings_by_severity = {
        "error": [finding],
        "warning": [finding],
        "info": [],
        "style": [],
    }
    return findings_by_severity[item.severity]


def _from_shellcheck(*, item: ShellFinding) -> Finding:
    return Finding(
        reason="shellcheck-finding",
        path=item.path,
        line=1,
        code=item.code,
        severity=item.severity,
    )


def findings_for_repo(*, repo_root: Path) -> list[Finding]:
    findings = _shellcheck_findings(repo_root=repo_root)
    findings.extend(recipe_findings(repo_root=repo_root))
    return findings


def _emit_findings(*, log: structlog.stdlib.BoundLogger, findings: Sequence[Finding]) -> None:
    for finding in findings:
        log.error(
            "shell-quality policy violation",
            check_id=_CHECK_ID,
            reason=finding.reason,
            path=str(finding.path),
            line=finding.line,
            recipe=finding.recipe,
            binary_name=finding.binary_name,
            required_version=finding.required_version,
            remedy=finding.remedy,
            code=finding.code,
            severity=finding.severity,
            construct=finding.construct,
        )


def main() -> int:
    log = _configure_logger()
    repo_root = Path.cwd()
    findings = findings_for_repo(repo_root=repo_root)
    exit_codes = {
        False: lambda: 0,
        True: lambda: _EXIT_VIOLATIONS,
    }
    _emit_findings(log=log, findings=findings)
    return exit_codes[bool(findings)]()


if __name__ == "__main__":
    raise SystemExit(main())
