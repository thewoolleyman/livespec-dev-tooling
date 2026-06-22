"""Tests for `livespec_dev_tooling/fleet/fleet_conformance.py`.

Engine functions run in-process against canned-response contexts; the
CLI entry point is exercised across its lever / precondition / finding
/ success branches, plus one `python -m` subprocess invocation for the
`__main__` guard (lever unset → fast logged skip).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

from _protection_fixtures import aligned_protection_payload

from livespec_dev_tooling.fleet import fleet_conformance
from livespec_dev_tooling.fleet._context import FleetContext, GhResult, GhRunner
from livespec_dev_tooling.fleet.fleet_conformance import (
    fetch_manifest,
    run_discovery_sweep,
    run_member_rows,
)

if TYPE_CHECKING:
    import pytest
    import structlog.stdlib

__all__: list[str] = []


_MANIFEST_SOURCE = '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}]}'
_MANIFEST_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec/contents/fleet-manifest.jsonc",
    "-H",
    "Accept: application/vnd.github.raw",
)
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_PYPROJECT_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/pyproject.toml",
    "-H",
    "Accept: application/vnd.github.raw",
)
_LATEST_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec-dev-tooling/releases/latest")
_SECRETS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/actions/secrets")
_INSTALL_ARGS: tuple[str, ...] = ("api", "installation/repositories?per_page=100")
_PROTECTION_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/branches/master/protection")
_TOPICS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/topics")
_CI_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.github/workflows/ci.yml",
    "-H",
    "Accept: application/vnd.github.raw",
)
_REPOS_ARGS: tuple[str, ...] = ("api", "users/acme/repos?per_page=100")

_CI_YML = "jobs:\n  check:\n    strategy:\n      matrix:\n        target:\n          - check-a\n"
_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.0.0" }\n'


def make_runner(*, table: dict[tuple[str, ...], GhResult]) -> GhRunner:
    """Canned-response `GhRunner` keyed on full arg tuples."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    return run


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""
    return FleetContext(owner="acme", run_gh=make_runner(table=table))


def ok(*, payload: object) -> GhResult:
    """A successful API result carrying a JSON payload."""
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def raw(*, text: str) -> GhResult:
    """A successful raw-content API result."""
    return GhResult(returncode=0, stdout=text, stderr="")


def _green_table(
    *, latest_tag: str = "v1.0.0", topics: list[str] | None = None
) -> dict[tuple[str, ...], GhResult]:
    """A table where every row of the one-member manifest passes."""
    workflows = [
        ".github/workflows/ci.yml",
        ".github/workflows/bump-pin-from-dispatch.yml",
        ".github/workflows/pin-freshness.yml",
        ".github/workflows/release-dispatch.yml",
        "pyproject.toml",
    ]
    tree_payload = {
        "tree": [{"path": p, "mode": "100644"} for p in workflows],
        "truncated": False,
    }
    return {
        _MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE),
        _TREE_ARGS: ok(payload=tree_payload),
        _PYPROJECT_ARGS: raw(text=_PYPROJECT),
        _LATEST_ARGS: ok(payload={"tag_name": latest_tag}),
        _SECRETS_ARGS: ok(payload={"secrets": [{"name": "APP_ID"}, {"name": "APP_PRIVATE_KEY"}]}),
        _INSTALL_ARGS: ok(payload={"repositories": [{"name": "widget"}]}),
        _PROTECTION_ARGS: ok(payload=aligned_protection_payload()),
        _CI_ARGS: raw(text=_CI_YML),
        _TOPICS_ARGS: ok(payload={"names": topics if topics is not None else ["livespec-sibling"]}),
        _REPOS_ARGS: ok(payload=_owner_repos_payload()),
    }


def _owner_repos_payload() -> list[object]:
    return [
        {"name": "widget", "topics": ["livespec-sibling"]},
        {"name": "unrelated", "topics": []},
    ]


def _log() -> structlog.stdlib.BoundLogger:
    import structlog

    return structlog.get_logger("test_fleet_conformance")


def test_fetch_manifest_success_and_failure_modes() -> None:
    ctx = make_context(table={_MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE)})
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert manifest.member_names() == frozenset({"widget"})
    assert fetch_manifest(ctx=make_context(table={})) is None
    bad = make_context(table={_MANIFEST_ARGS: raw(text="not jsonc {{{")})
    assert fetch_manifest(ctx=bad) is None


def test_member_rows_all_green_yields_zero_errors() -> None:
    ctx = make_context(table=_green_table())
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert run_member_rows(ctx=ctx, manifest=manifest, log=_log()) == 0


def test_member_rows_counts_errors_but_not_warnings_or_skips() -> None:
    # Stale pin → warning; missing topic → error; unreadable secrets → skip.
    table = _green_table(latest_tag="v2.0.0", topics=[])
    del table[_SECRETS_ARGS]
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert run_member_rows(ctx=ctx, manifest=manifest, log=_log()) == 1


def test_discovery_sweep_flags_unmanifested_family_repos() -> None:
    table = _green_table()
    sweep_payload: list[object] = [
        {"name": "widget", "topics": ["livespec-sibling"]},
        {"name": "livespec-straggler", "topics": []},
        {"name": "topic-bearing", "topics": ["livespec-sibling"]},
        {"name": "unrelated", "topics": "shapeless"},
        {"name": 7},
        "junk",
    ]
    table[_REPOS_ARGS] = ok(payload=sweep_payload)
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert run_discovery_sweep(ctx=ctx, manifest=manifest, log=_log()) == 2


def test_discovery_sweep_unreadable_repo_list_warns_and_passes() -> None:
    table = _green_table()
    del table[_REPOS_ARGS]
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert run_discovery_sweep(ctx=ctx, manifest=manifest, log=_log()) == 0


def _patch_runner(
    *, monkeypatch: pytest.MonkeyPatch, table: dict[tuple[str, ...], GhResult]
) -> None:
    monkeypatch.setattr(fleet_conformance, "default_gh_runner", make_runner(table=table))


def test_main_lever_unset_skips_with_exit_zero(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVESPEC_RUN_FLEET_CONFORMANCE", raising=False)
    monkeypatch.setattr(sys, "argv", ["fleet-conformance"])
    assert fleet_conformance.main() == 0


def test_main_owner_unresolvable_is_precondition_failure(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance"])

    def no_owner(*, cwd: object = None) -> str | None:
        del cwd
        return None

    monkeypatch.setattr(fleet_conformance, "resolve_owner", no_owner)
    assert fleet_conformance.main() == 1


def test_main_unfetchable_manifest_is_precondition_failure(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table={})
    assert fleet_conformance.main() == 1


def test_main_green_fleet_exits_zero(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_green_table())
    assert fleet_conformance.main() == 0


def test_main_error_findings_exit_four(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_green_table(topics=[]))
    assert fleet_conformance.main() == 4


def test_module_invocation_with_lever_unset_skips() -> None:
    env = {key: value for key, value in os.environ.items()}
    _ = env.pop("LIVESPEC_RUN_FLEET_CONFORMANCE", None)
    result = subprocess.run(
        [sys.executable, "-m", "livespec_dev_tooling.fleet.fleet_conformance"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    assert "skipped" in result.stderr
