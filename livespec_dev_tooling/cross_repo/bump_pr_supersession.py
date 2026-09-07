"""Decide which bump PRs to close, and which not to open at all.

The release fan-out opens PRs titled ``chore(deps): bump <source_repo> pin to
<tag>``. This module keeps the decision logic importable and unit-tested while
the workflow remains thin glue: gather open PR JSON, gather discovered master pin
records, call this module, and act on what it returns.

Two decisions share one bump identity, and each covers what the other cannot:

- ``classify_superseded_prs`` runs AFTER the create and closes OLD PRs — those a
  master pin or a STRICTLY newer open sibling has overtaken.
- ``find_duplicate_bump_pr`` runs BEFORE the create and refuses NEW duplicates —
  a second PR for a tuple that already has one open. Supersession structurally
  cannot clean an EQUAL-version pair up: its master category needs a master pin
  at or above the target, defeated in exactly the repo whose bump has not landed
  yet, and its sibling category needs a strictly newer sibling, which two PRs at
  the same version are not to each other. Both producers — the dispatch path
  (``chore/bump-*``) and the cron-freshness path (``chore/freshness-bump-*``) —
  reach the create for the same release, so the duplicate has to be refused
  rather than swept (livespec-dev-tooling-dqfmjr).

Together they hold the invariant of at most one open bump PR per
``(source_repo, consumer)``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from livespec_dev_tooling.cross_repo._bump_version_order import (
    version_gt,
    version_gte,
    version_lt,
    version_sort_key,
)

__all__: list[str] = [
    "BumpKey",
    "DuplicateBumpDecision",
    "OpenBumpPullRequest",
    "SupersessionDecision",
    "classify_superseded_prs",
    "find_duplicate_bump_pr",
    "main",
    "master_versions_from_records",
    "parse_open_bump_prs",
]

_BUMP_TITLE_RE = re.compile(r"^chore\(deps\): bump (?P<source>.+) pin to (?P<tag>\S+)$")


@dataclass(frozen=True, kw_only=True)
class BumpKey:
    """The shared bump identity used by supersession and dedupe alike."""

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
class DuplicateBumpDecision:
    """The already-open bump PR that makes another ``gh pr create`` redundant."""

    number: int
    branch: str
    notice: str


@dataclass(frozen=True, kw_only=True)
class SupersessionDecision:
    """A PR that should be closed, with the superseder named for the comment."""

    number: int
    branch: str
    category: str
    superseder: str
    comment: str


def _newer_sibling(
    *, pr: OpenBumpPullRequest, open_prs: list[OpenBumpPullRequest]
) -> OpenBumpPullRequest | None:
    candidates = [
        candidate
        for candidate in open_prs
        if candidate.number != pr.number
        and candidate.key.source_repo == pr.key.source_repo
        and candidate.key.consumer == pr.key.consumer
        and version_gt(left=candidate.key.target_version, right=pr.key.target_version)
    ]
    return max(
        candidates,
        key=lambda candidate: (
            version_sort_key(value=candidate.key.target_version),
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
    consumer)`` key, which is what lets ``find_duplicate_bump_pr`` share the same
    parser and domain model.
    """
    decisions: list[SupersessionDecision] = []
    for pr in sorted(open_prs, key=lambda candidate: candidate.number):
        master_version = master_versions.get((pr.key.source_repo, pr.key.consumer))
        if master_version is not None and version_gte(
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


def _duplicate_notice(*, incumbent: OpenBumpPullRequest, key: BumpKey) -> str:
    return (
        f"bump PR #{incumbent.number} ({incumbent.branch}) already targets "
        f"{key.source_repo} {key.target_version} for {key.consumer}; "
        "skipping a duplicate `gh pr create`."
    )


def find_duplicate_bump_pr(
    *, open_prs: list[OpenBumpPullRequest], key: BumpKey
) -> DuplicateBumpDecision | None:
    """Return the open bump PR that already covers ``key``, or ``None`` to create one.

    The match is on the whole ``(source_repo, target_version, consumer)`` identity
    and deliberately NOT on the branch name: the two producers name their branches
    differently for the same bump, and it is exactly that cross-producer pair the
    supersession sweep cannot close afterwards.

    A different target version for the same source and consumer is NOT a
    duplicate — that is an older sibling, which is
    ``classify_superseded_prs``'s concern. Refusing it here would suppress the
    legitimate newer bump and freeze the consumer at the older target.

    The lowest PR number wins so the notice names the same incumbent across
    repeated fan-outs when a duplicate pair is already open.
    """
    matches = [pr for pr in open_prs if pr.key == key]
    if not matches:
        return None
    incumbent = min(matches, key=lambda candidate: candidate.number)
    return DuplicateBumpDecision(
        number=incumbent.number,
        branch=incumbent.branch,
        notice=_duplicate_notice(incumbent=incumbent, key=key),
    )


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
        if existing is None or version_lt(left=current_value, right=existing):
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


def _duplicate_payload(*, duplicate: DuplicateBumpDecision | None) -> dict[str, str | int]:
    """Render the dedupe verdict; an empty object means "no duplicate, open the PR"."""
    if duplicate is None:
        return {}
    return {
        "number": duplicate.number,
        "branch": duplicate.branch,
        "notice": duplicate.notice,
    }


def _consumer_from_env() -> str:
    consumer = os.environ.get("CONSUMER")
    if consumer:
        return consumer
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    return repository.rsplit("/", maxsplit=1)[-1]


def _bump_key_from_env(*, consumer: str) -> BumpKey:
    """Build the bump identity the caller is about to open a PR for.

    ``SOURCE_REPO`` and ``TAG`` are the composite Action's own inputs, and the PR
    title it writes embeds them verbatim, so a title parsed back out of
    ``gh pr list`` compares equal to this key by construction.
    """
    return BumpKey(
        source_repo=os.environ.get("SOURCE_REPO", ""),
        target_version=os.environ.get("TAG", ""),
        consumer=consumer,
    )


def main() -> int:
    """Read workflow JSON from env and emit a JSON decision plan.

    ``BUMP_MODE=dedupe`` selects the pre-create dedupe verdict; anything else
    keeps the post-create close plan the supersession sweep already reads.
    """
    consumer = _consumer_from_env()
    open_pr_payload = json.loads(os.environ.get("OPEN_PRS", "[]"))
    open_prs = parse_open_bump_prs(payload=open_pr_payload, consumer=consumer)
    payload: object
    if os.environ.get("BUMP_MODE") == "dedupe":
        payload = _duplicate_payload(
            duplicate=find_duplicate_bump_pr(
                open_prs=open_prs, key=_bump_key_from_env(consumer=consumer)
            )
        )
    else:
        records_payload = cast(list[dict[str, str]], json.loads(os.environ.get("RECORDS", "[]")))
        master_versions = master_versions_from_records(records=records_payload, consumer=consumer)
        decisions = classify_superseded_prs(open_prs=open_prs, master_versions=master_versions)
        payload = _decision_payload(decisions=decisions)
    _ = sys.stdout.write(json.dumps(payload, indent=2))
    _ = sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
