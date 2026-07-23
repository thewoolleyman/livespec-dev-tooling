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
from pathlib import Path
from typing import TYPE_CHECKING

from _protection_fixtures import aligned_merge_settings_payload, aligned_protection_payload

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
_TWO_MEMBER_MANIFEST_SOURCE = (
    '{"owner": "acme", "members": ['
    '{"repo": "widget", "class": "library"}, '
    '{"repo": "gadget", "class": "library"}]}'
)
_MANIFEST_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/livespec/contents/.livespec-fleet-manifest.jsonc?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_LATEST_ARGS: tuple[str, ...] = ("api", "repos/acme/livespec-dev-tooling/releases/latest")
_SECRETS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/actions/secrets")
_INSTALL_ARGS: tuple[str, ...] = ("api", "installation/repositories?per_page=100")
_REPOS_ARGS: tuple[str, ...] = ("api", "users/acme/repos?per_page=100")

# The exact `event` string `run_member_rows` emits for a row that applied to at
# least one member and was evaluable for none of them. Asserted verbatim (the
# `test_discovery_sweep_uses_fleet_shape_wording` precedent) because the wording
# IS the signal an operator scans a green run's log for.
_BLIND_ROW_EVENT = "obligation row enforced NOTHING this run (skipped for every applicable member)"

# The exact `event` string emitted for a row the running lane structurally
# cannot evaluate. Asserted verbatim for the same reason as the blind-row
# event: an operator reading a green run must be able to tell "nobody
# enforced this" (blind) from "another named lane enforces this"
# (out-of-vantage) without reading the source.
_OUT_OF_VANTAGE_EVENT = "obligation row is outside this lane's vantage (another lane owns it)"

_CI_YML = "jobs:\n  check:\n    strategy:\n      matrix:\n        target:\n          - check-a\n"
_PYPROJECT = '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.0.0" }\n'
_LIVESPEC_JSONC = (
    '{"harnesses": {"claude": {"status": "exempt", "reason": "library; no harness surface"}}}'
)
_PLUGIN_SETTINGS = json.dumps(
    {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": "mise exec -- just ensure-plugins"}],
                }
            ]
        }
    }
)
_STANDARD_JUSTFILE = (
    "ensure-plugins:\n"
    "    mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins\n"
)


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


def _member_entries(
    *, repo: str, topics: list[str] | None = None
) -> dict[tuple[str, ...], GhResult]:
    """Canned per-repo responses making every applicable row pass for `repo`."""

    def contents(path: str) -> tuple[str, ...]:
        return (
            "api",
            f"repos/acme/{repo}/contents/{path}?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        )

    tracked = [
        ".github/workflows/ci.yml",
        ".github/workflows/bump-pin-from-dispatch.yml",
        ".github/workflows/pin-freshness.yml",
        ".github/workflows/release-dispatch.yml",
        "pyproject.toml",
        ".livespec.jsonc",
        ".claude/settings.json",
        "justfile",
    ]
    tree_payload = {
        "tree": [{"path": p, "mode": "100644"} for p in tracked],
        "truncated": False,
    }
    return {
        ("api", f"repos/acme/{repo}/git/trees/master?recursive=1"): ok(payload=tree_payload),
        contents(".livespec.jsonc"): raw(text=_LIVESPEC_JSONC),
        contents(".claude/settings.json"): raw(text=_PLUGIN_SETTINGS),
        contents("justfile"): raw(text=_STANDARD_JUSTFILE),
        contents("pyproject.toml"): raw(text=_PYPROJECT),
        contents(".github/workflows/ci.yml"): raw(text=_CI_YML),
        ("api", f"repos/acme/{repo}/actions/secrets"): ok(
            payload={"secrets": [{"name": "APP_ID"}, {"name": "APP_PRIVATE_KEY"}]}
        ),
        ("api", f"repos/acme/{repo}/branches/master/protection"): ok(
            payload=aligned_protection_payload()
        ),
        ("api", f"repos/acme/{repo}"): ok(payload=aligned_merge_settings_payload()),
        ("api", f"repos/acme/{repo}/topics"): ok(
            payload={"names": topics if topics is not None else ["livespec-sibling"]}
        ),
    }


def _green_table(
    *, latest_tag: str = "v1.0.0", topics: list[str] | None = None
) -> dict[tuple[str, ...], GhResult]:
    """A table where every row of the one-member manifest passes."""
    return {
        _MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE),
        _LATEST_ARGS: ok(payload={"tag_name": latest_tag}),
        _INSTALL_ARGS: ok(payload={"repositories": [{"name": "widget"}]}),
        _REPOS_ARGS: ok(payload=_owner_repos_payload()),
        **_member_entries(repo="widget", topics=topics),
    }


