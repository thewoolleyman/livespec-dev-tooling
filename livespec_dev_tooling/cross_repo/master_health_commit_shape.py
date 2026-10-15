"""Read what a master commit's SUBJECT says it is, for the rules that need it.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(the culprit-selection calibration of child C1, work-item
`livespec-dev-tooling-zdqnr2`).

TWO CLASSES OF CULPRIT CANNOT TAKE A PLAIN REVERT, and both announce
themselves in the subject line the fleet's own automation wrote.

A RELEASE-PLEASE RELEASE COMMIT. Reverting it would leave its tag and its
published release disagreeing with the branch: the version bump gone from
master while the tag still names it. The plan's calibration measured 8 of
overseer's 19 self-cleared episodes on release commits, each red on a check a
release commit's SHAPE alone can fail — it touches no `.py`, so a coverage
check can fail on it and fail again on every re-run — so a revert-by-default
reconciler meets this shape in practice rather than in theory.

A TOOLCHAIN PIN BUMP. Reverting it is correct locally and is NOT sufficient:
the pin-freshness sweep re-opens the same bump, so the breakage returns behind
a landed revert. The revert has to carry the version it undid, which is what
`hold_rebump_label` composes. The calibration measured this too — the
dev-tooling v1.37.1 and v1.40.0 bumps broke `Install Python dev deps via uv` in
four repositories at once, each red for 19-22 h until the next release — and
the version is IN the label because a bare "do not re-bump" would freeze the
pin for good, while naming the reverted version still lets a later upstream
release flow.

THE SUBJECTS ARE CONTRACTS, NOT GUESSES. release-please commits
`chore(<scope>): release <version>` (97 of them in this repository's own
history) and the `bump-pin-rewrite` composite Action commits
`chore(deps): bump <source_repo> pin to <tag>`. Both forms are written by
automation this repository owns, which is what makes a subject rule sound here
while being unsound in general — and it is why both are anchored on the WHOLE
subject. A rule matching the word "release" anywhere would read
`chore(docs): release notes for 1.2.3` as a release commit and silently disarm
the revert for an ordinary merge, which is the failure direction nothing
downstream would notice.

No LLM reads these subjects: they are matched by committed regular expressions,
the same discipline the infrastructure outage markers follow.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.cross_repo.fabro_image_pin_rewrite import tag_version_component

__all__: list[str] = ["HOLD_REBUMP_LABEL_PREFIX", "hold_rebump_label", "is_release_commit"]

# `chore` (optionally scoped), then `release`, then the last token — optionally
# preceded by the component name release-please emits in a monorepo. Anchored
# at both ends, so the candidate version must END the subject.
_RELEASE_SUBJECT_RE = re.compile(r"^chore(?:\([^)]*\))?: release (?:\S+ )?(?P<version>\S+)$")

# The subject the `bump-pin-rewrite` composite Action commits, verbatim. Same
# grammar as the bump PR title `bump_pr_supersession` parses, restated because
# that module's copy is private to it and a cross-module private import is
# forbidden; the two drift apart only if the Action's own commit changes, which
# would break that module's PR matching in the same breath.
_PIN_BUMP_SUBJECT_RE = re.compile(r"^chore\(deps\): bump (?P<source>.+) pin to (?P<version>\S+)$")

# The fixed prefix of the hold-rebump label. It is the JOIN between this
# producer and the bump-pin shim that must honour it, so renaming it here
# silently stops that hold from ever being read: a label nobody writes is a
# query that returns no rows rather than an error. Same hazard the sibling
# `master_health_reconcile.NEEDS_ATTENTION_LABEL` records.
HOLD_REBUMP_LABEL_PREFIX = "master-health-hold-rebump"


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


def hold_rebump_label(*, subject: str) -> str | None:
    """The label a revert of this commit must carry, or `None` for any other.

    `None` for every subject that is not a pin bump, so a caller asks ONE
    question instead of two: a label means "this culprit bumped a pin, and here
    is the version a revert of it undoes". Only a pin-bump revert may carry it —
    a label on every revert would read to the shim as a standing hold and
    freeze bumps this reconciler never reverted.
    """
    match = _PIN_BUMP_SUBJECT_RE.match(subject)
    if match is None:
        return None
    return f"{HOLD_REBUMP_LABEL_PREFIX}:{match.group('version')}"
