"""Execute actual CI members through independently authenticated incident policy."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
    ) -> int:
        """Recheck before each real member; no unknown or duplicate command can run."""
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
        failure = 0
        for name in names:
            current = self.plan(event=plan.event, payload=payload, environ=environ)
            if current is None or current != plan:
                return 2
            if name not in selected:
                continue
            try:
                done = subprocess.run(  # noqa: S603 — exact released member; no shell command.
                    ["just", name],  # noqa: S607 — declared repository toolchain executable.
                    cwd=self.repo,
                    env=environment,
                    check=False,
                )
                code = done.returncode if done.returncode >= 0 else 128 - done.returncode
            except OSError:
                code = 127
            outcome = CiOutcome(
                name=name,
                head_sha=plan.event.head_sha,
                scope=plan.scope,
                outcome="passed" if code == 0 else "failed",
            )
            with report.open("a") as stream:
                _ = stream.write(json.dumps(asdict(outcome), sort_keys=True) + "\n")
            failure = failure or code
        return failure

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
