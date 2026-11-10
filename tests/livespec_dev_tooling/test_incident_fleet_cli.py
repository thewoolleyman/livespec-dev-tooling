"""The runnable fleet audit command, its sources and the one incident enablement step."""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import subprocess
import sys
from dataclasses import replace
from itertools import takewhile
from pathlib import Path
from unittest.mock import Mock

import pytest
from returns.io import IOFailure, IOSuccess
from returns.result import Failure, Success

from livespec_dev_tooling._incident_fleet_capabilities import CAPABILITIES, SURFACE_CAPABILITY
from livespec_dev_tooling._incident_fleet_command import (
    FleetReport,
    exit_code,
    render_report,
    run_fleet_audit,
)
from livespec_dev_tooling._incident_fleet_driver_reader import read_driver_hooks
from livespec_dev_tooling._incident_fleet_recovery_reader import read_recovery_authorization
from livespec_dev_tooling._incident_fleet_sources import (
    CLAIMS_RELATIVE_PATH,
    COMMITTED_CLAIMS,
    core_manifest_reader,
    load_claims,
)
from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence, FleetAudit
from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.fleet._invocation_failure import BINARY_ABSENT, InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.incident_fleet_audit import SURFACES
from livespec_dev_tooling.incident_fleet_cli import (
    CliEnvironment,
    enable_repository,
    main,
    production_environment,
)
from livespec_dev_tooling.incident_fleet_host import HostProbe
from livespec_dev_tooling.incident_fleet_serving import ServingReader

# --- committed claims and core's manifest ---
CLAIM = {
    "repository": "example/tooling",
    "surface": "Pre-push",
    "disposition": "implemented",
    "manifest_sha256": "a" * 64,
    "source_path": "installed/component.py",
    "release_build": "1.2.3",
    "proof_ref": "independent-host-proof:receipt-1",
    "owner": "controller-owner",
    "incident_item": "incident-1",
    "cumulative_scope": "b" * 64,
    "normal_factory_proof": "factory:scope",
}


def _write_json(*, tmp_path: Path, document: object) -> Path:
    path = tmp_path / "claims.json"
    _ = path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_an_absent_claims_file_holds_no_claims_and_a_valid_one_never_carries_serving() -> None:
    assert load_claims(path=Path("/nonexistent/claims.json")) == Success(())


def test_valid_claims_load_with_an_empty_serving_build(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path=tmp_path,
        document={"schema": 1, "evidence": [CLAIM, {**CLAIM, "reason": "because"}]},
    )
    claims = load_claims(path=path).unwrap()
    assert [claim.surface for claim in claims] == ["Pre-push", "Pre-push"]
    assert [claim.serving_build for claim in claims] == ["", ""]
    assert [claim.reason for claim in claims] == ["", "because"]
    assert claims[0].release_build == "1.2.3"


@pytest.mark.parametrize(
    "document",
    [
        {"schema": 2, "evidence": []},
        {"schema": 1},
        ["not", "an", "object"],
        {"schema": 1, "evidence": ["not-an-object"]},
        {"schema": 1, "evidence": [{**CLAIM, "serving_build": "1.2.3"}]},
        {"schema": 1, "evidence": [{**CLAIM, "owner": 7}]},
        {"schema": 1, "evidence": [{**CLAIM, "reason": 7}]},
        {"schema": 1, "evidence": [{k: v for k, v in CLAIM.items() if k != "owner"}]},
    ],
)
def test_malformed_claims_or_a_caller_supplied_serving_build_are_refused(
    tmp_path: Path, document: object
) -> None:
    assert isinstance(load_claims(path=_write_json(tmp_path=tmp_path, document=document)), Failure)


def test_unparseable_claims_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "claims.json"
    _ = path.write_text("{", encoding="utf-8")
    assert isinstance(load_claims(path=path), Failure)


def _command_answer(*, stdout: str = "", returncode: int = 0) -> CommandOutcome:
    return IOSuccess(CommandResult(returncode=returncode, stdout=stdout, stderr=""))


