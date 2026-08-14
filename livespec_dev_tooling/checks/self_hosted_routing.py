"""self_hosted_routing — self-hosted CI routing must not be reachable, or fail open.

Security guard for the livespec fleet's self-hosted CI capacity. Because the
fleet repos are PUBLIC, a workflow that lets a fork-reachable or privileged
non-PR event reach a gating self-hosted job is a code-execution hole. Reading
ONLY a repo's own `.github/workflows/*.yml` and `*.yaml`, this check asserts two
independent properties per workflow file:

    1. REACHABILITY. If any job's `runs-on` references a GATING self-hosted
       label, or calls the shared CI runner router that can emit one, the
       workflow's `on:` trigger set MUST NOT contain any FORBIDDEN trigger.
    2. FAIL-CLOSED ROUTING. If a `runs-on` resolves through a repo variable
       with a fallback (`vars.X || <fallback>`), that fallback MUST NOT name
       self-hosted capacity — deleting or emptying the variable would
       otherwise route the merge gate to a runner that may not exist, and the
       gate would wait on a check that never arrives.

FORBIDDEN triggers (exactly these six): `pull_request_target`, `workflow_run`,
`issue_comment`, `repository_dispatch`, `merge_group`, `workflow_dispatch`.
`pull_request` is ALLOWED — same-repo fork safety is handled at runtime by the
repo's approval gate, not statically; `push`, `schedule`, `workflow_call`, and
any other non-forbidden trigger are likewise never flagged.

The GATING LABEL SET is consumer-declared. `local-ci` is this check's built-in
default, and a consumer adds its own dedicated labels through the
`gating_self_hosted_labels` key of its `[tool.livespec_dev_tooling]` block. The
declared labels are UNIONED with the default, never substituted for it: a
security guard must not be able to lose coverage through configuration. Keying
on a declared SET rather than the single literal `local-ci` is what closes the
blind spot a repo used to open the moment it adopted a dedicated runner label —
the guard silently stopped covering exactly the jobs it governs, and reported
green while doing so.

The fleet's deliberately-privileged tier — the gate runner labeled
`[self-hosted, livespec-orchestrator]` — intentionally runs on
`workflow_dispatch` / `repository_dispatch` and has its own separate exit
tests. It is absent from the default set, so it stays out of scope unless a
consumer explicitly nominates it.

Fail-by-default: this is a SECURITY guard, not a style check, so it carries NO
warn-vs-fail severity lever — any finding fails the check (exit 1, error-level
structlog diagnostics). Exit 0 when there is no finding. A repo with no gating
self-hosted job and no self-hosted fallback is a genuine no-op (exit 0).

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
    fail_open_reason,
    runs_on_values,
    strip_yaml_comments,
    workflow_triggers,
)
from livespec_dev_tooling.config import load_config  # noqa: E402

__all__: list[str] = []


_WORKFLOWS_DIR = Path(".github") / "workflows"
_WORKFLOW_GLOBS = ("*.yml", "*.yaml")
_CHECK_ID = "self_hosted_routing"
_CI_RUNNER_ROUTER_WORKFLOW = "reusable-ci-runner-router.yml"

# The built-in gating label. A consumer's `gating_self_hosted_labels` adds to
# this set rather than replacing it, so adopting a new dedicated label cannot
# drop the coverage this default already provides.
_DEFAULT_GATING_LABELS = frozenset({"local-ci"})

# GitHub's generic self-hosted marker. Every self-hosted `runs-on` carries it
# alongside its specific label, so a fallback naming it routes to self-hosted
# capacity whatever the specific label happens to be.
_BARE_SELF_HOSTED_LABEL = "self-hosted"

# The forbidden trigger set: fork-reachable or privileged non-PR events that
# must never reach a gating self-hosted job. `pull_request` is ABSENT — it
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
class _TriggerFinding:
    """A workflow routing a forbidden trigger to a gating self-hosted job."""

    workflow: str
    forbidden_triggers: tuple[str, ...]
    gating_labels: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class _FailOpenFinding:
    """A `runs-on` whose repo-variable fallback does not name hosted capacity."""

    workflow: str
    runs_on: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class _Findings:
    """The two finding kinds, kept in separate typed lists.

    Deliberately NOT one union walked by a `match`: the two kinds carry
    different payloads and neither needs the other's fields, and a union here
    would pull `assert_never` in from `typing_extensions`, which this package
    does not declare as a dependency.
    """

    triggers: tuple[_TriggerFinding, ...]
    fail_opens: tuple[_FailOpenFinding, ...]


def _iter_workflow_files(*, workflows_dir: Path) -> list[Path]:
    """Return the workflow files under `workflows_dir`, deduped and sorted."""
    files: set[Path] = set()
    for pattern in _WORKFLOW_GLOBS:
        files.update(workflows_dir.glob(pattern))
    return sorted(files)


def _referenced_gating_labels(
    *, values: list[str], gating_labels: frozenset[str]
) -> tuple[str, ...]:
    """Return the gating labels any `runs-on` value in the workflow references."""
    return tuple(
        sorted(label for label in gating_labels if any(label in value for value in values))
    )


def _references_ci_runner_router(*, stripped: str) -> bool:
    """Return whether this workflow can delegate ordinary CI to the shared router.

    The router's selected `runs-on` value is a job output, so it intentionally
    contains no literal self-hosted label for this check's existing parser to
    see. Treating the router call itself as a gating route preserves the
    forbidden-trigger invariant across that indirection.
    """
    return _CI_RUNNER_ROUTER_WORKFLOW in stripped


def _trigger_finding(
    *, path: Path, cwd: Path, stripped: str, values: list[str], gating_labels: frozenset[str]
) -> _TriggerFinding | None:
    """Return a finding when this workflow routes a forbidden trigger to a gating job."""
    referenced = _referenced_gating_labels(values=values, gating_labels=gating_labels)
    if _references_ci_runner_router(stripped=stripped):
        referenced = tuple(sorted((*referenced, "ci-runner-router")))
    if not referenced:
        return None
    forbidden = tuple(sorted(workflow_triggers(stripped=stripped) & _FORBIDDEN_TRIGGERS))
    if not forbidden:
        return None
    return _TriggerFinding(
        workflow=str(path.relative_to(cwd)),
        forbidden_triggers=forbidden,
        gating_labels=referenced,
    )


def _fail_open_findings(
    *, path: Path, cwd: Path, values: list[str], self_hosted_labels: frozenset[str]
) -> list[_FailOpenFinding]:
    """Return one finding per DISTINCT `runs-on` value that routes fail-open.

    Deduped by value: livespec's `ci.yml` repeats one `runs-on` expression
    across its matrices, and reporting the identical defect once per job would
    bury the single edit that fixes them all.
    """
    findings: list[_FailOpenFinding] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        reason = fail_open_reason(value=value, self_hosted_labels=self_hosted_labels)
        if reason is None:
            continue
        findings.append(
            _FailOpenFinding(workflow=str(path.relative_to(cwd)), runs_on=value, reason=reason)
        )
    return findings


def _collect_findings(*, cwd: Path, gating_labels: frozenset[str]) -> _Findings:
    """Scan the repo's own workflows for both holes."""
    workflows_dir = cwd / _WORKFLOWS_DIR
    if not workflows_dir.is_dir():
        return _Findings(triggers=(), fail_opens=())
    self_hosted_labels = gating_labels | {_BARE_SELF_HOSTED_LABEL}
    triggers: list[_TriggerFinding] = []
    fail_opens: list[_FailOpenFinding] = []
    for path in _iter_workflow_files(workflows_dir=workflows_dir):
        stripped = strip_yaml_comments(source=path.read_text(encoding="utf-8"))
        values = runs_on_values(stripped=stripped)
        trigger = _trigger_finding(
            path=path, cwd=cwd, stripped=stripped, values=values, gating_labels=gating_labels
        )
        if trigger is not None:
            triggers.append(trigger)
        fail_opens.extend(
            _fail_open_findings(
                path=path, cwd=cwd, values=values, self_hosted_labels=self_hosted_labels
            )
        )
    return _Findings(triggers=tuple(triggers), fail_opens=tuple(fail_opens))


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
    cwd = Path.cwd()
    gating_labels = _DEFAULT_GATING_LABELS | frozenset(
        load_config(repo_root=cwd).gating_self_hosted_labels
    )
    findings = _collect_findings(cwd=cwd, gating_labels=gating_labels)
    for trigger in findings.triggers:
        log.error(
            "workflow routes a forbidden trigger to a gating self-hosted job",
            check_id=_CHECK_ID,
            workflow=trigger.workflow,
            forbidden_triggers=list(trigger.forbidden_triggers),
            gating_labels=list(trigger.gating_labels),
        )
    for fail_open in findings.fail_opens:
        log.error(
            "runs-on fallback must name hosted capacity, not self-hosted",
            check_id=_CHECK_ID,
            workflow=fail_open.workflow,
            runs_on=fail_open.runs_on,
            reason=fail_open.reason,
        )
    return 1 if findings.triggers or findings.fail_opens else 0


if __name__ == "__main__":
    raise SystemExit(main())
