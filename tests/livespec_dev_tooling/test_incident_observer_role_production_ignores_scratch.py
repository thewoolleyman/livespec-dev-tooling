"""Production's observer ignores every scratch-branch job: no action, no state, no read.

livespec-dev-tooling-32qdja. Once `ci.yml` runs on pushes to `incident-scratch/**`
(livespec-dev-tooling-7w757z), GitHub's one webhook delivers those runs'
`workflow_job` events to PRODUCTION's listener, because only production has the
funnel. Production's controller.json names no `target_branch` (the role renders
none; see test_incident_observer_role_production_unchanged.py), so its
installation serves master, and livespec-dev-tooling#3950's configured-branch
filter must answer every scratch job `ignored`: no recovery effect, no write
under the state directory, no canonical-reader call and no forge read, whether
or not production holds a retained master registration.

The scratch branches are the ones the role's scratch instance and its drill
pull requests use, so the test fails if the role's branch naming ever moves
somewhere this filter does not cover.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base
from tests.livespec_dev_tooling import test_incident_observer_role_scratch_instance as scratch
from tests.livespec_dev_tooling.test_incident_observer_target_branch import (
    default,  # noqa: F401 -- #3950's observer world for an installation naming no branch
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-32qdja
_ROLE_BRANCH = base.resolve(variables=scratch.scratch_variables(overrides={}))[
    "incident_observer_target_branch"
]
_SCRATCH_BRANCHES = (_ROLE_BRANCH, "incident-scratch/thhgeg-a", "incident-scratch/thhgeg-b")
_IGNORED = ("202 Accepted", "ignored", "job is outside the configured target branch")


def _state(*, directory: Path) -> dict[str, bytes]:
    """Every file under the observer's state directory, by relative path, with its bytes."""
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _answer(*, reply: tuple[str, dict[str, object]]) -> tuple[object, ...]:
    status, result = reply
    return (status, result["status"], result["reason"])


def test_the_role_renders_production_onto_master_and_the_scratch_branch_off_it() -> None:
    controller = json.loads(
        base.render_installation(variables=base.production_variables())["controller.json"]
    )

    assert "target_branch" not in controller
    assert _ROLE_BRANCH == "incident-scratch/thhgeg-proof"
    assert all(branch.startswith("incident-scratch/") for branch in _SCRATCH_BRANCHES)


@pytest.mark.parametrize("branch", _SCRATCH_BRANCHES)
def test_production_with_no_registration_ignores_a_scratch_job_and_writes_nothing(
    default,  # noqa: F811 -- the imported fixture
    branch: str,
) -> None:
    assert default.installation.target_branch == "master"

    reply = default.leaf(branch=branch)

    assert _answer(reply=reply) == _IGNORED
    assert default.effects == []
    assert default.reader_calls == []
    assert default.reads == []
    assert not default.installation.state.exists(), "an ignored job creates no state"


@pytest.mark.parametrize("branch", _SCRATCH_BRANCHES)
def test_production_holding_a_master_registration_ignores_scratch_jobs_and_keeps_its_state(
    default,  # noqa: F811 -- the imported fixture
    branch: str,
) -> None:
    assert default.bind()[1]["status"] == "admitted"
    before = _state(directory=default.installation.state)
    reader_calls, reads = len(default.reader_calls), len(default.reads)

    for delivery in ("scratch-delivery-1", "scratch-delivery-2"):
        assert _answer(reply=default.leaf(branch=branch, delivery=delivery)) == _IGNORED

    assert default.effects == []
    assert _state(directory=default.installation.state) == before
    assert (len(default.reader_calls), len(default.reads)) == (reader_calls, reads)
    assert default.registration().branch == "master"
    # Production still acts on its own branch afterwards.
    _, result = default.leaf(branch="master", delivery="master-delivery")
    assert result["status"] in {"pending", "completed"}, result
    assert default.settled(action_id=result["action_id"])["status"] == "completed"
    assert [intent.registration.branch for intent in default.effects] == ["master"]
