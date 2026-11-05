"""Tests for the shared pytest command-spelling parser."""

from __future__ import annotations

import pytest

from livespec_dev_tooling.gate_runner_delegate import _remote_command
from livespec_dev_tooling.pytest_invocation import pytest_arguments

__all__: list[str] = []


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param(("pytest", "--cov=pkg"), ("--cov=pkg",), id="direct"),
        pytest.param(
            ("mise", "exec", "--", "pytest", "tests/unit.py"),
            ("tests/unit.py",),
            id="mise-direct",
        ),
        pytest.param(("python", "-m", "pytest"), (), id="interpreter-module"),
        pytest.param(
            (".venv/bin/python", "-m", "pytest", "tests/unit.py"),
            ("tests/unit.py",),
            id="interpreter-path-module",
        ),
        pytest.param(
            ("uv", "run", "pytest", "-n", "4"),
            ("-n", "4"),
            id="uv-direct",
        ),
        pytest.param(
            ("uv", "run", "--no-sync", "python", "-m", "pytest", "--cov=pkg"),
            ("--cov=pkg",),
            id="uv-interpreter-module",
        ),
    ],
)
def test_pytest_arguments_recognises_every_supported_spelling(
    *, command: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    """The runner and guard receive pytest's arguments, not its launcher words."""
    assert pytest_arguments(command=command) == expected


@pytest.mark.parametrize(
    "command",
    [
        (),
        ("python", "-m", "unittest"),
        ("uv", "run", "--no-sync", "python", "-m", "unittest"),
        ("just", "check"),
    ],
)
def test_pytest_arguments_rejects_other_commands(*, command: tuple[str, ...]) -> None:
    """Only actual pytest invocations enter the shared full-suite set."""
    assert pytest_arguments(command=command) is None


def test_remote_command_leaves_non_pytest_commands_unchanged() -> None:
    """Only recognised pytest spellings are normalised for the gate renderer."""
    assert _remote_command(command=("git", "status")) == (("git", "status"), ())
