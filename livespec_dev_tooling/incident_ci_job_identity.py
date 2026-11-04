"""Correlate a signed check to the exact independently observed PR run attempt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_dev_tooling._incident_ci_identity_json import identity_json
from livespec_dev_tooling._incident_observer_types import ObserverArmQuery
from livespec_dev_tooling.budgeted_gh import gh_read, github_api_url
from livespec_dev_tooling.incident_ci_oidc import OidcIdentity

_GITHUB_ACTIONS_APP = 15368
_PAGE_SIZE = 100
_MAX_JOBS = 1000

__all__: list[str] = ["CiJobIdentity", "CiJobVerifier"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb


@dataclass(frozen=True, kw_only=True)
class CiJobIdentity:
    """The Actions job is resolved through its canonical signed check-run URL."""

    job_id: int
    check_suite_id: int


@dataclass(frozen=True, kw_only=True)
class CiJobVerifier:
    """Reads use the controller account's independent budgeted forge credential."""

    identity: OidcIdentity
    query: ObserverArmQuery

    def verify(self) -> CiJobIdentity | None:
        identity, query = self.identity, self.query
        if identity.repository != query.repository or identity.pr_number != query.pr_number:
            return None
        root = f"repos/{identity.repository}"
        run_path = f"{root}/actions/runs/{identity.run_id}"
        suite = self._initial(root=root, run_path=run_path)
        if suite is None:
            return None
        jobs = _jobs(path=f"{run_path}/attempts/{identity.run_attempt}/jobs")
        if jobs is None:
            return None
        url = github_api_url(path=f"{root}/check-runs/{identity.check_run_id}")
        matched = [v for v in jobs if v.get("check_run_url") == url]
        check = _record(path=f"{root}/check-runs/{identity.check_run_id}")
        if (
            len(matched) != 1
            or not self._job(job=matched[0])
            or not self._check(check=check, suite=suite)
        ):
            return None
        latest, final_pr = _record(path=run_path), _record(path=f"{root}/pulls/{query.pr_number}")
        if (
            not self._run(run=latest)
            or type(latest.get("check_suite_id")) is not int
            or latest.get("check_suite_id") != suite
            or not self._pr(pr=final_pr)
        ):
            return None
        return CiJobIdentity(job_id=matched[0]["id"], check_suite_id=suite)

    def _initial(self, *, root: str, run_path: str) -> int | None:
        identity = self.identity
        run = _record(path=run_path)
        attempt = _record(path=f"{run_path}/attempts/{identity.run_attempt}")
        pr = _record(path=f"{root}/pulls/{self.query.pr_number}")
        merge = _record(path=f"{root}/git/commits/{identity.merge_sha}")
        suite = run.get("check_suite_id")
        parents = _objects(value=merge.get("parents"))
        valid = (
            self._run(run=run)
            and self._run(run=attempt)
            and self._pr(pr=pr)
            and _positive(value=suite)
            and type(attempt.get("check_suite_id")) is int
            and attempt.get("check_suite_id") == suite
            and merge.get("sha") == identity.merge_sha
            and parents is not None
            and [v.get("sha") for v in parents] == [self.query.base_sha, self.query.head_sha]
        )
        return cast("int", suite) if valid else None

    def _repo(self, *, value: Any) -> bool:
        identity = self.identity
        repo = _object(value=value)
        owner = _object(value=repo.get("owner"))
        return (
            repo.get("full_name") == identity.repository
            and type(repo.get("id")) is int
            and repo.get("id") == identity.repository_id
            and type(owner.get("id")) is int
            and owner.get("id") == identity.repository_owner_id
        )

    def _run(self, *, run: dict[str, Any]) -> bool:
        identity = self.identity
        caller = identity.caller_workflow_ref.split("@", maxsplit=1)[0].removeprefix(
            identity.repository + "/"
        )
        return (
            type(run.get("id")) is int
            and run.get("id") == identity.run_id
            and type(run.get("run_attempt")) is int
            and run.get("run_attempt") == identity.run_attempt
            and run.get("event") == "pull_request"
            and run.get("head_sha") == self.query.head_sha
            and run.get("head_branch") == identity.head_ref
            and run.get("path") == caller
            and self._repo(value=run.get("repository"))
        )

    def _pr(self, *, pr: dict[str, Any]) -> bool:
        base, head = _object(value=pr.get("base")), _object(value=pr.get("head"))
        return (
            type(pr.get("number")) is int
            and pr.get("number") == self.query.pr_number
            and pr.get("state") == "open"
            and pr.get("merged") is False
            and pr.get("merge_commit_sha") == self.identity.merge_sha
            and base.get("sha") == self.query.base_sha
            and head.get("sha") == self.query.head_sha
            and base.get("ref") == self.identity.base_ref
            and head.get("ref") == self.identity.head_ref
            and self._repo(value=base.get("repo"))
        )

    def _job(self, *, job: dict[str, Any]) -> bool:
        return (
            _positive(value=job.get("id"))
            and type(job.get("run_id")) is int
            and job.get("run_id") == self.identity.run_id
            and job.get("head_sha") == self.query.head_sha
        )

    def _check(self, *, check: dict[str, Any], suite: int) -> bool:
        app, observed = _object(value=check.get("app")), _object(value=check.get("check_suite"))
        return (
            type(check.get("id")) is int
            and check.get("id") == self.identity.check_run_id
            and check.get("head_sha") == self.query.head_sha
            and type(app.get("id")) is int
            and app.get("id") == _GITHUB_ACTIONS_APP
            and app.get("slug") == "github-actions"
            and type(observed.get("id")) is int
            and observed.get("id") == suite
        )


def _positive(*, value: Any) -> bool:
    return type(value) is int and value > 0


def _record(*, path: str) -> dict[str, Any]:
    try:
        result = gh_read(args=["api", path], timeout=10)
        return (
            identity_json(raw=result.stdout.encode(), limit=1048576)
            if result.returncode == 0
            else {}
        )
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        return {}


def _jobs(*, path: str) -> list[dict[str, Any]] | None:
    result: list[dict[str, Any]] = []
    total: int | None = None
    for page in range(1, 11):
        data = _record(path=f"{path}?per_page=100&page={page}")
        count, rows = data.get("total_count"), _objects(value=data.get("jobs"))
        if not _positive(value=count):
            return None
        count = cast("int", count)
        if (
            count > _MAX_JOBS
            or rows is None
            or not 0 < len(rows) <= _PAGE_SIZE
            or (total is not None and count != total)
        ):
            return None
        total = count
        result.extend(rows)
        if len(result) >= count:
            break
    ids = [v.get("id") for v in result]
    if (
        len(result) != total
        or any(not _positive(value=v) for v in ids)
        or len(set(ids)) != len(ids)
    ):
        return None
    final = _record(path=f"{path}?per_page=100&page=1")
    return (
        result
        if type(final.get("total_count")) is int and final.get("total_count") == total
        else None
    )


def _object(*, value: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _objects(*, value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    rows = cast("list[Any]", value)
    return cast("list[dict[str, Any]]", rows) if all(isinstance(v, dict) for v in rows) else None
