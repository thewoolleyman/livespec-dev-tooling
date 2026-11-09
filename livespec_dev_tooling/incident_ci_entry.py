"""Execute actual CI members through independently authenticated incident policy."""

from __future__ import annotations

import json
import threading
import time
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

# How long one confirmed launch-time recheck is shared by later launches. The
# bound it buys: one observer read pair (/current and /admitted, each up to a
# 45 s reader pass) per window instead of one per member, 8 at a time. What it
# costs is bounded too: a revocation still reaches every launch that starts more
# than one window after it, and `aggregate` rechecks fresh before publishing, so
# a revoked incident can never publish a passing aggregate.
_ADMISSION_WINDOW_SECONDS = 30.0


class _SharedAdmission:
    """A fail-closed launch-time recheck whose confirmed result later launches share.

    The lock makes concurrent launches wait for ONE read rather than each
    starting their own. One retry absorbs a single transient refusal; two
    refusals in a row refuse.
    """

    def __init__(self, *, check: Callable[[], bool], window_seconds: float) -> None:
        self._check = check
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._confirmed_at: float | None = None

    def __call__(self) -> bool:
        with self._lock:
            confirmed = self._confirmed_at
            if confirmed is not None and time.monotonic() - confirmed < self._window_seconds:
                return True
            admitted = self._check() or self._check()
            self._confirmed_at = time.monotonic() if admitted else None
            return admitted


# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
@dataclass(frozen=True, kw_only=True)
class CiEntry:
    """Bind each invocation and result to independently authenticated current policy."""

    repo: Path
    targets: tuple[CiTarget, ...]
    current: Callable[..., bool] | None = None
    observer: Callable[..., bool] | None = None
    admission_window_seconds: float = _ADMISSION_WINDOW_SECONDS

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
        producer/consumer ordering. The plan is rechecked before anything
        launches and again before each member launches, through one
        `_SharedAdmission`; a refused recheck launches nothing further and
        returns 2, after recording the honest outcome of every member that did
        run. No deadline is passed: a selected CI member is required evidence,
        and the aggregate has no deferral for one that was cut short, so the
        job's own timeout bounds it. Each member's captured output is handed to
        `echo` as that member completes, so a job killed by its timeout still
        logs every member that finished.
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

        admit = _SharedAdmission(
            check=lambda: self.plan(event=plan.event, payload=payload, environ=environ) == plan,
            window_seconds=self.admission_window_seconds,
        )
        if not admit():
            return 2

        def echo_completed(*, outcome: TargetOutcome) -> None:
            code = _member_code(outcome=outcome)
            if echo is not None and code is not None:
                echo(text=f"::: just {outcome.name} [exit {code}]\n{outcome.output}")

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
                on_complete=echo_completed,
            )
        failure, stopped = 0, False
        for outcome in outcomes:
            code = _member_code(outcome=outcome)
            if code is None:
                stopped = True
                continue
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
