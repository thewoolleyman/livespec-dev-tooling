"""Locate the queued pull request an expedited commit belongs to, on a merge_group event.

A merge_group event carries no pull request, and the merge queue rebases each queued
pull request's commits, so a commit in the range is a rebased copy whose SHA differs
from the one the incident chain recorded; one group can also batch several pull
requests. This module answers only WHICH pull request a commit belongs to, and
whether the commit is a byte-identical rebased copy of one commit that pull request
recorded. It never decides admission: the audited trailer and the observer's chain
stay with `_red_green_replay_incident`, and nothing a candidate writes grants either
(contracts `Expedited incident execution`, "Merge-queue admission of an expedited
commit"; livespec-dev-tooling-txon2s).

Every outcome that is not a located pull request is a string: the one reason the
commit stays convicted, in the order the contract lists them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_dev_tooling.budgeted_gh import gh_read
from livespec_dev_tooling.incident_ci_event import incident_block
from livespec_dev_tooling.incident_ci_payload import decode_authority
from livespec_dev_tooling.incident_git import IncidentGitError, run_git
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_dev_tooling.incident_ci_payload import CiAuthority
    from livespec_dev_tooling.incident_execution import OperationIdentity

__all__: list[str] = ["NO_BLOCK_ON_MERGE_GROUP", "LocatedPullRequest", "locate_queued_pull_request"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-txon2s
NO_BLOCK_ON_MERGE_GROUP = (
    "no livespec-incident-ci block was read: a merge_group event carries no pull_request body"
)
_QUERY = (
    "query($owner:String!,$name:String!,$branch:String!){repository(owner:$owner,name:$name)"
    "{mergeQueue(branch:$branch){entries(first:100){nodes{position pullRequest{number}"
    " baseCommit{oid} headCommit{oid}}}}}}"
)


@dataclass(frozen=True, kw_only=True)
class LocatedPullRequest:
    """The queued pull request a commit belongs to, with the block it recorded."""

    authority: CiAuthority
    identity: OperationIdentity


def _mapping(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _forge(*, args: list[str]) -> dict[str, Any] | None:
    answer = gh_read(args=["api", *args])
    if answer.returncode != 0:
        return None
    try:
        return _mapping(value=strict_json(text=answer.stdout, limit=None))
    except (ValueError, IncidentJsonRefusalError):
        return None


def _git_lines(*, args: list[str], data: bytes | None = None) -> list[str] | None:
    try:
        done = run_git(repo=Path.cwd(), args=args, data=data, check=False)
    except IncidentGitError:
        return None
    return done.stdout.decode().splitlines() if done.returncode == 0 else None


def _patch_id(*, sha: str) -> str | None:
    """The commit's `--verbatim` patch-id, or None when git prints none."""
    try:
        diff = run_git(repo=Path.cwd(), args=["show", "--format=", sha]).stdout
        printed = run_git(repo=Path.cwd(), args=["patch-id", "--verbatim"], data=diff).stdout
    except IncidentGitError:
        return None
    words = printed.decode().split()
    return words[0] if words else None


def _entries(*, environ: Mapping[str, str]) -> list[dict[str, Any]] | None:
    """The queue entries (position, pull request, base and head commit) the forge reports."""
    try:
        event = _mapping(
            value=strict_json(
                text=Path(environ.get("GITHUB_EVENT_PATH", "")).read_text(encoding="utf-8"),
                limit=None,
            )
        )
    except (OSError, ValueError, IncidentJsonRefusalError):
        return None
    branch = str(_mapping(value=event.get("merge_group")).get("base_ref", ""))
    owner, _, name = environ.get("GITHUB_REPOSITORY", "").partition("/")
    answer = _forge(
        args=[
            "graphql",
            "-f",
            "query=" + _QUERY,
            "-F",
            "owner=" + owner,
            "-F",
            "name=" + name,
            "-F",
            "branch=" + branch.removeprefix("refs/heads/"),
        ]
    )
    queue = _mapping(
        value=_mapping(
            value=_mapping(value=_mapping(value=answer).get("data")).get("repository")
        ).get("mergeQueue")
    )
    nodes = _mapping(value=queue.get("entries")).get("nodes")
    return (
        [_mapping(value=node) for node in cast("list[object]", nodes)]
        if isinstance(nodes, list)
        else None
    )


