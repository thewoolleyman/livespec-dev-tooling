"""Tests for `livespec_dev_tooling/fleet/fleet_conformance.py`.

Engine functions run in-process against canned-response contexts; the
CLI entry point is exercised across its lever / precondition / finding
/ success branches, plus one `python -m` subprocess invocation for the
`__main__` guard (lever unset → fast logged skip).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from _gh_railway import lift_gh
from _protection_fixtures import aligned_merge_settings_payload, aligned_protection_payload
from returns.io import IOFailure, IOSuccess
from returns.result import Failure

from livespec_dev_tooling.config import REQUIRED_ROLE_KEYS, UNION_ROLE_KEYS, Config
from livespec_dev_tooling.fleet import _cli_owner, _lanes, fleet_conformance
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhDownloader,
    GhOutcome,
    GhResult,
    GhRunner,
    OriginRemoteUnresolved,
    RowOutcome,
    RowPass,
)
from livespec_dev_tooling.fleet._contract_model import ObligationRow
from livespec_dev_tooling.fleet._contract_rows import (
    CENTRAL_APP_VANTAGE,
    CENTRAL_VANTAGE,
    REPO_CLASSES,
)
from livespec_dev_tooling.fleet._snapshot import DownloadOutcome, DownloadResult
from livespec_dev_tooling.fleet.fleet_conformance import (
    central_run_vantages,
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
_INSTALL_ARGS: tuple[str, ...] = ("api", "installation/repositories?per_page=100&page=1")
_REPOS_ARGS: tuple[str, ...] = ("api", "users/acme/repos?per_page=100")
_REPOS_PAGE_2_ARGS: tuple[str, ...] = ("api", "users/acme/repos?per_page=100&page=2")

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

# The vantage set an AUTOMATED central run holds (the fleet App
# installation token claims `central-app` on top of plain `central`),
# passed explicitly where a test exercises the CI-shaped sweep.
_AUTOMATED_VANTAGES = frozenset({CENTRAL_VANTAGE, CENTRAL_APP_VANTAGE})
# Named rather than inlined so ruff's S106 (hardcoded password in a
# `token=` argument) does not fire on every credential-class assertion.
_APP_TOKEN = "ghs_app-installation"
_OPERATOR_TOKEN = "ghp_operator-pat"

_CI_YML = "jobs:\n  check:\n    strategy:\n      matrix:\n        target:\n          - check-a\n"


def _all_required_role_keys_block() -> str:
    """Every required role key declared the way a CONFORMANT member declares it.

    The two halves are deliberately spelled differently, because the schema
    treats them differently (livespec-dev-tooling-8o8e.1). For a UNION key the
    declared value IS a consuming check's scan universe, so `[]` made that check
    scan nothing and exit 0 — the ambiguity the `role-key-spellings` row now
    rejects, which is why this fixture must carry a blessed declared-absent
    spelling instead. For every OTHER required key emptiness makes the consuming
    check STRICTER rather than blinder, so `[]` / `""` stays legitimate and is
    kept here on purpose: rendering both halves the same way would teach the
    next reader of this fixture a rule that is wrong for five of the keys.
    """
    lines = ["[tool.livespec_dev_tooling]"]
    fields = Config.__dataclass_fields__
    for key in sorted(REQUIRED_ROLE_KEYS):
        if key in UNION_ROLE_KEYS:
            lines.append(f'{key} = {{ not_applicable = "fixture member has no {key}" }}')
            continue
        default = fields[key].default
        value = '""' if default is None else "[]"
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


_PYPROJECT = (
    '[tool.uv.sources]\nlivespec-dev-tooling = { git = "x", tag = "v1.0.0" }\n\n'
    + _all_required_role_keys_block()
)
# The fixture members are BEADS-BACKED with a consistent connection pair,
# like every live fleet member: blind rows are error severity, so a canned
# fleet where `beads-tenant-connection-consistency` could never evaluate
# would fail every sweep for a fixture artifact rather than a real defect.
_BEADS_CONFIG = (
    "dolt.server-host: 127.0.0.1\n"
    "dolt.server-port: 3307\n"
    "dolt.server-user: tenant\n"
    "dolt.database: beads_tenant\n"
    "dolt.prefix: fleet\n"
)
_LIVESPEC_JSONC = (
    '{"harnesses": {"claude": {"status": "exempt", "reason": "library; no harness surface"}}, '
    '"implementation": {"plugin": "impl-beads"}, '
    '"impl-beads": {"dispatcher": {"acceptance_mode": "ai-only"}, '
    '"connection": {"server_host": "127.0.0.1", "server_port": 3307, '
    '"server_user": "tenant", "database": "beads_tenant", "prefix": "fleet"}}}'
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


# The credential preflight (livespec-dev-tooling-z4qi) probes `rate_limit`
# before any row runs, so every fixture must answer it or the sweep correctly
# stops at "credential unusable" before reaching what the test is about.
# Answered HERE rather than in each table so the probe stays invisible to tests
# that are not about it — and so a test that DOES want a rejected credential
# still gets one simply by overriding this key.
_PROBE_KEY = ("api", "rate_limit")
_PROBE_OK = GhResult(returncode=0, stdout='{"rate": {"remaining": 4999}}', stderr="")


def make_runner(*, table: dict[tuple[str, ...], GhResult]) -> GhRunner:
    """Canned-response `GhRunner` keyed on full arg tuples."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        key = tuple(args)
        if key == _PROBE_KEY and key not in table:
            return _PROBE_OK
        return table.get(key, GhResult(returncode=1, stdout="", stderr="no canned"))

    return lift_gh(run)


