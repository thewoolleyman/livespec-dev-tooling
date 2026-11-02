"""Tests for the detached gate runner's venue-selection adapter."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

__all__: list[str] = []

_MODULE_PATH = Path(__file__).parents[2] / "livespec_dev_tooling" / "gate_runner_delegate.py"


@pytest.mark.parametrize(
    ("command", "force_local", "delegated", "credential_readable", "venue", "reason"),
    [
        pytest.param(
            ("just", "check"), True, True, True, "host_local", "--local", id="explicit-local"
        ),
        pytest.param(
            ("just", "check"),
            False,
            False,
            True,
            "host_local",
            "undelegated repository",
            id="undelegated-repository",
        ),
        pytest.param(
            ("just", "check"),
            False,
            True,
            False,
            "host_local",
            "ineligible host",
            id="ineligible-host",
        ),
        pytest.param(
            ("git", "commit", "-m", "keep-hooks"),
            False,
            True,
            True,
            "host_local",
            "command outside full-suite set",
            id="commit-keeps-hooks-local",
        ),
        pytest.param(
            ("git", "push"),
            False,
            True,
            True,
            "host_local",
            "command outside full-suite set",
            id="push-keeps-hooks-local",
        ),
        pytest.param(
            ("just", "check"),
            False,
            True,
            True,
            "cluster_job",
            "eligible full-suite command",
            id="just-check",
        ),
        pytest.param(
            ("mise", "exec", "--", "just", "check-types"),
            False,
            True,
            True,
            "cluster_job",
            "eligible full-suite command",
            id="mise-just-check-member",
        ),
        pytest.param(
            ("uv", "run", "pytest", "tests"),
            False,
            True,
            True,
            "cluster_job",
            "eligible full-suite command",
            id="uv-pytest",
        ),
    ],
)
def test_gate_runner_venue_selection(
    *,
    command: tuple[str, ...],
    force_local: bool,
    delegated: bool,
    credential_readable: bool,
    venue: str,
    reason: str,
) -> None:
    """Only eligible full suites move to a Job; every other gate stays local."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")

    selected = module.select_venue(
        command=command,
        force_local=force_local,
        delegated=delegated,
        credential_readable=credential_readable,
    )

    assert selected.venue == venue
    assert selected.reason == reason
