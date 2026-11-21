"""Live-ledger manifest coverage for the factory workspace sweep."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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


def test_a_boolean_run_duration_is_not_proof_that_the_run_ended() -> None:
    """Booleans are integers in Python but are not a Fabro duration."""
    manifest = _load()

    assert (
        manifest.run_end(
            {
                "status": {"kind": "succeeded"},
                "start_time": "2026-11-19T00:00:00Z",
                "wall_time_ms": True,
            }
        )
        is None
    )


def test_manifest_helpers_fail_closed_for_malformed_controller_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _load()

    assert manifest.mapping({"a": 1}) == {"a": 1}
    assert manifest.mapping([]) is None
    assert manifest.sequence(["a"]) == ["a"]
    assert manifest.sequence(("a",)) == ("a",)
    assert manifest.sequence("a") == ()
    assert manifest.json_output(subprocess.CompletedProcess(["x"], 1, "{}", "")) is None
    assert manifest.json_output(subprocess.CompletedProcess(["x"], 0, "not-json", "")) is None
    assert manifest.json_output(subprocess.CompletedProcess(["x"], 0, "{}", "")) == {}
    with pytest.raises(manifest.ManifestConfigurationError, match="needs a non-empty ledger"):
        manifest.string_value({}, "ledger")
    with pytest.raises(manifest.ManifestConfigurationError, match="must be a JSON object"):
        raise manifest.ManifestConfigurationError.not_an_object()

    def unavailable(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("not installed")

    monkeypatch.setattr(manifest.subprocess, "run", unavailable)
    failed = manifest.command(["missing"], home="/controller-home")
    assert (failed.returncode, failed.stderr) == (127, "not installed")


def test_read_runs_queries_each_instance_and_provider_and_marks_bad_evidence_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _load()
    calls: list[tuple[str, ...]] = []

    def fake_command(argv: object, *, home: str | None = None) -> subprocess.CompletedProcess[str]:
        del home
        command = tuple(argv)
        calls.append(command)
        if command[1:3] == ("ps", "-a"):
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps([{"run_id": "known"}, "malformed"]),
                "",
            )
        return subprocess.CompletedProcess(command, 0, "[]", "")

    monkeypatch.setattr(manifest, "command", fake_command)
    runs, readable = manifest.read_runs(
        config={
            "fabro_bin": "fabro",
            "lithos_bin": "lithos",
            "instances": [
                {"server": "http://one", "home": "/one", "providers": ["kubernetes-rust"]},
                {"server": "http://two", "providers": [None]},
            ],
        }
    )

    assert tuple(runs) == ("KNOWN",)
    assert not readable
    assert ("fabro", "ps", "-a", "--json", "--server", "http://one") in calls
    assert ("fabro", "ps", "-a", "--json", "--server", "http://two") in calls
    assert (
        "lithos",
        "--provider",
        "kubernetes-rust",
        "--output",
        "json",
        "sandbox",
        "list",
    ) in calls


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        ({"status": {"kind": "running"}}, None),
        ({"status": {"kind": "succeeded"}, "start_time": None, "wall_time_ms": 1}, None),
        ({"status": {"kind": "succeeded"}, "start_time": "bad", "wall_time_ms": 1}, None),
        (
            {"status": {"kind": "failed"}, "start_time": "2026-11-19T00:00:00", "wall_time_ms": 2},
            "2026-11-19T00:00:00.002000+00:00",
        ),
    ],
)
def test_run_end_requires_a_terminal_run_with_valid_timing(
    run: dict[str, object], expected: str | None
) -> None:
    assert _load().run_end(run) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "needs_human"}, "item-needs-human"),
        ({"state": {"kind": "acceptance"}}, "item-acceptance"),
        ({}, "tenant-unreadable"),
    ],
)
def test_item_class_reads_each_ledger_state_shape(
    payload: dict[str, object], expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _load()
    monkeypatch.setattr(
        manifest,
        "command",
        lambda _argv: subprocess.CompletedProcess(["bd"], 0, json.dumps(payload), ""),
    )
    assert manifest.item_class(item="item-1", ledger_command="bd") == expected
    assert manifest.item_class(item=None, ledger_command="bd") == "item-unmapped"


def test_rows_keep_unreadable_live_evidence_and_archive_dirty_or_unpublished_checkouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _load()
    for name in ("petri-missing-l0", "petri-live-l0", "petri-done-l0", "other"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(
        manifest,
        "checkout_state",
        lambda directory: ("head", directory.name == "petri-done-l0", "head-on-no-origin-ref"),
    )
    monkeypatch.setattr(manifest, "directory_kb", lambda _directory: 2)
    rows = manifest.make_rows(
        root=tmp_path,
        runs={
            "LIVE": {"status": {"kind": "running"}},
            "DONE": {
                "status": {"kind": "succeeded"},
                "start_time": "2026-11-19T00:00:00Z",
                "wall_time_ms": 1,
                "labels": {"work.item.id": "item-done"},
            },
        },
        runs_readable=False,
        config={"ledger_command": "bd", "archive_record_command": "bd"},
    )

    assert [row["cls"] for row in rows] == ["run-end-unreadable"] * 4
    assert all(row["action"] == "archive" for row in rows)