def _empty_member_archive(*, repo: str) -> bytes:
    """A real gzip tarball for `repo` carrying one empty first-party package.

    FLEET-vantage rows read a member's whole TREE, not individual files, so a
    fixture answering only `run_gh` leaves them unable to evaluate — they skip
    for every member and trip the blind-row error. Serving a real (if bare)
    archive is what lets a lane test exercise the LANE rather than the
    downloader; a member with no consumable source has no cross-member edges
    and passes ON THE MERITS, which is the outcome these tests want.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        payload = b""
        entry = tarfile.TarInfo(name=f"acme-{repo}-abc123/pkg/__init__.py")
        entry.size = len(payload)
        bundle.addfile(entry, io.BytesIO(payload))
    return buffer.getvalue()


def make_downloader() -> GhDownloader:
    """A downloader serving every requested member a bare, valid archive."""

    def download(*, args: list[str], dest: Path) -> DownloadResult:
        _ = dest.write_bytes(_empty_member_archive(repo=args[1].split("/")[2]))
        return IOSuccess(DownloadOutcome(returncode=0, stderr=""))

    return download


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""
    return FleetContext(
        owner="acme", run_gh=make_runner(table=table), download_gh=make_downloader()
    )


def ok(*, payload: object) -> GhResult:
    """A successful API result carrying a JSON payload."""
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def raw(*, text: str) -> GhResult:
    """A successful raw-content API result."""
    return GhResult(returncode=0, stdout=text, stderr="")


_AGENTS_MD = """# Agent instructions

## Decision authority — when to ask, proceed, or self-resolve

Ported from `livespec/AGENTS.md` §"When to ask, proceed, or self-resolve".

- **Drive authorized work to completion; do not over-ask.** Execute the whole
  arc without re-confirming each already-authorized step.

## Repository mutation protocol

## Agent prerequisites for plugin work

## Beads runtime prerequisites

## Daily commands

