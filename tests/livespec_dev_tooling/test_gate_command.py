"""Tests for the shared full-suite gate-command classifier."""

from __future__ import annotations

import pytest

from livespec_dev_tooling.gate_command import is_full_suite_command, pytest_command

__all__: list[str] = []


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param(("just", "check"), True, id="just-check"),
        pytest.param(("mise", "exec", "--", "just", "check-types"), True, id="mise-just"),
        pytest.param(("just", "unit"), False, id="other-just-recipe"),
        pytest.param(("pytest", "tests"), True, id="direct-pytest"),
        pytest.param(("python", "-m", "pytest", "--cov=widget"), True, id="python-module"),
        pytest.param(
            ("uv", "run", "--no-sync", "python", "-m", "pytest", "--cov=widget"),
            True,
            id="uv-python-module",
        ),
        pytest.param((".venv/bin/python", "-m", "pytest", "-n", "8"), True, id="path-python"),
        pytest.param(("ruby", "-m", "pytest"), False, id="non-python-interpreter"),
    ],
)
def test_full_suite_recognition_covers_each_accepted_command_shape(
    *, command: tuple[str, ...], expected: bool
) -> None:
    """Only the delegated command set is recognized as a full-suite gate."""
    assert is_full_suite_command(command=command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param(("pytest", "tests"), ("pytest", "tests"), id="direct"),
        pytest.param(("uv", "run", "pytest", "tests"), ("pytest", "tests"), id="uv-direct"),
        pytest.param(
            ("uv", "run", "--no-sync", "python", "-m", "pytest", "--cov=widget"),
            ("pytest", "--cov=widget"),
            id="uv-module",
        ),
        pytest.param(
            (".venv/bin/python", "-m", "pytest", "-n", "8"),
            ("pytest", "-n", "8"),
            id="path-module",
        ),
        pytest.param(("just", "check"), None, id="just-is-not-pytest"),
        pytest.param(
            ("uv", "run", "--with", "pytest", "ruff", "check"),
            None,
            id="with-pytest-dependency-then-other-program",
        ),
        pytest.param(
            ("uv", "run", "--with", "pytest", "python", "scripts/foo.py"),
            None,
            id="with-pytest-dependency-then-interpreter-script",
        ),
        pytest.param(
            ("uv", "run", "--with-editable", "pytest", "ruff", "check"),
            None,
            id="with-editable-pytest-then-other-program",
        ),
        pytest.param(
            ("uv", "run", "--with", "pytest", "pytest"),
            ("pytest",),
            id="with-pytest-dependency-then-pytest-program",
        ),
        pytest.param(
            ("uv", "run", "--with", "pytest", "python", "-m", "pytest", "-n", "8"),
            ("pytest", "-n", "8"),
            id="with-pytest-dependency-then-python-module",
        ),
    ],
)
def test_pytest_command_normalizes_module_invocations(
    *, command: tuple[str, ...], expected: tuple[str, ...] | None
) -> None:
    """The renderer gets its established pytest argv from every accepted spelling."""
    assert pytest_command(command=command) == expected
