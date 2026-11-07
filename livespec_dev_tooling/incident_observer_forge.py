"""Bind a retained arm to its real merge and normal master run through the forge."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

from livespec_dev_tooling._incident_observer_types import ObserverArm, ObserverRegistration
from livespec_dev_tooling.incident_forge_reads import ForgeRead

__all__: list[str] = ["MergedRunVerifier"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-x3wwwc


@dataclass(frozen=True, kw_only=True)
class MergedRunVerifier:
    """Use independently provisioned forge access, never the tenant wrapper.

    These read-only API calls authenticate merge/run association. Constructing
    the complete landed inverse remains the recovery principal's separate task;
    this verifier does not claim the terminal SHA is the whole rollback unit.
    """

    read: ForgeRead
    workflow_path: str = ".github/workflows/ci.yml"
    target_branch: str = "master"

    def __call__(self, arm: ObserverArm, registration: ObserverRegistration) -> bool:
        if re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", arm.repository
        ) is None or arm.repository.split("/", maxsplit=1)[-1] in {".", ".."}:
            return False
        if registration.run_id <= 0 or registration.branch != self.target_branch:
            return False
        pr = _api_record(read=self.read, path=f"repos/{arm.repository}/pulls/{arm.pr_number}")
        run = _api_record(
            read=self.read,
            path=f"repos/{arm.repository}/actions/runs/{registration.run_id}",
        )
        if pr is None or run is None:
            return False
        return _matches_pr(
            pr=pr, arm=arm, registration=registration, branch=self.target_branch
        ) and _matches_run(
            run=run,
            registration=registration,
            workflow=self.workflow_path,
        )


def _api_record(*, read: ForgeRead, path: str) -> dict[str, object] | None:
    record = read(path)
    return cast("dict[str, object]", record) if isinstance(record, dict) else None


def _matches_pr(
    *,
    pr: dict[str, object],
    arm: ObserverArm,
    registration: ObserverRegistration,
    branch: str,
) -> bool:
    head, base = pr.get("head"), pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        return False
    head, base = cast("dict[str, object]", head), cast("dict[str, object]", base)
    repo = base.get("repo")
    return (
        type(pr.get("number")) is int
        and pr.get("number") == arm.pr_number
        and pr.get("merged") is True
        and pr.get("state") == "closed"
        and pr.get("merge_commit_sha") == registration.head_sha
        and head.get("sha") == arm.head_sha
        and base.get("ref") == branch
        and isinstance(repo, dict)
        and cast("dict[str, object]", repo).get("full_name") == arm.repository
    )


def _matches_run(
    *,
    run: dict[str, object],
    registration: ObserverRegistration,
    workflow: str,
) -> bool:
    repo, source = run.get("repository"), run.get("head_repository")
    return (
        type(run.get("id")) is int
        and run.get("id") == registration.run_id
        and run.get("event") == "push"
        and run.get("head_branch") == registration.branch
        and run.get("head_sha") == registration.head_sha
        and run.get("path") == workflow
        and isinstance(repo, dict)
        and cast("dict[str, object]", repo).get("full_name") == registration.repository
        and isinstance(source, dict)
        and cast("dict[str, object]", source).get("full_name") == registration.repository
    )