## Revise co-edit discipline — `tests/heading-coverage.json`
"""


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
        "AGENTS.md",
        ".github/workflows/ci.yml",
        ".github/workflows/bump-pin-from-dispatch.yml",
        ".github/workflows/pin-freshness.yml",
        ".github/workflows/release-dispatch.yml",
        "pyproject.toml",
        ".livespec.jsonc",
        ".beads/config.yaml",
        ".claude/settings.json",
        "justfile",
    ]
    tree_payload = {
        "tree": [{"path": p, "mode": "100644"} for p in tracked],
        "truncated": False,
    }
    return {
        ("api", f"repos/acme/{repo}/git/trees/master?recursive=1"): ok(payload=tree_payload),
        contents("AGENTS.md"): raw(text=_AGENTS_MD),
        contents(".livespec.jsonc"): raw(text=_LIVESPEC_JSONC),
        contents(".beads/config.yaml"): raw(text=_BEADS_CONFIG),
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
    """Logger test double capturing each event's text AND its structured fields.

    Error-level events are additionally captured in `error_events`, so a
    severity escalation (blind rows are error, not warning) is assertable
    rather than invisible behind the level-agnostic `events` list.
    """

    def __init__(self) -> None:
        self.events: list[str] = []
        self.error_events: list[str] = []
        self.records: list[tuple[str, dict[str, object]]] = []

    def error(self, event: str, **kwargs: object) -> None:
        self.events.append(event)
        self.error_events.append(event)
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
    """Both failure stages land on the failure track; the success carries the value.

    The two failures are compared as VALUES here rather than as one
    sentinel. Which stage each one is, and that they differ from each
    other, is pinned in `test_fleet_conformance_manifest_result.py`.
    """
    ctx = make_context(table={_MANIFEST_ARGS: raw(text=_MANIFEST_SOURCE)})
    manifest = fetch_manifest(ctx=ctx).unwrap()
    assert manifest.member_names() == frozenset({"widget"})
    assert isinstance(fetch_manifest(ctx=make_context(table={})), Failure)
    bad = make_context(table={_MANIFEST_ARGS: raw(text="not jsonc {{{")})
    assert isinstance(fetch_manifest(ctx=bad), Failure)


def _blind_rows_by_id(*, log: RecordingLog) -> dict[object, dict[str, object]]:
    """The blind-row warnings the sweep emitted, keyed by obligation row id."""
    return {fields["row"]: fields for fields in log.fields_for(event=_BLIND_ROW_EVENT)}


def test_blind_row_reported_when_no_applicable_member_could_be_evaluated() -> None:
    """A row skipped for EVERY applicable member enforced nothing — an ERROR, loudly.

    The sweep runs with the automated vantage set (the App token context
    OWNS `app-installation`), and the one read that row depends on answers
    for nobody: the row is blind, and the blind report is error-level (the
    b02 escalation — an owned row that enforced nothing fails the run).
    """
    ctx = make_context(table=_two_member_table())
    manifest = fetch_manifest(ctx=ctx).unwrap()
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantages=_AUTOMATED_VANTAGES)
    blind = _blind_rows_by_id(log=log)

    assert "app-installation" in blind
    assert blind["app-installation"]["applicable"] == 2
    assert blind["app-installation"]["skipped"] == 2
    # Per-member reasons carry a `<repo>: ` prefix; the blind-row report lists
    # the DISTINCT underlying causes, so two members sharing one cause read as one.
    assert blind["app-installation"]["reasons"] == (
        "installation repositories unreadable (needs an App installation token)",
    )
    assert _BLIND_ROW_EVENT in log.error_events
    assert result.blind_rows == len(blind)
    assert result.error_findings == 0


def test_blind_rows_never_change_the_error_count() -> None:
    """Blind rows fail the run at the lane level, never by inflating error_findings.

    The two counts stay SEPARATE so a summary can attribute a failure to
    violated obligations vs owned-but-unreadable rows; the lane mains fold
    both into the same non-zero exit.
    """
    ctx = make_context(table=_two_member_table())
    manifest = fetch_manifest(ctx=ctx).unwrap()
    result = run_member_rows(ctx=ctx, manifest=manifest, log=_log(), vantages=_AUTOMATED_VANTAGES)
    assert result.error_findings == 0
    assert result.blind_rows == 1


def test_partially_skipped_row_is_not_blind() -> None:
    """A row evaluated for even ONE applicable member did enforce something."""
    table = _two_member_table(blind_app_installation=False, gadget_topics_readable=False)
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx).unwrap()
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantages=_AUTOMATED_VANTAGES)
    blind = _blind_rows_by_id(log=log)

    # `topic-livespec-sibling` skipped for gadget but answered for widget, and
    # `app-installation` answered for both: partial blindness is not blindness.
    assert "topic-livespec-sibling" not in blind
    assert "app-installation" not in blind
    assert result.blind_rows == len(blind)


def test_run_member_rows_hands_row_functions_the_manifest_roster(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A FLEET-vantage row is answerable only if it can see the whole roster.

    `FleetContext.members` defaults to EMPTY — the fail-closed spelling — and
    its docstring says the central engine populates it once the manifest
    resolves. NOTHING DID. The context is a FROZEN dataclass built in `main()`
    BEFORE the manifest is fetched, no construction site anywhere passed a
    roster, and there is no `dataclasses.replace` in the package, so the field
    held its `()` default for every run either engine has ever made.

    IT SURFACED ONLY WHEN A ROW NEEDED IT. No row asked for the roster until
    the cross-repo public-API row, so an unpopulated field broke nothing and
    READ AS WIRED — its docstring described an intention as a fact.

    It would not have under-enforced quietly: a fleet-vantage row seeing an
    empty roster returns the named skip it was built to return, and a row that
    skips for EVERY applicable member is BLIND, which this repo escalates to an
    error. So registering such a row would have failed the run forever rather
    than passing green over nothing. The fail-closed default did its job; the
    wiring behind it was simply absent.

    `run_member_rows` is the ONE place holding both the context and the
    manifest, which is why the join belongs here rather than in either engine's
    `main()`: a caller cannot then pass a manifest alongside a roster-less
    context, and both lanes are fixed by one edit.
    """
    seen: list[tuple[FleetMember, tuple[FleetMember, ...]]] = []
    readable: list[bool] = []

    def probe(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
        # Both halves are recorded on purpose: the row protocol hands a row ONE
        # member, and the whole point of the roster is that it must ALSO see
        # the other eight.
        seen.append((member, ctx.members))
        # And the roster must be USABLE, not merely present. A fleet row's next
        # act after reading `ctx.members` is to read each member's TREE, so the
        # probe does exactly that: a roster whose members cannot be snapshotted
        # is a roster the row still cannot answer from, and asserting only on
        # the list would pass over that.
        readable.extend(
            not isinstance(ctx.member_tree_snapshot(repo=other.repo), IOFailure)
            for other in ctx.members
        )
        return RowPass()

    probe_row = ObligationRow(
        row_id="roster-probe",
        obligation_type="committed-file",
        applies_to=frozenset(REPO_CLASSES),
        assert_member=probe,
        manual_hint="probe row; never registered in OBLIGATION_ROWS",
    )
    monkeypatch.setattr(_lanes, "rows_for", lambda *, repo_class: (probe_row,))  # noqa: ARG005

    ctx = make_context(table=_green_table())
    manifest = fetch_manifest(ctx=ctx).unwrap()
    run_member_rows(ctx=ctx, manifest=manifest, log=_log())

    roster = tuple(manifest.members)
    assert seen == [(member, roster) for member in roster]
    assert roster != ()
    assert readable == [True] * (len(roster) * len(roster))


def test_member_rows_all_green_yields_zero_errors() -> None:
    ctx = make_context(table=_green_table())
    manifest = fetch_manifest(ctx=ctx).unwrap()
    assert run_member_rows(ctx=ctx, manifest=manifest, log=_log()).error_findings == 0


def test_member_rows_logs_named_exclusions() -> None:
    ctx = make_context(table=_green_table())
    manifest = fetch_manifest(ctx=ctx).unwrap()
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log)
    reported = {
        fields["row"]: fields
        for fields in log.fields_for(event="fleet obligation excluded with reason")
    }

    assert result.error_findings == 0
    assert reported["required-role-keys-declared"]["reason"] == ("no layout-dependent checks wired")


