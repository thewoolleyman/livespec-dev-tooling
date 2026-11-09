"""Correlate a signed check to the exact independently observed PR run attempt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_dev_tooling._incident_observer_types import ObserverArmQuery
from livespec_dev_tooling.budgeted_gh import github_api_url
from livespec_dev_tooling.incident_ci_oidc import OidcIdentity
from livespec_dev_tooling.incident_forge_reads import ForgeRead

_GITHUB_ACTIONS_APP = 15368
_PAGE_SIZE = 100
_MAX_JOBS = 1000
_MAX_PAGES = _MAX_JOBS // _PAGE_SIZE

__all__: list[str] = [
    "CiJobIdentity",
    "CiJobVerifier",
    "attempt_jobs",
    "forge_object",
    "forge_record",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-rqhqnb
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-x3wwwc


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
    read: ForgeRead

    def verify(self) -> CiJobIdentity | None:
        identity, query = self.identity, self.query
        if identity.repository != query.repository or identity.pr_number != query.pr_number:
            return None
        root = f"repos/{identity.repository}"
        run_path = f"{root}/actions/runs/{identity.run_id}"
        suite = self._initial(root=root, run_path=run_path)
        if suite is None:
            return None
        read = self.read
        jobs = attempt_jobs(read=read, path=f"{run_path}/attempts/{identity.run_attempt}/jobs")
        if jobs is None:
            return None
        url = github_api_url(path=f"{root}/check-runs/{identity.check_run_id}")
        matched = [v for v in jobs if v.get("check_run_url") == url]
        check = forge_record(read=read, path=f"{root}/check-runs/{identity.check_run_id}")
        if (
            len(matched) != 1
            or not self._job(job=matched[0])
            or not self._check(check=check, suite=suite)
        ):
            return None
        latest, final_pr = (
            forge_record(read=read, path=run_path),
            forge_record(read=read, path=f"{root}/pulls/{query.pr_number}"),
        )
        if (
            not self._run(run=latest)
            or type(latest.get("check_suite_id")) is not int
            or latest.get("check_suite_id") != suite
            or not self._pr(pr=final_pr)
        ):
            return None
        return CiJobIdentity(job_id=matched[0]["id"], check_suite_id=suite)

    def _initial(self, *, root: str, run_path: str) -> int | None:
        identity, read = self.identity, self.read
        run = forge_record(read=read, path=run_path)
        attempt = forge_record(read=read, path=f"{run_path}/attempts/{identity.run_attempt}")
        pr = forge_record(read=read, path=f"{root}/pulls/{self.query.pr_number}")
        merge = forge_record(read=read, path=f"{root}/git/commits/{identity.merge_sha}")
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
        repo = forge_object(value=value)
        owner = forge_object(value=repo.get("owner"))
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
        base, head = forge_object(value=pr.get("base")), forge_object(value=pr.get("head"))
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
        app, observed = (
            forge_object(value=check.get("app")),
            forge_object(value=check.get("check_suite")),
        )
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


def forge_record(*, read: ForgeRead, path: str) -> dict[str, Any]:
    """One budgeted controller-account read; any failure is an empty observation."""
    return forge_object(value=read(path))


def attempt_jobs(*, read: ForgeRead, path: str) -> list[dict[str, Any]] | None:
    """Complete bounded pages of one exact attempt, or unavailable.

    The one pager every reader of a run attempt's jobs shares: one page cap, one
    empty-listing rule (a total of zero with no rows is a complete empty listing),
    one duplicate-job-id check and one re-read of the total after the last page.
    """
    result: list[dict[str, Any]] = []
    total: int | None = None
    for page in range(1, _MAX_PAGES + 1):
        data = forge_record(read=read, path=f"{path}?per_page=100&page={page}")
        count, rows = data.get("total_count"), _objects(value=data.get("jobs"))
        if type(count) is not int or count < 0:
            return None
        if (
            count > _MAX_JOBS
            or rows is None
            or len(rows) > _PAGE_SIZE
            or (count > 0 and not rows)
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
    final = forge_record(read=read, path=f"{path}?per_page=100&page=1")
    return (
        result
        if type(final.get("total_count")) is int and final.get("total_count") == total
        else None
    )


def forge_object(*, value: Any) -> dict[str, Any]:
    """A JSON object, or empty for any other shape."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _objects(*, value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    rows = cast("list[Any]", value)
    return cast("list[dict[str, Any]]", rows) if all(isinstance(v, dict) for v in rows) else None
