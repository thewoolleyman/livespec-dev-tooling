"""A correction names the CURRENT attempt that reopen-regression created, not the original.

`reopen-regression` (livespec-orchestrator-beads-fabro#4579) records a new
`recovery-<digest>` attempt owned by the incident principal, and the revert
receipt moves THAT attempt to `collecting-failures`. `correct-attempt` refuses
any other identity, so the entrance must send the current attempt and owner.
"""

import json

import pytest

from livespec_dev_tooling import incident_original_run_entry as entry
from livespec_dev_tooling._incident_run_types import RunEvidence
from livespec_dev_tooling.incident_original_run_flows import Correction, propose
from livespec_dev_tooling.incident_run_evidence import evidence_digest
from tests.livespec_dev_tooling import test_incident_original_run_flows as flows
from tests.livespec_dev_tooling.test_incident_original_run_flows import REPOSITORY, World

world = flows.world


def test_correction_names_the_reopened_attempt_and_its_principal(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    collected = flows.gather(world)
    assert isinstance(collected, RunEvidence)
    digest = evidence_digest(evidence=collected)
    request = Correction(
        state_dir=world.state,
        repository=REPOSITORY,
        evidence_digest=digest,
        next_head_sha=world.shas["repair"],
        target_ref="refs/heads/incident-1-attempt-2",
        current_attempt="recovery-abc",
        current_owner="incident-principal",
        current_generation=4,
        base_ref="master",
    )
    receipt = propose(request=request, ports=world.ports())
    library_query = world.authority.call_args.args[1]
    argv = ["propose-correction", "--state-dir", str(world.state), "--repository", REPOSITORY]
    argv += ["--repo", str(world.repo), "--evidence-digest", digest, "--base-ref", "master"]
    argv += ["--next-head-sha", world.shas["repair"], "--target-ref", "refs/heads/r"]
    argv += ["--current-attempt", "recovery-def", "--current-owner", "principal-2"]
    argv += ["--current-generation", "5"]
    code = entry.main(argv=argv, ports=world.ports())
    reply = json.loads(capsys.readouterr().out)
    entrance_query = world.authority.call_args.args[1]
    expected = {
        "repository": REPOSITORY,
        "item": "incident-1",
        "attempt": "recovery-abc",
        "phase": "collecting-failures",
        "operation": "recovery-abc#collecting-failures",
        "generation": 4,
        "owner": "incident-principal",
    }
    facts = [
        receipt == "correction-2",
        library_query == expected,
        (code, reply["status"]) == (0, "proposed"),
        entrance_query["attempt"] == "recovery-def",
        entrance_query["operation"] == "recovery-def#collecting-failures",
        (entrance_query["owner"], entrance_query["generation"]) == ("principal-2", 5),
    ]
    assert all(facts)
