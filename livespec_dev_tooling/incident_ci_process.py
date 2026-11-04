"""Actual CI plan/run/aggregate process for an independently approved release."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from livespec_dev_tooling.incident_ci_entry import CiEntry
from livespec_dev_tooling.incident_ci_event import observe_event
from livespec_dev_tooling.incident_ci_inventory import load_inventory
from livespec_dev_tooling.incident_ci_payload import decode_outcome, strict_json
from livespec_dev_tooling.incident_ci_policy import CiOutcome
from livespec_dev_tooling.incident_transport import normal_child_environment

__all__: list[str] = ["CiProcess", "main"]


# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
_MAX_ROWS = 4096
_MAX_REPORT = 1048576


class CiProcess:
    """A process boundary over packaged inventory and authenticated fresh events."""

    @staticmethod
    def outcomes(*, directory: Path) -> tuple[CiOutcome, ...]:
        rows: list[CiOutcome] = []
        for path in sorted(directory.rglob("*.jsonl")):
            if path.is_symlink() or len(rows) >= _MAX_ROWS:
                message = "invalid incident CI report inventory"
                raise ValueError(message)
            raw = path.read_text()
            if len(raw.encode()) > _MAX_REPORT:
                message = "oversized incident CI report"
                raise ValueError(message)
            rows.extend(decode_outcome(value=strict_json(text=line)) for line in raw.splitlines())
        if len(rows) > _MAX_ROWS:
            message = "too many incident CI outcomes"
            raise ValueError(message)
        return tuple(rows)

    @staticmethod
    def run(*, args: argparse.Namespace) -> int:
        environment = dict(os.environ)
        if environment.get("GITHUB_EVENT_NAME") == "push":
            environment = normal_child_environment(environ=environment)
        observed = observe_event(environ=environment)
        if observed is None:
            return _emit(
                result={
                    "status": "refused",
                    "reason": "current PR/head/mode could not be authenticated",
                },
                code=2,
            )
        event, payload = observed
        entry = CiEntry(repo=args.repo, targets=load_inventory())
        plan = entry.plan(event=event, payload=payload, environ=environment)
        if plan is None:
            return _emit(
                result={
                    "status": "refused",
                    "reason": "fresh current authority and independent admission required",
                },
                code=2,
            )
        selected = tuple(target.name for target in plan.selected)
        jobs = sorted({target.batch for target in plan.selected})
        projection = {
            "mode": plan.mode,
            "scope": plan.scope,
            "selected": selected,
            "deferred": [asdict(item) for item in plan.deferred],
            "jobs": jobs,
        }
        if args.operation == "plan":
            if "GITHUB_OUTPUT" in environment:
                with Path(environment["GITHUB_OUTPUT"]).open("a") as stream:
                    for name, value in {
                        "mode": plan.mode,
                        "scope": plan.scope,
                        "jobs": json.dumps(jobs),
                        "selected": json.dumps(selected),
                    }.items():
                        _ = stream.write(name + "=" + value + "\n")
            return _emit(result={"status": "planned", **projection}, code=0)
        if args.operation == "run":
            code = entry.execute(
                plan=plan,
                names=tuple(args.target),
                report=args.report,
                payload=payload,
                environ=environment,
            )
            return _emit(
                result={"status": "executed" if code == 0 else "failed", **projection}, code=code
            )
        result = entry.aggregate(
            event=event,
            payload=payload,
            environ=environment,
            outcomes=CiProcess.outcomes(directory=args.reports),
        )
        return _emit(result=result, code=0 if result["status"] == "passed" else 1)


def _emit(*, result: dict[str, Any], code: int) -> int:
    _ = sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    if "GITHUB_STEP_SUMMARY" in os.environ:
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
            _ = stream.write("```json\n" + json.dumps(result, sort_keys=True, indent=2) + "\n```\n")
    return code


def main(*, argv: list[str] | None = None) -> int:
    """Preserve actual member exits and name configuration refusals without secrets."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("operation", choices=("plan", "run", "aggregate"))
    _ = parser.add_argument("--repo", type=Path, default=Path.cwd())
    _ = parser.add_argument("--report", type=Path, default=Path("tmp/incident-ci/outcomes.jsonl"))
    _ = parser.add_argument("--reports", type=Path, default=Path("tmp/incident-ci"))
    _ = parser.add_argument("--target", action="append", default=[])
    try:
        return CiProcess.run(args=parser.parse_args(argv))
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return _emit(
            result={
                "status": "refused",
                "reason": "unavailable or invalid inventory, event or outcome",
            },
            code=2,
        )


if __name__ == "__main__":
    raise SystemExit(main())
