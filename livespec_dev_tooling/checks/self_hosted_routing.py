"""self_hosted_routing — a forbidden trigger must never reach a `local-ci` self-hosted job.

Security guard for the livespec fleet's co-located, unprivileged self-hosted CI
runner (label `local-ci`, the "contained CI lane"). Because the fleet repos are
PUBLIC, a workflow that lets a fork-reachable or privileged non-PR event reach a
`local-ci` job is a code-execution hole. Reading ONLY a repo's own
`.github/workflows/*.yml` and `*.yaml`, this check asserts, per workflow file:

    if any job's `runs-on` references the label `local-ci`, the workflow's `on:`
    trigger set MUST NOT contain any FORBIDDEN trigger.

FORBIDDEN triggers (exactly these six): `pull_request_target`, `workflow_run`,
`issue_comment`, `repository_dispatch`, `merge_group`, `workflow_dispatch`.
`pull_request` is ALLOWED — same-repo fork safety is handled at runtime by the
repo's approval gate, not statically; `push`, `schedule`, `workflow_call`, and
any other non-forbidden trigger are likewise never flagged.

Scope is the `local-ci` label SPECIFICALLY, not generic `self-hosted`. The
fleet's SECOND, deliberately-privileged tier — the gate runner labeled
`[self-hosted, livespec-orchestrator]` — intentionally runs on
`workflow_dispatch` / `repository_dispatch` and has its own separate exit
tests; keying on `local-ci` (not `self-hosted`) exempts it automatically. Any
self-hosted label other than `local-ci` is out of scope for this check.

Fail-by-default: this is a SECURITY guard, not a style check, so it carries NO
warn-vs-fail severity lever — any finding fails the check (exit 1, error-level
structlog diagnostics). Exit 0 when there is no finding. A repo with no
`local-ci` job anywhere is a genuine no-op (exit 0) — the normal case for every
fleet repo except `livespec`.

Comments are stripped before parsing (see `_self_hosted_routing_parse`): a
comment that merely NAMES a forbidden trigger — such as the self-hosted shadow
lane's `# NEVER ... workflow_dispatch` header — must NOT match. Parsing the
`on:` block structurally rather than grepping raw text is what makes this check
correct where a raw grep was not.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow
through structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at module
import time.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._self_hosted_routing_parse import (  # noqa: E402
    runs_on_values,
    strip_yaml_comments,
    workflow_triggers,
)

__all__: list[str] = []


_WORKFLOWS_DIR = Path(".github") / "workflows"
_WORKFLOW_GLOBS = ("*.yml", "*.yaml")
_LOCAL_CI_LABEL = "local-ci"
_CHECK_ID = "self_hosted_routing"

# The forbidden trigger set: fork-reachable or privileged non-PR events that
# must never reach a `local-ci` self-hosted job. `pull_request` is ABSENT — it
# is ALLOWED (runtime approval gates same-repo fork safety), as are `push`,
# `schedule`, `workflow_call`, and any other trigger outside this set.
_FORBIDDEN_TRIGGERS = frozenset(
    {
        "pull_request_target",
        "workflow_run",
        "issue_comment",
        "repository_dispatch",
        "merge_group",
        "workflow_dispatch",
    }
)


@dataclass(frozen=True, kw_only=True)
class _Finding:
    """One offending workflow: its path plus the forbidden trigger(s) it routes."""

    workflow: str
    forbidden_triggers: tuple[str, ...]


def _iter_workflow_files(*, workflows_dir: Path) -> list[Path]:
    """Return the workflow files under `workflows_dir`, deduped and sorted."""
    files: set[Path] = set()
    for pattern in _WORKFLOW_GLOBS:
        files.update(workflows_dir.glob(pattern))
    return sorted(files)


def _workflow_finding(*, path: Path, cwd: Path) -> _Finding | None:
    """Return a finding when `path` routes a forbidden trigger to a `local-ci` job."""
    stripped = strip_yaml_comments(source=path.read_text(encoding="utf-8"))
    if not any(_LOCAL_CI_LABEL in value for value in runs_on_values(stripped=stripped)):
        return None
    forbidden = tuple(sorted(workflow_triggers(stripped=stripped) & _FORBIDDEN_TRIGGERS))
    if not forbidden:
        return None
    return _Finding(workflow=str(path.relative_to(cwd)), forbidden_triggers=forbidden)


def _collect_findings(*, cwd: Path) -> list[_Finding]:
    """Scan the repo's own workflows for the forbidden-trigger-to-`local-ci` hole."""
    workflows_dir = cwd / _WORKFLOWS_DIR
    if not workflows_dir.is_dir():
        return []
    findings: list[_Finding] = []
    for path in _iter_workflow_files(workflows_dir=workflows_dir):
        finding = _workflow_finding(path=path, cwd=cwd)
        if finding is not None:
            findings.append(finding)
    return findings


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("self_hosted_routing")
    findings = _collect_findings(cwd=Path.cwd())
    for finding in findings:
        log.error(
            "workflow routes a forbidden trigger to a `local-ci` self-hosted job",
            check_id=_CHECK_ID,
            workflow=finding.workflow,
            forbidden_triggers=list(finding.forbidden_triggers),
            local_ci_label=_LOCAL_CI_LABEL,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
