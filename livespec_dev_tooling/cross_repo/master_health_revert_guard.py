"""Refuse to open a revert that would do harm: clobber a later commit, or revert a revert.

Per `SPECIFICATION/contracts.md` section "Master-health reconciler" (work-item
`livespec-dev-tooling-joqff6`, child of plan `red-master-self-healing`).

THREE REFUSALS, EACH BECAUSE THE REVERT COMMIT RESTORES BYTES RATHER THAN
REPLAYING A DIFF. `master_health_revert_commit` writes the culprit's PARENT
bytes at every path the culprit changed, and nothing narrows that by what landed
afterwards, so the revert is only safe when nothing did:

- a later `master` commit that changed a path the culprit changed would be
  silently overwritten, so the revert is refused and that commit is NAMED for a
  human (the same state `git revert` would stop on as a conflict, which is
  deliberately not resolved by hand: a hand-resolved conflict is new code the
  server-side-revert exemption's byte-identity half would correctly refuse);
- a culprit that is itself a revert is never reverted, because undoing an undo
  re-introduces the original breakage;
- a culprit that a reconciler revert already landed on is not reverted again,
  because `master` is still red despite it and a second revert would only repeat
  the first.

The order is the safety argument: the two identity refusals are matched before
the path overlap, because a landed revert changes the very paths it restored and
would otherwise be reported as an obstruction when the true answer is that this
culprit has already been reverted.

UNRECORDED PATHS REFUSE. A commit whose changed paths the forge did not report
cannot show it does not overlap, so with a later commit in play the revert is
not opened. A culprit at the head has nothing after it to obstruct and needs no
paths.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.master_health_revert_commit import (
    REVERT_HEADLINE_PREFIX,
    revert_headline_marker,
)
from livespec_dev_tooling.cross_repo.master_health_state import MasterCommit

__all__: list[str] = ["revert_refusal"]

# The subject the forge's own revert button writes. A culprit with this subject
# is a revert even though this reconciler did not author it.
_FORGE_REVERT_PREFIX = 'Revert "'

_OVERLAP_PATHS_SHOWN = 3


def _is_revert(*, subject: str) -> bool:
    return subject.startswith((REVERT_HEADLINE_PREFIX, _FORGE_REVERT_PREFIX))


def _overlap_refusal(*, culprit: MasterCommit, later: tuple[MasterCommit, ...]) -> str | None:
    """Why a later commit's changes make the revert unsafe, or `None`."""
    if culprit.changed_paths is None:
        return (
            f"the paths culprit {culprit.sha} changed are not recorded, so a revert "
            "cannot be shown not to overwrite a later commit"
        )
    touched = set(culprit.changed_paths)
    for commit in later:
        if commit.changed_paths is None:
            return (
                f"the paths later commit {commit.sha} changed are not recorded, so a "
                f"revert of {culprit.sha} cannot be shown not to overwrite it"
            )
        shared = sorted(touched & set(commit.changed_paths))
        if shared:
            return (
                f"later commit {commit.sha} changed a path culprit {culprit.sha} changed "
                f"({', '.join(shared[:_OVERLAP_PATHS_SHOWN])}); a revert would overwrite "
                "it, so raise the episode for a human"
            )
    return None


def revert_refusal(*, culprit: MasterCommit, later: tuple[MasterCommit, ...]) -> str | None:
    """Why the revert of `culprit` must not be opened, or `None` when it may.

    `later` are the episode's commits AFTER the culprit, oldest first.
    """
    if _is_revert(subject=culprit.subject):
        return (
            f"culprit {culprit.sha} is itself a revert; reverting a revert would "
            "re-introduce the original breakage, so raise the episode for a human"
        )
    marker = revert_headline_marker(culprit_sha=culprit.sha)
    if any(commit.subject.startswith(marker) for commit in later):
        return (
            f"culprit {culprit.sha} was already reverted once this episode and master "
            "is still red, so raise the episode for a human"
        )
    if not later:
        return None
    return _overlap_refusal(culprit=culprit, later=later)
