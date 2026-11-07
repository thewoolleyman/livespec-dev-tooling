"""A corrected attempt is measured from its staged tree, before its commit can exist.

The expedited hook admits a commit only once the chain is back in `repair`, and
the chain gets there only through this correction. So a real repair stages its
tree, names the base as the next head, and commits under the hook afterwards,
exactly as a genesis attempt does.
"""

import json

import pytest

from livespec_dev_tooling import incident_original_run_entry as entry
from livespec_dev_tooling._incident_run_types import RunEvidence
from livespec_dev_tooling.incident_original_run_flows import EvidenceRefusal
from livespec_dev_tooling.incident_run_evidence import evidence_digest
from tests.livespec_dev_tooling import test_incident_original_run_entry as entry_tests
from tests.livespec_dev_tooling import test_incident_original_run_flows as flows
from tests.livespec_dev_tooling.test_incident_original_run_flows import World, git

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-se537s
world = flows.world
installation = entry_tests.installation


def _digest(world: World) -> str:
    collected = flows.gather(world)
    assert isinstance(collected, RunEvidence)
    return evidence_digest(evidence=collected)


def _tree(world: World, name: str) -> str:
    return git(world.repo, "rev-parse", world.shas[name] + "^{tree}").decode().strip()


def test_a_staged_repair_is_recorded_with_its_tree_and_the_base_as_head(world: World) -> None:
    tree = _tree(world, "repair")
    result = flows.correction(world, _digest(world), "later", staged_tree=tree)
    action, _query, payload = world.authority.call_args.args
    correct = json.loads(payload["correction-json"])
    facts = [
        result == "correction-2",
        action == "correct-attempt",
        correct["kind"] == "repair",
        correct["head"] == world.shas["later"],
        correct["base"] == world.shas["later"],
        correct["staged_tree"] == tree,
    ]
    assert all(facts)


def test_a_staged_tree_equal_to_the_reverted_change_is_an_unchanged_reland(world: World) -> None:
    tree = _tree(world, "reland")
    result = flows.correction(world, _digest(world), "later", staged_tree=tree)
    actions = [call.args[0] for call in world.authority.call_args_list]
    facts = [
        isinstance(result, EvidenceRefusal),
        getattr(result, "code", "") == "incident-original-run-invalid",
        "correct-attempt" not in actions,
    ]
    assert all(facts)


def test_a_staged_tree_needs_the_base_as_its_next_head(world: World) -> None:
    result = flows.correction(world, _digest(world), "repair", staged_tree=_tree(world, "repair"))
    facts = [
        isinstance(result, EvidenceRefusal),
        getattr(result, "code", "") == "incident-original-run-local-revision",
    ]
    assert all(facts)


def test_the_entrance_passes_the_staged_tree_through(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = _tree(world, "repair")
    digest = _digest(world)
    argv = ["propose-correction", *entry_tests.common(world)]
    argv += ["--evidence-digest", digest, "--base-ref", "master"]
    argv += ["--next-head-sha", world.shas["later"], "--target-ref", "refs/heads/r"]
    argv += ["--current-attempt", "recovery-1", "--current-owner", "incident-principal"]
    argv += ["--current-generation", "3", "--staged-tree", tree]
    code = entry.main(argv=argv, ports=world.ports())
    reply = json.loads(capsys.readouterr().out)
    correct = json.loads(world.authority.call_args.args[2]["correction-json"])
    assert all([code == 0, reply["status"] == "proposed", correct["staged_tree"] == tree])