def test_core_manifest_reader_reads_core_master_afresh_each_call() -> None:
    calls: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        calls.append(args)
        return _command_answer(stdout="manifest-bytes")

    read = core_manifest_reader(owner="example", run=run)
    assert read() == "manifest-bytes"
    assert read() == "manifest-bytes"
    assert len(calls) == 4
    assert any("example/livespec.git" in part for part in calls[0])
    assert calls[1][-1] == "HEAD:.livespec-fleet-manifest.jsonc"


def test_core_manifest_reader_reports_an_unavailable_read_as_none() -> None:
    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        return IOFailure(InvocationNotPerformed(argv=tuple(args), kind=BINARY_ABSENT, detail="x"))

    assert core_manifest_reader(owner="example", run=run)() is None


def test_the_committed_claims_are_the_ones_released_with_this_code_not_the_callers() -> None:
    root = Path(__file__).resolve().parents[2]
    assert root / CLAIMS_RELATIVE_PATH == COMMITTED_CLAIMS
    assert COMMITTED_CLAIMS.is_file()
    assert isinstance(load_claims(path=COMMITTED_CLAIMS), Success)


# --- the audit command ---
FLEET_MANIFEST = (
    '{"owner": "example",'
    ' "fleet": [{"repo": "tooling", "class": "enforcement-suite"},'
    ' {"repo": "other", "class": "enforcement-suite"}],'
    ' "adopters": [{"repo": "notes", "profile": ["instruction-only"], "posture": "none"}]}'
)
FLEET_DIGEST = hashlib.sha256(FLEET_MANIFEST.encode()).hexdigest()
GUIDANCE_SURFACES = ("Agent tool and stop guards", "Operator factory routing")


def _cap_claim(*, repository: str, surface: str) -> CapabilityEvidence:
    return CapabilityEvidence(
        repository=repository,
        surface=surface,
        disposition="implemented",
        manifest_sha256=FLEET_DIGEST,
        source_path="installed/component.py",
        release_build="v1.0.0",
        serving_build="",
        proof_ref="independent-host-proof:receipt-1",
        owner="controller-owner",
        incident_item="" if repository.endswith("notes") else "incident-1",
        cumulative_scope="" if repository.endswith("notes") else "b" * 64,
        normal_factory_proof="" if repository.endswith("notes") else "factory:scope",
    )


def _cap_claims() -> tuple[CapabilityEvidence, ...]:
    return (
        *(
            _cap_claim(repository=repository, surface=surface)
            for repository in ("example/tooling", "example/other")
            for surface in SURFACES
        ),
        *(_cap_claim(repository="example/notes", surface=surface) for surface in GUIDANCE_SURFACES),
    )


def _cap_serving(*, unreadable: frozenset[tuple[str, str]] = frozenset()) -> ServingReader:
    def read(*, repository: str, capability: str) -> str | None:
        return None if (repository, capability) in unreadable else "v1.0.0"

    return read


def _run_audit(
    *,
    texts: tuple[str | None, ...] = (FLEET_MANIFEST, FLEET_MANIFEST),
    claims: tuple[CapabilityEvidence, ...] | None = None,
    unreadable: frozenset[tuple[str, str]] = frozenset(),
) -> FleetReport:
    reads = iter(texts)
    return run_fleet_audit(
        read_manifest=lambda: next(reads, None),
        claims=_cap_claims() if claims is None else claims,
        read_serving=_cap_serving(unreadable=unreadable),
    )


def test_prints_one_row_per_surface_and_consumer_with_its_disposition_and_serving_version() -> None:
    report = _run_audit()
    lines = render_report(report=report)
    rows = [line for line in lines if line.startswith("row\t")]
    assert len(rows) == 37 * 2 + 37
    assert "row\texample/tooling\tHook installation and wiring\timplemented\tv1.0.0" in rows
    assert "row\texample/notes\tPre-push\tnot-applicable\t-" in rows
    assert "ready\texample/other" in lines
    assert "ready\texample/tooling" in lines
    assert exit_code(report=report) == 0


