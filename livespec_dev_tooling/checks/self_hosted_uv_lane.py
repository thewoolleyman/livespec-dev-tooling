"""self_hosted_uv_lane — a self-hosted-routing workflow must bound uv's fetch concurrency.

Reliability guard over a repo's OWN `.github/workflows/*.yml` / `*.yaml`. It
reads nothing cross-repo, which is what makes it legal under the
No-Circular-Dependency Directive: the check SHIPS from `livespec-dev-tooling`
and RUNS in each consumer against that consumer's own files, so the upstream
never reads into a downstream. That is resolution 2 of the directive, reached
with no cross-repo read at all.

## The invariant

    A workflow that routes gating jobs to self-hosted capacity through
    `vars.CI_RUNNER_LABELS`, and that invokes uv, MUST declare
    `UV_CONCURRENT_DOWNLOADS` and `UV_HTTP_TIMEOUT` in its top-level `env:`,
    lane-selected against the SAME fallback literal its `runs-on` expressions
    use.

## Why it exists

uv defaults to 50 concurrent downloads per job. Multiplied by the self-hosted
slots sharing one host, that reached ~2500 simultaneous connections from a
single address and produced repeated PyPI fetch timeouts that reddened master
branches. The fix -- capping concurrency and raising the timeout on the
self-hosted lane only -- was authored in one repo and, for a period, PRESENT in
only that repo while nine others ran at the default. Nothing detected the gap;
it surfaced when two master branches went red within an hour.

So the check exists because the previous absence was SILENT. Presence had been
read off the repo the fix was authored in and generalised to a fleet that did
not have it.

## The three steps

1. PRECONDITION. Unless some `runs-on` value references `vars.CI_RUNNER_LABELS`
   AND the workflow invokes uv, this workflow is out of scope: PASS, emit
   nothing. Read from the COMMENT-STRIPPED view, which is load-bearing rather
   than cosmetic -- `livespec-orchestrator-beads-fabro` is hosted-only by
   design and its header comment names the variable while explaining why it
   refuses to route self-hosted. A raw substring precondition flags exactly the
   repo the precondition exists to exempt.
2. PRESENCE. Both variables MUST appear in the top-level `env:` block.
3. LOCKSTEP. Each variable's routing fallback literal MUST match the one the
   `runs-on` expressions use. Step 3 is the part that makes this a real
   lockstep check rather than a presence check a copy-paste carrying a stale
   literal would satisfy vacuously: a workflow whose `env` defaults differently
   from its `runs-on` routes self-hosted while resolving the HOSTED uv values,
   which is the silent no-op failure mode.

The uv-usage marker in step 1 is deliberately independent of the two variables
under test. Gating on the `UV_*` names themselves would mean deleting them also
deletes the precondition, so the check would pass on precisely the regression
it exists to catch.

## Deliberately NOT in scope

This is not a general "every env var must match the fleet's" check. The
invariant is specifically about bounding per-job fetch concurrency against
SHARED host capacity; a general env-lockstep rule would recreate the cross-repo
coupling the directive forbids.

Severity: this guards CI reliability, not security, so unlike its
`self_hosted_routing` sibling it is an ordinary failing check rather than a
fail-by-default security guard. Any finding fails (exit 1); exit 0 when there
is none.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow
through structlog (JSON to stderr).
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
)
from livespec_dev_tooling.checks._self_hosted_uv_lane_parse import (  # noqa: E402
    env_assignments,
    references_variable,
    uses_uv,
    variable_fallback_literal,
)

__all__: list[str] = []


_WORKFLOWS_DIR = Path(".github") / "workflows"
_WORKFLOW_GLOBS = ("*.yml", "*.yaml")
_CHECK_ID = "self_hosted_uv_lane"

# The repo variable through which the fleet routes gating jobs to self-hosted
# capacity. Not consumer-configurable: the invariant is about THIS routing
# mechanism, and a repo routing by some other means is out of scope entirely
# rather than differently configured.
_ROUTING_VARIABLE = "CI_RUNNER_LABELS"

# The two variables that bound uv's behaviour on the shared self-hosted host.
_REQUIRED_VARIABLES = ("UV_CONCURRENT_DOWNLOADS", "UV_HTTP_TIMEOUT")

# The three ways a present variable can still fail the lockstep rule.
_NOT_LANE_SELECTED = "not lane-selected against the routing variable"
_UNRESOLVABLE_LITERAL = "fallback literal is unresolvable"
_LITERAL_MISMATCH = "fallback literal differs from the runs-on fallback"


@dataclass(frozen=True, kw_only=True)
class _MissingFinding:
    """A routed, uv-using workflow omitting one or both required variables."""

    workflow: str
    missing: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class _LockstepFinding:
    """A present variable whose routing fallback does not match `runs-on`."""

    workflow: str
    variable: str
    reason: str
    env_fallback: str
    runs_on_fallbacks: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class _Findings:
    """The two finding kinds, kept in separate typed lists.

    Deliberately NOT one union walked by a `match`, for the reason the
    `self_hosted_routing` sibling records: the kinds carry different payloads,
    neither needs the other's fields, and a union would pull `assert_never` in
    from `typing_extensions`, which this package does not declare.
    """

    missing: tuple[_MissingFinding, ...]
    lockstep: tuple[_LockstepFinding, ...]


def _iter_workflow_files(*, workflows_dir: Path) -> list[Path]:
    """Return the workflow files under `workflows_dir`, deduped and sorted."""
    files: set[Path] = set()
    for pattern in _WORKFLOW_GLOBS:
        files.update(workflows_dir.glob(pattern))
    return sorted(files)


def _routing_fallbacks(*, values: list[str]) -> tuple[str, ...]:
    """Return the distinct fallback literals the `runs-on` expressions route to."""
    literals: set[str] = set()
    for value in values:
        literal = variable_fallback_literal(value=value, variable=_ROUTING_VARIABLE)
        if literal:
            literals.add(literal)
    return tuple(sorted(literals))


def _lockstep_reason(
    *, env_value: str, routing_fallbacks: tuple[str, ...]
) -> tuple[str, str] | None:
    """Return `(reason, env_fallback)` when `env_value` breaks lockstep, else `None`."""
    fallback = variable_fallback_literal(value=env_value, variable=_ROUTING_VARIABLE)
    if fallback is None:
        return (_NOT_LANE_SELECTED, "")
    if not fallback:
        return (_UNRESOLVABLE_LITERAL, "")
    if fallback not in routing_fallbacks:
        return (_LITERAL_MISMATCH, fallback)
    return None


def _workflow_findings(*, path: Path, cwd: Path) -> _Findings:
    """Apply the three steps to a single workflow file."""
    stripped = strip_yaml_comments(source=path.read_text(encoding="utf-8"))
    values = runs_on_values(stripped=stripped)
    routed = any(references_variable(value=value, variable=_ROUTING_VARIABLE) for value in values)
    if not routed or not uses_uv(stripped=stripped):
        return _Findings(missing=(), lockstep=())
    workflow = str(path.relative_to(cwd))
    env = env_assignments(stripped=stripped)
    missing = tuple(name for name in _REQUIRED_VARIABLES if name not in env)
    routing_fallbacks = _routing_fallbacks(values=values)
    lockstep: list[_LockstepFinding] = []
    for name in _REQUIRED_VARIABLES:
        if name in missing:
            continue
        verdict = _lockstep_reason(env_value=env[name], routing_fallbacks=routing_fallbacks)
        if verdict is None:
            continue
        reason, env_fallback = verdict
        lockstep.append(
            _LockstepFinding(
                workflow=workflow,
                variable=name,
                reason=reason,
                env_fallback=env_fallback,
                runs_on_fallbacks=routing_fallbacks,
            )
        )
    missing_findings = (_MissingFinding(workflow=workflow, missing=missing),) if missing else ()
    return _Findings(missing=missing_findings, lockstep=tuple(lockstep))


def _collect_findings(*, cwd: Path) -> _Findings:
    """Scan the repo's own workflows for both holes."""
    workflows_dir = cwd / _WORKFLOWS_DIR
    if not workflows_dir.is_dir():
        return _Findings(missing=(), lockstep=())
    missing: list[_MissingFinding] = []
    lockstep: list[_LockstepFinding] = []
    for path in _iter_workflow_files(workflows_dir=workflows_dir):
        found = _workflow_findings(path=path, cwd=cwd)
        missing.extend(found.missing)
        lockstep.extend(found.lockstep)
    return _Findings(missing=tuple(missing), lockstep=tuple(lockstep))


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("self_hosted_uv_lane")
    cwd = Path.cwd()
    findings = _collect_findings(cwd=cwd)
    for absent in findings.missing:
        log.error(
            "self-hosted-routing workflow must bound uv fetch concurrency",
            check_id=_CHECK_ID,
            workflow=absent.workflow,
            missing=list(absent.missing),
        )
    for broken in findings.lockstep:
        log.error(
            "uv lane variable must match the runs-on routing fallback",
            check_id=_CHECK_ID,
            workflow=broken.workflow,
            variable=broken.variable,
            reason=broken.reason,
            env_fallback=broken.env_fallback,
            runs_on_fallbacks=list(broken.runs_on_fallbacks),
        )
    return 1 if findings.missing or findings.lockstep else 0


if __name__ == "__main__":
    raise SystemExit(main())
