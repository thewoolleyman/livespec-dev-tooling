"""Boundary coverage for the controller-side workspace manifest."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "ansible/roles/factory_workspace_sweep/files/factory_workspace_manifest.py"
_SWEEP = _ROOT / "ansible/roles/factory_workspace_sweep/files/factory_workspace_sweep.py"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_fails_closed_for_bad_instances_and_ledger_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _load(_MANIFEST, "factory_workspace_manifest_coverage")
    config = {
        "fabro_bin": "fabro",
        "lithos_bin": "lithos",
        "instances": [None, {}, {"server": "x"}],
    }
    assert manifest.read_runs(config=config) == ({}, False)
    monkeypatch.setattr(
        manifest, "command", lambda _argv, **_kw: subprocess.CompletedProcess([], 1, "", "")
    )
    assert manifest.item_class(item="x", ledger_command="bd") == "tenant-unreadable"


def test_manifest_preserves_bad_provider_data_and_unended_or_linked_workspaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _load(_MANIFEST, "factory_workspace_manifest_provider_coverage")
    monkeypatch.setattr(
        manifest,
        "command",
        lambda argv, **_kw: subprocess.CompletedProcess(
            [], 0, "[]" if argv[0] == "fabro" else "{}", ""
        ),
    )
    assert manifest.read_runs(
        config={
            "fabro_bin": "fabro",
            "lithos_bin": "lithos",
            "instances": [{"server": "x", "providers": ["kubernetes-rust"]}],
        }
    ) == ({}, False)
    root = tmp_path / "root"
    root.mkdir()
    (root / "petri-live-l0").mkdir()
    (root / "link").symlink_to(root / "petri-live-l0", target_is_directory=True)
    monkeypatch.setattr(
        manifest, "checkout_state", lambda _directory: ("h", False, "head-on-origin-ref")
    )
    rows = manifest.make_rows(
        root=root,
        runs={"LIVE": {"status": {"kind": "running"}}},
        runs_readable=True,
        config={"ledger_command": "bd", "archive_record_command": "bd"},
    )
    assert [row["cls"] for row in rows] == ["run-no-end-time"]


def test_manifest_collects_checkout_and_directory_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _load(_MANIFEST, "factory_workspace_manifest_checkout_coverage")
    directory = tmp_path / "petri-run-l0"
    directory.mkdir()
    calls = iter(
        [
            subprocess.CompletedProcess([], 1, "", "no head"),
            subprocess.CompletedProcess([], 0, "a" * 40 + "\n", ""),
            subprocess.CompletedProcess([], 1, "", ""),
            subprocess.CompletedProcess([], 0, "  origin/master\n", ""),
        ]
    )
    monkeypatch.setattr(manifest, "command", lambda _argv, **_kw: next(calls))
    assert manifest.checkout_state(directory) == ("", True, "checkout-unreadable")
    assert manifest.checkout_state(directory) == ("a" * 40, True, "head-on-origin-ref")
    monkeypatch.setattr(
        Path, "rglob", lambda _self, _pattern: (_ for _ in ()).throw(OSError("bad"))
    )
    assert manifest.directory_kb(directory) == 1


def test_manifest_rows_and_main_write_live_controller_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _load(_MANIFEST, "factory_workspace_manifest_main_coverage")
    root = tmp_path / "root"
    root.mkdir()
    (root / "petri-finished-l0").mkdir()
    (root / "odd").mkdir()
    monkeypatch.setattr(
        manifest, "checkout_state", lambda _directory: ("h", False, "head-on-origin-ref")
    )
    monkeypatch.setattr(manifest, "directory_kb", lambda _directory: 1)
    rows = manifest.make_rows(
        root=root,
        runs={
            "FINISHED": {
                "status": {"kind": "succeeded"},
                "start_time": "2026-01-01T00:00:00Z",
                "wall_time_ms": 1,
            }
        },
        runs_readable=True,
        config={"ledger_command": "bd", "archive_record_command": "bd"},
    )
    assert {row["cls"] for row in rows} == {"item-unmapped"}
    config_path = tmp_path / "config.json"
    output_path = tmp_path / "out" / "manifest.json"
    config_path.write_text(
        json.dumps(
            {
                "root": str(root),
                "manifest": str(output_path),
                "fabro_bin": "fabro",
                "lithos_bin": "lithos",
                "instances": [],
                "ledger_command": "bd",
                "archive_record_command": "bd",
            }
        )
    )
    monkeypatch.setattr(manifest, "read_runs", lambda *, config: ({}, bool(config)))
    monkeypatch.setattr(sys, "argv", ["manifest", "--config", str(config_path)])
    assert manifest.main() == 0
    assert json.loads(output_path.read_text())
    assert "factory-workspace-manifest" in capsys.readouterr().out
    config_path.write_text("[]")
    with pytest.raises(manifest.ManifestConfigurationError, match="JSON object"):
        manifest.main()


def test_sweep_live_manifest_keep_and_archive_receipt_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = _load(_SWEEP, "factory_workspace_sweep_coverage")
    root = tmp_path / "root"
    dest = tmp_path / "archive"
    root.mkdir()
    directory = root / "petri-run-l0"
    directory.mkdir()
    row = {
        "manifest_version": 2,
        "dir": directory.name,
        "kb": 1,
        "cls": "item-ready",
        "head": "h",
        "dirty": False,
        "evidence": "head-on-origin-ref",
        "item": "item",
        "run_ended_at": None,
        "action": "delete",
        "archive_record_command": "bd",
    }
    assert sweep.keep_reason(row=row, root=root, refs=set(), min_age_s=0) == "run-no-end-time"
    row["run_ended_at"] = "done"
    row["dirty"] = True
    monkeypatch.setattr(sweep, "head_of", lambda _directory: "h")
    monkeypatch.setattr(sweep, "archive", lambda **_kw: (dest / "x.tar.zst", "digest"))
    monkeypatch.setattr(
        sweep, "run", lambda _argv, **_kw: subprocess.CompletedProcess([], 1, "", "")
    )
    dest.mkdir()
    record, reason = sweep.apply_row(row=row, root=root, dest=dest)
    assert record is None
    assert reason == "archive-record-failed"
    assert directory.is_dir()
    assert (
        sweep.keep_reason(
            row={**row, "cls": "tenant-unreadable"}, root=root, refs=set(), min_age_s=0
        )
        == "tenant-unreadable"
    )
    assert (
        sweep.record_archive(
            row={"manifest_version": 2, "item": None}, archive_path=dest / "x", digest="d"
        )
        == "archive-record-unavailable"
    )
