"""The canonical subprocess path is fixed and its current reply is identity bound."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_hook_process as module
from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
)


def query() -> dict[str, Any]:
    return dict(
        repository="owner/repo",
        item="incident",
        attempt="attempt",
        phase="repair",
        operation="operation",
        generation=1,
        owner="operator",
    )


def reading() -> dict[str, Any]:
    return dict(
        attempt=dict(
            repository="owner/repo",
            item_id="incident",
            attempt_id="attempt",
            phase="repair",
            operation_id="operation",
            generation=1,
            owner="operator",
            base="a" * 40,
            head="b" * 40,
            landed_commits=[],
        ),
        is_current=True,
        committed_token_id="closed",  # noqa: S106 — public record identity.
        current_token_id="open",  # noqa: S106 — public record identity.
    )


@pytest.mark.parametrize(
    "text", ["[]", "{}", " " * 16385, '{"repository":"first","repository":"last"}']
)
def test_invalid_query_never_supplies_authority(text: str) -> None:
    assert module.parse_query(text=text) is None


@pytest.mark.parametrize(
    "change", [{"generation": True}, {"generation": 0}, {"owner": ""}, {"owner": " spaced "}]
)
def test_query_requires_exact_complete_identity(change: dict[str, Any]) -> None:
    assert module.parse_query(text=module.canonical(value=query() | change)) is None


def test_current_reader_uses_registered_path_not_caller_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.append(argv)
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps(
                dict(
                    schema=1,
                    status="verified",
                    authorizes_current_effects=True,
                    normal_factory_proof=False,
                    result=reading(),
                )
            ),
            "",
        )

    monkeypatch.setattr(module, "_governed_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(module, "registered_plugin_root", lambda **_kwargs: tmp_path / "registered")
    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.invoke_authority(repo=tmp_path, query=query(), action="read-current") == reading()
    assert captured[0][:5] == [
        "/usr/local/bin/with-livespec-env.sh",
        "--",
        "python3",
        str(tmp_path / "registered/scripts/bin/incident_authority.py"),
        "read-current",
    ]
    response = dict(
        schema=1,
        status="verified",
        authorizes_current_effects=False,
        normal_factory_proof=False,
        result={"receipt_id": "r"},
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, json.dumps(response), ""),
    )
    assert module.invoke_authority(
        repo=tmp_path, query=query(), action="record-local-gates", receipt="{}"
    ) == {"receipt_id": "r"}


@pytest.mark.parametrize(
    "change",
    [
        {"schema": True},
        {"schema": 2},
        {"status": "refused"},
        {"normal_factory_proof": True},
        {"authorizes_current_effects": False},
    ],
)
def test_canonical_protocol_refuses_wrong_kind_or_normal_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: dict[str, Any]
) -> None:
    response = (
        dict(
            schema=1,
            status="verified",
            authorizes_current_effects=True,
            normal_factory_proof=False,
            result=reading(),
        )
        | change
    )
    monkeypatch.setattr(module, "_governed_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(module, "registered_plugin_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, json.dumps(response), ""),
    )
    with pytest.raises(module.HookRefusalError):
        module.invoke_authority(repo=tmp_path, query=query(), action="read-current")


@pytest.mark.parametrize(
    "change",
    [
        {"is_current": False},
        {"attempt": {}},
        {"attempt": reading()["attempt"] | {"generation": True}},
    ],
)
def test_reply_cannot_change_identity(change: dict[str, Any]) -> None:
    with pytest.raises(module.HookRefusalError):
        module.resolve_current(reading=reading() | change, query=query())


def test_resolver_rejects_invalid_phase_or_transport_and_supports_recorded_revert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(EXPEDITED_INCIDENT_RESPONSE, "1")
    monkeypatch.delenv(EXPEDITED_INCIDENT_RESPONSE_REVERT, raising=False)
    monkeypatch.setenv(module.CONTEXT_ENV, "{}")
    with pytest.raises(module.HookRefusalError):
        module.resolve_current(reading=reading(), query=query())
    monkeypatch.delenv(module.CONTEXT_ENV)
    invalid = reading()
    invalid["attempt"]["base"] = "invalid"
    with pytest.raises(module.HookRefusalError):
        module.resolve_current(reading=invalid, query=query())
    monkeypatch.setenv(EXPEDITED_INCIDENT_RESPONSE_REVERT, "1")
    revert = reading()
    revert["attempt"].update(phase="reverting", landed_commits=["c" * 40])
    assert (
        module.resolve_current(reading=revert, query=query() | {"phase": "reverting"}).mode
        == "emergency-revert"
    )


def test_git_invocation_is_structured_and_failure_is_not_empty_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert (
            argv == ["git", "write-tree"] and kwargs["cwd"] == tmp_path and kwargs["check"] is True
        )
        return subprocess.CompletedProcess(argv, 0, "tree\n", "")

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.git_text(repo=tmp_path, args=["write-tree"]) == "tree"


@pytest.mark.parametrize(
    ("mutation", "hook"),
    [
        ("head", "pre-commit"),
        ("master", "pre-commit"),
        ("dirty", "pre-commit"),
        ("untracked", "pre-commit"),
        ("staged", "pre-push"),
        ("origin", "pre-commit"),
        ("multiple", "pre-push"),
        ("foreignpush", "pre-push"),
        ("ok", "pre-push"),
    ],
)
def test_exact_git_state_rejects_foreign_or_mutable_carriers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str, hook: str
) -> None:
    monkeypatch.setenv(EXPEDITED_INCIDENT_RESPONSE, "1")
    monkeypatch.delenv(EXPEDITED_INCIDENT_RESPONSE_REVERT, raising=False)
    monkeypatch.delenv(module.CONTEXT_ENV, raising=False)
    current = module.resolve_current(reading=reading(), query=query())

    def git(**kwargs: Any) -> str:
        args = kwargs["args"]
        values = {
            ("rev-parse", "HEAD"): "wrong" if mutation == "head" else "b" * 40,
            ("symbolic-ref", "--short", "HEAD"): "master" if mutation == "master" else "repair",
            ("ls-files", "--others", "--exclude-standard"): "new.py"
            if mutation == "untracked"
            else "",
            ("diff", "--name-only"): "app.py" if mutation == "dirty" else "",
            ("diff", "--cached", "--name-only"): "app.py" if mutation == "staged" else "",
            ("config", "--get", "remote.origin.url"): "https://github.com/foreign/repo"
            if mutation == "origin"
            else "https://github.com/owner/repo.git",
            (
                "remote",
                "get-url",
                "--push",
                "--all",
                "origin",
            ): "https://github.com/owner/repo\nhttps://github.com/foreign/repo"
            if mutation == "multiple"
            else "https://github.com/foreign/repo"
            if mutation == "foreignpush"
            else "https://github.com/owner/repo.git",
        }
        return values.get(tuple(args), "tree")

    monkeypatch.setattr(module, "git_text", git)
    if mutation == "ok":
        assert module.exact_tree(repo=tmp_path, context=current, hook=hook) == "tree"
    else:
        with pytest.raises(module.HookRefusalError):
            module.exact_tree(repo=tmp_path, context=current, hook=hook)


def test_linked_worktree_resolves_the_primary_registered_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = tmp_path / "primary"
    primary.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Fixture"],
        ["config", "user.email", "fixture@example.com"],
        ["commit", "--allow-empty", "-qm", "fixture"],
    ):
        subprocess.run(["git", *args], cwd=primary, check=True, capture_output=True)
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "worktree", "add", "-b", "repair", str(linked)],
        cwd=primary,
        check=True,
        capture_output=True,
    )
    original_run = subprocess.run

    def registered(*, repo_root: Path, registry: Path) -> Path:
        assert repo_root == primary
        assert registry.name == "installed_plugins.json"
        return tmp_path / "registered"

    def invoke(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == "git":
            return original_run(argv, **kwargs)
        assert argv[3] == str(tmp_path / "registered/scripts/bin/incident_authority.py")
        assert argv[argv.index("--repo") + 1] == str(primary)
        response = dict(
            schema=1,
            status="verified",
            authorizes_current_effects=True,
            normal_factory_proof=False,
            result=reading(),
        )
        return subprocess.CompletedProcess(argv, 0, json.dumps(response), "")

    monkeypatch.setattr(module, "registered_plugin_root", registered)
    monkeypatch.setattr(module.subprocess, "run", invoke)
    assert module.invoke_authority(repo=linked, query=query(), action="read-current") == reading()


def test_nonstandard_git_administration_never_guesses_registered_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(module, "git_text", lambda **_kwargs: str(tmp_path / "custom-git"))
    with pytest.raises(module.HookRefusalError):
        module.invoke_authority(repo=tmp_path, query=query(), action="read-current")
