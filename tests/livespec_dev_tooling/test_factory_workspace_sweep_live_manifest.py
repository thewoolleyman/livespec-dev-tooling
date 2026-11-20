"""The workspace sweep preserves directories for items that are not finished.

This is the controller-manifest boundary for livespec-dev-tooling-iwvy4u: a
manifest row must carry the item's freshly-read ledger state into the host
reaper, and an item in acceptance must never be removed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
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
    / "factory_workspace_sweep.py"
)
_HEAD = "a" * 40


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("factory_workspace_sweep_live_manifest", _SCRIPT)
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


def test_apply_keeps_a_workspace_whose_live_item_state_is_in_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance is not finished, even when all ordinary removal checks pass."""
    sweep = _load()
    root = tmp_path / "root"
    directory = root / "petri-finished-run-l0"
    archive = tmp_path / "archive"
    root.mkdir()
    directory.mkdir()
    (directory / "file.txt").write_text("work")
    old = time.time() - 3 * 86400
    os.utime(directory, (old, old))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "dir": directory.name,
                    "kb": 1024,
                    "cls": "item-acceptance",
                    "head": _HEAD,
                    "dirty": False,
                    "evidence": "live-ledger-state",
                    "item": "livespec-dev-tooling-iwvy4u",
                    "repo": "livespec-dev-tooling",
                    "action": "archive",
                }
            ]
        )
    )
    monkeypatch.setattr(sweep, "head_of", lambda _directory: _HEAD)
    monkeypatch.setattr(sweep, "referenced_dirs", lambda _kubectl, _scope: set())
    monkeypatch.setattr(sweep, "free_bytes", lambda _root: 0)
    monkeypatch.setattr(sweep, "archive", lambda **_kw: (archive / "saved.tar.zst", "digest"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "factory_workspace_sweep.py",
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--archive-dir",
            str(archive),
            "--stop-free-gib",
            "1",
            "--apply",
        ],
    )

    assert sweep.main() == 0
    assert directory.is_dir()
    assert f"APPLY KEEP {directory.name} item-in-acceptance" in capsys.readouterr().out
