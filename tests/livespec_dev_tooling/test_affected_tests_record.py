"""Contract tests for the factory sandbox's affected-tests gate record."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun, GateCommandResult

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "affected_tests_record.py"


def _module() -> object:
    """Import the entry point after the Red assertion established its surface."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module("livespec_dev_tooling.affected_tests_record")


def test_affected_tests_gate_records_its_tree_outcome_and_selected_paths(*, tmp_path: Path) -> None:
    """A scoped gate persists its own evidence and preserves its exit status."""
    assert _MODULE_PATH.is_file()
    module = _module()
    selected = tmp_path / "selected-tests"
    selected.write_text("tests/test_widget.py\ntests/test_widget_edges.py\n", encoding="utf-8")
    recorded: list[object] = []

    status = module.run_affected_tests_gate(
        command=["just", "check-check-coverage-incremental"],
        cwd=tmp_path,
        paths_file=selected,
        execute=lambda **_kwargs: 7,
        record=lambda **kwargs: recorded.append(kwargs),
        tree_hash=lambda **_kwargs: "tree-under-test",
    )

    assert status == 7
    assert recorded == [
        {
            "cwd": tmp_path,
            "outcome": "failed",
            "test_paths": ("tests/test_widget.py", "tests/test_widget_edges.py"),
            "tree_hash": "tree-under-test",
        }
    ]


def test_affected_tests_gate_records_failed_and_empty_selections_without_changing_status(
    *, tmp_path: Path
) -> None:
    """The record reports the gate's facts even when they cannot be reused."""
    module = _module()
    absent = tmp_path / "not-selected"
    recorded: list[dict[str, object]] = []

    status = module.run_affected_tests_gate(
        command=["check-changed"],
        cwd=tmp_path,
        paths_file=absent,
        execute=lambda **_kwargs: 0,
        record=lambda **kwargs: recorded.append(kwargs),
        tree_hash=lambda **_kwargs: "tree-under-test",
    )

    assert status == 0
    assert recorded[0]["outcome"] == "passed"
    assert recorded[0]["test_paths"] == ()


def test_record_reader_retains_a_failed_or_empty_record_but_rejects_malformed_data(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scope selection, rather than parsing, decides whether evidence qualifies."""
    module = _module()
    path = tmp_path / "affected-record.json"
    monkeypatch.setattr(module, "_git_path", lambda **_kwargs: path)
    path.write_text(
        json.dumps(
            {
                "tree_hash": "tree",
                "outcome": "failed",
                "test_paths": [],
                "run_id": "affected-tests:run-1",
            }
        ),
        encoding="utf-8",
    )

    evidence = module.read_affected_tests_evidence(cwd=tmp_path)

    assert evidence is not None
    assert evidence.outcome == "failed"
    assert evidence.test_paths == ()
    path.write_text('{"tree_hash": 1}', encoding="utf-8")
    assert module.read_affected_tests_evidence(cwd=tmp_path) is None
    path.write_text("{", encoding="utf-8")
    assert module.read_affected_tests_evidence(cwd=tmp_path) is None


def test_record_writes_readable_evidence_and_ignores_an_unavailable_git_path(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Evidence is advisory: a write failure cannot change a gate verdict."""
    module = _module()
    path = tmp_path / "affected-record.json"
    monkeypatch.setattr(module, "_git_path", lambda **_kwargs: path)
    module._record(  # noqa: SLF001
        cwd=tmp_path,
        tree_hash="tree",
        outcome="passed",
        test_paths=("tests/test_widget.py",),
    )
    evidence = module.read_affected_tests_evidence(cwd=tmp_path)
    assert evidence is not None
    assert evidence.tree_hash == "tree"
    assert evidence.outcome == "passed"
    assert evidence.test_paths == ("tests/test_widget.py",)
    monkeypatch.setattr(module, "_git_path", lambda **_kwargs: (_ for _ in ()).throw(OSError()))
    module._record(  # noqa: SLF001
        cwd=tmp_path,
        tree_hash="tree",
        outcome="passed",
        test_paths=("tests/test_widget.py",),
    )
    module._record(  # noqa: SLF001
        cwd=tmp_path,
        tree_hash=None,
        outcome="passed",
        test_paths=(),
    )


def test_git_and_command_helpers_preserve_answers_and_unavailable_boundaries(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The entry point distinguishes a gate answer from a command that never ran."""
    module = _module()
    success = Success(GateCommandResult(returncode=0, stdout=".git/evidence\n", stderr=""))
    monkeypatch.setattr(module, "default_gate_command_runner", lambda **_kwargs: success)
    assert module._git_path(cwd=tmp_path) == (tmp_path / ".git" / "evidence").resolve()  # noqa: SLF001
    assert module._tree_hash(cwd=tmp_path) == ".git/evidence"  # noqa: SLF001
    assert module._execute(command=["check-changed"], cwd=tmp_path) == 0  # noqa: SLF001
    failure = Failure(GateCommandNotRun(argv=("git",), detail="missing"))
    monkeypatch.setattr(module, "default_gate_command_runner", lambda **_kwargs: failure)
    with pytest.raises(OSError, match="git path unavailable"):
        module._git_path(cwd=tmp_path)  # noqa: SLF001
    assert module._tree_hash(cwd=tmp_path) is None  # noqa: SLF001
    assert module._execute(command=["check-changed"], cwd=tmp_path) == 127  # noqa: SLF001
    nonzero = Success(GateCommandResult(returncode=7, stdout="", stderr=""))
    monkeypatch.setattr(module, "default_gate_command_runner", lambda **_kwargs: nonzero)
    with pytest.raises(OSError, match="git path unavailable"):
        module._git_path(cwd=tmp_path)  # noqa: SLF001
    assert module._tree_hash(cwd=tmp_path) is None  # noqa: SLF001


def test_cli_forwards_command_and_requires_one(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Consumer hooks invoke one command and receive its own exit status."""
    module = _module()
    called: list[dict[str, object]] = []
    monkeypatch.setattr(
        module, "run_affected_tests_gate", lambda **kwargs: called.append(kwargs) or 7
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "affected_tests_record",
            "--paths-file",
            str(tmp_path / "paths"),
            "--",
            "just",
            "check-changed",
        ],
    )

    assert module.main() == 7
    assert called[0]["command"] == ["just", "check-changed"]
    monkeypatch.setattr(sys, "argv", ["affected_tests_record", "--paths-file", str(tmp_path)])
    with pytest.raises(SystemExit, match="2"):
        module.main()
