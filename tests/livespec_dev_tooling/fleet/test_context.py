"""Tests for `livespec_dev_tooling/fleet/_context.py`.

Everything runs hermetically: `gh`/`git` subprocess seams are
monkeypatched, and `FleetContext` is exercised with canned-response
runners (the same fake idiom every other fleet test module reuses).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    GhResult,
    GhRunner,
    TreeState,
    default_gh_runner,
    resolve_owner,
)

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


def make_runner(
    *,
    table: dict[tuple[str, ...], GhResult],
    calls: list[tuple[tuple[str, ...], str | None]] | None = None,
) -> GhRunner:
    """Canned-response `GhRunner`: maps arg tuples to results, records stdin."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        key = tuple(args)
        if calls is not None:
            calls.append((key, stdin))
        return table.get(key, GhResult(returncode=1, stdout="", stderr="no canned response"))

    return run


def make_context(
    *,
    table: dict[tuple[str, ...], GhResult],
    calls: list[tuple[tuple[str, ...], str | None]] | None = None,
) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""
    return FleetContext(owner="acme", run_gh=make_runner(table=table, calls=calls))


def tree_result(*, entries: list[dict[str, str]], truncated: bool = False) -> GhResult:
    """A successful `git/trees` API result carrying `entries`."""
    import json

    payload = {"tree": entries, "truncated": truncated}
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")


