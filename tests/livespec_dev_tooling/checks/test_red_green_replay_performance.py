"""Focused incident-budget regression coverage for the Red/Green replay tests."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPLAY_TEST = "tests/livespec_dev_tooling/checks/test_red_green_replay.py"


def test_replay_module_replaces_nested_suite_execution_with_a_test_double() -> None:
    """Focused replay cases must not pay for a real suite-green child pytest."""
    source = (_REPO_ROOT / _REPLAY_TEST).read_text(encoding="utf-8")

    assert "def _fast_local_suite_run(" in source
