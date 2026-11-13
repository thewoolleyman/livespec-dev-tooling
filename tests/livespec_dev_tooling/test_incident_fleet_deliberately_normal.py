"""A deliberately-normal row classifies from the ruling it cites, not from a serving read.

Under the maintainer's 2026-11-12 ruling, four consumers adopt expedited incident mode and
the other eighteen keep normal behaviour. No independent controller installation will
ever serve those eighteen, so a deliberately-normal claim's evidence is the decision it
cites: the audit classifies its row without a release build or a serving read. The one
read that contradicts it is a serving read of the consumer's own incident installation
(independent-controller or recovery-authorization). Shared gate-reader, template and
driver-hooks builds serve every consumer that pins this library, so a read of one is
printed and is no contradiction. A consumer with a deliberately-normal row is never
ready, and one whose rows are all deliberately-normal or not-applicable is not named for
lacking serving-version evidence (livespec-dev-tooling-kddu2b).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling._incident_fleet_command import FleetReport, run_fleet_audit
from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence
from livespec_dev_tooling.incident_fleet_audit import SURFACES

_MANIFEST = (
    '{"owner": "example",'
    ' "fleet": [{"repo": "tooling", "class": "enforcement-suite"}],'
    ' "adopters": [{"repo": "notes", "profile": ["instruction-only"], "posture": "none"}]}'
)
_DIGEST = hashlib.sha256(_MANIFEST.encode()).hexdigest()
_RULING = "maintainer ruling 2026-11-12, recorded on epic example-epic: this consumer stays normal"
_NORMAL = CapabilityEvidence(
    repository="example/tooling",
    surface="Pre-push",
    disposition="deliberately-normal",
    manifest_sha256=_DIGEST,
    source_path="example/tooling: normal hooks",
    release_build="",
    serving_build="",
    proof_ref="example/tooling: ruling on example-epic",
    owner="example/tooling",
    incident_item="",
    cumulative_scope="",
    normal_factory_proof="",
    reason=_RULING,
)
_GUIDANCE = ("Agent tool and stop guards", "Operator factory routing")
_OWN_INSTALLATION = {"independent-controller", "recovery-authorization"}


def _member_claims() -> tuple[CapabilityEvidence, ...]:
    return tuple(replace(_NORMAL, surface=surface) for surface in SURFACES)


def _notes_claims() -> tuple[CapabilityEvidence, ...]:
    return tuple(
        replace(
            _NORMAL,
            repository="example/notes",
            surface=surface,
            source_path="example/notes: guidance",
            proof_ref="example/notes: ruling on example-epic",
            owner="example/notes",
        )
        for surface in _GUIDANCE
    )


def _audit(*, claims: tuple[CapabilityEvidence, ...], served: set[str]) -> FleetReport:
    def read(*, repository: str, capability: str) -> str | None:
        del repository
        return "v9.9.9" if capability in served else None

    return run_fleet_audit(read_manifest=lambda: _MANIFEST, claims=claims, read_serving=read)


def _dispositions(*, report: FleetReport, repository: str) -> dict[str, str]:
    return {
        row.surface: row.disposition for row in report.audit.rows if row.repository == repository
    }


def test_with_no_serving_read_every_ruled_row_reads_deliberately_normal() -> None:
    report = _audit(claims=(*_member_claims(), *_notes_claims()), served=set())
    member = _dispositions(report=report, repository="example/tooling")
    assert set(member.values()) == {"deliberately-normal"}
    notes = _dispositions(report=report, repository="example/notes")
    assert {notes[surface] for surface in _GUIDANCE} == {"deliberately-normal"}
    assert sum(value == "not-applicable" for value in notes.values()) == len(SURFACES) - 2
    assert report.audit.ready_repositories == ()
    assert not any("lacks serving-version evidence" in f for f in report.audit.findings)


def test_a_shared_build_read_is_printed_and_contradicts_nothing() -> None:
    shared = {"gate-readers", "templates", "driver-hooks"}
    report = _audit(claims=_member_claims(), served=shared)
    member = _dispositions(report=report, repository="example/tooling")
    assert set(member.values()) == {"deliberately-normal"}
    printed = {(r, c, b) for r, c, b, _detail, _head in report.readings}
    assert {("example/tooling", c, "v9.9.9") for c in shared} <= printed


def test_a_read_of_the_consumers_own_installation_contradicts_the_ruling() -> None:
    report = _audit(claims=_member_claims(), served=_OWN_INSTALLATION)
    member = _dispositions(report=report, repository="example/tooling")
    own = {s for s in SURFACES if SURFACE_CAPABILITY.get(s) in _OWN_INSTALLATION}
    assert len(own) == 8
    assert {member[s] for s in own} == {"unclassified"}
    assert {member[s] for s in SURFACES if s not in own} == {"deliberately-normal"}
    reasons = {
        row.reason
        for row in report.audit.rows
        if row.repository == "example/tooling" and row.surface in own
    }
    assert all("contradicts" in reason and "v9.9.9" in reason for reason in reasons)


def test_a_ruled_claim_with_no_reason_stays_unclassified() -> None:
    claims = (replace(_member_claims()[0], reason=""), *_member_claims()[1:])
    report = _audit(claims=claims, served=set())
    first = _dispositions(report=report, repository="example/tooling")[SURFACES[0]]
    assert first == "unclassified"


def test_an_implemented_claim_keeps_its_serving_check_and_its_finding() -> None:
    controller = next(s for s in SURFACES if SURFACE_CAPABILITY.get(s) == "independent-controller")
    implemented = replace(
        _NORMAL,
        surface=controller,
        disposition="implemented",
        release_build="v1.0.0",
        reason="",
        incident_item="incident-1",
        cumulative_scope="b" * 64,
        normal_factory_proof="factory:scope",
    )
    others = tuple(c for c in _member_claims() if c.surface != controller)
    report = _audit(claims=(implemented, *others), served=set())
    row = _dispositions(report=report, repository="example/tooling")[controller]
    assert row == "unclassified"
    assert any(
        f.startswith("example/tooling: lacks serving-version evidence")
        and "independent-controller" in f
        for f in report.audit.findings
    )


# --- the scenario as an operator runs it: `just incident-fleet-audit` in a child process ---

_DRIVER = """
import json, sys
from pathlib import Path
from livespec_dev_tooling.incident_fleet_cli import CliEnvironment, main
config = json.loads(sys.argv[1])
served = set(config["served"])
environment = CliEnvironment(
    claims_path=Path(config["claims"]),
    state_dir=Path(config["state"]),
    read_manifest=lambda: config["manifest"],
    read_serving=lambda *, repository, capability: "v9.9.9" if capability in served else None,
)
raise SystemExit(main(argv=["audit"], environment=environment))
"""


def _child_audit(*, tmp_path: Path, served: set[str]) -> subprocess.CompletedProcess[str]:
    claims = tmp_path / "claims.json"
    evidence = [
        {k: v for k, v in asdict(c).items() if k != "serving_build"}
        for c in (*_member_claims(), *_notes_claims())
    ]
    _ = claims.write_text(json.dumps({"schema": 1, "evidence": evidence}), encoding="utf-8")
    config = {
        "manifest": _MANIFEST,
        "served": sorted(served),
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
def test_run_as_a_child_process_a_ruled_normal_member_and_adopter_classify_with_no_installation(
    tmp_path: Path,
) -> None:
    audit = _child_audit(tmp_path=tmp_path, served=set())
    lines = audit.stdout.splitlines()
    member = [line for line in lines if line.startswith("row\texample/tooling\t")]
    notes = [line for line in lines if line.startswith("row\texample/notes\t")]
    assert len(member) == len(SURFACES)
    assert all(line.split("\t")[3] == "deliberately-normal" for line in member)
    assert {line.split("\t")[3] for line in notes} == {"deliberately-normal", "not-applicable"}
    assert not any("lacks serving-version evidence" in line for line in lines)
    assert not any(line.startswith("ready\texample/") for line in lines)
    assert audit.returncode == 0


@pytest.mark.integration
def test_run_as_a_child_process_a_read_of_the_members_own_controller_contradicts_the_ruling(
    tmp_path: Path,
) -> None:
    audit = _child_audit(tmp_path=tmp_path, served={"independent-controller"})
    lines = audit.stdout.splitlines()
    controller = [s for s in SURFACES if SURFACE_CAPABILITY.get(s) == "independent-controller"]
    for surface in controller:
        assert f"row\texample/tooling\t{surface}\tunclassified\tv9.9.9" in lines
        assert any(
            "example/tooling" in line and surface in line and "contradicts" in line
            for line in lines
            if not line.startswith("row\t")
        )
    assert audit.returncode != 0