def test_member_rows_counts_errors_but_not_warnings_or_skips() -> None:
    # Stale pin → warning; missing topic → error. The secrets read is dropped
    # too, but `secret-names` is an ADMIN-vantage row the central lane never
    # calls, so its absence is inert here rather than a skip.
    table = _green_table(latest_tag="v2.0.0", topics=[])
    del table[_SECRETS_ARGS]
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx).unwrap()
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
    manifest = fetch_manifest(ctx=ctx).unwrap()
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantages=_AUTOMATED_VANTAGES)
    blind = _blind_rows_by_id(log=log)

    assert "secret-names" not in blind
    assert "branch-protection" not in blind
    assert result.blind_rows == len(blind)
    assert result.out_of_vantage_rows == 2


def test_out_of_vantage_report_names_the_lane_that_owns_the_row() -> None:
    """An out-of-vantage row is only actionable if the report says who DOES run it."""
    ctx = make_context(table=_blind_admin_table())
    manifest = fetch_manifest(ctx=ctx).unwrap()
    log = RecordingLog()

    assert manifest is not None
    _ = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantages=_AUTOMATED_VANTAGES)
    reported = {fields["row"]: fields for fields in log.fields_for(event=_OUT_OF_VANTAGE_EVENT)}

    assert set(reported) == {"secret-names", "branch-protection"}
    for fields in reported.values():
        assert fields["applicable"] == 2
        assert fields["vantage"] == "admin"
        assert fields["owned_by"] == "check-fleet-conformance-admin"