def test_prints_the_serving_version_read_for_every_consumer_and_capability_even_without_claims() -> (
    None
):
    report = _run_audit(claims=())
    lines = render_report(report=report)
    for repository in ("example/tooling", "example/other"):
        for capability in CAPABILITIES:
            assert f"serving\t{repository}\t{capability}\tv1.0.0" in lines
    assert not any(line.startswith("serving\texample/notes") for line in lines)
    assert exit_code(report=report) != 0
    assert "ready\t-" in lines


def test_a_capability_that_cannot_be_read_is_printed_as_unread() -> None:
    report = _run_audit(unreadable=frozenset({("example/tooling", "templates")}))
    assert "serving\texample/tooling\ttemplates\t-" in render_report(report=report)


def test_exits_non_zero_naming_the_surface_and_consumer_of_every_unclassified_row() -> None:
    report = _run_audit(claims=_cap_claims()[:-1])
    lines = render_report(report=report)
    assert "row\texample/notes\tOperator factory routing\tunclassified\t-" in lines
    assert any(
        line.startswith("finding\texample/notes: Operator factory routing:") for line in lines
    )
    assert exit_code(report=report) != 0
    assert "ready\texample/notes" not in lines


def test_an_unauthenticated_manifest_is_reported_with_its_cause_and_zero_ready() -> None:
    cases = {
        "read unavailable": (None,),
        "second read unavailable": (FLEET_MANIFEST, None),
        "second read names another member": (
            FLEET_MANIFEST,
            FLEET_MANIFEST.replace("other", "moved"),
        ),
        "second read differs only in bytes": (FLEET_MANIFEST, FLEET_MANIFEST + "\n"),
        "unparseable": ("{",),
    }
    for cause, texts in cases.items():
        report = _run_audit(texts=texts)
        lines = render_report(report=report)
        assert report.audit.rows == (), cause
        assert report.readings == (), cause
        assert report.audit.ready_repositories == (), cause
        findings = [line for line in lines if line.startswith("finding\t")]
        assert len(findings) == 1, cause
        assert "unauthenticated:" in findings[0], cause
        assert lines[-1] == "ready\t-", cause
        assert exit_code(report=report) != 0, cause


def test_the_unauthenticated_finding_names_a_failed_core_read() -> None:
    line = render_report(report=_run_audit(texts=(None,)))[1]
    assert (
        line
        == "finding\tmanifest membership or committed identity is unauthenticated: livespec core master read unavailable"
    )
    assert render_report(report=_run_audit(texts=(None,)))[0] == "manifest\t-"


def test_a_consumer_with_no_controller_evidence_is_left_out_and_named_with_what_it_lacks() -> None:
    report = _run_audit(unreadable=frozenset({("example/tooling", "independent-controller")}))
    lines = render_report(report=report)
    assert report.audit.ready_repositories == ("example/other",)
    assert "row\texample/tooling\tFirst-failure observer\tunclassified\t-" in lines
    assert (
        "finding\texample/tooling: lacks serving-version evidence for independent-controller"
        in lines
    )
    assert (
        "finding\texample/other: lacks serving-version evidence for independent-controller"
        not in lines
    )
    assert exit_code(report=report) != 0


def test_every_missing_capability_is_named_in_capability_order() -> None:
    gone = frozenset({("example/other", "templates"), ("example/other", "gate-readers")})
    lines = render_report(report=_run_audit(unreadable=gone))
    assert (
        "finding\texample/other: lacks serving-version evidence for gate-readers, templates"
        in lines
    )


def test_a_not_applicable_claim_cannot_stand_in_for_a_capability_that_was_not_read() -> None:
    unread = frozenset({("example/tooling", "independent-controller")})
    claims = tuple(
        replace(claim, disposition="not-applicable", reason="no such surface")
        if claim.repository == "example/tooling"
        and SURFACE_CAPABILITY.get(claim.surface) == "independent-controller"
        else claim
        for claim in _cap_claims()
    )
    report = _run_audit(claims=claims, unreadable=unread)
    assert report.audit.ready_repositories == ("example/other",)
    assert any(
        row.disposition == "unclassified" and row.repository == "example/tooling"
        for row in report.audit.rows
    )


