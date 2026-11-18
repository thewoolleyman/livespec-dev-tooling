"""incident_merge_principal — the incident-merge principal's merge decision and act.

The `Incident-merge principal.` paragraph of SPECIFICATION/contracts.md (inside its
expedited incident execution contract, v246) lets an independently provisioned
principal merge one expedited repair pull request outside the merge queue. This module
composes the three halves already on master (livespec-dev-tooling-u3nbm3, slice B4):

- B1 `incident_merge_app`: the App identity and its scoped installation access. The
  injected `forge` is a `MergeForge`.
- B2 `incident_merge_authority`: the chain-only authority decision (`decide`).
- B3 `incident_merge_forge`: the label and the effective required checks on the head.

ORDER. Every condition is read at merge time and each failure is one NAMED refusal that
is recorded on the incident work item before it is returned: the pull request as the
forge shows it (open, unmerged, on the default branch), the chain (the sole authority;
the label is necessary and never sufficient, so it is read second), the label, then the
principal's own green-check verification, which a ruleset bypass does not do for it. The
expected head SHA is the head the checks were verified on; a head that moved after
verification makes the forge refuse the merge (HTTP 409, `head-moved`).

THE ENDPOINT. GitHub documents `PUT /pulls/{n}/merge` as not supporting a merge queue
and `PUT /pulls/{n}/merge-async` as taking `bypass_rules` ("whether to bypass
repository rules that the authenticated actor is permitted to bypass", default false).
The principal's whole purpose is to merge on a queue-required branch as a
`pull_request`-mode bypass actor, so the DEFAULT is `merge-async` with
`bypass_rules: true`. The synchronous `merge` endpoint stays one `endpoint=` argument
away because the documentation is silent on whether an actor that may bypass can use
it; the first live proof on a real queue (the DoD's host-captured assertions) decides,
and flipping `DEFAULT_ENDPOINT` is the whole change. Either way the merge method is
`rebase` and the call carries `sha`, and the principal never trusts the call's answer:
it reads the pull request back until the forge says `merged` (an async merge is
accepted before it lands) and takes the resulting `master` SHA from the pull request's
`merge_commit_sha`.

THE QUEUE. The entries ahead of the pull request are recorded, not gated: they are
state at merge time. `queue_entries_ahead` parses the GraphQL `mergeQueue` answer; the
production runner that issues the GraphQL call and writes the ledger comment binds the
`queue` and `record` seams (slice B5). A queue that cannot be read is recorded as
unreadable and does not stop a merge whose every other condition holds.

It acts only by merging: it calls no ref, ruleset or push endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, cast

from livespec_dev_tooling.incident_merge_authority import (
    MergeChainReader,
    decide,
)
from livespec_dev_tooling.incident_merge_forge import (
    ForgeReader,
    Green,
    IncidentForgeReadError,
    has_incident_label,
    required_checks_verdict,
)

__all__: list[str] = [
    "DEFAULT_ENDPOINT",
    "IncidentRecorder",
    "MergeEndpoint",
    "MergeRequester",
    "Merged",
    "QueueEntries",
    "QueueUnreadableError",
    "Refused",
    "merge_incident_repair",
    "queue_entries_ahead",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-u3nbm3

MergeEndpoint = Literal["merge", "merge-async"]
DEFAULT_ENDPOINT: MergeEndpoint = "merge-async"
_CONFIRM_READS = 5
_CONFIRM_WAIT_SECONDS = 2.0
_HTTP_OK = 200
_HTTP_SUCCESS = range(200, 300)
_HTTP_HEAD_MOVED = 409
_UNIVERSAL_TIME = "%Y-%m-%dT%H:%M:%SZ"


class QueueUnreadableError(Exception):
    """The merge queue's entries could not be read; recorded, never a reason to merge or refuse."""

    def __init__(self, *, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class MergeRequester(Protocol):
    """The incident-merge App's REST access under `repos/<repository>/` (`MergeForge`)."""

    def request(
        self, *, method: str, path: str, value: object | None = None
    ) -> tuple[int, object]: ...


class QueueEntries(Protocol):
    """The pull request numbers queued ahead of `pr_number`; raises `QueueUnreadableError`."""

    def __call__(self, *, repo: str, pr_number: int) -> tuple[int, ...]: ...


class IncidentRecorder(Protocol):
    """Writes one record onto the incident work item's ledger."""

    def __call__(self, *, incident_id: str, text: str) -> None: ...


@dataclass(frozen=True, kw_only=True)
class Merged:
    """The pull request is merged; every field is what the spec requires recorded."""

    incident_id: str
    pr_number: int
    principal: str
    head_sha: str
    master_sha: str
    merged_at: str
    queue_ahead: tuple[int, ...] | None
    endpoint: MergeEndpoint


@dataclass(frozen=True, kw_only=True)
class Refused:
    """Nothing was merged; `reason` names why and the refusal was recorded."""

    reason: str
    detail: str


def _dig(*, value: object, keys: tuple[str, ...]) -> object:
    """The value under `keys` in nested objects, or None where the path breaks."""
    for key in keys:
        value = cast("dict[str, object]", value).get(key) if isinstance(value, dict) else None
    return value


def queue_entries_ahead(*, payload: object, pr_number: int) -> tuple[int, ...]:
    """Parse a GraphQL `mergeQueue` answer into the entries ahead of `pr_number`.

    A pull request that is not queued has the whole queue ahead of it, and a
    repository with no merge queue has nothing ahead. A malformed answer raises
    `QueueUnreadableError`.
    """
    if not isinstance(_dig(value=payload, keys=("data", "repository")), dict):
        raise QueueUnreadableError(detail="the answer carried no repository")
    if _dig(value=payload, keys=("data", "repository", "mergeQueue")) is None:
        return ()
    nodes = _dig(value=payload, keys=("data", "repository", "mergeQueue", "entries", "nodes"))
    if not isinstance(nodes, list):
        raise QueueUnreadableError(detail="the merge queue carried no entries list")
    entries = [
        (_dig(value=node, keys=("position",)), _dig(value=node, keys=("pullRequest", "number")))
        for node in cast("list[object]", nodes)
    ]
    if not all(type(position) is int and type(number) is int for position, number in entries):
        raise QueueUnreadableError(detail="a queue entry carried no position or number")
    ordered = sorted(cast("list[tuple[int, int]]", entries))
    own = [position for position, number in ordered if number == pr_number]
    return tuple(number for position, number in ordered if not own or position < own[0])


def _text(*, lines: list[tuple[str, str]]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in lines)


@dataclass(frozen=True, kw_only=True)
class _Pull:
    head_sha: str
    base_sha: str


def _read_pull(*, forge: MergeRequester, pr_number: int) -> _Pull | Refused:
    status, body = forge.request(method="GET", path=f"pulls/{pr_number}")
    if status != _HTTP_OK or not isinstance(body, dict):
        return Refused(reason="forge-unreadable", detail=f"pull request read: HTTP {status}")
    pull = cast("dict[str, Any]", body)
    base, head = pull.get("base"), pull.get("head")
    base_shape = cast("dict[str, Any]", base) if isinstance(base, dict) else {}
    head_sha, base_sha = cast("dict[str, Any]", head or {}).get("sha"), base_shape.get("sha")
    if not isinstance(head_sha, str) or not isinstance(base_sha, str):
        return Refused(reason="forge-unreadable", detail="pull request carried no base or head sha")
    if pull.get("state") != "open" or pull.get("merged") is True:
        return Refused(reason="pull-request-not-open", detail="the pull request is not open")
    repo = base_shape.get("repo")
    default = cast("dict[str, Any]", repo).get("default_branch") if isinstance(repo, dict) else None
    if base_shape.get("ref") != default:
        return Refused(
            reason="default-branch-mismatch",
            detail=f"base {base_shape.get('ref')} is not the default branch {default}",
        )
    return _Pull(head_sha=head_sha, base_sha=base_sha)


def _issue_merge(
    *, forge: MergeRequester, endpoint: MergeEndpoint, pr_number: int, head_sha: str
) -> Refused | None:
    body: dict[str, object] = {"merge_method": "rebase", "sha": head_sha}
    if endpoint == "merge-async":
        body["bypass_rules"] = True
    status, answer = forge.request(method="PUT", path=f"pulls/{pr_number}/{endpoint}", value=body)
    if status in _HTTP_SUCCESS:
        return None
    message = cast("dict[str, Any]", answer).get("message", "") if isinstance(answer, dict) else ""
    reason = "head-moved" if status == _HTTP_HEAD_MOVED else "merge-rejected"
    return Refused(reason=reason, detail=f"{endpoint}: HTTP {status} {message}".rstrip())


def _confirm(
    *, forge: MergeRequester, pr_number: int, sleep: Callable[[float], None]
) -> str | Refused:
    for attempt in range(_CONFIRM_READS):
        status, body = forge.request(method="GET", path=f"pulls/{pr_number}")
        pull = cast("dict[str, Any]", body) if status == _HTTP_OK and isinstance(body, dict) else {}
        master = pull.get("merge_commit_sha")
        if pull.get("merged") is True and isinstance(master, str):
            return master
        if attempt < _CONFIRM_READS - 1:
            sleep(_CONFIRM_WAIT_SECONDS)
    return Refused(
        reason="merge-unconfirmed",
        detail=f"not merged after {_CONFIRM_READS} reads of the pull request",
    )


def _queue_state(
    *, queue: QueueEntries, repo: str, pr_number: int
) -> tuple[tuple[int, ...] | None, str]:
    try:
        ahead = queue(repo=repo, pr_number=pr_number)
    except QueueUnreadableError as error:
        return None, f"unreadable: {error.detail}"
    return ahead, ", ".join(str(number) for number in ahead) or "none"


def _preconditions(
    *,
    repo: str,
    incident_id: str,
    pr_number: int,
    forge: MergeRequester,
    check_reader: ForgeReader,
    chain: MergeChainReader,
) -> _Pull | Refused:
    """Every condition the spec reads at merge time, in order; the first failure is the refusal."""
    pull = _read_pull(forge=forge, pr_number=pr_number)
    if isinstance(pull, Refused):
        return pull
    verdict = decide(
        reader=chain,
        incident_id=incident_id,
        pr_number=pr_number,
        base_sha=pull.base_sha,
        head_sha=pull.head_sha,
    )
    if not verdict.allowed:
        return Refused(reason=str(verdict.reason), detail=verdict.detail)
    try:
        labelled = has_incident_label(forge=check_reader, repo=repo, pr_number=pr_number)
    except IncidentForgeReadError as error:
        return Refused(reason="forge-unreadable", detail=str(error))
    if not labelled:
        return Refused(reason="label-absent", detail="no expedited-incident-response label")
    checks = required_checks_verdict(forge=check_reader, repo=repo, head_sha=pull.head_sha)
    if not isinstance(checks, Green):
        return Refused(reason="checks-not-green", detail=checks.reason)
    return pull


def merge_incident_repair(  # noqa: PLR0913 — every collaborator is an injected seam.
    *,
    repo: str,
    incident_id: str,
    pr_number: int,
    principal: str,
    forge: MergeRequester,
    check_reader: ForgeReader,
    chain: MergeChainReader,
    queue: QueueEntries,
    record: IncidentRecorder,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    endpoint: MergeEndpoint = DEFAULT_ENDPOINT,
) -> Merged | Refused:
    """Merge one verified expedited repair outside the queue, or refuse by name; record either."""

    def refused(*, outcome: Refused) -> Refused:
        lines = [("incident-merge", "refused"), ("reason", outcome.reason)]
        lines += [("detail", outcome.detail), ("pull-request", str(pr_number))]
        record(incident_id=incident_id, text=_text(lines=lines))
        return outcome

    pull = _preconditions(
        repo=repo,
        incident_id=incident_id,
        pr_number=pr_number,
        forge=forge,
        check_reader=check_reader,
        chain=chain,
    )
    if isinstance(pull, Refused):
        return refused(outcome=pull)
    ahead, ahead_text = _queue_state(queue=queue, repo=repo, pr_number=pr_number)
    failure = _issue_merge(
        forge=forge, endpoint=endpoint, pr_number=pr_number, head_sha=pull.head_sha
    )
    if failure is not None:
        return refused(outcome=failure)
    master = _confirm(forge=forge, pr_number=pr_number, sleep=sleep)
    if isinstance(master, Refused):
        return refused(outcome=master)
    merged_at = clock().strftime(_UNIVERSAL_TIME)
    record(
        incident_id=incident_id,
        text=_text(
            lines=[
                ("incident-merge", "merged"),
                ("principal", principal),
                ("pull-request", str(pr_number)),
                ("head-sha", pull.head_sha),
                ("master-sha", master),
                ("merged-at", merged_at),
                ("queue-ahead", ahead_text),
                ("endpoint", endpoint),
            ]
        ),
    )
    return Merged(
        incident_id=incident_id,
        pr_number=pr_number,
        principal=principal,
        head_sha=pull.head_sha,
        master_sha=master,
        merged_at=merged_at,
        queue_ahead=ahead,
        endpoint=endpoint,
    )