def test_local_central_run_reports_app_installation_out_of_vantage() -> None:
    """Without the App installation token, `app-installation` is owned elsewhere.

    A LOCAL central sweep holds an operator credential, under which
    `GET /installation/repositories` can never answer — so the row is
    out-of-vantage naming the App-token contexts that do enforce it, NOT
    blind, and costs zero API reads. This is the completion of the vantage
    model: after it, `blind_rows` is structurally 0 in every healthy
    context, which is what made the blind-to-error escalation shippable.
    """
    calls: list[tuple[str, ...]] = []
    inner = make_runner(table=_two_member_table())

    def recording(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        calls.append(tuple(args))
        return inner(args=args, stdin=stdin)

    ctx = FleetContext(owner="acme", run_gh=recording, download_gh=make_downloader())
    manifest = fetch_manifest(ctx=ctx).unwrap()
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(
        ctx=ctx, manifest=manifest, log=log, vantages=frozenset({CENTRAL_VANTAGE})
    )
    reported = {fields["row"]: fields for fields in log.fields_for(event=_OUT_OF_VANTAGE_EVENT)}

    assert result.blind_rows == 0
    assert "app-installation" in reported
    assert reported["app-installation"]["vantage"] == CENTRAL_APP_VANTAGE
    owned_by = reported["app-installation"]["owned_by"]
    assert isinstance(owned_by, str)
    assert "App installation token" in owned_by
    assert _INSTALL_ARGS not in calls


def test_central_run_vantages_follows_the_credential_class() -> None:
    """`central-app` is held exactly when the run's token is an App installation token.

    The `ghs_` prefix marks GitHub's server-to-server (installation)
    tokens — the only credential class under which the app-installation
    read answers. An operator PAT or no token at all leaves the run
    holding plain `central`.

    The token arrives as a PARAMETER now, so this pins the RULE and no
    longer the environment; which env vars supply it, in which order, is
    pinned at the boundary that reads them
    (`test_main_reads_the_gh_token_env_pair_in_gh_s_own_order`).
    """
    assert central_run_vantages(token="") == frozenset({CENTRAL_VANTAGE})
    assert central_run_vantages(token=_OPERATOR_TOKEN) == frozenset({CENTRAL_VANTAGE})
    assert central_run_vantages(token=_APP_TOKEN) == _AUTOMATED_VANTAGES


def test_central_lane_never_spends_an_api_read_on_an_admin_row() -> None:
    """Out-of-vantage rows are skipped BEFORE their assert runs, not after.

    The ~35-API-read cost of the central sweep is why local `just check` does
    not run it. Filtering by vantage before dispatch means the split makes the
    automated sweep cheaper, never more expensive.
    """
    calls: list[tuple[str, ...]] = []
    table = _two_member_table(blind_app_installation=False)
    inner = make_runner(table=table)

    def recording(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        calls.append(tuple(args))
        return inner(args=args, stdin=stdin)

    ctx = FleetContext(owner="acme", run_gh=recording)
    manifest = fetch_manifest(ctx=ctx).unwrap()
    _ = run_member_rows(ctx=ctx, manifest=manifest, log=_log())

    assert not [call for call in calls if any("actions/secrets" in arg for arg in call)]
    assert not [call for call in calls if any("branches/master/protection" in arg for arg in call)]


def test_admin_lane_runs_exactly_the_admin_rows() -> None:
    """The mirror assertion: the admin lane evaluates the rows the central one cannot."""
    ctx = make_context(table=_two_member_table(blind_app_installation=False))
    manifest = fetch_manifest(ctx=ctx).unwrap()
    log = RecordingLog()

    assert manifest is not None
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantages=frozenset({"admin"}))
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
    manifest = fetch_manifest(ctx=ctx).unwrap()
    assert run_discovery_sweep(ctx=ctx, manifest=manifest, log=_log()) == 2


def test_discovery_sweep_paginates_owner_repo_list() -> None:
    table = _green_table()
    table[_REPOS_ARGS] = ok(
        payload=[{"name": f"unrelated-{index}", "topics": []} for index in range(100)]
    )
    table[_REPOS_PAGE_2_ARGS] = ok(payload=[{"name": "livespec-driver-pi", "topics": []}])
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx).unwrap()
    assert run_discovery_sweep(ctx=ctx, manifest=manifest, log=_log()) == 1


def test_discovery_sweep_uses_fleet_shape_wording() -> None:
    table = _green_table()
    table[_REPOS_ARGS] = ok(payload=[{"name": "livespec-straggler", "topics": []}])
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx).unwrap()
    log = RecordingLog()

    assert manifest is not None
    assert run_discovery_sweep(ctx=ctx, manifest=manifest, log=log) == 1
    assert log.events == ["fleet-shaped repo is not registered in the fleet manifest"]