def test_a_claim_is_confirmed_by_a_second_independent_read_before_it_counts() -> None:
    reads: dict[tuple[str, str], int] = {}

    def drifting(*, repository: str, capability: str) -> str | None:
        key = (repository, capability)
        reads[key] = reads.get(key, 0) + 1
        return "v1.0.0" if reads[key] == 1 else "v2.0.0"

    reads_manifest = iter((FLEET_MANIFEST, FLEET_MANIFEST))
    report = run_fleet_audit(
        read_manifest=lambda: next(reads_manifest, None),
        claims=_cap_claims(),
        read_serving=drifting,
    )
    assert report.audit.ready_repositories == ()
    assert all(
        row.disposition == "unclassified"
        for row in report.audit.rows
        if row.repository != "example/notes" or row.evidence is not None
    )


def test_each_capability_is_read_once_per_pass_not_once_per_surface() -> None:
    reads: dict[tuple[str, str], int] = {}

    def counting(*, repository: str, capability: str) -> str | None:
        reads[(repository, capability)] = reads.get((repository, capability), 0) + 1
        return "v1.0.0"

    reads_manifest = iter((FLEET_MANIFEST, FLEET_MANIFEST))
    _ = run_fleet_audit(
        read_manifest=lambda: next(reads_manifest, None),
        claims=_cap_claims(),
        read_serving=counting,
    )
    assert reads
    assert set(reads.values()) == {2}


def test_a_stale_manifest_identity_in_a_claim_is_unclassified() -> None:
    stale = tuple(replace(claim, manifest_sha256="c" * 64) for claim in _cap_claims())
    report = _run_audit(claims=stale)
    assert report.audit.rows
    assert report.audit.ready_repositories == ()
    assert all(row.disposition != "implemented" for row in report.audit.rows)


def test_an_unclassified_row_with_a_claim_still_prints_the_version_that_was_read() -> None:
    stale = tuple(replace(claim, release_build="v0.0.1") for claim in _cap_claims())
    lines = render_report(report=_run_audit(claims=stale))
    assert "row\texample/tooling\tPre-push\tunclassified\tv1.0.0" in lines


# --- the operator entry points ---
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    '{"owner": "example",'
    ' "fleet": [{"repo": "tooling", "class": "enforcement-suite"}],'
    ' "adopters": [{"repo": "notes", "profile": ["instruction-only"], "posture": "none"}]}'
)
DIGEST = hashlib.sha256(MANIFEST.encode()).hexdigest()
GUIDANCE = ("Agent tool and stop guards", "Operator factory routing")


def _claim(*, repository: str, surface: str) -> dict[str, str]:
    notes = repository.endswith("notes")
    return {
        "repository": repository,
        "surface": surface,
        "disposition": "implemented",
        "manifest_sha256": DIGEST,
        "source_path": "installed/component.py",
        "release_build": "1.0.0",
        "proof_ref": "independent-host-proof:receipt-1",
        "owner": "controller-owner",
        "incident_item": "" if notes else "incident-1",
        "cumulative_scope": "" if notes else "b" * 64,
        "normal_factory_proof": "" if notes else "factory:scope",
    }


def _write_claims(*, path: Path) -> None:
    claims = [_claim(repository="example/tooling", surface=s) for s in SURFACES] + [
        _claim(repository="example/notes", surface=s) for s in GUIDANCE
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps({"schema": 1, "evidence": claims}), encoding="utf-8")


def _cli_serving(*, unreadable: str = "") -> ServingReader:
    def read(*, repository: str, capability: str) -> str | None:
        _ = repository
        return None if capability == unreadable else "1.0.0"

    return read


def _environment(
    *, tmp_path: Path, manifest: str | None = MANIFEST, unreadable: str = "", claims: bool = True
) -> CliEnvironment:
    claims_path = tmp_path / "claims" / "incident-fleet-evidence.json"
    if claims:
        _write_claims(path=claims_path)
    texts = iter((manifest, manifest))
    return CliEnvironment(
        claims_path=claims_path,
        state_dir=tmp_path / "state",
        read_manifest=lambda: next(texts, None),
        read_serving=_cli_serving(unreadable=unreadable),
    )


