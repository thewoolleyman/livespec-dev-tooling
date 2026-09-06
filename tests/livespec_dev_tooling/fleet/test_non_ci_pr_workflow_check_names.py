"""A required check reported by a non-ci.yml pull_request(_target) workflow is real.

The phantom-check rule (`assert_branch_protection` →
`_protection_problems` → `member_ci_check_names`) used to derive the set of
legitimate required-check reporters from ci.yml ALONE. A fleet member may
require a status check reported by a workflow kept deliberately OUTSIDE
ci.yml — a base-branch-side gate that runs the BASE branch's definition
against an untrusted head via `pull_request_target` (the shape
`livespec-console-beads-fabro`'s `gate-wiring-required.yml` uses to require
`upstream-dep-gate-wired`). A ci.yml-only view read that check as a phantom
that can never report, BLOCKED every dev-tooling push at the pre-push fleet
gate reading live cross-repo state, and could never be satisfied by any
ci.yml change (livespec-dev-tooling-uyhtih).

The behaviour, from `assert_branch_protection`'s own docstring: aligned
means every required check matches a ci.yml matrix leg, a top-level ci.yml
job, OR a job in any other `.github/workflows/*` file triggered by
`pull_request`/`pull_request_target`; a required check matching NONE of
those is still a phantom.

⛔ THE NEGATIVE CONTROLS ARE NOT OPTIONAL. If widening to other workflows
blinded the row to a real phantom — or admitted a workflow that does NOT
run on pull requests — the row would have stopped distinguishing anything.
`test_required_check_no_workflow_reports_is_still_a_phantom` and
`test_a_non_pull_request_workflow_supplies_no_reporters` are the inputs
that must still produce a finding.
"""

from __future__ import annotations

import json

from _gh_railway import lift_gh

from livespec_dev_tooling.checks._ci_job_names import workflow_triggers_pull_request
from livespec_dev_tooling.fleet._ci_workflow_source import _extra_workflow_paths
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
)
from livespec_dev_tooling.fleet._rows_github import assert_branch_protection

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_CI_WORKFLOW = ".github/workflows/ci.yml"
_GATE_WORKFLOW = ".github/workflows/gate-wiring-required.yml"
_RELEASE_WORKFLOW = ".github/workflows/release.yml"
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_PROTECTION_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/branches/master/protection")


def _contents_args(path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


# A single-gate ci.yml: one top-level `ci-green` aggregate job (the required
# context ci.yml legitimately reports).
_CI_YML = "name: CI\njobs:\n  ci-green:\n    name: ci-green\n"
# The console gate-wiring shape: a `pull_request_target` workflow OUTSIDE
# ci.yml whose job `upstream-dep-gate-wired` reports a real required check.
_GATE_YML = (
    "name: gate-wiring\n"
    "on:\n"
    "  pull_request_target:\n"
    "    types: [opened, synchronize, reopened]\n"
    "jobs:\n"
    "  upstream-dep-gate-wired:\n"
    "    name: upstream-dep-gate-wired\n"
)
# A push-only workflow: its job `publish` is NEVER a pull-request status
# check, so requiring `publish` is still a phantom.
_RELEASE_YML = (
    "name: release\non:\n  push:\n    branches: [master]\njobs:\n  publish:\n    name: publish\n"
)


def _context(
    *,
    tree_paths: list[str],
    contents: dict[str, GhResult],
    contexts: list[str],
) -> FleetContext:
    tree = {"tree": [{"path": p, "mode": "100644"} for p in tree_paths], "truncated": False}
    protection = {
        "enforce_admins": {"enabled": True},
        "required_status_checks": {"strict": False, "contexts": contexts},
    }
    table = {
        _TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree), stderr=""),
        _PROTECTION_ARGS: GhResult(returncode=0, stdout=json.dumps(protection), stderr=""),
    }
    for path, result in contents.items():
        table[_contents_args(path)] = result

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def _ok(text: str) -> GhResult:
    return GhResult(returncode=0, stdout=text, stderr="")


def test_pull_request_target_gate_job_is_a_legitimate_required_check() -> None:
    """CRITERION 1 — a check reported by a non-ci.yml PR-target workflow is real."""
    ctx = _context(
        tree_paths=[_CI_WORKFLOW, _GATE_WORKFLOW],
        contents={_CI_WORKFLOW: _ok(_CI_YML), _GATE_WORKFLOW: _ok(_GATE_YML)},
        contexts=["ci-green", "upstream-dep-gate-wired"],
    )

    assert assert_branch_protection(ctx=ctx, member=_MEMBER) == RowPass()


