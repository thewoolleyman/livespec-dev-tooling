"""Every released adopter inventory equals a fresh render of the source it records.

`just render-incident-ci-inventory` writes an adopter's entry under
`livespec_dev_tooling/data/incident-ci-inventory/<owner>/<repo>.json` and keeps
the exact source bytes it rendered from (the adopter's `ci.yml` and
`check-targets.txt` at the recorded default-branch commit) under
`tests/fixtures/incident_ci_inventory_sources/<owner>/<repo>/`, together with
each file's git blob id at that commit. These tests prove, offline, that the
fixture bytes are the blobs the entry's source commit names and that the entry
is byte-identical to a fresh render of them (livespec-dev-tooling-k5nzpk).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_ci_inventory as module
from livespec_dev_tooling._incident_ci_plan import NOT_RUN, execution_view

_ROOT = Path(__file__).resolve().parents[2]
_ENTRIES = _ROOT / "livespec_dev_tooling/data/incident-ci-inventory"
_SOURCES = _ROOT / "tests/fixtures/incident_ci_inventory_sources"
_ADOPTERS = (
    "thewoolleyman/livespec",
    "thewoolleyman/livespec-orchestrator-beads-fabro",
    "thewoolleyman/livespec-overseer",
)


def _blob_id(*, data: bytes) -> str:
    """The git blob id of `data`, computed the way `git hash-object` does."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def _entries() -> list[str]:
    return sorted(str(p.relative_to(_ENTRIES).with_suffix("")) for p in _ENTRIES.glob("*/*.json"))


def test_every_adopter_named_by_the_plan_has_a_released_entry():
    assert _entries() == sorted(_ADOPTERS)


@pytest.mark.parametrize("repository", _entries())
def test_a_released_entry_equals_a_fresh_render_of_its_recorded_source(repository):
    entry = (_ENTRIES / f"{repository}.json").read_text()
    source = json.loads(entry)["source"]
    fixture = _SOURCES / repository
    recorded = json.loads((fixture / "source.json").read_text())
    workflow = (fixture / "ci.yml").read_bytes()
    inventory = (fixture / "check-targets.txt").read_bytes()
    assert source == {"repository": repository, "commit": recorded["commit"]}
    assert recorded["repository"] == repository
    assert _blob_id(data=workflow) == recorded["workflow_blob"]
    assert _blob_id(data=inventory) == recorded["check_targets_blob"]
    # The render script reads each input through a shell command substitution,
    # which drops trailing newlines; the fresh render applies the same reading.
    fresh = module.render_inventory(
        workflow=workflow.decode().rstrip("\n"),
        inventory=inventory.decode().rstrip("\n"),
        source=module.InventorySource(repository=repository, commit=recorded["commit"]),
    )
    assert fresh == entry


@pytest.mark.parametrize("repository", _entries())
def test_a_released_entry_loads_and_has_a_runnable_execution_view(repository):
    targets = module.load_repository_inventory(repository=repository)
    view = execution_view(targets=targets)
    assert view is not None
    executed, _conditional, attribution = view
    assert executed
    assert {name for name, _jobs in attribution} == {t.name for t in targets}


def test_the_orchestrator_factory_provenance_job_reads_as_not_run_on_this_event():
    targets = module.load_repository_inventory(
        repository="thewoolleyman/livespec-orchestrator-beads-fabro"
    )
    view = execution_view(targets=targets)
    assert view is not None
    executed, conditional, _attribution = view
    lines = {line.job: (line.names, line.reason) for line in conditional}
    assert lines["check-factory-provenance"] == (("check-factory-provenance",), NOT_RUN)
    assert "check-factory-provenance" not in {t.name for t in executed}


def test_livespec_release_gate_members_read_as_not_run_on_this_event():
    targets = module.load_repository_inventory(repository="thewoolleyman/livespec")
    view = execution_view(targets=targets)
    assert view is not None
    _executed, conditional, attribution = view
    lines = {line.job: (set(line.names), line.reason) for line in conditional}
    assert lines["release-gate-pre-tag"] == (
        {"check-mutation", "check-no-lloc-soft-warnings", "check-no-todo-registry"},
        NOT_RUN,
    )
    declared = dict(attribution)
    assert "release-gate-pre-tag" in declared["check-no-todo-registry"]
    assert len(declared["check-no-todo-registry"]) == 2
