"""Live-ledger manifest coverage for the factory workspace sweep."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    _REPO_ROOT
    / "ansible"
    / "roles"
    / "factory_workspace_sweep"
    / "files"
    / "factory_workspace_manifest.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("factory_workspace_manifest_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _clean_checkout_state(_directory: Path) -> tuple[str, bool, str]:
    return "a" * 40, False, "head-on-origin-ref"


def test_a_known_run_uses_its_work_item_id_for_the_live_ledger_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _load()
    workspace = tmp_path / "petri-01run-l0"
    workspace.mkdir()
    run = {
        "run_id": "01RUN",
        "status": {"kind": "succeeded"},
        "start_time": "2026-11-19T00:00:00Z",
        "wall_time_ms": 1,
        "labels": {
            "work.item.id": "livespec-dev-tooling-item",
            "livespec.dispatch.id": "dispatch-attempt-only",
        },
    }
    monkeypatch.setattr(
        manifest,
        "checkout_state",
        _clean_checkout_state,
    )
    seen: dict[str, str | None] = {}

    def classify(*, item: str | None, ledger_command: str) -> str:
        seen["item"] = item
        seen["ledger_command"] = ledger_command
        return "item-acceptance"

    monkeypatch.setattr(manifest, "item_class", classify)
    rows = manifest.make_rows(
        root=tmp_path,
        runs={"01RUN": run},
        runs_readable=True,
        config={"ledger_command": "bd", "archive_record_command": "bd"},
    )

    assert seen == {"item": "livespec-dev-tooling-item", "ledger_command": "bd"}
    assert rows == [
        {
            "manifest_version": 2,
            "dir": "petri-01run-l0",
            "kb": 1,
            "cls": "item-acceptance",
            "head": "a" * 40,
            "dirty": False,
            "evidence": "head-on-origin-ref",
            "item": "livespec-dev-tooling-item",
            "run_ended_at": "2026-11-19T00:00:00.001000+00:00",
            "action": "delete",
            "archive_record_command": "bd",
        }
    ]
