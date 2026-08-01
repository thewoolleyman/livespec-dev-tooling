"""_bump_pr_list — read the member's open bump PRs, and say when it could not be read.

Split out of `_rows_pin_currency` to keep that file under the 250-LLOC hard
ceiling once `open_bump_prs_for` grew a failure track — the same
private-sibling split as `_pin_walk_failure` and `_ci_matrix_parse`. The
leading underscore marks it a private sibling: it is neither a canonical
check slug nor a mirror-paired module.

WHAT THIS MODULE EXISTS TO STOP BEING SAYABLE. `SPECIFICATION/contracts.md`
§"Pin-currency severity policy" partitions a STALE pin into exactly two
classes and calls the partition EXHAUSTIVE, "because a bump PR for the
latest release either is open or is not". That is true of the WORLD and
false of a RUN: a run that could not read the PR list has established
neither class. Before this split both persisting-gap sites spelled the
unreadable list as `None` and read it as "no bump PR is open" — the
NEVER-FIRED class — so a member whose PR list never answered was reported
under a class the run had not established, which the same section forbids
("naming ... WHICH of the two classes applies").
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.cross_repo.bump_pr_supersession import (  # noqa: E402
    OpenBumpPullRequest,
    parse_open_bump_prs,
)
from livespec_dev_tooling.cross_repo.pin_staleness import denotes_same_release  # noqa: E402
from livespec_dev_tooling.fleet._context import FleetContext, FleetMember  # noqa: E402

__all__: list[str] = [
    "BumpPrListUnreadable",
    "bump_pr_class_undecidable_clause",
    "open_bump_prs_for",
    "persisting_bump_pr_number",
]


@dataclass(frozen=True, kw_only=True)
class BumpPrListUnreadable:
    """This run did not obtain `repo`'s open-PR list, so neither class is established.

    ONE inhabitant, not two, because both arms call for the SAME response —
    do not escalate, do not name a class, tell the operator the read failed.
    `detail` distinguishes them for the human without inventing a
    discriminated union no consumer branches on. Contrast
    `_pin_walk_failure`, whose two arms genuinely diverge (a can't-read
    SKIPS, a can't-parse is a FINDING) and therefore need distinct types.
    """

    repo: str
    detail: str


def open_bump_prs_for(
    *, ctx: FleetContext, member: FleetMember
) -> IOResult[list[OpenBumpPullRequest], BumpPrListUnreadable]:
    """The member's open bump PRs, or the reason this run could not list them.

    The failure track is NOT an escalation. Per
    `SPECIFICATION/contracts.md` §"Pin-currency severity policy", "a
    can't-READ never escalates" (livespec-dev-tooling-6ge) — both callers
    fold this onto the SAME warning severity a plain stale pin carries.
    The `6ge` principle is about SEVERITY, not representation: preserving
    it costs nothing here, and spelling "unreadable" the same as "no bump
    PR" is what made the never-fired class claimable from a read that
    never happened.

    TWO conditions leave the success track, and the second is not spelled
    `None` anywhere upstream:

    - `api_object` yields None — `gh` never ran, exited non-zero, or
      answered with unparseable bytes. It records the cause on
      `ctx.read_failures` either way.
    - the payload parses but is NOT a list. The `pulls` endpoint's body
      exists SOLELY to be the list of open PRs, so a JSON object there
      (GitHub's error shape) is a non-answer, not an empty answer.
      `parse_open_bump_prs` returns `[]` for it — correct for that
      function, whose contract is "skip unrelated PRs", and a fail-open
      here, where `[]` means "the mechanism never fired".
    """
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{member.repo}/pulls?state=open&per_page=100")
    if payload is None:
        return IOFailure(
            BumpPrListUnreadable(
                repo=member.repo,
                detail="the open-PR read did not answer; see this run's read failures",
            )
        )
    if not isinstance(payload, list):
        return IOFailure(
            BumpPrListUnreadable(
                repo=member.repo,
                detail=(
                    "the open-PR endpoint answered with a "
                    f"{type(payload).__name__}, not a list of pull requests"
                ),
            )
        )
    items = cast("list[object]", payload)
    return IOSuccess(
        parse_open_bump_prs(payload=_normalized_rest_prs(payload=items), consumer=member.repo)
    )


def _normalized_rest_prs(*, payload: list[object]) -> object:
    """Adapt REST `pulls` items to the `gh pr list --json` shape the parser reads.

    The parser consumes `headRefName`; the REST endpoint nests the same
    value at `head.ref`. Without this mapping every REST item is
    silently skipped and the persisting-gap conjunction can never fire —
    a vacuous non-implementation.
    """
    normalized: list[object] = []
    for item in payload:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        entry = dict(cast("dict[str, object]", item))
        head = entry.get("head")
        if "headRefName" not in entry and isinstance(head, dict):
            ref = cast("dict[str, object]", head).get("ref")
            if isinstance(ref, str):
                entry["headRefName"] = ref
        normalized.append(entry)
    return normalized


def persisting_bump_pr_number(
    *,
    open_prs: list[OpenBumpPullRequest],
    source_repo: str,
    latest: str,
) -> int | None:
    """The open bump PR that would fix this stale pin, if one exists.

    A stale pin WITH an open bump PR targeting the latest release is a
    PERSISTING gap — the self-heal mechanism already fired and could not
    land — which is the conjunction `livespec-dh9r` escalates to error.
    An open bump PR for an older tag or another source does not qualify:
    it does not prove the mechanism fired for the CURRENT release.

    `open_prs` is a LIST, never `None`. It was `list[...] | None` while
    `open_bump_prs_for` collapsed its read failure, and the `None` arm
    carried that INHERITED failure into a return value the callers read
    as a plain absence. With the failure lifted to its own track the
    remaining `None` has exactly one meaning — no open bump PR qualifies
    — which is an ordinary answer both callers act on.
    """
    for pr in open_prs:
        if pr.key.source_repo == source_repo and denotes_same_release(
            pinned_tag=pr.key.target_version, release_tag=latest
        ):
            return pr.number
    return None


def bump_pr_class_undecidable_clause(*, failure: BumpPrListUnreadable) -> str:
    """The clause BOTH persisting-gap sites append when neither class is established.

    One renderer rather than two literals, because the two sites are
    required to agree: `_rows_files`'s own comment already says "both
    persisting-gap sites must move together or the promotion is
    half-armed", and a second copy of this sentence is how they drift.
    """
    return (
        "which staleness class applies is UNDETERMINED "
        f"(open-PR list unread for {failure.repo}: {failure.detail})"
    )
