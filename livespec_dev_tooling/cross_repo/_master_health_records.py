"""Parse the revert pull request half of a recording, and the field readers it shares.

Split out of `master_health_step` to keep that adapter under the file-size
ceiling, along the one seam that is genuinely a separate concern: the revert
pull request, with the claims posted on it and the fix pull requests those
claims name, is a nested record with its own shape, while the commit window,
configuration and state it sits beside are flat. The four field readers move
with it because both halves use them, and a reader that crosses a module
boundary must be public.

NOTHING HERE DECIDES. Every parser answers `None` for a record it cannot read,
and the caller turns that into the fail-closed exit the adapter's docstring
describes; see `master_health_step`.
"""

from __future__ import annotations

from typing import cast

from livespec_dev_tooling.cross_repo.master_health_state import (
    FIX_CLOSED,
    FIX_MERGED,
    FIX_OPEN,
    FixCommit,
    FixForwardClaim,
    FixPullRequest,
    RevertPullRequest,
)

__all__: list[str] = [
    "number_field",
    "parse_revert",
    "positive_field",
    "strings_field",
    "text_field",
]


def text_field(*, record: dict[str, object], key: str) -> str | None:
    """`record[key]` when it is a string; None when absent, null or another type."""
    value = record.get(key)
    return value if isinstance(value, str) else None


def number_field(*, record: dict[str, object], key: str) -> int | None:
    """`record[key]` when it is an integer; None when absent, null or another type.

    `bool` is excluded explicitly: it is an `int` subclass in Python, so a
    recorded `true` would otherwise parse as pull request number 1 — or as a
    lookback of one commit, which is a bound nobody configured.
    """
    value = record.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def positive_field(*, record: dict[str, object], key: str) -> int | None:
    """`record[key]` when it is a strictly positive integer; None otherwise.

    A zero or negative limit is as unusable as an absent one: read literally it
    would release every claim at once or never, and neither is what the
    committed configuration meant.
    """
    value = number_field(record=record, key=key)
    return value if value is not None and value > 0 else None


def strings_field(*, record: dict[str, object], key: str) -> tuple[str, ...] | None:
    """`record[key]` as a tuple of strings; None when it is not a list of strings."""
    value = record.get(key)
    if not isinstance(value, list):
        return None
    entries = cast("list[object]", value)
    if not all(isinstance(entry, str) for entry in entries):
        return None
    return tuple(cast("list[str]", entries))


def _objects(*, payload: object) -> tuple[dict[str, object], ...] | None:
    """`payload` as a tuple of JSON objects; None when it is not a list of objects."""
    if not isinstance(payload, list):
        return None
    entries = cast("list[object]", payload)
    if not all(isinstance(entry, dict) for entry in entries):
        return None
    return tuple(cast("dict[str, object]", entry) for entry in entries)


def _claims(*, payload: object) -> tuple[FixForwardClaim, ...] | None:
    """The comments recorded on the revert, or None when any does not parse."""
    records = _objects(payload=payload)
    if records is None:
        return None
    claims: list[FixForwardClaim] = []
    for record in records:
        author = text_field(record=record, key="author")
        body = text_field(record=record, key="body")
        posted_at = number_field(record=record, key="posted_at")
        if author is None or body is None or posted_at is None:
            return None
        claims.append(FixForwardClaim(author=author, body=body, posted_at=posted_at))
    return tuple(claims)


def _fix_commit(*, record: dict[str, object]) -> FixCommit | None:
    """One recorded fix commit, or None when it does not parse."""
    sha = text_field(record=record, key="sha")
    pushed_at = number_field(record=record, key="pushed_at")
    ci_conclusion = text_field(record=record, key="ci_conclusion")
    failing = strings_field(record=record, key="failing_checks")
    if sha is None or pushed_at is None or ci_conclusion is None or failing is None:
        return None
    return FixCommit(
        sha=sha,
        pushed_at=pushed_at,
        ci_conclusion=ci_conclusion,
        ci_started_at=number_field(record=record, key="ci_started_at"),
        ci_finished_at=number_field(record=record, key="ci_finished_at"),
        failing_checks=failing,
    )


def _fix_pull_request(*, record: dict[str, object]) -> FixPullRequest | None:
    """One recorded fix pull request, or None when it does not parse."""
    number = number_field(record=record, key="number")
    state = text_field(record=record, key="state")
    opened_at = number_field(record=record, key="opened_at")
    commit_records = _objects(payload=record.get("commits"))
    if number is None or opened_at is None or commit_records is None:
        return None
    if state not in (FIX_OPEN, FIX_MERGED, FIX_CLOSED):
        return None
    commits = [_fix_commit(record=commit) for commit in commit_records]
    if any(commit is None for commit in commits):
        return None
    return FixPullRequest(
        number=number,
        state=state,
        opened_at=opened_at,
        commits=tuple(commit for commit in commits if commit is not None),
        auto_merge_armed_at=number_field(record=record, key="auto_merge_armed_at"),
        merged_at=number_field(record=record, key="merged_at"),
        master_ci_conclusion=text_field(record=record, key="master_ci_conclusion"),
        master_ci_started_at=number_field(record=record, key="master_ci_started_at"),
    )


def _fix_pull_requests(*, payload: object) -> tuple[FixPullRequest, ...] | None:
    """The recorded fix pull requests, or None when any does not parse."""
    records = _objects(payload=payload)
    if records is None:
        return None
    fixes = [_fix_pull_request(record=record) for record in records]
    if any(fix is None for fix in fixes):
        return None
    return tuple(fix for fix in fixes if fix is not None)


def parse_revert(*, payload: object) -> RevertPullRequest | None:
    """The recorded revert pull request, or None when it does not parse."""
    if not isinstance(payload, dict):
        return None
    record = cast("dict[str, object]", payload)
    number = number_field(record=record, key="number")
    reverts = number_field(record=record, key="reverts_pull_request")
    ci_conclusion = text_field(record=record, key="ci_conclusion")
    opener = record.get("culprit_opened_by")
    claims = _claims(payload=record.get("claims"))
    fixes = _fix_pull_requests(payload=record.get("fix_pull_requests"))
    if number is None or reverts is None or ci_conclusion is None:
        return None
    if claims is None or fixes is None or not (opener is None or isinstance(opener, str)):
        return None
    return RevertPullRequest(
        number=number,
        reverts_pull_request=reverts,
        ci_conclusion=ci_conclusion,
        auto_merge_armed=bool(record.get("auto_merge_armed")),
        culprit_opened_by=opener,
        claims=claims,
        fix_pull_requests=fixes,
    )