def _two_member_table(
    *, blind_app_installation: bool = True, gadget_topics_readable: bool = True
) -> dict[tuple[str, ...], GhResult]:
    """Two green members; optionally blind the App-installation or topics reads.

    `blind_app_installation` drops the single `installation/repositories`
    entry, which is the one read the `app-installation` row depends on for
    EVERY member — so the row skips fleet-wide (evaluated for nobody).
    `gadget_topics_readable=False` instead drops ONE member's topics read,
    leaving `topic-livespec-sibling` evaluable for the other member — the
    partial-skip case that must NOT be reported as blind.
    """
    table = {
        _MANIFEST_ARGS: raw(text=_TWO_MEMBER_MANIFEST_SOURCE),
        _LATEST_ARGS: ok(payload={"tag_name": "v1.0.0"}),
        _REPOS_ARGS: ok(
            payload=[
                {"name": "widget", "topics": ["livespec-sibling"]},
                {"name": "gadget", "topics": ["livespec-sibling"]},
            ]
        ),
        **_member_entries(repo="widget"),
        **_member_entries(repo="gadget"),
    }
    if not blind_app_installation:
        table[_INSTALL_ARGS] = ok(
            payload={"repositories": [{"name": "widget"}, {"name": "gadget"}]}
        )
    if not gadget_topics_readable:
        del table[("api", "repos/acme/gadget/topics")]
    return table


def _owner_repos_payload() -> list[object]:
    return [
        {"name": "widget", "topics": ["livespec-sibling"]},
        {"name": "unrelated", "topics": []},
    ]


def _log() -> structlog.stdlib.BoundLogger:
    import structlog

    return structlog.get_logger("test_fleet_conformance")


