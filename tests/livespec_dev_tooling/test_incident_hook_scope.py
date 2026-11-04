"""Actual push updates, cumulative paths and legal comments stay incident scoped."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_hook_scope as module
from livespec_dev_tooling.incident_execution import ExecutionContext, OperationIdentity


def context() -> ExecutionContext:
    return ExecutionContext(
        mode="expedited-repair",
        invocation="ordinary",
        identity=OperationIdentity(
            incident_item_id="incident",
            attempt_id="attempt",
            phase="repair",
            repository="owner/repo",
            base_sha="a" * 40,
            head_sha="b" * 40,
            operation_id="operation",
        ),
    )


def attempt() -> dict[str, Any]:
    return dict(pr_number=1, head="b" * 40, base="a" * 40, original_paths=["app.py"])


def pr() -> dict[str, Any]:
    return dict(
        number=1,
        state="open",
        merged=False,
        head=dict(ref="repair", sha="c" * 40, repo=dict(full_name="owner/repo")),
        base=dict(sha="a" * 40, repo=dict(full_name="owner/repo")),
    )


def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    def git(**kwargs: Any) -> str:
        command = kwargs["args"][0]
        if command == "diff":
            return "app.py"
        if command == "ls-tree":
            return "app.py"
        return "# EXPEDITED_INCIDENT_RESPONSE flag: incident\nvalue = 2\n"

    monkeypatch.setattr(module, "git_text", git)
    monkeypatch.setattr(
        module,
        "gh_read",
        lambda **_kwargs: subprocess.CompletedProcess([], 0, json.dumps(pr()), ""),
    )


def test_push_binds_single_actual_ref_update_and_authenticated_existing_pr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch)
    call = module.HookCall(
        hook="pre-push",
        extra=("origin", "https://github.com/owner/repo.git"),
        stdin=f"refs/heads/repair {'b'*40} refs/heads/repair {'c'*40}\n",
    )
    result = module.validate_scope(
        repo=tmp_path,
        context=context(),
        reading={"attempt": attempt()},
        query={"repository": "owner/repo"},
        tree="d" * 40,
        call=call,
    )
    assert result["push_update"]["local_sha"] == "b" * 40
    assert result["marker"] == "app.py"


@pytest.mark.parametrize(
    "stdin",
    [
        "",
        "delete 000 refs/heads/repair c",
        f"refs/heads/other {'b'*40} refs/heads/repair {'c'*40}",
        f"refs/heads/repair {'e'*40} refs/heads/repair {'c'*40}",
        f"refs/heads/repair {'b'*40} refs/heads/repair {'f'*40}",
        "x" * 16385,
        "one\ntwo\n",
    ],
)
def test_foreign_multiple_deleted_or_mismatched_updates_refuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stdin: str
) -> None:
    _setup(monkeypatch)
    with pytest.raises(module.HookRefusalError):
        module.validate_scope(
            repo=tmp_path,
            context=context(),
            reading={"attempt": attempt()},
            query={"repository": "owner/repo"},
            tree="d" * 40,
            call=module.HookCall(
                hook="pre-push", extra=("origin", "https://github.com/owner/repo"), stdin=stdin
            ),
        )


@pytest.mark.parametrize(
    "extra",
    [
        (),
        ("origin",),
        ("foreign", "https://github.com/owner/repo"),
        ("origin", "https://github.com/foreign/repo"),
        ("origin", "https://github.com/owner/repo", "extra"),
    ],
)
def test_actual_push_destination_cannot_be_replaced_by_fetch_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extra: tuple[str, ...]
) -> None:
    _setup(monkeypatch)
    with pytest.raises(module.HookRefusalError):
        module.validate_scope(
            repo=tmp_path,
            context=context(),
            reading={"attempt": attempt()},
            query={"repository": "owner/repo"},
            tree="d" * 40,
            call=module.HookCall(
                hook="pre-push",
                extra=extra,
                stdin=f"refs/heads/repair {'b'*40} refs/heads/repair {'c'*40}",
            ),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"pr_number": 0},
        {"original_paths": None},
        {"original_paths": []},
        {"original_paths": ["other.py"]},
    ],
)
def test_incomplete_or_pre_pr_push_identity_never_admits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: dict[str, Any]
) -> None:
    _setup(monkeypatch)
    with pytest.raises(module.HookRefusalError):
        module.validate_scope(
            repo=tmp_path,
            context=context(),
            reading={"attempt": attempt() | change},
            query={"repository": "owner/repo"},
            tree="d" * 40,
            call=module.HookCall(hook="pre-push", extra=(), stdin=""),
        )


def test_unscoped_workflow_and_illegal_comment_refuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch)
    data = attempt() | {"original_paths": [".github/workflows/ci.yml"]}
    monkeypatch.setattr(module, "git_text", lambda **_kwargs: ".github/workflows/ci.yml")
    with pytest.raises(module.HookRefusalError):
        module.validate_scope(
            repo=tmp_path,
            context=context(),
            reading={"attempt": data},
            query={},
            tree="d" * 40,
            call=module.HookCall(hook="pre-commit", extra=(), stdin=""),
        )
    _setup(monkeypatch)
    git = module.git_text
    monkeypatch.setattr(
        module,
        "git_text",
        lambda **kwargs: "marker = 'EXPEDITED_INCIDENT_RESPONSE flag: incident'"
        if kwargs["args"][0] == "show"
        else git(**kwargs),
    )
    with pytest.raises(module.HookRefusalError):
        module.validate_scope(
            repo=tmp_path,
            context=context(),
            reading={"attempt": attempt()},
            query={},
            tree="d" * 40,
            call=module.HookCall(hook="pre-commit", extra=(), stdin=""),
        )


def test_non_python_or_deleted_carrier_requires_an_adjacent_legal_python_comment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _setup(monkeypatch)

    def git(**kwargs: Any) -> str:
        return "deleted.py\nplain.txt" if kwargs["args"][0] == "diff" else ""

    monkeypatch.setattr(module, "git_text", git)
    with pytest.raises(module.HookRefusalError):
        module.validate_scope(
            repo=tmp_path,
            context=context(),
            reading={"attempt": attempt() | {"original_paths": ["deleted.py", "plain.txt"]}},
            query={},
            tree="d" * 40,
            call=module.HookCall(hook="pre-commit", extra=(), stdin=""),
        )


def test_emergency_revert_requires_its_separate_inverse_authority(tmp_path: Path) -> None:
    current = context()
    with pytest.raises(module.HookRefusalError):
        module.validate_scope(
            repo=tmp_path,
            context=ExecutionContext(
                mode="emergency-revert", invocation="ordinary", identity=current.identity
            ),
            reading={},
            query={},
            tree="d" * 40,
            call=module.HookCall(hook="pre-commit", extra=(), stdin=""),
        )
