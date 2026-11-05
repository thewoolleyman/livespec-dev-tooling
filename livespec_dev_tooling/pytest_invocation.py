"""Recognise command spellings that invoke pytest.

The detached gate runner and the agent-session guard make different venue
decisions, but they must agree on which command spellings run pytest. Keeping
that parsing here prevents an interpreter-module spelling from being a gate
command for one caller and an ordinary host command for the other.
"""

from __future__ import annotations

__all__: list[str] = [
    "pytest_arguments",
]

_MISE_EXEC_PREFIX = ("mise", "exec", "--")
_UV_RUN_PREFIX = ("uv", "run")
_MODULE_PYTEST_WORDS = 3


def pytest_arguments(*, command: tuple[str, ...]) -> tuple[str, ...] | None:
    """Return pytest's arguments when ``command`` invokes pytest, else ``None``.

    ``uv run`` accepts options before the command it executes, so its command
    boundary is the first direct ``pytest`` or interpreter ``-m pytest`` shape.
    A ``mise exec --`` prefix is transparent in the same way for every caller.
    """
    normalized = command[len(_MISE_EXEC_PREFIX) :] if command[:3] == _MISE_EXEC_PREFIX else command
    if normalized[:1] == ("pytest",):
        return normalized[1:]
    if normalized[:2] == _UV_RUN_PREFIX:
        return _pytest_arguments_after_uv_run(words=normalized[2:])
    return _interpreter_pytest_arguments(words=normalized)


def _pytest_arguments_after_uv_run(*, words: tuple[str, ...]) -> tuple[str, ...] | None:
    """Find the command ``uv run`` will execute after its own options."""
    for index, word in enumerate(words):
        tail = words[index:]
        if word == "pytest":
            return tail[1:]
        interpreted = _interpreter_pytest_arguments(words=tail)
        if interpreted is not None:
            return interpreted
    return None


def _interpreter_pytest_arguments(*, words: tuple[str, ...]) -> tuple[str, ...] | None:
    """Recognise any interpreter name or path used as ``-m pytest``."""
    if len(words) >= _MODULE_PYTEST_WORDS and words[1:_MODULE_PYTEST_WORDS] == ("-m", "pytest"):
        return words[_MODULE_PYTEST_WORDS:]
    return None
