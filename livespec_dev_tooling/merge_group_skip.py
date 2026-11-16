"""merge_group_skip — may this merge group skip re-running the suite its head already passed?

The guard job of `.github/workflows/ci.yml` calls this on a `merge_group` event
and writes the verdict to its `skip` output (livespec-dev-tooling-ymog6r, plan
stale-base-merge-options, ruling on epic livespec-dev-tooling-xowhol,
2026-11-16). `skip` is `true` ONLY when every condition holds; every other case,
including any forge error or unexpected payload, is `false` and the workflow
runs its full job graph:

1. the group holds exactly one merge queue entry (its head is the first entry);
2. the entry's base commit is the group's base commit (master did not move);
3. the group's base commit is an ancestor of, or equal to, the pull request head;
4. the tree sha of the group's head commit equals the tree sha of the pull
   request head commit;
5. for that exact head sha, the LATEST GitHub Actions check run of every
   required name (each leg `ci-green` needs, read from `ci.yml` at the group's
   base commit, and `ci-green` itself) is bound to this pull request and
   concluded `success`; and
6. the head's `ci-green` did not report an incident-omitted set.

Nothing is inferred: every fact is read from the forge. The kill switch
`LIVESPEC_MERGE_GROUP_SKIP_DISABLED=true` forces `false`.

CLI (env: GITHUB_REPOSITORY, MG_HEAD_SHA, MG_BASE_SHA, MG_BASE_REF,
LIVESPEC_MERGE_GROUP_SKIP_DISABLED): prints one `skip=<true|false>` line, then a
`reason:` line, and always exits 0 so the guard step never fails the job.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias

from livespec_dev_tooling.budgeted_gh import gh_read
from livespec_dev_tooling.ci_green_required_legs import required_legs

__all__: list[str] = [
    "ForgeReadError",
    "GhForge",
    "GroupInputs",
    "SkipVerdict",
    "decide",
    "main",
]

# Forge answers are untyped JSON; every read below sits inside `decide`'s fail-closed guard.
Payload: TypeAlias = Any

_GATE_JOB = "ci-green"
_ACTIONS_APP = "github-actions"
_OMITTED_STEP = "Report members omitted-by-incident-policy"
_ANCESTOR_STATUSES = frozenset({"identical", "ahead"})


class ForgeReadError(Exception):
    """A forge read ended without an answer; the verdict then fails closed."""


class Forge(Protocol):
    """The four forge reads the verdict needs."""

    def get(self, *, path: str) -> Payload: ...

    def check_runs(self, *, sha: str) -> list[Payload]: ...

    def queue_entries(self, *, branch: str) -> list[Payload]: ...

    def workflow_text(self, *, ref: str) -> str: ...


@dataclass(frozen=True, kw_only=True)
class GroupInputs:
    """The merge group under judgment, as the `merge_group` event states it."""

    repo: str
    head_sha: str
    base_sha: str
    base_ref: str
    disabled: bool


@dataclass(frozen=True, kw_only=True)
class SkipVerdict:
    """`skip` and the one-line reason the guard logs beside it."""

    skip: bool
    reason: str


def _no(*, reason: str) -> SkipVerdict:
    return SkipVerdict(skip=False, reason=reason)


def _tree(*, forge: Forge, repo: str, sha: str) -> object:
    commit = forge.get(path=f"repos/{repo}/git/commits/{sha}")
    return commit["tree"]["sha"]


def _required_names(*, workflow: str) -> tuple[str, ...] | None:
    names: list[str] = [_GATE_JOB]
    for _job, legs in required_legs(ci_yaml_text=workflow, gate_job=_GATE_JOB):
        if not legs:
            return None
        names.extend(legs)
    return tuple(names)


def _latest_actions_runs(*, runs: list[Payload], number: int, base_ref: str) -> dict[str, Payload]:
    latest: dict[str, Payload] = {}
    for run in runs:
        app = run["app"]
        bound = [(pr["number"], pr["base"]["ref"]) for pr in run["pull_requests"]]
        if app["slug"] != _ACTIONS_APP or (number, base_ref) not in bound:
            continue
        name = str(run["name"])
        if name not in latest or int(run["id"]) > int(latest[name]["id"]):
            latest[name] = run
    return latest


def _head_checks_gap(*, forge: Forge, inputs: GroupInputs, pr_head: str, number: int) -> str | None:
    names = _required_names(workflow=forge.workflow_text(ref=inputs.base_sha))
    if names is None:
        return "a required leg name cannot be derived from ci.yml at the base commit"
    latest = _latest_actions_runs(
        runs=forge.check_runs(sha=pr_head),
        number=number,
        base_ref=inputs.base_ref.removeprefix("refs/heads/"),
    )
    bad = [name for name in names if name not in latest or latest[name]["conclusion"] != "success"]
    if bad:
        return f"required check runs missing or not success on the head: {', '.join(bad)}"
    job = forge.get(path=f"repos/{inputs.repo}/actions/jobs/{latest[_GATE_JOB]['id']}")
    steps = {str(step["name"]): step["conclusion"] for step in job["steps"]}
    if steps.get(_OMITTED_STEP) != "skipped":
        return "the head's ci-green reports an incident-omitted set or no omitted-set step"
    return None


def _entry_gap(*, forge: Forge, inputs: GroupInputs) -> tuple[str | None, Payload]:
    branch = inputs.base_ref.removeprefix("refs/heads/")
    entries = sorted(forge.queue_entries(branch=branch), key=lambda e: int(e["position"]))
    cut = [i for i, e in enumerate(entries) if e["headCommit"]["oid"] == inputs.head_sha]
    if cut != [0]:
        return "the group is not exactly the first queue entry", {}
    entry = entries[0]
    if entry["baseCommit"]["oid"] != inputs.base_sha:
        return "the entry's base commit is not the group's base commit", {}
    if entry["pullRequest"]["baseRefName"] != branch:
        return "the pull request does not target the group's base branch", {}
    return None, entry


def _verdict(*, forge: Forge, inputs: GroupInputs) -> SkipVerdict:
    gap, entry = _entry_gap(forge=forge, inputs=inputs)
    if gap is not None:
        return _no(reason=gap)
    pr = entry["pullRequest"]
    pr_head = str(pr["headRefOid"])
    number = int(pr["number"])
    status = forge.get(path=f"repos/{inputs.repo}/compare/{inputs.base_sha}...{pr_head}")["status"]
    if status not in _ANCESTOR_STATUSES:
        return _no(reason=f"the group's base is not an ancestor of the head (compare: {status})")
    group_tree = _tree(forge=forge, repo=inputs.repo, sha=inputs.head_sha)
    if group_tree != _tree(forge=forge, repo=inputs.repo, sha=pr_head):
        return _no(reason="the group's tree differs from the pull request head's tree")
    checks_gap = _head_checks_gap(forge=forge, inputs=inputs, pr_head=pr_head, number=number)
    if checks_gap is not None:
        return _no(reason=checks_gap)
    return SkipVerdict(skip=True, reason=f"tree {group_tree} equals PR #{number} head {pr_head}")


def decide(*, inputs: GroupInputs, forge: Forge) -> SkipVerdict:
    """The skip verdict for one merge group; `skip=False` on any doubt."""
    if inputs.disabled:
        return _no(reason="LIVESPEC_MERGE_GROUP_SKIP_DISABLED is true")
    try:
        return _verdict(forge=forge, inputs=inputs)
    except (ForgeReadError, KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
        return _no(reason=f"unreadable or unexpected forge answer: {error!r}")


class GhForge:
    """The real forge: the `gh` CLI under the job's read-only token."""

    def __init__(self, *, repo: str) -> None:
        self._repo = repo

    def _gh(self, *, args: list[str]) -> str:
        read = gh_read(args=args, timeout=120)
        if read.returncode != 0:
            raise ForgeReadError(read.stderr.strip()[:200])
        return read.stdout

    def get(self, *, path: str) -> Payload:
        return json.loads(self._gh(args=["api", path]))

    def check_runs(self, *, sha: str) -> list[Payload]:
        pages = json.loads(
            self._gh(
                args=[
                    "api",
                    "--paginate",
                    "--slurp",
                    f"repos/{self._repo}/commits/{sha}/check-runs?per_page=100",
                ]
            )
        )
        return [run for page in pages for run in page["check_runs"]]

    def queue_entries(self, *, branch: str) -> list[Payload]:
        owner, name = self._repo.split("/", 1)
        query = (
            "query($owner: String!, $name: String!, $branch: String!) {"
            " repository(owner: $owner, name: $name) { mergeQueue(branch: $branch) {"
            " entries(first: 100) { nodes { position headCommit { oid } baseCommit { oid }"
            " pullRequest { number headRefOid baseRefName } } } } } }"
        )
        data = json.loads(
            self._gh(
                args=[
                    "api",
                    "graphql",
                    "-f",
                    f"query={query}",
                    "-f",
                    f"owner={owner}",
                    "-f",
                    f"name={name}",
                    "-f",
                    f"branch={branch}",
                ]
            )
        )
        return data["data"]["repository"]["mergeQueue"]["entries"]["nodes"]

    def workflow_text(self, *, ref: str) -> str:
        return self._gh(
            args=[
                "api",
                "-H",
                "Accept: application/vnd.github.raw",
                f"repos/{self._repo}/contents/.github/workflows/ci.yml?ref={ref}",
            ]
        )


def main(*, env: dict[str, str] | None = None) -> int:
    """Print the guard's `skip=` line and reason; always exit 0 (fail closed to false)."""
    env = dict(os.environ) if env is None else env
    try:
        inputs = GroupInputs(
            repo=env["GITHUB_REPOSITORY"],
            head_sha=env["MG_HEAD_SHA"],
            base_sha=env["MG_BASE_SHA"],
            base_ref=env["MG_BASE_REF"],
            disabled=env.get("LIVESPEC_MERGE_GROUP_SKIP_DISABLED", "").strip().lower() == "true",
        )
    except KeyError as error:
        verdict = _no(reason=f"missing environment variable {error}")
    else:
        verdict = decide(inputs=inputs, forge=GhForge(repo=inputs.repo))
    _ = sys.stdout.write(f"skip={'true' if verdict.skip else 'false'}\nreason: {verdict.reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
