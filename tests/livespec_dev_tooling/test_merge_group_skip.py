"""merge_group_skip: a merge group skips the suite only on proven tree equality.

Work-item livespec-dev-tooling-ymog6r. Every case builds the one world in which
the skip is allowed (`_world`), then breaks exactly one condition and asserts the
verdict falls back to a full run. The forge is a dict-backed fake: a path the
world does not hold raises `ForgeReadError`, as an unanswered read does.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from livespec_dev_tooling import merge_group_skip
from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.merge_group_skip import (
    ForgeReadError,
    GroupInputs,
    SkipVerdict,
    decide,
    main,
)

__all__: list[str] = []

_WORKFLOW = """name: CI
jobs:
  merge-group-guard:
    name: merge-group-guard
  check-lint:
    name: ${{ matrix.target }}
    strategy:
      matrix:
        target:
          - check-lint
          - check-format
  check-batch:
    name: check-batch
  ci-green:
    name: ci-green
    needs: [check-lint, check-batch]
"""
_UNDERIVABLE_WORKFLOW = _WORKFLOW.replace("name: check-batch", "name: ${{ inputs.x }}")
_NAMES = ("check-lint", "check-format", "check-batch", "ci-green")
_INPUTS = GroupInputs(
    repo="o/r", head_sha="G", base_sha="B", base_ref="refs/heads/master", disabled=False
)


def _run(
    *, name: str, run_id: int, conclusion: str | None = "success", **over: Any
) -> dict[str, Any]:
    run: dict[str, Any] = {
        "id": run_id,
        "name": name,
        "conclusion": conclusion,
        "app": {"slug": "github-actions"},
        "pull_requests": [{"number": 7, "base": {"ref": "master"}}],
    }
    run.update(over)
    return run


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


def _world() -> dict[str, Any]:
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
        "runs:P": [_run(name=name, run_id=index + 10) for index, name in enumerate(_NAMES)],
        "repos/o/r/actions/jobs/13": {
            "steps": [
                {"name": "Report members omitted-by-incident-policy", "conclusion": "skipped"}
            ]
        },
        "workflow:B": _WORKFLOW,
    }


def _verdict(*, world: dict[str, Any], inputs: GroupInputs = _INPUTS) -> SkipVerdict:
    return decide(inputs=inputs, forge=_Forge(world=world))


def test_every_condition_holding_skips_the_suite() -> None:
    verdict = _verdict(world=_world())
    assert verdict.skip is True, verdict.reason
    assert "tree T equals PR #7 head P" in verdict.reason


def test_the_latest_run_of_a_name_decides_and_an_older_failure_is_ignored() -> None:
    world = _world()
    world["runs:P"] = [
        _run(name="check-lint", run_id=1, conclusion="failure"),
        *world["runs:P"],
        _run(name="check-format", run_id=2, conclusion="failure"),
    ]
    assert _verdict(world=world).skip is True


def _queue_behind(*, world: dict[str, Any]) -> None:
    second = {**world["queue:master"][0], "position": 2, "headCommit": {"oid": "G2"}}
    world["queue:master"].append(second)
    world["queue:master"][0]["headCommit"] = {"oid": "G0"}
    world["queue:master"][1]["headCommit"] = {"oid": "G"}


def _first_entry(*, world: dict[str, Any]) -> dict[str, Any]:
    return world["queue:master"][0]


def _set_runs(*, world: dict[str, Any], runs: list[dict[str, Any]]) -> None:
    world["runs:P"] = runs


def _runs_except(*, name: str) -> list[dict[str, Any]]:
    return [_run(name=n, run_id=i + 10) for i, n in enumerate(_NAMES) if n != name]


_BREAKERS: dict[str, Callable[[dict[str, Any]], None]] = {
    "group behind another entry": lambda w: _queue_behind(world=w),
    "group head is not a queue entry": lambda w: _first_entry(world=w).update(
        headCommit={"oid": "OTHER"}
    ),
    "entry base moved": lambda w: _first_entry(world=w).update(baseCommit={"oid": "B2"}),
    "pr retargeted": lambda w: _first_entry(world=w)["pullRequest"].update(baseRefName="dev"),
    "head behind base": lambda w: w.update({"repos/o/r/compare/B...P": {"status": "behind"}}),
    "head diverged from base": lambda w: w.update(
        {"repos/o/r/compare/B...P": {"status": "diverged"}}
    ),
    "trees differ": lambda w: w.update({"repos/o/r/git/commits/G": {"tree": {"sha": "T2"}}}),
    "required run failed": lambda w: _set_runs(
        world=w,
        runs=[
            *_runs_except(name="check-batch"),
            _run(name="check-batch", run_id=30, conclusion="failure"),
        ],
    ),
    "required run still running": lambda w: _set_runs(
        world=w,
        runs=[
            *_runs_except(name="check-format"),
            _run(name="check-format", run_id=30, conclusion=None),
        ],
    ),
    "matrix leg missing": lambda w: _set_runs(world=w, runs=_runs_except(name="check-format")),
    "ci-green missing": lambda w: _set_runs(world=w, runs=_runs_except(name="ci-green")),
    "success from another app": lambda w: _set_runs(
        world=w,
        runs=[
            *_runs_except(name="check-lint"),
            _run(name="check-lint", run_id=30, app={"slug": "other"}),
        ],
    ),
    "run bound to another pull request": lambda w: _set_runs(
        world=w,
        runs=[
            *_runs_except(name="check-lint"),
            _run(
                name="check-lint",
                run_id=30,
                pull_requests=[{"number": 8, "base": {"ref": "master"}}],
            ),
        ],
    ),
    "run bound to another base": lambda w: _set_runs(
        world=w,
        runs=[
            *_runs_except(name="check-lint"),
            _run(
                name="check-lint", run_id=30, pull_requests=[{"number": 7, "base": {"ref": "dev"}}]
            ),
        ],
    ),
    "newer failure supersedes an older success": lambda w: _set_runs(
        world=w, runs=[*w["runs:P"], _run(name="check-lint", run_id=99, conclusion="failure")]
    ),
    "incident-omitted set reported": lambda w: w.update(
        {
            "repos/o/r/actions/jobs/13": {
                "steps": [
                    {"name": "Report members omitted-by-incident-policy", "conclusion": "success"}
                ]
            }
        }
    ),
    "omitted-set step absent": lambda w: w.update({"repos/o/r/actions/jobs/13": {"steps": []}}),
    "workflow leg underivable": lambda w: w.update({"workflow:B": _UNDERIVABLE_WORKFLOW}),
    "queue unreadable": lambda w: w.pop("queue:master"),
    "compare unreadable": lambda w: w.pop("repos/o/r/compare/B...P"),
    "payload of unexpected shape": lambda w: w.update({"queue:master": [{"position": "x"}]}),
}


@pytest.mark.parametrize("breaker", sorted(_BREAKERS))
def test_any_broken_condition_runs_the_full_suite(breaker: str) -> None:
    world = _world()
    _BREAKERS[breaker](world)
    assert _verdict(world=world).skip is False


def test_the_kill_switch_forces_a_full_run_without_reading_the_forge() -> None:
    inputs = GroupInputs(
        repo="o/r", head_sha="G", base_sha="B", base_ref="refs/heads/master", disabled=True
    )
    verdict = _verdict(world={}, inputs=inputs)
    assert (verdict.skip, verdict.reason) == (
        False,
        "LIVESPEC_MERGE_GROUP_SKIP_DISABLED is true",
    )


class _ScriptedGh:
    """gh_read stand-in answering by what the argument tail contains."""

    def __init__(self, *, answers: dict[str, str]) -> None:
        self.answers = answers
        self.calls: list[list[str]] = []

    def __call__(self, *, args: list[str], **_kwargs: Any) -> GhRead:
        self.calls.append(args)
        for needle, out in self.answers.items():
            if needle in " ".join(args):
                return GhRead(returncode=0, stdout=out, stderr="")
        return GhRead(returncode=1, stdout="", stderr="HTTP 404")


def test_the_gh_forge_reads_each_surface_through_the_budgeted_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_pages = json.dumps([{"check_runs": [{"id": 1}]}, {"check_runs": [{"id": 2}]}])
    nodes = {"data": {"repository": {"mergeQueue": {"entries": {"nodes": [{"position": 1}]}}}}}
    gh = _ScriptedGh(
        answers={
            "check-runs": runs_pages,
            "graphql": json.dumps(nodes),
            "contents/.github/workflows/ci.yml?ref=B": "WORKFLOW",
            "compare/B...P": json.dumps({"status": "ahead"}),
        }
    )
    monkeypatch.setattr(merge_group_skip, "gh_read", gh)
    forge = merge_group_skip.GhForge(repo="o/r")
    assert forge.get(path="repos/o/r/compare/B...P") == {"status": "ahead"}
    assert forge.check_runs(sha="P") == [{"id": 1}, {"id": 2}]
    assert forge.queue_entries(branch="master") == [{"position": 1}]
    assert forge.workflow_text(ref="B") == "WORKFLOW"
    assert len(gh.calls) == 4


def test_a_failing_gh_read_is_a_forge_read_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(merge_group_skip, "gh_read", _ScriptedGh(answers={}))
    forge = merge_group_skip.GhForge(repo="o/r")
    with pytest.raises(ForgeReadError, match="HTTP 404"):
        forge.get(path="repos/o/r/anything")


def test_main_prints_the_verdict_and_always_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = _world()

    def fake_forge(*, repo: str) -> _Forge:
        _ = repo
        return _Forge(world=world)

    monkeypatch.setattr(merge_group_skip, "GhForge", fake_forge)
    env = {
        "GITHUB_REPOSITORY": "o/r",
        "MG_HEAD_SHA": "G",
        "MG_BASE_SHA": "B",
        "MG_BASE_REF": "refs/heads/master",
    }
    assert main(env=env) == 0
    assert capsys.readouterr().out.startswith("skip=true\n")
    assert main(env={**env, "LIVESPEC_MERGE_GROUP_SKIP_DISABLED": " TRUE "}) == 0
    assert capsys.readouterr().out.startswith("skip=false\n")
    assert main(env={}) == 0
    out = capsys.readouterr().out
    assert out.startswith("skip=false\n") and "GITHUB_REPOSITORY" in out
