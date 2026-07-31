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

from _gh_railway import lift_gh
from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    GhResult,
    GhRunner,
    TreeState,
    default_gh_runner,
    resolve_owner,
    resolve_repo_name,
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

    return lift_gh(run)


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


def repo_result(*, default_branch: str) -> GhResult:
    """A successful repo-metadata API result naming `default_branch`."""
    import json

    return GhResult(returncode=0, stdout=json.dumps({"default_branch": default_branch}), stderr="")


_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_REPO_ARGS: tuple[str, ...] = ("api", "repos/acme/widget")


def test_default_runner_without_gh_is_a_failure_value(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """CORRECTED, not updated.

    This asserted `result.returncode == 127` and was NAMED
    `..._yields_synthetic_failure`, so the fabricated sentinel was written
    into the suite as expected behavior in the NAME as well as the
    assertion — the third time across these three seams. A test name is a
    claim like any other.

    Scoped to the SHAPE (the seam does not answer with a success-shaped
    record); the kind and argv are asserted once, in
    `test_context_invocation_railway.py`, rather than in two places.
    """

    def fake_which(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    assert isinstance(default_gh_runner(args=["api", "rate_limit"]), IOFailure)


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
    assert unsafe_perform_io(result.unwrap()) == GhResult(returncode=0, stdout="ok", stderr="")
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
    assert unsafe_perform_io(ctx.api(path="rate_limit").unwrap()).returncode == 0
    put = ctx.api(path="repos/acme/widget/topics", method="PUT", body='{"names": []}')
    assert unsafe_perform_io(put.unwrap()).returncode == 0
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


def test_canonical_ref_pins_file_text_and_tree_to_the_same_default_branch() -> None:
    """A repo whose default branch is not `master` reads BOTH its file and its tree on it."""
    contents_args = (
        "api",
        "repos/acme/widget/contents/justfile?ref=main",
        "-H",
        "Accept: application/vnd.github.raw",
    )
    table: dict[tuple[str, ...], GhResult] = {
        _REPO_ARGS: repo_result(default_branch="main"),
        contents_args: GhResult(returncode=0, stdout="default:\n", stderr=""),
        ("api", "repos/acme/widget/git/trees/main?recursive=1"): tree_result(
            entries=[{"path": "justfile", "mode": "100644"}]
        ),
    }
    ctx = make_context(table=table)
    assert ctx.file_text(repo="widget", path="justfile") == "default:\n"
    assert ctx.tree(repo="widget").readable


def test_canonical_ref_is_memoized_per_repo() -> None:
    """The default-branch lookup costs one API call per repo per run."""
    calls: list[tuple[tuple[str, ...], str | None]] = []
    ctx = make_context(table={_REPO_ARGS: repo_result(default_branch="main")}, calls=calls)
    assert ctx.canonical_ref(repo="widget") == "main"
    assert ctx.canonical_ref(repo="widget") == "main"
    assert len(calls) == 1


def test_canonical_ref_falls_back_to_master_when_unresolvable() -> None:
    """An unreadable or shapeless repo payload keeps the historical `master` pin.

    The fallback is memoized too, so a transient failure can never let
    `file_text` and `tree` resolve against divergent branches mid-run.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    unreadable = make_context(table={}, calls=calls)
    assert unreadable.canonical_ref(repo="widget") == "master"
    assert unreadable.canonical_ref(repo="widget") == "master"
    assert len(calls) == 1
    non_dict = make_context(table={_REPO_ARGS: GhResult(returncode=0, stdout="[1, 2]", stderr="")})
    assert non_dict.canonical_ref(repo="widget") == "master"
    absent_key = make_context(
        table={_REPO_ARGS: GhResult(returncode=0, stdout='{"name": "widget"}', stderr="")}
    )
    assert absent_key.canonical_ref(repo="widget") == "master"
    blank_branch = make_context(table={_REPO_ARGS: repo_result(default_branch="")})
    assert blank_branch.canonical_ref(repo="widget") == "master"


def test_file_text_returns_raw_content_or_none() -> None:
    raw_args = (
        "api",
        "repos/acme/widget/contents/pyproject.toml?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )
    missing_args = (
        "api",
        "repos/acme/widget/contents/nope.txt?ref=master",
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
    """One default-branch lookup plus one tree read; the second `tree` call is memoized."""
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {_TREE_ARGS: tree_result(entries=[{"path": "justfile", "mode": "100644"}])}
    ctx = make_context(table=table, calls=calls)
    first = ctx.tree(repo="widget")
    second = ctx.tree(repo="widget")
    assert first is second
    assert len(calls) == 2


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


def test_resolve_repo_name_parses_both_remote_forms(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """The running-member derivation: the repo short name, `.git` and slash stripped.

    This is the "which member am I RUNNING AS" answer the member-CI exit scoping
    depends on. It shares one parse with `resolve_owner` — same subprocess, same
    pattern, different capture group — because a rule with two copies drifts.
    """
    for remote, expected in (
        ("https://github.com/acme/widget.git\n", "widget"),
        ("git@github.com:acme/widget\n", "widget"),
        ("https://github.com/acme/livespec-dev-tooling/\n", "livespec-dev-tooling"),
    ):

        def fake_run(
            cmd: list[str], *, _remote: str = remote, **_kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=_remote, stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert resolve_repo_name() == expected


def test_resolve_repo_name_is_none_when_git_fails_or_remote_is_not_github(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unresolvable is None, never a guess.

    The member-CI caller turns this None into a loud precondition failure rather than
    a pass, because scoping an exit to an unidentifiable repo would scope it to
    nothing and enforce nothing while reporting success.
    """

    def git_fails(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=128, stdout="", stderr="fatal")

    monkeypatch.setattr(subprocess, "run", git_fails)
    assert resolve_repo_name() is None

    def not_github(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="git@gitlab.com:acme/widget.git\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", not_github)
    assert resolve_repo_name() is None