def test_required_check_no_workflow_reports_is_still_a_phantom() -> None:
    """CRITERION 2 + 4 — an unreported check is still drift; the hint names both sources."""
    ctx = _context(
        tree_paths=[_CI_WORKFLOW, _GATE_WORKFLOW],
        contents={_CI_WORKFLOW: _ok(_CI_YML), _GATE_WORKFLOW: _ok(_GATE_YML)},
        contexts=["upstream-dep-gate-wired", "ghost-check"],
    )

    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "ghost-check" in outcome.message
    # The recognized PR-target reporter is NOT flagged.
    assert "upstream-dep-gate-wired" not in outcome.message
    # The remediation hint names BOTH places a check can legitimately come from.
    assert "matches no ci.yml matrix leg or top-level job" in outcome.message
    assert "pull_request_target" in outcome.message


def test_a_non_pull_request_workflow_supplies_no_reporters() -> None:
    """A push-only workflow's job is not a PR status check, so requiring it is a phantom."""
    ctx = _context(
        tree_paths=[_CI_WORKFLOW, _RELEASE_WORKFLOW],
        contents={_CI_WORKFLOW: _ok(_CI_YML), _RELEASE_WORKFLOW: _ok(_RELEASE_YML)},
        contexts=["publish"],
    )

    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "publish" in outcome.message


def test_an_unread_supplementary_workflow_does_not_block_a_ci_yml_verdict() -> None:
    """A can't-read of a SUPPLEMENTARY workflow degrades to ci.yml alone, not a skip.

    Only ci.yml (the canonical reporter) escalates a can't-read to a
    whole-comparison SKIP. An unreadable auxiliary workflow simply has its
    names uncounted — a member green on ci.yml still passes, and a check the
    unread workflow WOULD have reported falls back to the pre-uyhtih phantom
    finding (over-strict, never a false pass).
    """
    # ci.yml covers `ci-green`; gate-wiring is in the tree but unreadable.
    green = _context(
        tree_paths=[_CI_WORKFLOW, _GATE_WORKFLOW],
        contents={_CI_WORKFLOW: _ok(_CI_YML)},
        contexts=["ci-green"],
    )
    assert assert_branch_protection(ctx=green, member=_MEMBER) == RowPass()

    # The check only the UNREAD workflow would report falls back to a phantom.
    degraded = _context(
        tree_paths=[_CI_WORKFLOW, _GATE_WORKFLOW],
        contents={_CI_WORKFLOW: _ok(_CI_YML)},
        contexts=["upstream-dep-gate-wired"],
    )
    outcome = assert_branch_protection(ctx=degraded, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "upstream-dep-gate-wired" in outcome.message


def test_workflow_triggers_pull_request_recognises_every_on_shape() -> None:
    """The `on:` trigger parser across inline, flow-list, block, quoted, and absent forms."""
    assert workflow_triggers_pull_request(source="on: pull_request\n") is True
    assert workflow_triggers_pull_request(source="on: [push, pull_request]\n") is True
    assert workflow_triggers_pull_request(source=_GATE_YML) is True
    # A bare `on:` with a trailing comment, events on the indented lines below.
    assert workflow_triggers_pull_request(source="on: # triggers\n  pull_request:\n") is True
    # Some YAML linters rewrite the truthy `on` key to a quoted form.
    assert workflow_triggers_pull_request(source='"on": pull_request_target\n') is True


def test_workflow_triggers_pull_request_rejects_workflows_off_the_pull_request() -> None:
    """Inline non-PR, block non-PR ended by a top-level key, and no `on:` at all."""
    assert workflow_triggers_pull_request(source="on: push\n") is False
    assert workflow_triggers_pull_request(source=_RELEASE_YML) is False
    assert workflow_triggers_pull_request(source="jobs:\n  build:\n    name: build\n") is False


def test_extra_workflow_paths_selects_top_level_yml_yaml_other_than_ci() -> None:
    """Only `.yml`/`.yaml` files directly under the workflows dir, ci.yml excluded."""
    paths = frozenset(
        {
            _CI_WORKFLOW,
            _GATE_WORKFLOW,
            ".github/workflows/release.yaml",
            ".github/workflows/nested/deeper.yml",
            ".github/workflows/notes.txt",
            "README.md",
        }
    )

    assert _extra_workflow_paths(tree_paths=paths) == {
        _GATE_WORKFLOW,
        ".github/workflows/release.yaml",
    }