def test_default_runner_without_gh_yields_synthetic_failure(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_which(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    result = default_gh_runner(args=["api", "rate_limit"])
    assert result.returncode == 127
    assert "gh CLI not on PATH" in result.stderr


def test_default_runner_invokes_gh_with_stdin(*, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(_name: str) -> str | None:
        return "/usr/bin/gh"

    monkeypatch.setattr(shutil, "which", fake_which)
    seen: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["cmd"] = cmd
        seen["input"] = kwargs.get("input")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_gh_runner(args=["secret", "set", "X"], stdin="value")
    assert result == GhResult(returncode=0, stdout="ok", stderr="")
    assert seen["cmd"] == ["gh", "secret", "set", "X"]
    assert seen["input"] == "value"


def test_resolve_owner_parses_https_remote(*, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert cmd == ["git", "remote", "get-url", "origin"]
        assert kwargs.get("cwd") is None
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="https://github.com/acme/widget.git\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert resolve_owner() == "acme"


def test_resolve_owner_with_cwd_and_ssh_remote(*, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs.get("cwd") == "/somewhere"
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="git@github.com:acme/widget\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert resolve_owner(cwd=Path("/somewhere")) == "acme"


def test_resolve_owner_handles_git_failure(*, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=128, stdout="", stderr="fatal")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert resolve_owner() is None


def test_resolve_owner_rejects_non_github_remote(*, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="https://gitlab.com/acme/widget\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert resolve_owner() is None


def test_api_get_and_mutating_methods_shape_args() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        ("api", "rate_limit"): GhResult(returncode=0, stdout="{}", stderr=""),
        ("api", "repos/acme/widget/topics", "--method", "PUT", "--input", "-"): GhResult(
            returncode=0, stdout="{}", stderr=""
        ),
    }
    ctx = make_context(table=table, calls=calls)
    assert ctx.api(path="rate_limit").returncode == 0
    put = ctx.api(path="repos/acme/widget/topics", method="PUT", body='{"names": []}')
    assert put.returncode == 0
    assert calls[0] == (("api", "rate_limit"), None)
    assert calls[1][1] == '{"names": []}'


def test_api_object_parses_failures_and_bad_json() -> None:
    table = {
        ("api", "good"): GhResult(returncode=0, stdout='{"a": 1}', stderr=""),
        ("api", "bad-json"): GhResult(returncode=0, stdout="not json", stderr=""),
        ("api", "fails"): GhResult(returncode=1, stdout="", stderr="boom"),
    }
    ctx = make_context(table=table)
    assert ctx.api_object(path="good") == {"a": 1}
    assert ctx.api_object(path="bad-json") is None
    assert ctx.api_object(path="fails") is None


def test_file_text_returns_raw_content_or_none() -> None:
    raw_args = (
        "api",
        "repos/acme/widget/contents/pyproject.toml",
        "-H",
        "Accept: application/vnd.github.raw",
    )
    missing_args = (
        "api",
        "repos/acme/widget/contents/nope.txt",
        "-H",
        "Accept: application/vnd.github.raw",
    )
    table: dict[tuple[str, ...], GhResult] = {
        raw_args: GhResult(returncode=0, stdout="[tool]\n", stderr=""),
        missing_args: GhResult(returncode=1, stdout="", stderr="Not Found"),
    }
    ctx = make_context(table=table)
    assert ctx.file_text(repo="widget", path="pyproject.toml") == "[tool]\n"
    assert ctx.file_text(repo="widget", path="nope.txt") is None


def test_tree_parses_paths_gitlinks_and_truncation() -> None:
    entries = [
        {"path": "justfile", "mode": "100644"},
        {"path": "vendored/dep", "mode": "160000"},
        {"path": "lib/a.py", "mode": "100644"},
    ]
    table = {_TREE_ARGS: tree_result(entries=entries, truncated=True)}
    ctx = make_context(table=table)
    state = ctx.tree(repo="widget")
    assert state.readable
    assert state.truncated
    assert state.paths == frozenset({"justfile", "vendored/dep", "lib/a.py"})
    assert state.gitlink_paths == ("vendored/dep",)


def test_tree_is_memoized_per_repo() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {_TREE_ARGS: tree_result(entries=[{"path": "justfile", "mode": "100644"}])}
    ctx = make_context(table=table, calls=calls)
    first = ctx.tree(repo="widget")
    second = ctx.tree(repo="widget")
    assert first is second
    assert len(calls) == 1


def test_tree_unreadable_on_api_failure_or_bad_payload() -> None:
    ctx = make_context(table={})
    assert ctx.tree(repo="widget") == TreeState(readable=False)
    bad_payload_table = {_TREE_ARGS: GhResult(returncode=0, stdout='{"no_tree": []}', stderr="")}
    ctx_bad = make_context(table=bad_payload_table)
    assert ctx_bad.tree(repo="widget") == TreeState(readable=False)
    list_payload_table = {_TREE_ARGS: GhResult(returncode=0, stdout="[1, 2]", stderr="")}
    ctx_list = make_context(table=list_payload_table)
    assert ctx_list.tree(repo="widget") == TreeState(readable=False)


def test_tree_skips_malformed_entries() -> None:
    import json

    payload = {"tree": [{"path": "ok", "mode": "100644"}, "junk", {"mode": "100644"}]}
    table = {_TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(payload), stderr="")}
    ctx = make_context(table=table)
    state = ctx.tree(repo="widget")
    assert state.paths == frozenset({"ok"})
    assert state.gitlink_paths == ()


def test_installed_repos_success_and_memoization() -> None:
    import json

    calls: list[tuple[tuple[str, ...], str | None]] = []
    payload = {"repositories": [{"name": "widget"}, {"id": 7}, "junk"]}
    table = {
        ("api", "installation/repositories?per_page=100"): GhResult(
            returncode=0, stdout=json.dumps(payload), stderr=""
        )
    }
    ctx = make_context(table=table, calls=calls)
    assert ctx.installed_repos() == frozenset({"widget"})
    assert ctx.installed_repos() == frozenset({"widget"})
    assert len(calls) == 1


def test_installed_repos_unreadable_is_memoized_none() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    ctx = make_context(table={}, calls=calls)
    assert ctx.installed_repos() is None
    assert ctx.installed_repos() is None
    assert len(calls) == 1


def test_installed_repos_handles_non_list_repositories() -> None:
    table = {
        ("api", "installation/repositories?per_page=100"): GhResult(
            returncode=0, stdout='{"repositories": "nope"}', stderr=""
        )
    }
    ctx = make_context(table=table)
    assert ctx.installed_repos() is None


def test_once_fires_exactly_once_per_key() -> None:
    ctx = make_context(table={})
    assert ctx.once(key="shim-pr:widget")
    assert not ctx.once(key="shim-pr:widget")
    assert ctx.once(key="shim-pr:gadget")