def _owning_entry(*, sha: str, entries: list[dict[str, Any]]) -> dict[str, Any] | str:
    """The one queue entry whose baseCommit..headCommit range contains `sha`."""
    owners: list[dict[str, Any]] = []
    for entry in entries:
        base = _mapping(value=entry.get("baseCommit")).get("oid")
        head = _mapping(value=entry.get("headCommit")).get("oid")
        commits = _git_lines(args=["rev-list", f"{base}..{head}"])
        if commits is not None and sha in commits:
            owners.append(entry)
    if len(owners) != 1:
        return (
            "no merge queue entry range contains it"
            if not owners
            else ("more than one merge queue entry range contains it")
        )
    return owners[0]


def _ids(*, base: str, head: str) -> list[str | None] | None:
    commits = _git_lines(args=["rev-list", f"{base}..{head}"])
    return None if commits is None else [_patch_id(sha=commit) for commit in commits]


def _recorded_block(*, number: object, environ: Mapping[str, str]) -> LocatedPullRequest | str:
    """The pull request's block, decoded and equal to what the forge reports of it."""
    pull = _forge(args=[f"repos/{environ.get('GITHUB_REPOSITORY', '')}/pulls/{number}"])
    if pull is None:
        return f"pull request {number} could not be read from the forge"
    body = pull.get("body")
    block = incident_block(body=body) if isinstance(body, str) else None
    if block is None:
        return NO_BLOCK_ON_MERGE_GROUP
    authority = decode_authority(payload=block)
    identity = None if authority is None else authority.context.identity
    if authority is None or identity is None:
        return "the livespec-incident-ci block does not decode"
    forged = (
        number,
        _mapping(value=pull.get("base")).get("sha"),
        _mapping(value=pull.get("head")).get("sha"),
    )
    if forged != (authority.pr_number, identity.base_sha, identity.head_sha):
        return "the block names a different pull request, base or head than the forge reports"
    return LocatedPullRequest(authority=authority, identity=identity)


def locate_queued_pull_request(*, sha: str, environ: Mapping[str, str]) -> LocatedPullRequest | str:
    """The queued pull request `sha` is a rebased copy of, or the one reason it is not."""
    entries = _entries(environ=environ)
    if entries is None:
        return "the merge queue entries could not be read from the forge"
    entry = _owning_entry(sha=sha, entries=entries)
    if isinstance(entry, str):
        return entry
    number = _mapping(value=entry.get("pullRequest")).get("number")
    located = _recorded_block(number=number, environ=environ)
    if isinstance(located, str):
        return located
    if _git_lines(args=["fetch", "--no-tags", "origin", f"refs/pull/{number}/head"]) is None:
        return f"the fetch of refs/pull/{number}/head failed"
    return _matched(sha=sha, entry=entry, located=located)


def _matched(
    *, sha: str, entry: dict[str, Any], located: LocatedPullRequest
) -> LocatedPullRequest | str:
    """`located` when `sha` has exactly one recorded counterpart and no sibling copy."""
    own = _patch_id(sha=sha)
    if own is None:
        return "no patch-id: git prints none for this commit"
    recorded = _ids(base=located.identity.base_sha, head=located.identity.head_sha)
    queued = _ids(
        base=str(_mapping(value=entry.get("baseCommit")).get("oid")),
        head=str(_mapping(value=entry.get("headCommit")).get("oid")),
    )
    if recorded is None or queued is None:
        return "the recorded or queued commits could not be listed"
    if recorded.count(own) != 1 or queued.count(own) != 1:
        return "patch-id mismatch: it matches no single commit in the recorded base..head"
    return located
