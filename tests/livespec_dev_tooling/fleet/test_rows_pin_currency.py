"""Tests for pin-currency fleet rows."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
)

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_LATEST_LIVESPEC_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec/releases/latest")
_LATEST_DEV_TOOLING_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec-dev-tooling/releases/latest",
)
_LATEST_DRIVER_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec-driver-codex/releases/latest")


class PinCurrencyRow(Protocol):
    """One pin-currency row assertion."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> object: ...


def _module() -> object:
    module_path = (
        Path(__file__).resolve().parents[3]
        / "livespec_dev_tooling"
        / "fleet"
        / "_rows_pin_currency.py"
    )
    assert module_path.is_file()
    return importlib.import_module("livespec_dev_tooling.fleet._rows_pin_currency")


def _raw_args(*, path: str) -> tuple[str, ...]:
    return (
        "api",
        f"repos/acme/widget/contents/{path}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )


def _context(*, files: dict[str, str], latest: dict[tuple[str, ...], str]) -> FleetContext:
    tree_payload = {
        "tree": [{"path": path, "mode": "100644"} for path in files],
        "truncated": False,
    }
    table = {
        _TREE_ARGS: GhResult(returncode=0, stdout=json.dumps(tree_payload), stderr=""),
    }
    for path, text in files.items():
        table[_raw_args(path=path)] = GhResult(returncode=0, stdout=text, stderr="")
    for args, tag in latest.items():
        table[args] = GhResult(returncode=0, stdout=json.dumps({"tag_name": tag}), stderr="")

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def _assert_row_finding(*, outcome: object, pin_format: str, current: str, latest: str) -> None:
    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert _MEMBER.repo in outcome.message
    assert pin_format in outcome.message
    assert current in outcome.message
    assert latest in outcome.message


def test_livespec_compat_pin_currency_warns_for_stale_record() -> None:
    module = _module()
    assert_livespec_compat_pin_currency = cast(
        "PinCurrencyRow", module.assert_livespec_compat_pin_currency
    )
    ctx = _context(
        files={
            ".livespec.jsonc": json.dumps(
                {"impl-plugin": {"compat": {"pinned": "v1.0.0", "livespec": "v1"}}}
            )
        },
        latest={_LATEST_LIVESPEC_ARGS: "v1.1.0"},
    )

    outcome = assert_livespec_compat_pin_currency(ctx=ctx, member=_MEMBER)

    _assert_row_finding(
        outcome=outcome,
        pin_format="livespec_jsonc_compat_pinned",
        current="v1.0.0",
        latest="v1.1.0",
    )


def test_github_workflow_uses_pin_currency_warns_for_stale_record() -> None:
    module = _module()
    assert_github_workflow_uses_pin_currency = cast(
        "PinCurrencyRow", module.assert_github_workflow_uses_pin_currency
    )
    ctx = _context(
        files={
            ".github/workflows/ci.yml": (
                "jobs:\n"
                "  test:\n"
                "    uses: acme/livespec-driver-codex/.github/workflows/ci.yml@v2.0.0\n"
            )
        },
        latest={_LATEST_DRIVER_ARGS: "v2.1.0"},
    )

    outcome = assert_github_workflow_uses_pin_currency(ctx=ctx, member=_MEMBER)

    _assert_row_finding(
        outcome=outcome,
        pin_format="github_workflow_uses_ref",
        current="v2.0.0",
        latest="v2.1.0",
    )


def test_fabro_sandbox_image_pin_currency_uses_version_component_comparison() -> None:
    module = _module()
    assert_fabro_sandbox_image_pin_currency = cast(
        "PinCurrencyRow", module.assert_fabro_sandbox_image_pin_currency
    )
    ctx = _context(
        files={
            ".fabro/workflows/build/workflow.toml": (
                'docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v3.0.0"\n'
            ),
            ".github/workflows/ci.yml": (
                "jobs:\n"
                "  test:\n"
                "    container: ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v2.9.0\n"
            ),
        },
        latest={_LATEST_DEV_TOOLING_ARGS: "v3.0.0"},
    )

    outcome = assert_fabro_sandbox_image_pin_currency(ctx=ctx, member=_MEMBER)

    _assert_row_finding(
        outcome=outcome,
        pin_format="fabro_sandbox_docker_image",
        current="python-v2.9.0",
        latest="v3.0.0",
    )


def test_pin_currency_rows_pass_when_records_are_current_or_latest_unreadable() -> None:
    module = _module()
    assert_livespec_compat_pin_currency = cast(
        "PinCurrencyRow", module.assert_livespec_compat_pin_currency
    )
    assert_github_workflow_uses_pin_currency = cast(
        "PinCurrencyRow", module.assert_github_workflow_uses_pin_currency
    )
    assert_fabro_sandbox_image_pin_currency = cast(
        "PinCurrencyRow", module.assert_fabro_sandbox_image_pin_currency
    )
    ctx = _context(
        files={
            ".livespec.jsonc": json.dumps(
                {"impl-plugin": {"compat": {"pinned": "v1.1.0", "livespec": "v1"}}}
            ),
            ".github/workflows/ci.yml": (
                "jobs:\n"
                "  use:\n"
                "    uses: acme/livespec-driver-codex/.github/workflows/ci.yml@v2.1.0\n"
                "  image:\n"
                "    container: ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v3.0.0\n"
            ),
        },
        latest={
            _LATEST_LIVESPEC_ARGS: "v1.1.0",
            _LATEST_DEV_TOOLING_ARGS: "v3.0.0",
        },
    )

    assert assert_livespec_compat_pin_currency(ctx=ctx, member=_MEMBER) == RowPass()
    assert assert_github_workflow_uses_pin_currency(ctx=ctx, member=_MEMBER) == RowPass(
        note="pin records present; freshness unverified (latest release unreadable)"
    )
    assert assert_fabro_sandbox_image_pin_currency(ctx=ctx, member=_MEMBER) == RowPass()
