"""Recognise and normalize pytest spellings accepted by the gate runner."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = [
    "is_full_suite_command",
    "pytest_command",
]

_JUST_COMMAND_MINIMUM_WORDS = 2


def is_full_suite_command(*, command: tuple[str, ...]) -> bool:
    """Whether ``command`` is a delegated full-suite command."""
    normalized = _without_mise(command=command)
    return _is_just_check(command=normalized) or pytest_command(command=normalized) is not None


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
    """Remove every ``uv run`` option before reading the program it will execute.

    Which options take a value is not knowable from the words alone, so the
    scan does not enumerate them: a dashed word is an option, and a bare word
    straight after one is its value unless it names pytest or an interpreter,
    which is then the program. That errs toward reading a pytest, never away.
    """
    index = 0
    after_option = False
    while index < len(command):
        word = command[index]
        if word.startswith("-"):
            after_option = True
        elif after_option and not _names_pytest_program(word=word):
            after_option = False
        else:
            break
        index += 1
    return command[index:]


def _names_pytest_program(*, word: str) -> bool:
    """Whether a word is ``pytest`` or a Python interpreter, the programs read as pytest."""
    return word == "pytest" or _is_python(command=(word,))


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
