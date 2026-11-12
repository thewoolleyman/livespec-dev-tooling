"""Contract tests for the factory sandbox's affected-tests gate record."""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "affected_tests_record.py"


def test_affected_tests_gate_records_its_tree_outcome_and_selected_paths(*, tmp_path: Path) -> None:
    """A scoped gate persists its own evidence and preserves its exit status."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module("livespec_dev_tooling.affected_tests_record")
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