def test_audit_prints_every_row_the_serving_versions_the_ready_list_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv=["audit"], environment=_environment(tmp_path=tmp_path)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len([line for line in lines if line.startswith("row\t")]) == len(SURFACES) * 2
    assert "row\texample/tooling\tPre-push\timplemented\t1.0.0" in lines
    assert "serving\texample/tooling\tindependent-controller\t1.0.0" in lines
    assert "ready\texample/tooling" in lines


def test_audit_exits_non_zero_and_names_the_consumer_lacking_controller_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = _environment(tmp_path=tmp_path, unreadable="independent-controller")
    assert main(argv=["audit"], environment=environment) != 0
    lines = capsys.readouterr().out.splitlines()
    assert "row\texample/tooling\tFirst-failure observer\tunclassified\t-" in lines
    assert "serving\texample/tooling\tindependent-controller\t-" in lines
    assert (
        "finding\texample/tooling: lacks serving-version evidence for independent-controller"
        in lines
    )
    assert "ready\t-" in lines


def test_audit_of_an_unauthenticated_manifest_reports_it_lists_zero_ready_and_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv=["audit"], environment=_environment(tmp_path=tmp_path, manifest=None)) != 0
    out = capsys.readouterr().out
    assert "unauthenticated: livespec core master read unavailable" in out
    assert "ready\t-" in out


def test_unreadable_claims_are_reported_and_fail_the_audit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = _environment(tmp_path=tmp_path, claims=False)
    _ = environment.claims_path.parent.mkdir(parents=True)
    _ = environment.claims_path.write_text("{", encoding="utf-8")
    assert main(argv=["audit"], environment=environment) != 0
    assert "finding\tevidence claims:" in capsys.readouterr().out


def test_enablement_enables_a_repository_on_the_fresh_ready_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = _environment(tmp_path=tmp_path)
    assert main(argv=["enable", "example/tooling"], environment=environment) == 0
    assert capsys.readouterr().out == "enabled\texample/tooling\n"
    record = json.loads((tmp_path / "state" / "example__tooling.json").read_text(encoding="utf-8"))
    assert record == {"repository": "example/tooling", "manifest_sha256": DIGEST}


def test_enablement_refuses_a_repository_missing_from_the_ready_list_and_enables_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = _environment(tmp_path=tmp_path, unreadable="independent-controller")
    assert main(argv=["enable", "example/tooling"], environment=environment) != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("refused\texample/tooling: missing evidence: ")
    assert "lacks serving-version evidence for independent-controller" in captured.err
    assert not (tmp_path / "state").exists()


def test_enablement_refuses_a_repository_no_finding_names_and_enables_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(argv=["enable", "example/foreign"], environment=_environment(tmp_path=tmp_path)) != 0
    )
    err = capsys.readouterr().err
    assert err.startswith("refused\texample/foreign: missing evidence: ")
    assert "no audited incident surface classifies it as a ready consumer" in err
    assert not (tmp_path / "state").exists()


def test_enablement_under_an_unauthenticated_manifest_prints_the_recorded_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = _environment(tmp_path=tmp_path, manifest=None)
    assert main(argv=["enable", "example/tooling"], environment=environment) != 0
    err = capsys.readouterr().err
    assert "missing evidence: manifest membership or committed identity is unauthenticated: " in err
    assert "livespec core master read unavailable" in err
    assert "no audited incident surface" not in err
    assert not (tmp_path / "state").exists()


def test_enable_repository_takes_the_report_it_is_given_only_by_its_ready_list() -> None:
    audit = FleetAudit(
        manifest_sha256="a" * 64, rows=(), findings=("x/y: gap",), ready_repositories=()
    )
    status, line = enable_repository(
        repository="x/y",
        report=FleetReport(audit=audit, readings=()),
        state_dir=Path("/nonexistent"),
    )
    assert status == 1
    assert line == "refused\tx/y: missing evidence: x/y: gap"


