"""Packaged inventory derives from the workflow's target set, not its bytes."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_ci_inventory as module

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github/workflows/ci.yml"
_PACKAGED = _ROOT / "livespec_dev_tooling/data/incident-ci-inventory.json"
_HOSTED_RUNS_ON = (
    "    runs-on: ${{ fromJSON(github.event_name == 'push' && vars.CI_RUNNER_LABELS_MASTER"
    " || vars.CI_RUNNER_LABELS || '[\"ubuntu-latest\"]') }}\n"
)


def data():
    return dict(
        schema=1,
        targets=[
            dict(
                name="check-fast",
                classification="fast",
                batch="checks",
                needs=[],
                produces=[],
                consumes=[],
            )
        ],
    )


def _workflow(*, jobs: dict[str, list[str]]) -> str:
    text = "on: push\njobs:\n"
    for job, targets in jobs.items():
        bullets = "\n".join(f"          - {t}" for t in targets)
        text += (
            f"  {job}:\n"
            "    runs-on: ubuntu-latest\n"
            "    strategy:\n"
            "      matrix:\n"
            "        target:\n"
            f"{bullets}\n"
            "    steps:\n"
            "      - run: just ${{ matrix.target }}\n"
        )
    return text


def test_packaged_inventory_equals_the_target_set_derived_from_the_live_workflow():
    # A target added, removed or renamed in ci.yml shows up here as a named
    # difference, and regenerating only the packaged data file resolves it.
    derived = module.decode_inventory(text=module.render_inventory(workflow=_WORKFLOW.read_text()))
    packaged = module.load_inventory()
    assert {t.name for t in derived} ^ {t.name for t in packaged} == set()
    assert set(derived) == set(packaged)
    assert {t.name for t in packaged if t.classification == "fast"} == {
        "check-lint",
        "check-format",
    }
    coverage = next(t for t in packaged if t.name == "check-coverage")
    assert coverage.needs == ("check-per-file-coverage",)
    assert coverage.consumes == ("coverage-data",)


def test_workflow_edit_that_keeps_the_target_set_renders_the_packaged_bytes():
    workflow = _WORKFLOW.read_text()
    assert _HOSTED_RUNS_ON in workflow
    edited = workflow.replace(
        _HOSTED_RUNS_ON, "    runs-on: ubuntu-latest\n    timeout-minutes: 9\n"
    )
    assert edited != workflow
    assert module.render_inventory(workflow=edited) == _PACKAGED.read_text()
    assert module.render_inventory(workflow=edited) == module.render_inventory(workflow=workflow)


def test_rendered_inventory_follows_only_the_contributed_target_set():
    base = _workflow(jobs={"python": ["check-lint", "check-types"], "meta": ["check-shell"]})
    rendered = module.decode_inventory(text=module.render_inventory(workflow=base))
    assert {(t.name, t.batch, t.classification) for t in rendered} == {
        ("check-lint", "python", "fast"),
        ("check-types", "python", "unclassified"),
        ("check-shell", "meta", "unclassified"),
    }
    assert module.render_inventory(workflow=base.replace("on: push", "on: [push]")) == (
        module.render_inventory(workflow=base)
    )
    renamed = _workflow(jobs={"python": ["check-lint", "check-typing"], "meta": ["check-shell"]})
    assert {
        t.name for t in module.decode_inventory(text=module.render_inventory(workflow=renamed))
    } == {
        "check-lint",
        "check-typing",
        "check-shell",
    }


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        data() | {"schema": True},
        data() | {"schema": 2},
        data() | {"workflow_sha256": "a" * 64},
        data() | {"targets": {}},
        data() | {"targets": []},
    ],
)
def test_incomplete_manifest_refuses(value):
    with pytest.raises(ValueError, match="invalid released"):
        module.decode_inventory(text=json.dumps(value))


@pytest.mark.parametrize(
    "change",
    [
        {"extra": "x"},
        {"name": 1},
        {"name": "--help"},
        {"name": "check-BAD"},
        {"batch": "?"},
        {"classification": "invented"},
        {"needs": {}},
        {"needs": [1]},
        {"needs": ["bad value"]},
        {"produces": ["same", "same"]},
    ],
)
def test_malformed_released_member_refuses(change):
    value = data()
    value["targets"][0].update(change)
    with pytest.raises(ValueError, match="invalid released incident CI target"):
        module.decode_inventory(text=json.dumps(value))


def test_non_mapping_member_duplicate_and_missing_dependencies_refuse():
    for rows in (
        [None],
        data()["targets"] * 2,
        [data()["targets"][0] | {"needs": ["check-missing"]}],
        [data()["targets"][0] | {"needs": ["check-fast"]}],
    ):
        with pytest.raises(ValueError, match="invalid released|duplicate or missing"):
            module.decode_inventory(text=json.dumps(data() | {"targets": rows}))


def test_load_inventory_reads_only_packaged_bytes_through_strict_validation(monkeypatch, tmp_path):
    assert not inspect.signature(module.load_inventory).parameters
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data() | {"targets": []}))
    monkeypatch.setattr(module, "_PATH", path)
    with pytest.raises(ValueError, match="invalid released"):
        module.load_inventory()
    path.write_text(json.dumps(data()))
    assert [t.name for t in module.load_inventory()] == ["check-fast"]
