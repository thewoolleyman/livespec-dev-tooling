"""Classify bump PRs superseded by master or newer open sibling PRs.

The release fan-out opens PRs titled ``chore(deps): bump <source_repo> pin to
<tag>``. This module keeps the decision logic importable and unit-tested while
the workflow remains thin glue: gather open PR JSON, gather discovered master pin
records, call this module, and close the PR numbers it returns.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

__all__: list[str] = [
    "BumpKey",
    "OpenBumpPullRequest",
    "SupersessionDecision",
    "classify_superseded_prs",
    "main",
    "master_versions_from_records",
    "parse_open_bump_prs",
]

_BUMP_TITLE_RE = re.compile(r"^chore\(deps\): bump (?P<source>.+) pin to (?P<tag>\S+)$")
_VERSION_RE = re.compile(r"(?:^|-)?v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


@dataclass(frozen=True, kw_only=True)
class BumpKey:
    """The shared bump identity used by supersession and future dedupe logic."""

    source_repo: str
    target_version: str
    consumer: str


@dataclass(frozen=True, kw_only=True)
class OpenBumpPullRequest:
    """Open bump PR metadata relevant to supersession."""

    number: int
    branch: str
    key: BumpKey


@dataclass(frozen=True, kw_only=True)
class SupersessionDecision:
    """A PR that should be closed, with the superseder named for the comment."""

    number: int
    branch: str
    category: str
    superseder: str
    comment: str


def _version_tuple(*, value: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.search(value)
    if match is None:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def _version_gte(*, left: str, right: str) -> bool:
    if left == right:
        return True
    left_tuple = _version_tuple(value=left)
    right_tuple = _version_tuple(value=right)
    if left_tuple is None or right_tuple is None:
        return False
    return left_tuple >= right_tuple


def _version_gt(*, left: str, right: str) -> bool:
    left_tuple = _version_tuple(value=left)
    right_tuple = _version_tuple(value=right)
    if left_tuple is None or right_tuple is None:
        return False
    return left_tuple > right_tuple


def _version_lt(*, left: str, right: str) -> bool:
    left_tuple = _version_tuple(value=left)
    right_tuple = _version_tuple(value=right)
    if left_tuple is None or right_tuple is None:
        return False
    return left_tuple < right_tuple


def _newer_sibling(
    *, pr: OpenBumpPullRequest, open_prs: list[OpenBumpPullRequest]
) -> OpenBumpPullRequest | None:
    candidates = [
        candidate
        for candidate in open_prs
        if candidate.number != pr.number
        and candidate.key.source_repo == pr.key.source_repo
        and candidate.key.consumer == pr.key.consumer
        and _version_gt(left=candidate.key.target_version, right=pr.key.target_version)
    ]
    return max(
        candidates,
        key=lambda candidate: (
            _version_tuple(value=candidate.key.target_version) or (0, 0, 0),
            candidate.number,
        ),
        default=None,
    )


def _master_comment(*, pr: OpenBumpPullRequest, master_version: str) -> str:
    return (
        "Closing this bump PR because master already carries "
        f"{pr.key.source_repo} at {master_version} for {pr.key.consumer}, "
        f"which supersedes target {pr.key.target_version}."
    )


def _sibling_comment(*, pr: OpenBumpPullRequest, sibling: OpenBumpPullRequest) -> str:
    return (
        "Closing this bump PR because it targets "
        f"{pr.key.source_repo} {pr.key.target_version} for {pr.key.consumer}, "
        f"and newer open bump PR #{sibling.number} targeting {sibling.key.target_version}."
    )


def classify_superseded_prs(
    *,
    open_prs: list[OpenBumpPullRequest],
    master_versions: dict[tuple[str, str], str],
) -> list[SupersessionDecision]:
    """Return open bump PRs that should be closed.

    ``master_versions`` is keyed as ``(source_repo, consumer)``. Each
    ``OpenBumpPullRequest`` carries the full ``(source_repo, target_version,
    consumer)`` key so a future duplicate-PR dedupe pass can share the same
    parser and domain model.
    """
    decisions: list[SupersessionDecision] = []
    for pr in sorted(open_prs, key=lambda candidate: candidate.number):
        master_version = master_versions.get((pr.key.source_repo, pr.key.consumer))
        if master_version is not None and _version_gte(
            left=master_version, right=pr.key.target_version
        ):
            decisions.append(
                SupersessionDecision(
                    number=pr.number,
                    branch=pr.branch,
                    category="master",
                    superseder=master_version,
                    comment=_master_comment(pr=pr, master_version=master_version),
                )
            )
            continue

        sibling = _newer_sibling(pr=pr, open_prs=open_prs)
        if sibling is not None:
            decisions.append(
                SupersessionDecision(
                    number=pr.number,
                    branch=pr.branch,
                    category="open_sibling",
                    superseder=f"#{sibling.number}",
                    comment=_sibling_comment(pr=pr, sibling=sibling),
                )
            )
    return decisions


def _payload_mapping(*, value: object) -> Mapping[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(Mapping[str, object], value)


def _payload_str(*, value: object, key: str) -> str | None:
    mapping = _payload_mapping(value=value)
    if mapping is None:
        return None
    raw = mapping.get(key)
    return raw if isinstance(raw, str) and raw else None


def _payload_int(*, value: object, key: str) -> int | None:
    mapping = _payload_mapping(value=value)
    if mapping is None:
        return None
    raw = mapping.get(key)
    return raw if isinstance(raw, int) else None


def parse_open_bump_prs(*, payload: object, consumer: str) -> list[OpenBumpPullRequest]:
    """Parse ``gh pr list`` JSON into bump PR records, skipping unrelated PRs."""
    if not isinstance(payload, list):
        return []
    items = cast(list[object], payload)
    prs: list[OpenBumpPullRequest] = []
    for item in items:
        title = _payload_str(value=item, key="title")
        branch = _payload_str(value=item, key="headRefName")
        number = _payload_int(value=item, key="number")
        if title is None or branch is None or number is None:
            continue
        match = _BUMP_TITLE_RE.match(title)
        if match is None:
            continue
        prs.append(
            OpenBumpPullRequest(
                number=number,
                branch=branch,
                key=BumpKey(
                    source_repo=match.group("source"),
                    target_version=match.group("tag"),
                    consumer=consumer,
                ),
            )
        )
    return prs


def master_versions_from_records(
    *, records: list[dict[str, str]], consumer: str
) -> dict[tuple[str, str], str]:
    """Return the lowest discovered master pin per source for a consumer.

    Some consumers carry several pins for the same source. The master supersedes
    a bump only when the lowest discovered pin is still at or above that bump's
    target; otherwise the PR may still be needed to raise an older surface.
    """
    versions: dict[tuple[str, str], str] = {}
    for record in records:
        source_repo = record.get("source_repo")
        current_value = record.get("current_value")
        if not source_repo or not current_value:
            continue
        key = (source_repo, consumer)
        existing = versions.get(key)
        if existing is None or _version_lt(left=current_value, right=existing):
            versions[key] = current_value
    return versions


def _decision_payload(*, decisions: list[SupersessionDecision]) -> list[dict[str, str | int]]:
    return [
        {
            "number": decision.number,
            "branch": decision.branch,
            "category": decision.category,
            "superseder": decision.superseder,
            "comment": decision.comment.replace(" targeting ", " targets "),
        }
        for decision in decisions
    ]


def _consumer_from_env() -> str:
    consumer = os.environ.get("CONSUMER")
    if consumer:
        return consumer
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    return repository.rsplit("/", maxsplit=1)[-1]


def main() -> int:
    """Read workflow JSON from env and emit a JSON close plan."""
    open_pr_payload = json.loads(os.environ.get("OPEN_PRS", "[]"))
    records_payload = cast(list[dict[str, str]], json.loads(os.environ.get("RECORDS", "[]")))
    consumer = _consumer_from_env()
    open_prs = parse_open_bump_prs(payload=open_pr_payload, consumer=consumer)
    master_versions = master_versions_from_records(records=records_payload, consumer=consumer)
    decisions = classify_superseded_prs(open_prs=open_prs, master_versions=master_versions)
    _ = sys.stdout.write(json.dumps(_decision_payload(decisions=decisions), indent=2))
    _ = sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
