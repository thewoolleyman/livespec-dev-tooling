"""Consumer proof for the committed token-spend guard's factory-pool rule."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD = _REPO_ROOT / "ansible" / "roles" / "token_spend_report" / "files" / "spend_staleness.py"


def _guard() -> ModuleType:
    assert (
        _GUARD.is_file()
    ), "the committed token-spend route must carry spend_staleness.py under its Ansible role"
    spec = importlib.util.spec_from_file_location("token_spend_spend_staleness", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_factory_over_requires_every_committed_pool_slot_and_never_holds_on_unreadable_slot() -> (
    None
):
    """A single exhausted account must not block the factory while another slot has headroom."""
    guard = _guard()
    over = {
        "slot": "anthropic-2",
        "over": True,
        "line": "slot 2 OVER: release no more factory runs",
    }
    headroom = {"slot": "anthropic-4", "over": False, "line": "slot 4 has headroom"}
    unreadable = {"slot": "anthropic-4", "line": "no reading"}

    assert guard.pool_slots(_REPO_ROOT / ".livespec.jsonc") == ("anthropic-4", "anthropic-2")
    assert guard.pool_over([over, headroom]) is False
    assert guard.pool_over([over, unreadable]) is False
    assert guard.pool_over([over, {**headroom, "over": True}]) is True
    line = guard.pool_line(over, ["anthropic-2"], held=False)
    assert "release no more factory runs" not in line
    assert "pool is not over" in line
    assert "no hold" in line
