"""Pairing coverage for the gate-Job wait surface."""

from __future__ import annotations

from livespec_dev_tooling.gate_remote_wait import await_terminal_state

__all__: list[str] = []


def test_the_wait_surface_is_public() -> None:
    """The client imports the cohesive wait operation through its public name."""
    assert callable(await_terminal_state)