def test_the_command_has_no_owner_switch(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as refused:
        _ = main(argv=["--owner", "other", "audit"], environment=_environment(tmp_path=tmp_path))
    assert refused.value.code == 2


def test_the_production_environment_cannot_be_steered_by_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "LIVESPEC_FLEET_PROJECTS_ROOT",
        "LIVESPEC_INCIDENT_CONTROLLER_CONFIG_ROOT",
        "XDG_STATE_HOME",
        "HOME",
    ):
        monkeypatch.setenv(name, str(tmp_path / "redirected"))
    monkeypatch.chdir(tmp_path)
    _write_claims(path=tmp_path / "config" / "incident-fleet-evidence.json")
    asked: list[list[str]] = []

    def run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
        _ = cwd
        asked.append(args)
        return IOSuccess(CommandResult(returncode=1, stdout="", stderr="unavailable"))

    environment = production_environment(run=run)
    assert environment.claims_path == COMMITTED_CLAIMS
    assert environment.state_dir == (
        Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/livespec/incident-enabled"
    )
    assert environment.read_manifest() is None
    assert any("github.com/thewoolleyman/livespec.git" in part for a in asked for part in a)
    assert (
        environment.read_serving(
            repository="thewoolleyman/livespec", capability="no-such-capability"
        )
        is None
    )


def _recipe(*, name: str) -> list[str]:
    lines = (REPO_ROOT / "justfile").read_text(encoding="utf-8").splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith((f"{name}:", f"{name} "))]
    body = takewhile(lambda line: line.startswith("    "), lines[heads[0] + 1 :]) if heads else ()
    return [line.strip() for line in body]


def test_the_recipes_audit_without_syncing_the_environment_they_read() -> None:
    assert _recipe(name="incident-fleet-audit") == [
        "uv run --no-sync python -m livespec_dev_tooling.incident_fleet_cli audit"
    ]
    assert _recipe(name="incident-enable") == [
        'uv run --no-sync python -m livespec_dev_tooling.incident_fleet_cli enable "$1"'
    ]


_DRIVER = """
import json, sys
from pathlib import Path
from livespec_dev_tooling.incident_fleet_cli import CliEnvironment, main
config = json.loads(sys.argv[1])
unreadable = config["unreadable"]
environment = CliEnvironment(
    claims_path=Path(config["claims"]),
    state_dir=Path(config["state"]),
    read_manifest=lambda: config["manifest"],
    read_serving=lambda *, repository, capability: None if capability == unreadable else "1.0.0",
)
raise SystemExit(main(argv=config["argv"], environment=environment))
"""


