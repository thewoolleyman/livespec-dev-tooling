"""The cumulative-scope base is the attempt's branch point, not the pull request's base."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_hook_scope as module
from livespec_dev_tooling.incident_execution import ExecutionContext, OperationIdentity

BRANCH_POINT = "a" * 40
PR_BASE = "9" * 40
MARKER = "# EXPEDITED_INCIDENT_RESPONSE flag: incident\nvalue = 2\n"
OTHER_OUTPUT = {"ls-tree": "app.py", "rev-parse": BRANCH_POINT}


def context() -> ExecutionContext:
    return ExecutionContext(
        mode="expedited-repair",
        invocation="ordinary",
        identity=OperationIdentity(
            incident_item_id="incident",
            attempt_id="attempt",
            phase="repair",
            repository="owner/repo",
            base_sha=PR_BASE,
            head_sha="b" * 40,
            operation_id="operation",
        ),
    )


def moved_master_attempt() -> dict[str, Any]:
    """A pr-bound attempt whose base is the PR base while master has since moved."""
    return dict(
        pr_number=1,
        head="b" * 40,
        base=PR_BASE,
        original_paths=["app.py"],
        carrier=dict(
            state="pr-bound",
            target_ref="refs/heads/repair",
            input_parent=BRANCH_POINT,
            staged_tree="d" * 40,
            remote_head="c" * 40,
        ),
    )


def install(monkeypatch: pytest.MonkeyPatch, *, branch_point_diff: str) -> None:
    diffs = {BRANCH_POINT: branch_point_diff, PR_BASE: "app.py\nmaster_own.py"}

    def git(**kwargs: Any) -> str:
        args = kwargs["args"]
        if args[0] == "diff":
            return diffs[args[2]]
        return OTHER_OUTPUT.get(args[0], MARKER)

    pull = dict(
        number=1,
        state="open",
        merged=False,
        head=dict(ref="repair", sha="c" * 40, repo=dict(full_name="owner/repo")),
        base=dict(sha=PR_BASE, repo=dict(full_name="owner/repo")),
    )
    monkeypatch.setattr(module, "git_text", git)
    monkeypatch.setattr(
        module,
        "gh_read",
        lambda **_kwargs: subprocess.CompletedProcess([], 0, json.dumps(pull), ""),
    )


def run(call: module.HookCall, tmp_path: Path) -> dict[str, Any]:
    return module.validate_scope(
        repo=tmp_path,
        context=context(),
        reading={"attempt": moved_master_attempt()},
        query={"repository": "owner/repo"},
        tree="d" * 40,
        call=call,
    )


def test_fix_round_commit_within_original_paths_is_admitted_after_master_moves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install(monkeypatch, branch_point_diff="app.py")
    result = run(module.HookCall(hook="pre-commit", extra=(), stdin=""), tmp_path)
    assert result["original_paths"] == ["app.py"]


def test_pr_bound_push_is_admitted_under_the_pr_base_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install(monkeypatch, branch_point_diff="app.py")
    call = module.HookCall(
        hook="pre-push",
        extra=("origin", "https://github.com/owner/repo.git"),
        stdin=f"refs/heads/repair {'b' * 40} refs/heads/repair {'c' * 40}\n",
    )
    result = run(call, tmp_path)
    assert result["push_update"]["carrier_state"] == "pr-bound"


def test_fix_round_commit_outside_original_paths_refuses_naming_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install(monkeypatch, branch_point_diff="app.py\nescaped.py")
    with pytest.raises(
        module.HookRefusalError,
        match=r"changed paths escape the canonical cumulative scope.*escaped\.py",
    ):
        run(module.HookCall(hook="pre-commit", extra=(), stdin=""), tmp_path)
