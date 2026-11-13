"""Shell-command parsing for the layered container-image check."""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath

__all__: list[str] = ["runs_aggregate_target"]

_RUN_KEY = re.compile(r"^(?P<lead>[ \t]*(?:-[ \t]+)?)run:[ \t]*(?P<value>.*)$")
_BLOCK_SCALAR = re.compile(r"^(?P<style>[|>])[-+0-9]*[ \t]*(?:#.*)?$")
_SHELL_OPERATOR = re.compile(r"^[();<>|&]+$")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_UNPARSEABLE_SHELL = re.compile(r"""["'\\]|(?:^|\s)#.*$""")
_QUOTED = re.compile(r"""^(?P<quote>["'])(?P<body>.*?)(?P=quote)""")
_TRAILING_COMMENT = re.compile(r"[ \t]+#.*$")
_SHELL_C_ARGUMENT_COUNT = 2
_HERE_DOCUMENT = re.compile(r"""<<-?[ \t]*["']?(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)["']?""")
_TRANSPARENT_PREFIXES = {
    ("command",): 1,
    ("exec",): 1,
    ("time",): 1,
    ("nice",): 1,
    ("env",): 1,
    ("mise", "exec", "--"): 3,
    ("mise", "x", "--"): 3,
    ("uv", "run"): 2,
}


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
            commands.extend(_literal_commands(lines=body))
    return commands


def _literal_commands(*, lines: list[str]) -> list[str]:
    """Return literal-block commands, excluding here-document contents."""
    commands: list[str] = []
    delimiter: str | None = None
    for command in re.sub(r"\\\n", " ", "\n".join(lines)).splitlines():
        if delimiter is not None:
            if command == delimiter:
                delimiter = None
            continue
        commands.append(command)
        match = _HERE_DOCUMENT.search(command)
        if match is not None:
            delimiter = match.group("delimiter")
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


def _command_runs_aggregate(*, command: str, aggregate: set[str]) -> bool:
    """Whether the shell command invokes just with any aggregate target."""
    return _segments_run_aggregate(command=command, aggregate=aggregate, allow_reparse=True)


def _segments_run_aggregate(*, command: str, aggregate: set[str], allow_reparse: bool) -> bool:
    """Whether any simple command in ``command`` invokes an aggregate target."""
    segment: list[str] = []
    for word in [*_shell_words(command=command), ";"]:
        if not _SHELL_OPERATOR.match(word):
            segment.append(word)
            continue
        if _segment_runs_aggregate(words=segment, aggregate=aggregate, allow_reparse=allow_reparse):
            return True
        segment = []
    return False


def _command_word_position(*, words: list[str]) -> int:
    """The command word after leading assignments and transparent runner prefixes."""
    position = 0
    while position < len(words):
        position = _skip_assignments(words=words, position=position)
        prefix_length = next(
            (
                width
                for prefix, width in _TRANSPARENT_PREFIXES.items()
                if tuple(words[position : position + width]) == prefix
            ),
            0,
        )
        if prefix_length == 0:
            return position
        position += prefix_length
    return position


def _skip_assignments(*, words: list[str], position: int) -> int:
    while position < len(words) and _ASSIGNMENT.match(words[position]) is not None:
        position += 1
    return position


def _segment_runs_aggregate(*, words: list[str], aggregate: set[str], allow_reparse: bool) -> bool:
    position = _command_word_position(words=words)
    if position == len(words):
        return False
    command_word = words[position]
    arguments = words[position + 1 :]
    if PurePosixPath(command_word).name == "just":
        return _just_arguments_run_aggregate(arguments=arguments, aggregate=aggregate)
    if allow_reparse and (
        command_word in {"bash", "sh"}
        and arguments[:1] == ["-c"]
        and len(arguments) == _SHELL_C_ARGUMENT_COUNT
    ):
        return _segments_run_aggregate(
            command=arguments[1], aggregate=aggregate, allow_reparse=False
        )
    if allow_reparse and command_word == "eval" and len(arguments) == 1:
        return _segments_run_aggregate(
            command=arguments[0], aggregate=aggregate, allow_reparse=False
        )
    return False


def _just_arguments_run_aggregate(*, arguments: list[str], aggregate: set[str]) -> bool:
    return any(
        not argument.startswith("-")
        and _ASSIGNMENT.match(argument) is None
        and argument in aggregate
        for argument in arguments
    )


def runs_aggregate_target(
    *, lines: list[str], job_start: int, job_end: int, aggregate: set[str]
) -> bool:
    """Whether this job runs any declared aggregate target in a step run value."""
    return any(
        _command_runs_aggregate(command=command, aggregate=aggregate)
        for command in _run_commands(lines=lines[job_start:job_end])
    )