def _child(
    *, tmp_path: Path, argv: list[str], manifest: str | None = MANIFEST, unreadable: str = ""
) -> subprocess.CompletedProcess[str]:
    claims = tmp_path / "claims" / "incident-fleet-evidence.json"
    if not claims.exists():
        _write_claims(path=claims)
    config = {
        "argv": argv,
        "manifest": manifest,
        "unreadable": unreadable,
        "claims": str(claims),
        "state": str(tmp_path / "state"),
    }
    scrubbed = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("COV_CORE_", "COVERAGE_"))
    }
    return subprocess.run(
        [sys.executable, "-I", "-c", _DRIVER, json.dumps(config)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=scrubbed,
    )


@pytest.mark.integration
def test_run_as_a_child_process_a_consumer_without_controller_evidence_is_left_out_named_and_refused(
    tmp_path: Path,
) -> None:
    audit = _child(tmp_path=tmp_path, argv=["audit"], unreadable="independent-controller")
    lines = audit.stdout.splitlines()
    assert audit.returncode != 0
    assert "row\texample/tooling\tFirst-failure observer\tunclassified\t-" in lines
    assert "row\texample/tooling\tPre-push\timplemented\t1.0.0" in lines
    assert (
        "finding\texample/tooling: lacks serving-version evidence for independent-controller"
        in lines
    )
    assert "ready\t-" in lines
    enable = _child(
        tmp_path=tmp_path, argv=["enable", "example/tooling"], unreadable="independent-controller"
    )
    assert enable.returncode != 0
    assert "example/tooling" in enable.stderr
    assert "independent-controller" in enable.stderr
    assert not (tmp_path / "state").exists()


@pytest.mark.integration
def test_run_as_a_child_process_an_unauthenticated_manifest_reports_it_and_lists_zero_ready(
    tmp_path: Path,
) -> None:
    audit = _child(tmp_path=tmp_path, argv=["audit"], manifest=None)
    assert audit.returncode != 0
    assert "unauthenticated: livespec core master read unavailable" in audit.stdout
    assert audit.stdout.splitlines()[-1] == "ready\t-"
    enable = _child(tmp_path=tmp_path, argv=["enable", "example/tooling"], manifest=None)
    assert enable.returncode != 0
    assert "unauthenticated: livespec core master read unavailable" in enable.stderr
    assert not (tmp_path / "state").exists()


@pytest.mark.integration
def test_run_as_a_child_process_a_ready_consumer_is_enabled_from_the_fresh_audit(
    tmp_path: Path,
) -> None:
    done = _child(tmp_path=tmp_path, argv=["enable", "example/tooling"])
    assert (done.returncode, done.stdout) == (0, "enabled\texample/tooling\n")
    assert (tmp_path / "state" / "example__tooling.json").is_file()


def test_enabling_an_already_enabled_repository_again_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environment = _environment(tmp_path=tmp_path)
    assert main(argv=["enable", "example/tooling"], environment=environment) == 0
    environment = _environment(tmp_path=tmp_path)
    assert main(argv=["enable", "example/tooling"], environment=environment) == 0
    assert capsys.readouterr().out == "enabled\texample/tooling\n" * 2


def test_a_missing_subcommand_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as refused:
        _ = main(argv=[], environment=_environment(tmp_path=tmp_path))
    assert refused.value.code == 2


def test_one_install_record_with_its_cache_present_is_enough_for_a_plugin(tmp_path: Path) -> None:
    clone = tmp_path / "clones" / "tooling"
    (clone / ".claude").mkdir(parents=True)
    (tmp_path / "home" / ".claude" / "plugins").mkdir(parents=True)
    cache = tmp_path / "cache"
    cache.mkdir()
    records = [
        {
            "projectPath": str(clone),
            "gitCommitSha": "9" * 40,
            "installPath": str(tmp_path / "gone"),
        },
        {"projectPath": str(clone), "gitCommitSha": "9" * 40, "installPath": str(cache)},
    ]
    _ = (clone / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "enabledPlugins": {"alpha@alpha": True},
                "extraKnownMarketplaces": {
                    "alpha": {
                        "source": {"source": "github", "repo": "acme/alpha", "ref": "release"}
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    _ = (tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"alpha@alpha": records}}), encoding="utf-8"
    )
    probe = HostProbe(
        clones_root=tmp_path / "clones",
        proc_root=Path("/proc"),
        home=tmp_path / "home",
        run=Mock(),
    )
    assert read_driver_hooks(probe=probe, repository="example/tooling") == f"alpha@alpha={'9' * 40}"


def test_a_ruleset_guarding_the_default_branch_among_other_refs_still_counts() -> None:
    ruleset = {
        "id": 7,
        "enforcement": "active",
        "target": "branch",
        "conditions": {"ref_name": {"include": ["refs/heads/feature", "~DEFAULT_BRANCH"]}},
        "bypass_actors": [{"actor_id": 5, "actor_type": "Integration", "bypass_mode": "always"}],
    }
    answers = {
        "repos/example/tooling/rulesets": [ruleset],
        "repos/example/tooling/rulesets/7": ruleset,
    }

    def read_forge(*, args: list[str]) -> GhRead:
        return GhRead(returncode=0, stdout=json.dumps(answers[args[1]]), stderr="")

    served = read_recovery_authorization(
        repository="example/tooling", controller="v1@" + "c" * 40, read_forge=read_forge
    )
    assert served == "v1@" + "c" * 40 + "+bypass-app-5"


def test_enablement_creates_the_whole_state_directory_path(tmp_path: Path) -> None:
    deep = replace(_environment(tmp_path=tmp_path), state_dir=tmp_path / "a" / "b" / "state")
    assert main(argv=["enable", "example/tooling"], environment=deep) == 0
    assert (tmp_path / "a" / "b" / "state" / "example__tooling.json").is_file()
