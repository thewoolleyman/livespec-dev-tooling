"""Read what a master commit's SUBJECT says it is, for the rules that need it.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(the culprit-selection calibration of child C1, work-item
`livespec-dev-tooling-zdqnr2`).

A RELEASE-PLEASE RELEASE COMMIT CANNOT TAKE A PLAIN REVERT. Reverting it would
leave its tag and its published release disagreeing with the branch: the
version bump gone from master while the tag still names it. The plan's
calibration measured 8 of overseer's 19 self-cleared episodes on release
commits, each red on a check a release commit's SHAPE alone can fail — it
touches no `.py`, so a coverage check can fail on it and fail again on every
re-run — so a revert-by-default reconciler meets this shape in practice rather
than in theory.

THE SUBJECT IS A CONTRACT, NOT A GUESS. release-please commits
`chore(<scope>): release <version>`, and this repository's own history carries
97 of them. The form is written by automation this repository owns, which is
what makes a subject rule sound here while being unsound in general — and it is
why the rule is anchored on the WHOLE subject. A rule matching the word
"release" anywhere would read `chore(docs): release notes for 1.2.3` as a
release commit and silently disarm the revert for an ordinary merge, which is
the failure direction nothing downstream would notice.

No LLM reads these subjects: they are matched by committed regular expressions,
the same discipline the infrastructure outage markers follow.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.cross_repo.fabro_image_pin_rewrite import tag_version_component

__all__: list[str] = ["is_release_commit"]

# `chore` (optionally scoped), then `release`, then the last token — optionally
# preceded by the component name release-please emits in a monorepo. Anchored
# at both ends, so the candidate version must END the subject.
_RELEASE_SUBJECT_RE = re.compile(r"^chore(?:\([^)]*\))?: release (?:\S+ )?(?P<version>\S+)$")


def is_release_commit(*, subject: str) -> bool:
    """Whether this subject is one release-please wrote to publish a release.

    The semver grammar itself is NOT respelled here: this repository keeps
    exactly one definition of it, and `tag_version_component` is its public
    face (`tests/livespec_dev_tooling/cross_repo/test_pin_staleness.py` fails a
    second copy). That owner's grammar requires the `v` a tag carries, while a
    release-please subject's version is bare, so the candidate is normalised to
    the tag spelling before being handed over — one grammar, asked the one
    question that matters: does this trailing token denote a version at all.
    """
    match = _RELEASE_SUBJECT_RE.match(subject)
    if match is None:
        return False
    candidate = match.group("version")
    return tag_version_component(tag=f"v{candidate.removeprefix('v')}") is not None
