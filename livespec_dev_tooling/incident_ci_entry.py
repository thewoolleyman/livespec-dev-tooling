"""Execute actual CI members through independently authenticated incident policy."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from livespec_dev_tooling._check_target_runner import (
    BLOCKED,
    LAUNCH_FAILED,
    TargetOutcome,
    TargetRun,
    cap_workers,
    run_targets,
)
from livespec_dev_tooling._dispatcher_coverage_namespaces import (
    COVERAGE_CONSUMERS,
    isolated_environments,
)
from livespec_dev_tooling.allowed_cpus import current_allowed_cpu_count
from livespec_dev_tooling.incident_ci_authority import CiAuthorityBoundary
from livespec_dev_tooling.incident_ci_payload import decode_authority, decode_outcome, query_for
from livespec_dev_tooling.incident_ci_policy import (
    CiEvent,
    CiOutcome,
    CiPlan,
    CiTarget,
    CiTrust,
    aggregate_ci_results,
    select_ci_plan,
)
from livespec_dev_tooling.incident_execution import IncidentConfigurationRefusal
from livespec_dev_tooling.incident_transport import normal_child_environment

__all__: list[str] = ["CiEntry"]


# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
@dataclass(frozen=True, kw_only=True)
class CiEntry:
    """Bind each invocation and result to independently authenticated current policy."""

    repo: Path
    targets: tuple[CiTarget, ...]
    current: Callable[..., bool] | None = None
    observer: Callable[..., bool] | None = None

    def plan(self, *, event: CiEvent, payload: str, environ: Mapping[str, str]) -> CiPlan | None:
        # Resolve normal/master BEFORE payload or observer configuration access.
        normal = event.kind != "pull_request" or "expedited-incident-response" not in event.labels
        authority = None if normal else decode_authority(payload=payload)
        if not normal and authority is None:
            return None
        trust = CiTrust(current=lambda _: False, observer=lambda _authority, _event: False)
        if authority is not None:
            boundary = CiAuthorityBoundary(
                observer_url=environ.get("LIVESPEC_INCIDENT_OBSERVER_URL", ""),
                observer_token=environ.get("LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN", ""),
            )
            current, observer = self.current or boundary.current, self.observer or boundary.admitted
            query = query_for(authority=authority)
            trust = CiTrust(
                current=lambda _: current(query=query),
                observer=lambda _authority, _event: observer(query=query),
            )
        result = select_ci_plan(
            event=event,
            targets=self.targets,
            authority=authority,
            trust=trust,
            environ=normal_child_environment(environ=environ) if normal else environ,
        )
        return result if isinstance(result, CiPlan) else None

    def execute(
        self,
        *,
        plan: CiPlan,
        names: tuple[str, ...],
        report: Path,
        payload: str,
        environ: Mapping[str, str],
        echo: Callable[..., None] | None = None,
    ) -> int:
        """Recheck before each real member; no unknown or duplicate command can run.

        Members run through the normal aggregate's own runner, in parallel and
        under its process semantics, coverage-namespace isolation and
        producer/consumer ordering. The plan is rechecked once before anything
        launches and again by `admit` immediately before EACH member launches; a
        failed recheck launches nothing further and returns 2, after recording
        the honest outcome of every member that did run. No deadline is
        passed: a selected CI member is required evidence, and the aggregate has
        no deferral for one that was cut short, so the job's own timeout bounds it.
        Each member's captured output is handed to `echo` for the job log.
        """
        known = {target.name for target in self.targets}
        if not names or len(set(names)) != len(names) or any(name not in known for name in names):
            return 2
        selected = {target.name for target in plan.selected}
        environment = {
            key: value
            for key, value in normal_child_environment(environ=dict(plan.environment)).items()
            if not key.startswith("LIVESPEC_INCIDENT_")
        }
        report.parent.mkdir(parents=True, exist_ok=True)

        def admit() -> bool:
            return self.plan(event=plan.event, payload=payload, environ=environ) == plan

        if not admit():
            return 2
        members = [name for name in names if name in selected]
        with isolated_environments(names=members, base=environment) as environments:
            outcomes = run_targets(
                runs=[
                    TargetRun(
                        name=name,
                        argv=("just", name),
                        env=environments[name],
                        after=COVERAGE_CONSUMERS.get(name),
                    )
                    for name in members
                ],
                cwd=self.repo,
                max_workers=cap_workers(requested=None, allowed=current_allowed_cpu_count()),
                admit=admit,
            )
        failure, stopped = 0, False
        for outcome in outcomes:
            code = _member_code(outcome=outcome)
            if code is None:
                stopped = True
                continue
            if echo is not None:
                echo(text=f"::: just {outcome.name} [exit {code}]\n{outcome.output}")
            row = CiOutcome(
                name=outcome.name,
                head_sha=plan.event.head_sha,
                scope=plan.scope,
                outcome="passed" if code == 0 else "failed",
            )
            with report.open("a") as stream:
                _ = stream.write(json.dumps(asdict(row), sort_keys=True) + "\n")
            failure = failure or code
        return 2 if stopped else failure

    def aggregate(
        self,
        *,
        event: CiEvent,
        payload: str,
        environ: Mapping[str, str],
        outcomes: tuple[CiOutcome, ...],
    ) -> dict[str, Any]:
        """Re-read canonical current AND admission at actual aggregate publication."""
        plan = self.plan(event=event, payload=payload, environ=environ)
        if plan is None:
            return {"status": "refused", "reason": "current authority or admission unavailable"}
        try:
            outcomes = tuple(decode_outcome(value=asdict(outcome)) for outcome in outcomes)
        except (ValueError, TypeError):
            return {"status": "refused", "reason": "invalid incident CI outcome"}
        result = aggregate_ci_results(
            plan=plan,
            current_event=event,
            outcomes=outcomes,
            targets=self.targets,
            observer_arm_admitted=lambda _authority, _event: self.plan(
                event=event, payload=payload, environ=environ
            )
            == plan,
        )
        if isinstance(result, IncidentConfigurationRefusal):
            return {"status": "refused", "reason": result.detail}
        return {"status": "passed" if result.successful else "failed", **asdict(result)}


def _member_code(*, outcome: TargetOutcome) -> int | None:
    """A member's shell-style exit status, or None when a recheck stopped it.

    A consumer whose producer did not pass never ran, so it is a failure, as the
    normal aggregate reports it; it can never satisfy the aggregate.
    """
    if outcome.status == LAUNCH_FAILED:
        return 127
    if outcome.status == BLOCKED:
        return 1
    if outcome.returncode is None:
        return None
    return outcome.returncode if outcome.returncode >= 0 else 128 - outcome.returncode
