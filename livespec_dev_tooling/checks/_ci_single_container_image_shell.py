"""Shell-command parsing for the layered container-image check."""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath

__all__ = ["runs_aggregate_target"]

_RUN_KEY = re.compile(r"^(?P<lead>[ \t]*(?:-[ \t]+)?)run:[ \t]*(?P<value>.*)$")
_BLOCK_SCALAR = re.compile(r"^(?P<style>[|>])[-+0-9]*[ \t]*(?:#.*)?$")
_SHELL_OPERATOR = re.compile(r"^[();<>|&]+$")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_UNPARSEABLE_SHELL = re.compile(r"""["'\\]|(?:^|\s)#.*$""")
_QUOTED = re.compile(r"""^(?P<quote>["'])(?P<body>.*?)(?P=quote)""")
_TRAILING_COMMENT = re.compile(r"[ \t]+#.*$")
_SHELL_C_ARGUMENT_COUNT = 2


def _reference(*, raw: str) -> str:
    quoted = _QUOTED.match(raw)
    if quoted is not None:
        return quoted.group("body")
    return _TRAILING_COMMENT.sub("", raw).strip()


def _indent_of(*, line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _run_commands(*, lines: list[str]) -> list[str]:
    """The shell command lines of every step run value in a job's source lines."""
    commands: list[str] = []
    index = 0
    while index < len(lines):
        match = _RUN_KEY.match(lines[index])
        index += 1
        if match is None:
            continue
        key_indent = len(match.group("lead"))
        body: list[str] = []
        while index < len(lines) and (
            not lines[index].strip() or _indent_of(line=lines[index]) > key_indent
        ):
            body.append(lines[index].strip())
            index += 1
        block = _BLOCK_SCALAR.match(match.group("value"))
        if block is None:
            commands.append(_reference(raw=" ".join([match.group("value"), *body])))
        elif block.group("style") == ">":
            commands.append(" ".join(part for part in body if part))
        else:
            commands.extend(re.sub(r"\\\n", " ", "\n".join(body)).splitlines())
    return commands


def _shell_words(*, command: str) -> list[str]:
    """The command's shell words, comments removed and quoting resolved."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        return list(lexer)
    except ValueError:
        sanitized = _UNPARSEABLE_SHELL.sub(" ", command)
        return [
            word
            for segment in re.split(r"(&&|\|\||[;|&()])", sanitized)
            for word in (
                [segment] if _SHELL_OPERATOR.match(segment) is not None else segment.split()
            )
            if word
        ]


def _command_runs_aggregate(*, command: str, aggregate: set[str], reparse_depth: int = 0) -> bool:
    """Whether the shell command invokes just with any aggregate target."""
    segment: list[str] = []
    for word in [*_shell_words(command=command), ";"]:
        if not _SHELL_OPERATOR.match(word):
            segment.append(word)
            continue
        if _segment_runs_aggregate(
            words=segment, aggregate=aggregate, reparse_depth=reparse_depth
        ):
            return True
        segment = []
    return False


def _command_word_position(*, words: list[str]) -> int:
    """The command word after leading assignments and transparent runner prefixes."""
    position = 0
    while position < len(words) and _ASSIGNMENT.match(words[position]) is not None:
        position += 1
    while position < len(words):
        word = words[position]
        if word == "env":
            position += 1
            while position < len(words) and _ASSIGNMENT.match(words[position]) is not None:
                position += 1
        elif word in {"command", "exec", "time", "nice"}:
            position += 1
        elif word == "mise" and words[position + 1 : position + 3] in (["exec", "--"], ["x", "--"]):
            position += 3
        elif word == "uv" and words[position + 1 : position + 2] == ["run"]:
            position += 2
        else:
            break
        while position < len(words) and _ASSIGNMENT.match(words[position]) is not None:
            position += 1
    return position


def _segment_runs_aggregate(*, words: list[str], aggregate: set[str], reparse_depth: int) -> bool:
    position = _command_word_position(words=words)
    if position == len(words):
        return False
    command_word = words[position]
    arguments = words[position + 1 :]
    if PurePosixPath(command_word).name == "just":
        return any(
            not argument.startswith("-")
            and _ASSIGNMENT.match(argument) is None
            and argument in aggregate
            for argument in arguments
        )
    if reparse_depth != 0:
        return False
    if (
        command_word in {"bash", "sh"}
        and arguments[:1] == ["-c"]
        and len(arguments) == _SHELL_C_ARGUMENT_COUNT
    ):
        return _command_runs_aggregate(
            command=arguments[1], aggregate=aggregate, reparse_depth=reparse_depth + 1
        )
    if command_word == "eval" and len(arguments) == 1:
        return _command_runs_aggregate(
            command=arguments[0], aggregate=aggregate, reparse_depth=reparse_depth + 1
        )
    return False


def runs_aggregate_target(
    *, lines: list[str], job_start: int, job_end: int, aggregate: set[str]
) -> bool:
    """Whether this job runs any declared aggregate target in a step run value."""
    return any(
        _command_runs_aggregate(command=command, aggregate=aggregate)
        for command in _run_commands(lines=lines[job_start:job_end])
    )
