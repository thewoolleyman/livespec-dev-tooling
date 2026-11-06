"""Recognise and normalize pytest spellings accepted by the gate runner."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = [
    "is_foreground_full_suite_pytest",
    "is_full_suite_command",
    "pytest_command",
]

_JUST_COMMAND_MINIMUM_WORDS = 2
_PYTEST_VALUE_OPTIONS: frozenset[str] = frozenset(
    {
        "-c",
        "-k",
        "-m",
        "-o",
        "-r",
        "--basetemp",
        "--confcutdir",
        "--cov",
        "--cov-config",
        "--deselect",
        "--durations",
        "--ignore",
        "--ignore-glob",
        "--junitxml",
        "--maxfail",
        "--numprocesses",
        "--rootdir",
        "--tb",
    }
)


def is_full_suite_command(*, command: tuple[str, ...]) -> bool:
    """Whether ``command`` is a delegated full-suite command."""
    normalized = _without_mise(command=command)
    return _is_just_check(command=normalized) or pytest_command(command=normalized) is not None


def is_foreground_full_suite_pytest(*, command: tuple[str, ...]) -> bool:
    """Whether pytest has the guard's narrower full-suite shape."""
    normalized = pytest_command(command=command)
    if normalized is None:
        return False
    arguments = normalized[1:]
    if any(argument.startswith(("-n", "--numprocesses")) for argument in arguments):
        return True
    consumes_next = False
    for argument in arguments:
        if consumes_next:
            consumes_next = False
        elif argument in _PYTEST_VALUE_OPTIONS:
            consumes_next = True
        elif not argument.startswith("-"):
            return False
    return True


def pytest_command(*, command: tuple[str, ...]) -> tuple[str, ...] | None:
    """Normalize a direct, ``uv run``, or interpreter-module pytest command."""
    normalized = _without_mise(command=command)
    if normalized[:1] == ("pytest",):
        return normalized
    if normalized[:2] == ("uv", "run"):
        normalized = _without_uv_options(command=normalized[2:])
        if normalized[:1] == ("pytest",):
            return normalized
    if _is_python(command=normalized[:1]) and normalized[1:3] == ("-m", "pytest"):
        return ("pytest", *normalized[3:])
    return None


def _without_mise(*, command: tuple[str, ...]) -> tuple[str, ...]:
    """Remove the transparent ``mise exec --`` prefix when it is present."""
    return command[3:] if command[:3] == ("mise", "exec", "--") else command


def _without_uv_options(*, command: tuple[str, ...]) -> tuple[str, ...]:
    """Remove ``uv run`` flags before reading the program it will execute."""
    while command[:1] == ("--no-sync",):
        command = command[1:]
    return command


def _is_just_check(*, command: tuple[str, ...]) -> bool:
    """Recognise the gate runner's existing ``just check*`` command set."""
    return (
        len(command) >= _JUST_COMMAND_MINIMUM_WORDS
        and command[:1] == ("just",)
        and (command[1] == "check" or (command[1].startswith("check-") and command[1] != "check-"))
    )


def _is_python(*, command: tuple[str, ...]) -> bool:
    """Whether the command word names a Python interpreter executable."""
    return bool(command) and Path(command[0]).name.startswith("python")