def test_discovery_sweep_unreadable_repo_list_warns_and_passes() -> None:
    table = _green_table()
    del table[_REPOS_ARGS]
    ctx = make_context(table=table)
    manifest = fetch_manifest(ctx=ctx).unwrap()
    assert run_discovery_sweep(ctx=ctx, manifest=manifest, log=_log()) == 0


def _patch_runner(
    *, monkeypatch: pytest.MonkeyPatch, table: dict[tuple[str, ...], GhResult]
) -> None:
    monkeypatch.setattr(fleet_conformance, "default_gh_runner", make_runner(table=table))
    # BOTH I/O seams, because a `main()` test replacing only the gh runner would
    # still reach the real network through the tarball downloader — and would do
    # so SILENTLY, since a failed download is a legitimate named skip rather than
    # an error the test could notice.
    monkeypatch.setattr(fleet_conformance, "default_gh_downloader", make_downloader())
    # Keep `main()` tests on the canned remote fixtures. If a test patches
    # `resolve_repo_name` to a fixture member while leaving local_vantage live,
    # the public-api row can scan this real checkout as though it were that
    # fixture repo, which makes the test depend on sandbox contents and runtime.
    monkeypatch.setattr(fleet_conformance, "local_vantage", lambda **_kwargs: (None, None))


