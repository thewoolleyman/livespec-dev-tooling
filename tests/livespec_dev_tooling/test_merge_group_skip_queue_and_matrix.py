"""merge_group_skip: a queued unbuilt entry and a literal-named matrix job fail closed no more.

Work-item livespec-dev-tooling-jwz2ls. Defect 1: an entry still queued behind the
group has a null `headCommit`, which must not abort the verdict. Defect 2: a job
with a literal `name:` and a `strategy.matrix` reports its legs as the name
followed by the matrix values in parentheses, and the verdict must require those
suffixed names. The forge is a dict-backed fake, as in `test_merge_group_skip`.
"""

from __future__ import annotations

from typing import Any

import pytest

from livespec_dev_tooling.merge_group_skip import ForgeReadError, GroupInputs, SkipVerdict, decide

__all__: list[str] = []

_WORKFLOW = """name: CI
jobs:
  merge-group-guard:
    name: merge-group-guard
  release-gate:
    name: release-gate-pre-tag
    strategy:
      matrix:
        target:
          - check-mutation
          - check-no-todo-registry
  ci-green:
    name: ci-green
    needs: [release-gate]
"""
_TWO_AXES = _WORKFLOW.replace(
    "        target:\n",
    "        os: [linux, mac]\n        target:\n",
)
_INCLUDE = _WORKFLOW.replace(
    "        target:\n          - check-mutation\n          - check-no-todo-registry\n",
    "        include:\n          - target: extra\n",
)
_LEGS = (
    "release-gate-pre-tag (check-mutation)",
    "release-gate-pre-tag (check-no-todo-registry)",
    "ci-green",
)
_INPUTS = GroupInputs(
    repo="o/r", head_sha="G", base_sha="B", base_ref="refs/heads/master", disabled=False
)


class _Forge:
    def __init__(self, *, world: dict[str, Any]) -> None:
        self.world = world

    def _read(self, *, key: str) -> Any:
        if key not in self.world:
            raise ForgeReadError(key)
        return self.world[key]

    def get(self, *, path: str) -> dict[str, Any]:
        return self._read(key=path)

    def check_runs(self, *, sha: str) -> list[dict[str, Any]]:
        return self._read(key=f"runs:{sha}")

    def queue_entries(self, *, branch: str) -> list[dict[str, Any]]:
        return self._read(key=f"queue:{branch}")

    def workflow_text(self, *, ref: str) -> str:
        return self._read(key=f"workflow:{ref}")


def _runs(*, names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "id": index + 10,
            "name": name,
            "conclusion": "success",
            "app": {"slug": "github-actions"},
            "pull_requests": [{"number": 7, "base": {"ref": "master"}}],
        }
        for index, name in enumerate(names)
    ]


def _world(*, workflow: str = _WORKFLOW, names: tuple[str, ...] = _LEGS) -> dict[str, Any]:
    entry = {
        "position": 1,
        "headCommit": {"oid": "G"},
        "baseCommit": {"oid": "B"},
        "pullRequest": {"number": 7, "headRefOid": "P", "baseRefName": "master"},
    }
    return {
        "queue:master": [entry],
        "repos/o/r/git/commits/G": {"tree": {"sha": "T"}},
        "repos/o/r/git/commits/P": {"tree": {"sha": "T"}},
        "repos/o/r/compare/B...P": {"status": "ahead"},
        "runs:P": _runs(names=names),
        f"repos/o/r/actions/jobs/{10 + names.index('ci-green')}": {
            "steps": [
                {"name": "Report members omitted-by-incident-policy", "conclusion": "skipped"}
            ]
        },
        "workflow:B": workflow,
    }


def _verdict(*, world: dict[str, Any]) -> SkipVerdict:
    return decide(inputs=_INPUTS, forge=_Forge(world=world))


def test_an_unbuilt_entry_with_a_null_head_commit_behind_the_group_still_skips() -> None:
    world = _world()
    behind = {**world["queue:master"][0], "position": 2, "headCommit": None}
    world["queue:master"].append(behind)
    verdict = _verdict(world=world)
    assert verdict.skip is True, verdict.reason


def test_a_first_entry_with_a_null_head_commit_is_not_the_group() -> None:
    world = _world()
    world["queue:master"][0]["headCommit"] = None
    verdict = _verdict(world=world)
    assert verdict.skip is False
    assert "the group is not exactly the first queue entry" in verdict.reason


def test_every_suffixed_leg_of_a_literal_named_matrix_job_on_the_head_skips() -> None:
    verdict = _verdict(world=_world())
    assert verdict.skip is True, verdict.reason


@pytest.mark.parametrize("missing", _LEGS[:2])
def test_a_missing_suffixed_leg_of_a_literal_named_matrix_job_refuses(missing: str) -> None:
    names = tuple(name for name in _LEGS if name != missing)
    verdict = _verdict(world=_world(names=names))
    assert verdict.skip is False
    assert missing in verdict.reason


def test_the_bare_job_name_alone_does_not_stand_for_its_matrix_legs() -> None:
    names = ("release-gate-pre-tag", "ci-green")
    verdict = _verdict(world=_world(names=names))
    assert verdict.skip is False
    assert "release-gate-pre-tag (check-mutation)" in verdict.reason


def test_two_matrix_axes_render_in_the_order_the_workflow_declares_them() -> None:
    names = (
        "release-gate-pre-tag (linux, check-mutation)",
        "release-gate-pre-tag (linux, check-no-todo-registry)",
        "release-gate-pre-tag (mac, check-mutation)",
        "release-gate-pre-tag (mac, check-no-todo-registry)",
        "ci-green",
    )
    verdict = _verdict(world=_world(workflow=_TWO_AXES, names=names))
    assert verdict.skip is True, verdict.reason


def test_a_matrix_the_reader_does_not_model_fails_closed() -> None:
    verdict = _verdict(world=_world(workflow=_INCLUDE))
    assert verdict.skip is False
    assert "a required leg name cannot be derived" in verdict.reason
