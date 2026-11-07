"""A canonical refusal reaches the operator by its own code, apart from a transport failure.

During a live correction the operator has to tell `incident-correction-failures-
missing` (the item has no retained Finding yet) from an unreachable authority.
The registered `incident_authority.py` answers a refusal with exit 78 and a
schema-1 reply whose `result` carries `code` and `detail`; the entrance passes
both through, for the attempt-history read, the collector's authorize step and
`correct-attempt`.
"""

import json
import subprocess
from typing import Any
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_original_run_entry as entry
from livespec_dev_tooling._incident_original_run_canonical import CanonicalPorts
from livespec_dev_tooling._incident_run_types import EvidenceRefusal, RunEvidence
from livespec_dev_tooling.incident_original_run_flows import (
    Collection,
    Correction,
    EntryPorts,
    collect,
    propose,
)
from livespec_dev_tooling.incident_run_evidence import evidence_digest
from tests.livespec_dev_tooling import test_incident_original_run_entry as entry_tests
from tests.livespec_dev_tooling import test_incident_original_run_flows as flows
from tests.livespec_dev_tooling.test_incident_original_run_flows import REPOSITORY, World

world = flows.world
installation = entry_tests.installation
# The patch below replaces the shared `subprocess.run`; the fixture's real Git keeps it.
REAL_RUN = subprocess.run


def reply(status: str, result: object) -> dict[str, object]:
    return {
        "schema": 1,
        "status": status,
        "result": result,
        "authorizes_current_effects": False,
        "normal_factory_proof": False,
    }


def refused(code: str) -> tuple[int, dict[str, object]]:
    return 78, reply("refused", {"code": code, "detail": "incident-1"})


class Authority:
    """The registered process as the forge-free fake: scripted replies per action."""

    def __init__(self, world: World) -> None:
        self.verified = (0, reply("verified", flows.attempt(world)))
        self.script: dict[str, list[tuple[int, object]]] = {}

    def spawn(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if argv[0] == "git":
            return REAL_RUN(argv, **kwargs)
        code, body = self.script[argv[2]].pop(0)
        stdout = body if isinstance(body, bytes) else json.dumps(body).encode()
        return subprocess.CompletedProcess(args=argv, returncode=code, stdout=stdout)


@pytest.fixture
def authority(world: World, monkeypatch: pytest.MonkeyPatch) -> Authority:
    fake = Authority(world)
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=fake.spawn))
    (world.state.parent / "reader.env").write_text("BEADS_DOLT_PASSWORD=tenant\n")
    return fake


def ports(world: World) -> EntryPorts:
    settings = entry.ControllerInstallation.load(config=world.state.parent / "controller.json")
    assert settings is not None
    registered = entry.installed_ports(installation=settings).canonical.authority
    local = world.ports()
    return EntryPorts(
        canonical=CanonicalPorts(authority=registered, ledger=world.ledger),
        git=local.git,
        read=local.read,
    )


def gather(world: World) -> RunEvidence | EvidenceRefusal:
    return collect(
        request=Collection(
            state_dir=world.state,
            repository=REPOSITORY,
            revert_sha=world.shas["revert"],
            expected=flows.GRAPH,
        ),
        ports=ports(world),
    )


def correct(world: World, digest: str) -> str | EvidenceRefusal:
    request = Correction(
        state_dir=world.state,
        repository=REPOSITORY,
        evidence_digest=digest,
        next_head_sha=world.shas["repair"],
        target_ref="refs/heads/incident-1-attempt-2",
        current_attempt="recovery-1",
        current_owner="incident-principal",
        current_generation=4,
        base_ref="master",
    )
    return propose(request=request, ports=ports(world))


def test_canonical_refusals_pass_through_by_code(
    world: World, authority: Authority, capsys: pytest.CaptureFixture[str]
) -> None:
    authority.script["read-history"] = [refused("incident-authority-history-unreadable")]
    history = gather(world)
    stale = refused("incident-authority-stale-generation")
    authority.script["read-history"] = [authority.verified, stale]
    authorize = gather(world)
    authority.script["read-history"] = [authority.verified, authority.verified]
    collected = gather(world)
    digest = evidence_digest(evidence=collected) if isinstance(collected, RunEvidence) else ""
    authority.script["correct-attempt"] = [
        refused("incident-correction-failures-missing"),
        (1, b"authority crashed"),
        refused("incident-correction-not-eligible"),
    ]
    missing = correct(world, digest)
    transport = correct(world, digest)
    argv = ["propose-correction", *entry_tests.common(world)]
    argv += ["--evidence-digest", digest, "--base-ref", "master"]
    argv += ["--next-head-sha", world.shas["repair"], "--target-ref", "refs/heads/r"]
    argv += ["--current-attempt", "recovery-1", "--current-owner", "p", "--current-generation", "4"]
    code = entry.main(argv=argv, ports=ports(world))
    printed: Any = json.loads(capsys.readouterr().out)
    facts = [
        (getattr(history, "code", None), getattr(history, "detail", None))
        == ("incident-authority-history-unreadable", "incident-1"),
        getattr(authorize, "code", None) == "incident-authority-stale-generation",
        isinstance(collected, RunEvidence),
        (getattr(missing, "code", None), getattr(missing, "detail", None))
        == ("incident-correction-failures-missing", "incident-1"),
        getattr(transport, "code", None) == "incident-original-run-refused",
        (code, printed["code"]) == (78, "incident-correction-not-eligible"),
    ]
    assert all(facts), facts
