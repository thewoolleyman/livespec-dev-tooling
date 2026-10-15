"""Tests for `master_health_commit_shape` — rules over a master commit's subject.

No I/O, no forge, no LLM: every state replayed here is a RECORDED GitHub state
built in-process (work-item `livespec-dev-tooling-zdqnr2`, the culprit-selection
calibration of child C1 in plan `red-master-self-healing`).

THE SUBJECTS ARE THE REAL ONES THE AUTOMATION WRITES, not invented samples:
release-please commits this repository's releases as `chore(master): release
<version>` (its own history carries 97 of them), and the bump-pin composite
Action commits `chore(deps): bump <source_repo> pin to <tag>`. A rule written
against a paraphrase of either would pass its test and miss every real commit.

THE NEGATIVE CASES ARE THE POINT. Both rules route a culprit AWAY from the
plain revert, so a rule that over-matches silently disarms the reconciler for
ordinary merges — the failure mode nothing downstream would notice.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from livespec_dev_tooling.cross_repo.master_health_reconcile import (
    STEP_NEEDS_ATTENTION,
    STEP_OPEN_REVERT,
    reconcile_step,
)
from livespec_dev_tooling.cross_repo.master_health_state import (
    CI_FAILURE,
    CI_SUCCESS,
    RERUN_STILL_RED,
    MasterCommit,
    ReconcileConfig,
    ReconcileState,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "cross_repo"
    / "master_health_commit_shape.py"
)
_MODULE_NAME = "livespec_dev_tooling.cross_repo.master_health_commit_shape"

_GATING_WORKFLOW = "CI"
_COVERAGE_FAILURE = "check-per-file-coverage failed"
_RELEASE_SUBJECT = "chore(master): release 1.97.3"
_ORDINARY_SUBJECT = "feat(cross-repo): an ordinary merge"
_PIN_BUMP_SUBJECT = "chore(deps): bump livespec-dev-tooling pin to v1.97.2"
_HOLD_REBUMP_LABEL = "master-health-hold-rebump:v1.97.2"


def _module() -> ModuleType:
    """Import the subject rules only after asserting their module exists."""
    assert _MODULE_PATH.is_file(), f"missing commit-shape module: {_MODULE_PATH}"
    return importlib.import_module(_MODULE_NAME)


def _config() -> ReconcileConfig:
    return ReconcileConfig(
        target_branch="master",
        infra_outage_markers=("No runner matching",),
        gating_workflow=_GATING_WORKFLOW,
    )


def _commit(
    *,
    sha: str,
    parent_sha: str,
    conclusion: str,
    subject: str,
    pull_request: int | None = None,
) -> MasterCommit:
    return MasterCommit(
        sha=sha,
        parent_sha=parent_sha,
        pull_request=pull_request,
        ci_workflow=_GATING_WORKFLOW,
        ci_conclusion=conclusion,
        failure_signature=_COVERAGE_FAILURE if conclusion == CI_FAILURE else None,
        subject=subject,
    )


def _episode_on(*, subject: str) -> ReconcileState:
    """A one-commit regression episode whose culprit carries `subject`."""
    return ReconcileState(
        head_sha="culprit",
        commits=(
            _commit(
                sha="parent0",
                parent_sha="root",
                conclusion=CI_SUCCESS,
                subject=_ORDINARY_SUBJECT,
            ),
            _commit(
                sha="culprit",
                parent_sha="parent0",
                conclusion=CI_FAILURE,
                subject=subject,
                pull_request=4100,
            ),
        ),
        rerun_outcome=RERUN_STILL_RED,
        revert_pull_request=None,
        open_needs_attention_episodes=(),
        unrelated_failure_signatures=(),
    )


def test_release_please_release_subjects_are_recognised_in_every_spelling() -> None:
    """The component and branch-scope spellings release-please actually writes.

    All three are release-please output: the bare `chore:` form, the
    branch-scoped form this repository's own 97 release commits carry, and the
    monorepo form that names the component before the version.
    """
    module = _module()

    assert module.is_release_commit(subject="chore: release 1.97.3")
    assert module.is_release_commit(subject=_RELEASE_SUBJECT)
    assert module.is_release_commit(subject="chore(main): release livespec-runtime v0.4.0")


def test_a_subject_that_merely_mentions_a_release_is_not_a_release_commit() -> None:
    """Over-matching here would disarm the revert for ordinary merges.

    Each of these is a commit a revert SHOULD be opened for, and every one of
    them carries the word "release". The rule is anchored on the whole subject
    — a release type, then a version — rather than on that word appearing.
    """
    module = _module()

    assert not module.is_release_commit(subject=_ORDINARY_SUBJECT)
    assert not module.is_release_commit(subject="chore(docs): release notes for 1.2.3")
    assert not module.is_release_commit(subject="feat: release the gate at 1.2.3")


def test_a_release_commit_culprit_is_escalated_rather_than_reverted() -> None:
    """The acceptance assertion: a release commit gets a human, not a revert.

    Reverting a `chore(master): release …` commit would leave its tag and its
    published release disagreeing with the branch — the version bump would be
    gone from master while the tag still names it. The plan's calibration found
    8 of overseer's 19 self-cleared episodes on release commits, every one of
    them red on a check a release commit's shape alone can fail, so a
    revert-by-default reconciler would have met this.
    """
    step = reconcile_step(state=_episode_on(subject=_RELEASE_SUBJECT), config=_config())

    assert step.kind == STEP_NEEDS_ATTENTION
    assert step.culprit_pull_request is None
    assert step.episode_key == "master@culprit"


def test_an_ordinary_culprit_is_still_reverted() -> None:
    """The converse: the release rule must not swallow the ordinary episode."""
    step = reconcile_step(state=_episode_on(subject=_ORDINARY_SUBJECT), config=_config())

    assert step.kind == STEP_OPEN_REVERT
    assert step.culprit_pull_request == 4100


def test_the_hold_rebump_rule_is_part_of_this_modules_public_surface() -> None:
    """Asserted on the declared surface so this file's Red fails on an assertion.

    The label is the JOIN with the bump-pin shim, so it has to BE public: a
    rule the shim cannot import is a rule the shim cannot honour.
    """
    module = _module()

    assert "hold_rebump_label" in module.__all__


def test_the_hold_rebump_label_names_the_pin_version_the_revert_undoes() -> None:
    """The version is in the label because the shim needs to know WHICH bump.

    A bare "do not re-bump" label would freeze the pin for good. Naming the
    reverted version lets the shim hold re-bumps TO THAT VERSION while a later
    upstream release still flows — which is the whole remedy the plan's
    calibration asks for: the dev-tooling v1.37.1 and v1.40.0 bumps broke
    `Install Python dev deps via uv` in four repositories at once, and each
    stayed red for 19-22 h because reverting alone would have been re-bumped
    straight back.
    """
    module = _module()

    assert module.hold_rebump_label(subject=_PIN_BUMP_SUBJECT) == _HOLD_REBUMP_LABEL
    assert module.hold_rebump_label(subject=_ORDINARY_SUBJECT) is None
    assert module.hold_rebump_label(subject=_RELEASE_SUBJECT) is None


def test_a_pin_bump_culprits_revert_carries_the_hold_rebump_label() -> None:
    """The acceptance assertion: the opened revert names the reverted version.

    Reverting a pin bump is correct locally and is NOT sufficient on its own —
    the pin-freshness sweep re-opens the same bump, so the breakage returns
    behind a landed revert. The label rides the revert the reconciler opens;
    honouring it inside the bump-pin shim is a separate work-item.
    """
    step = reconcile_step(state=_episode_on(subject=_PIN_BUMP_SUBJECT), config=_config())

    assert step.kind == STEP_OPEN_REVERT
    assert step.culprit_pull_request == 4100
    assert step.hold_rebump_label == _HOLD_REBUMP_LABEL


def test_an_ordinary_culprits_revert_carries_no_hold_rebump_label() -> None:
    """The label is a pin-bump remedy, so no other revert may carry it.

    A label on every revert would be read by the shim as a standing hold and
    would freeze pin bumps the reconciler never reverted.
    """
    step = reconcile_step(state=_episode_on(subject=_ORDINARY_SUBJECT), config=_config())

    assert step.hold_rebump_label is None
