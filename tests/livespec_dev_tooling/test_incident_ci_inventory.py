"""Packaged inventory binds the complete existing workflow to reviewed bytes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling import incident_ci_inventory as module


def data():
    return dict(
        schema=1,
        workflow_sha256="a" * 64,
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


def test_actual_packaged_inventory_matches_complete_workflow_and_coverage_graph():
    root = Path(__file__).resolve().parents[2]
    text = module.render_inventory(workflow=(root / ".github/workflows/ci.yml").read_text())
    assert text == (root / "livespec_dev_tooling/data/incident-ci-inventory.json").read_text()
    targets = module.load_inventory()
    assert len(targets) == 71
    assert {t.name for t in targets if t.classification == "fast"} == {"check-lint", "check-format"}
    coverage = next(t for t in targets if t.name == "check-coverage")
    assert coverage.needs == ("check-per-file-coverage",)
    assert coverage.consumes == ("coverage-data",)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        data() | {"schema": True},
        data() | {"schema": 2},
        data() | {"workflow_sha256": 1},
        data() | {"workflow_sha256": "bad"},
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


def test_packaged_digest_mismatch_cannot_silently_subset(monkeypatch, tmp_path):
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data()))
    monkeypatch.setattr(module, "_PATH", path)
    with pytest.raises(ValueError, match="digest mismatch"):
        module.load_inventory()