def test_main_lever_unset_skips_with_exit_zero(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVESPEC_RUN_FLEET_CONFORMANCE", raising=False)
    monkeypatch.setattr(sys, "argv", ["fleet-conformance"])
    assert fleet_conformance.main() == 0


def test_main_owner_unresolvable_is_precondition_failure(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance"])

    def no_owner(*, argument: str | None = None, cwd: object = None) -> object:
        del argument, cwd
        return IOFailure(OriginRemoteUnresolved(reason="git-not-run", detail="git absent"))

    # Patched one layer DOWN so the real `resolved_owner` runs and emits the
    # three-way diagnostic; patching it directly would skip the code under test.
    monkeypatch.setattr(_cli_owner, "owner_or_origin", no_owner)
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


def test_main_local_run_exits_zero_with_app_installation_out_of_vantage(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tokenless local sweep is healthy: no blind row, exit 0.

    The same table (no installation/repositories read canned) fails the
    run under an App token, as a blind `app-installation` row. Locally
    that read is structurally unanswerable, so the row is out-of-vantage
    rather than blind — and the run stays green.
    """
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_two_member_table())
    assert fleet_conformance.main() == 0


def test_main_app_token_run_fails_on_a_blind_app_installation_row(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under an App installation token the lane OWNS `app-installation`: blind fails.

    The `ghs_` token claims the `central-app` vantage, the canned table
    answers the installation read for nobody, and the row this run should
    have evaluated enforced nothing — error severity, exit 4 (b02's
    recorded end state; no lever, env var, or exemption can demote it).
    """
    monkeypatch.setenv("GH_TOKEN", "ghs_minted-by-ci")
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_two_member_table())
    assert fleet_conformance.main() == 4


def test_main_reads_the_gh_token_env_pair_in_gh_s_own_order(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`GH_TOKEN` first, `GITHUB_TOKEN` second — the pair `gh` itself consults.

    The env read is the supervisor's, not the rule's, so THIS is where the
    pair and its precedence are pinned. Both directions are asserted
    against the same canned table, whose `app-installation` read answers
    for nobody: a run that claims `central-app` exits 4 on the blind row,
    one that does not exits 0. So the exit code reports which variable the
    boundary actually believed.

    The precedence leg sets the two variables to OPPOSITE classes. A
    boundary that consulted only `GITHUB_TOKEN`, or that consulted the two
    in the other order, would classify the run App-class and exit 4 — an
    assertion on a single variable cannot tell those apart.
    """
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_two_member_table())
    monkeypatch.setenv("GH_TOKEN", "ghp_operator-pat")
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_dispatch-sandbox-projects-this")
    precedence = fleet_conformance.main()
    monkeypatch.delenv("GH_TOKEN")

    assert precedence == 0 and fleet_conformance.main() == 4


def test_main_blind_central_row_exits_four(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A blind row within the plain `central` vantage fails a local run too.

    Both members' topics reads are dropped, so `topic-livespec-sibling` —
    a row every central run owns whatever its credential — skips for
    every applicable member: blind, error severity, exit 4.
    """
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    table = _two_member_table(blind_app_installation=False)
    for repo in ("widget", "gadget"):
        del table[("api", f"repos/acme/{repo}/topics")]
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=table)
    assert fleet_conformance.main() == 4


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


def test_main_defers_the_adopter_leg_out_of_vantage_without_reading_adopters(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The central lane never reads an adopter repo — the admin lane owns the leg.

    The manifest carries a `released` adopter, but every automated
    central-lane context holds the fleet App installation token, which
    MUST NOT reach adopter repos (livespec non-functional-requirements:
    the fleet App is restricted to fleet repos only) — so the adopter
    currency leg is deferred out-of-vantage at zero API cost and the run
    stays green with nothing else changed. The deferral line's fields
    (owner recipe, applicable count) are asserted in `test_adopter_lane`.
    """
    calls: list[tuple[str, ...]] = []
    table = _green_table()
    table[_MANIFEST_ARGS] = raw(
        text=(
            '{"owner": "acme", "members": [{"repo": "widget", "class": "library"}], '
            '"adopters": [{"repo": "adopted", "profile": ["baseline"], "posture": "released"}]}'
        )
    )
    inner = make_runner(table=table)

    def recording(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        calls.append(tuple(args))
        return inner(args=args, stdin=stdin)

    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    monkeypatch.setattr(fleet_conformance, "default_gh_runner", recording)
    monkeypatch.setattr(fleet_conformance, "default_gh_downloader", make_downloader())

    assert fleet_conformance.main() == 0
    assert not [call for call in calls if any("adopted" in arg for arg in call)]


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


def _unwired_member_table() -> dict[tuple[str, ...], GhResult]:
    """Two members where `gadget` is REGISTERED but UNWIRED, and `widget` is clean.

    This is the shape of the incident this scoping exists for: a member was added to
    the manifest before its wiring landed, and because the manifest is fetched at run
    time the obligation applied instantly — reddening a repo that neither owned nor
    could fix the problem.
    """
    table = _two_member_table(blind_app_installation=False)
    unwired_tree = {
        "tree": [
            {"path": path, "mode": "100644"}
            for path in (
                ".github/workflows/ci.yml",
                "pyproject.toml",
                ".livespec.jsonc",
                ".beads/config.yaml",
                ".claude/settings.json",
                "justfile",
            )
        ],
        "truncated": False,
    }
    table[("api", "repos/acme/gadget/git/trees/master?recursive=1")] = ok(payload=unwired_tree)
    return table


def test_member_ci_exit_is_scoped_to_the_running_member(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """The incident, pinned: an unwired member must not redden a DIFFERENT member's CI.

    `gadget` is registered but unwired. Running as `widget` under `--member-ci`, the
    exit status must be 0 — widget owns no violation and cannot fix gadget's. Running
    as `gadget` must be non-zero, because it owns the violation. Same manifest, same
    canned reads, same evaluation; only the ATTRIBUTION of the exit differs.

    Surfacing and BLOCKING are separable, and this separates them: gadget's finding is
    still REPORTED in widget's log (asserted below), because register-first
    deliberately wants an unwired member visible. What it must not do is fail the merge
    gate of a repo with no defect of its own.
    """
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme", "--member-ci"])
    _patch_runner(monkeypatch=monkeypatch, table=_unwired_member_table())

    monkeypatch.setattr(
        fleet_conformance, "resolve_repo_name", lambda **_kwargs: IOSuccess("widget")
    )
    assert fleet_conformance.main() == 0, "an unwired OTHER member must not fail this repo's CI"

    monkeypatch.setattr(
        fleet_conformance, "resolve_repo_name", lambda **_kwargs: IOSuccess("gadget")
    )
    assert fleet_conformance.main() != 0, "a member owning the violation MUST fail its own CI"


def test_member_ci_still_reports_other_members_findings(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scoping changes the EXIT STATUS only — evaluation and reporting are untouched.

    Filtering the evaluation instead would make each repo blind to fleet state and
    would silently shrink what the central sweep's own per-repo runs cover, so the
    other member's violation must still appear at error severity in the log even
    though it no longer affects this repo's exit.
    """
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme", "--member-ci"])
    _patch_runner(monkeypatch=monkeypatch, table=_unwired_member_table())
    monkeypatch.setattr(
        fleet_conformance, "resolve_repo_name", lambda **_kwargs: IOSuccess("widget")
    )

    recorder = RecordingLog()
    monkeypatch.setattr(fleet_conformance.structlog, "get_logger", lambda *_a, **_k: recorder)

    assert fleet_conformance.main() == 0
    violations = [
        fields
        for fields in recorder.fields_for(event="fleet obligation violated")
        if fields.get("member") == "gadget"
    ]
    assert violations, f"gadget's violation must still be reported; got {recorder.records!r}"


def test_fleet_view_is_the_default_so_a_forgotten_flag_fails_safe(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WITHOUT `--member-ci` the run is fleet-wide and ANY member's violation fails.

    The polarity is deliberate and load-bearing. The scheduled sweep and the release
    fan-out preflight are the fleet-level contexts, and all three legs run inside a
    livespec-dev-tooling checkout, so running-as derivation alone cannot tell them
    apart. Defaulting to the STRICT behavior means a future fleet-level caller that
    forgets to declare its surface still fails loudly, instead of silently becoming a
    one-repo gate — which is the vacuity hole livespec-dev-tooling-b02 and -29qo exist
    to close.
    """
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    _patch_runner(monkeypatch=monkeypatch, table=_unwired_member_table())
    monkeypatch.setattr(
        fleet_conformance, "resolve_repo_name", lambda **_kwargs: IOSuccess("widget")
    )

    assert fleet_conformance.main() != 0, "the default must remain fleet-wide and strict"


def test_member_ci_fails_loudly_when_the_running_repo_is_not_in_the_manifest(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unresolvable or unregistered running repo is a precondition failure, not a pass.

    If the running-as derivation cannot place this repo in the manifest, scoping the
    exit to "this repo's findings" would scope it to NOTHING and pass vacuously — a
    gate that enforces nothing while reporting success. It must say so loudly instead.
    """
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme", "--member-ci"])
    _patch_runner(monkeypatch=monkeypatch, table=_unwired_member_table())

    monkeypatch.setattr(
        fleet_conformance, "resolve_repo_name", lambda **_kwargs: IOSuccess("not-a-member")
    )
    assert fleet_conformance.main() == 1

    monkeypatch.setattr(
        fleet_conformance,
        "resolve_repo_name",
        lambda **_kwargs: IOFailure(
            OriginRemoteUnresolved(reason="not-github-remote", detail="git@gitlab.com:acme/x")
        ),
    )
    assert fleet_conformance.main() == 1


def test_main_unusable_credential_fails_before_any_row_runs(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate is NOT relaxed by the z4qi preflight — a rejected token still reds.

    This is the assertion that must never regress. `livespec-dev-tooling-z4qi`
    fixed a FALSE red (one transient rejection surfacing as nine blind rows);
    the standing risk while fixing it was demoting the TRUE red with it.
    Rejecting the probe persistently must still exit 1.
    """
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    table = _green_table()
    table[_PROBE_KEY] = GhResult(
        returncode=1, stdout="", stderr="gh: Resource not accessible (HTTP 403)"
    )
    _patch_runner(monkeypatch=monkeypatch, table=table)

    assert fleet_conformance.main() == 1


def test_main_transient_credential_rejection_recovers(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """The z4qi scenario end to end: rejected once, then the sweep proceeds.

    Before the preflight this run reddened master with nine blind rows on a
    commit that changed nothing.
    """
    monkeypatch.setenv("LIVESPEC_RUN_FLEET_CONFORMANCE", "true")
    monkeypatch.setattr(sys, "argv", ["fleet-conformance", "--owner", "acme"])
    inner = make_runner(table=_green_table())
    rejected: list[int] = [0]

    def flaky(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        if tuple(args) == _PROBE_KEY and rejected[0] == 0:
            rejected[0] += 1
            return IOSuccess(
                GhResult(returncode=1, stdout="", stderr="gh: bad credentials (HTTP 401)")
            )
        return inner(args=args, stdin=stdin)

    monkeypatch.setattr(fleet_conformance, "default_gh_runner", flaky)
    monkeypatch.setattr(fleet_conformance, "default_gh_downloader", make_downloader())
    monkeypatch.setattr(fleet_conformance, "preflight_credential", _no_sleep_preflight)

    assert fleet_conformance.main() == 0
    assert rejected[0] == 1, "the transient rejection should have been exercised"


def _no_sleep_preflight(*, ctx: object) -> object:
    """`preflight_credential` with the real logic and no real delay."""
    from livespec_dev_tooling.fleet._credential_preflight import preflight_credential

    return preflight_credential(ctx=cast("Any", ctx), sleep=lambda _seconds: None)