class RecordingLog:
    """Logger test double capturing each event's text AND its structured fields."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.records: list[tuple[str, dict[str, object]]] = []

    def error(self, event: str, **kwargs: object) -> None:
        self.events.append(event)
        self.records.append((event, kwargs))

    def warning(self, event: str, **kwargs: object) -> None:
        self.events.append(event)
        self.records.append((event, kwargs))

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append(event)
        self.records.append((event, kwargs))

    def fields_for(self, *, event: str) -> list[dict[str, object]]:
        """The structured fields of every record whose event text is `event`."""
        return [fields for recorded, fields in self.records if recorded == event]


def test_fetch_manifest_success_and_failure_modes() -> None:
    ctx = make_context(table={_MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE)})
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert manifest.member_names() == frozenset({"widget"})
    assert fetch_manifest(ctx=make_context(table={})) is None
    bad = make_context(table={_MANIFEST_ARGS: raw(text="not jsonc {{{")})
    assert fetch_manifest(ctx=bad) is None


def _blind_rows_by_id(*, log: RecordingLog) -> dict[object, dict[str, object]]:
    """The blind-row warnings the sweep emitted, keyed by obligation row id."""
    return {fields["row"]: fields for fields in log.fields_for(event=_BLIND_ROW_EVENT)}


def test_blind_row_reported_when_no_applicable_member_could_be_evaluated() -> None:
    """A row skipped for EVERY applicable member enforced nothing — say so, loudly."""
    ctx = make_context(table=_two_member_table())
    manifest = fetch_manifest(ctx=ctx)
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log)
    blind = _blind_rows_by_id(log=log)

    assert "app-installation" in blind
    assert blind["app-installation"]["applicable"] == 2
    assert blind["app-installation"]["skipped"] == 2
    # Per-member reasons carry a `<repo>: ` prefix; the blind-row warning reports
    # the DISTINCT underlying causes, so two members sharing one cause read as one.
    assert blind["app-installation"]["reasons"] == (
        "installation repositories unreadable (needs an App installation token)",
    )
    assert result.blind_rows == len(blind)
    assert result.error_findings == 0


def test_blind_rows_never_change_the_error_count() -> None:
    """Blindness is WARNING-severity new signal, never an error-count contribution."""
    ctx = make_context(table=_two_member_table())
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert run_member_rows(ctx=ctx, manifest=manifest, log=_log()).error_findings == 0


def test_partially_skipped_row_is_not_blind() -> None:
    """A row evaluated for even ONE applicable member did enforce something."""
    table = _two_member_table(blind_app_installation=False, gadget_topics_readable=False)
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx)
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log)
    blind = _blind_rows_by_id(log=log)

    # `topic-livespec-sibling` skipped for gadget but answered for widget, and
    # `app-installation` answered for both: partial blindness is not blindness.
    assert "topic-livespec-sibling" not in blind
    assert "app-installation" not in blind
    assert result.blind_rows == len(blind)


def test_member_rows_all_green_yields_zero_errors() -> None:
    ctx = make_context(table=_green_table())
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert run_member_rows(ctx=ctx, manifest=manifest, log=_log()).error_findings == 0


def test_member_rows_counts_errors_but_not_warnings_or_skips() -> None:
    # Stale pin → warning; missing topic → error. The secrets read is dropped
    # too, but `secret-names` is an ADMIN-vantage row the central lane never
    # calls, so its absence is inert here rather than a skip.
    table = _green_table(latest_tag="v2.0.0", topics=[])
    del table[_SECRETS_ARGS]
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    assert run_member_rows(ctx=ctx, manifest=manifest, log=_log()).error_findings == 1


def _blind_admin_table() -> dict[tuple[str, ...], GhResult]:
    """Two green members whose ADMIN-scoped reads (secrets, protection) all fail.

    This is the shape a real automated run has: the fleet GitHub App
    installation token cannot read Actions secrets or branch protection, so
    both admin rows answer for NOBODY. Before the vantage split that made
    them blind rows — a permanent CI warning nothing could ever clear.
    """
    table = _two_member_table(blind_app_installation=False)
    for repo in ("widget", "gadget"):
        del table[("api", f"repos/acme/{repo}/actions/secrets")]
        del table[("api", f"repos/acme/{repo}/branches/master/protection")]
    return table


def test_admin_rows_are_out_of_vantage_not_blind_in_the_central_lane() -> None:
    """Structurally-unevaluable-here is a THIRD state, distinct from blind.

    Blind means "this lane should have read it and could not" — b02's warning,
    which must stay loud. Out-of-vantage means "no credential this lane holds
    could ever answer this row, and a named other lane owns it". Collapsing
    the two would flag both admin rows in every automated run forever, which
    trains operators to ignore the blind-row signal entirely.
    """
    ctx = make_context(table=_blind_admin_table())
    manifest = fetch_manifest(ctx=ctx)
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log)
    blind = _blind_rows_by_id(log=log)

    assert "secret-names" not in blind
    assert "branch-protection" not in blind
    assert result.blind_rows == len(blind)
    assert result.out_of_vantage_rows == 2


def test_out_of_vantage_report_names_the_lane_that_owns_the_row() -> None:
    """An out-of-vantage row is only actionable if the report says who DOES run it."""
    ctx = make_context(table=_blind_admin_table())
    manifest = fetch_manifest(ctx=ctx)
    log = RecordingLog()

    assert manifest is not None
    _ = run_member_rows(ctx=ctx, manifest=manifest, log=log)
    reported = {fields["row"]: fields for fields in log.fields_for(event=_OUT_OF_VANTAGE_EVENT)}

    assert set(reported) == {"secret-names", "branch-protection"}
    for fields in reported.values():
        assert fields["applicable"] == 2
        assert fields["vantage"] == "admin"
        assert fields["owned_by"] == "check-fleet-conformance-admin"


def test_central_lane_never_spends_an_api_read_on_an_admin_row() -> None:
    """Out-of-vantage rows are skipped BEFORE their assert runs, not after.

    The ~35-API-read cost of the central sweep is why local `just check` does
    not run it. Filtering by vantage before dispatch means the split makes the
    automated sweep cheaper, never more expensive.
    """
    calls: list[tuple[str, ...]] = []
    table = _two_member_table(blind_app_installation=False)
    inner = make_runner(table=table)

    def recording(*, args: list[str], stdin: str | None = None) -> GhResult:
        calls.append(tuple(args))
        return inner(args=args, stdin=stdin)

    ctx = FleetContext(owner="acme", run_gh=recording)
    manifest = fetch_manifest(ctx=ctx)
    assert manifest is not None
    _ = run_member_rows(ctx=ctx, manifest=manifest, log=_log())

    assert not [call for call in calls if any("actions/secrets" in arg for arg in call)]
    assert not [call for call in calls if any("branches/master/protection" in arg for arg in call)]


def test_admin_lane_runs_exactly_the_admin_rows() -> None:
    """The mirror assertion: the admin lane evaluates the rows the central one cannot."""
    ctx = make_context(table=_two_member_table(blind_app_installation=False))
    manifest = fetch_manifest(ctx=ctx)
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantage="admin")
    reported = {fields["row"] for fields in log.fields_for(event=_OUT_OF_VANTAGE_EVENT)}

    # Every NON-admin row is out of the admin lane's vantage, and the two admin
    # rows evaluated cleanly against the green table — zero blind, zero errors.
    assert "secret-names" not in reported
    assert "branch-protection" not in reported
    assert result.blind_rows == 0
    assert result.error_findings == 0


def test_discovery_sweep_flags_unmanifested_fleet_repos() -> None:
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


def test_discovery_sweep_uses_fleet_shape_wording() -> None:
    table = _green_table()
    table[_REPOS_ARGS] = ok(payload=[{"name": "livespec-straggler", "topics": []}])
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx)
    log = RecordingLog()

    assert manifest is not None
    assert run_discovery_sweep(ctx=ctx, manifest=manifest, log=log) == 1
    assert log.events == ["fleet-shaped repo is not registered in the fleet manifest"]


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


def test_main_blind_row_still_exits_zero(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sweep whose rows went blind is still a PASS: warning severity, exit 0."""
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_two_member_table())
    assert fleet_conformance.main() == 0


def test_main_error_findings_exit_four(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_green_table(topics=[]))
    assert fleet_conformance.main() == 4


def test_main_emits_member_verdicts(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_path = tmp_path / "member-verdicts.json"
    table = _green_table(topics=[])
    del table[_SECRETS_ARGS]
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fleet-conformance",
            "--owner",
            "acme",
            "--emit-member-verdicts",
            str(output_path),
        ],
    )
    _patch_runner(monkeypatch=monkeypatch, table=table)

    assert fleet_conformance.main() == 4
    assert json.loads(output_path.read_text()) == [
        {
            "member": "widget",
            "conformant": False,
            "failing_rows": ["topic-livespec-sibling"],
        }
    ]


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
