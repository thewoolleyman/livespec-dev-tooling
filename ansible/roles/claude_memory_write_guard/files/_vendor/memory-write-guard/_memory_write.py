#!/usr/bin/env python3
"""
Does a Bash command POSITIVELY write a file into an agent memory directory?

The auto-memory redirect (`block_auto_memory.py`) refuses memory writes on
every route, and the shell is the route a file-tool matcher cannot see: on
2026-10-18 a governed session wrote two notes with `cat >>` and `sed`
unrefused (work-item livespec-driver-claude-cb2mzo). livespec core
`SPECIFICATION/contracts.md` (v225) names the memory directories — the Claude
Code layout `~/.claude/projects/<slug>/memory/` and the Codex store
`~/.codex/memories/` — and a NON-EXHAUSTIVE minimum of write forms, judged per
`;` / `&&` / `||` / pipeline segment and through `sh -c` / `bash -c` / `env`
wrappers:

  - output redirection (`>`, `>>`, a here-document redirected into the path);
  - `tee`, `sed -i`, `perl -i`;
  - `cp`, `mv`, `install`, `ln` whose DESTINATION is there, and `touch`,
    `truncate`, `dd of=` on a path there;
  - an inline interpreter program (`python3 -c`, `perl -e`, `node -e`, or the
    same interpreter fed a here-document) whose write target names such a
    path.

Reads (`cat`, `grep`, `ls`, `head`, `find`) and `rm` match no rule, so they
pass: removal is how a migrated note is discharged. A destination computed at
runtime (a variable, a script file) is a STATED LIMIT: the answer is True only
on a positive identification, and anything unlexable or nested past the depth
budget reads as "not identified".

The cheap `memor` substring pre-filter runs first, because this classifier
now sees EVERY Bash call.

Self-contained by contract: the plugin installer ships this file under bare
system `python3` with no virtualenv and no third-party packages, so every
import here is the standard library or a sibling module shipped beside it.
"""

from __future__ import annotations

import re

from _shell_io import SCRIPT_HEADS, payload_of, stdin_text, without_stdin_redirects
from _shell_lex import (
    SHELL_KEYWORDS_PASS,
    basename,
    first_command_index,
    heredoc_count,
    operands,
    split_heredocs,
    split_segments_with_separators,
    substitutions,
    tokens_or_none,
    without_continuations,
)

__all__: list[str] = ["names_memory_dir", "writes_memory"]

_MAX_DEPTH = 4
_PREFILTER = "memor"
_MEMORY_DIR = re.compile(
    r"(?:\.claude|\$\{?CLAUDE_CONFIG_DIR\}?)/projects/[^/\s'\"]+/memory(?:/|$|(?=[\s'\")]))"
    r"|(?:\.codex|\$\{?CODEX_HOME\}?)/memories(?:/|$|(?=[\s'\")]))"
)
_REDIRECT_OPERATOR = re.compile(r"^(?:\d*|&)>{1,2}\|?$")
_WRITE_TARGETS = (
    re.compile(
        r"open\s*\(\s*(?P<destination>[^,\n]+)\s*,\s*"
        r"(?:(?:mode\s*=\s*)?['\"](?:[wax]|r\+)[bt+]*['\"])"
    ),
    re.compile(
        r"(?:pathlib\.)?Path\s*\(\s*(?P<destination>[^)\n]+)\s*\)" r"\s*\.write_(?:text|bytes)\s*\("
    ),
    re.compile(r"(?:writeFile|appendFile)(?:Sync)?\s*\(\s*(?P<destination>[^,\n]+)"),
    re.compile(r"createWriteStream\s*\(\s*(?P<destination>[^,\n]+)"),
    # Perl three-argument open; the parentheses are optional (`open FH, ">", $path or die`).
    re.compile(
        r"open\s*\(?\s*(?:my\s+)?[\w$]+\s*,\s*['\"]\s*\+?>+[^'\"]*['\"]"
        r"\s*,\s*(?P<destination>[^)\n;]+?)\s*(?:\)|;|\n|$|\bor\b|\|\|)"
    ),
    re.compile(r"open\s*\(?\s*(?:my\s+)?[\w$]+\s*,\s*['\"]\s*\+?>+?(?P<destination>[^'\"]+)['\"]"),
)
_MEMORY_ASSIGNMENT = re.compile(
    r"(?m)(?:^|;)\s*(?:my\s+)?(?P<name>\$?[A-Za-z_]\w*)\s*=\s*['\"](?P<destination>[^'\"]+)['\"]"
)
_IN_PLACE_FLAG = re.compile(r"^(?:-[A-Za-z]*i|--in-place)")
_PYTHON = re.compile(r"^python[0-9.]*$")
_PROGRAM_FLAGS = {
    "python": re.compile(r"^-[A-Za-z]*c$"),
    "perl": re.compile(r"^-[A-Za-z]*[eE]$"),
    "node": re.compile(r"^(?:-e|--eval|-p|--print)$"),
}
_PASS_THROUGH_WRAPPERS = frozenset({"nohup", "command", "exec", "builtin", "time"})
# Wrappers whose options may take a value word, so the value is not the command.
_OPTION_WRAPPERS = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}),
}
_STDERR_OR_FD = re.compile(r"^(?:\d*|&)>")
_DESTINATION_HEADS = frozenset({"cp", "mv", "install", "ln"})
_ANY_OPERAND_HEADS = frozenset({"tee", "touch", "truncate"})


def names_memory_dir(*, text: str) -> bool:
    """True when the text names a Claude Code memory directory or the Codex store."""
    return _MEMORY_DIR.search(text) is not None


def _literal_relative_destination(*, text: str) -> bool:
    """Whether `text` is a lexical relative file destination, not a computed path."""
    return bool(text) and not text.startswith(("/", "~", "$", "-")) and text not in (".", "..")


def _writes_to_memory(*, destination: str, cwd_is_memory: bool) -> bool:
    """Whether a destination names memory directly or is relative to a literal memory cwd."""
    return names_memory_dir(text=destination) or (
        cwd_is_memory and _literal_relative_destination(text=destination)
    )


def _redirects_into_memory(*, tokens: list[str], cwd_is_memory: bool) -> bool:
    """An output redirection (`>`, `>>`, `2>`, `&>`, fused `x>path`) whose target is there."""
    for index, token in enumerate(tokens):
        if ">" not in token or any(char.isspace() for char in token):
            continue
        target = token.rsplit(">", 1)[1].lstrip("|")
        if not target and _REDIRECT_OPERATOR.match(token) and index + 1 < len(tokens):
            target = tokens[index + 1]
        if _writes_to_memory(destination=target, cwd_is_memory=cwd_is_memory):
            return True
    return False


def _destination(*, arguments: list[str]) -> str:
    """Where a `cp` / `mv` / `install` / `ln` lands: `-t DIR`, else its last operand."""
    for index, argument in enumerate(arguments):
        if argument in ("-t", "--target-directory") and index + 1 < len(arguments):
            return arguments[index + 1]
        if argument.startswith(("--target-directory=", "-t")) and argument != "-t":
            return argument.split("=", 1)[-1] if "=" in argument else argument[2:]
    found = operands(arguments=arguments)
    return found[-1] if found else ""


def _program(*, head: str, arguments: list[str], stdin: str | None) -> str | None:
    """The inline program an interpreter runs: its `-c` / `-e` text, else a fed here-document."""
    flag = _PROGRAM_FLAGS.get("python" if _PYTHON.match(head) else head)
    if flag is None:
        return None
    arguments = without_stdin_redirects(tokens=arguments)
    for index, argument in enumerate(arguments):
        if flag.match(argument):
            return arguments[index + 1] if index + 1 < len(arguments) else None
    return stdin if not operands(arguments=arguments) else None


def _program_writes_memory(*, program: str) -> bool:
    """Whether an inline interpreter's identified write target is an agent-memory path."""
    memory_variables = {
        match["name"]
        for match in _MEMORY_ASSIGNMENT.finditer(program)
        if names_memory_dir(text=match["destination"])
    }
    return any(
        names_memory_dir(text=match["destination"])
        or match["destination"].strip() in memory_variables
        for pattern in _WRITE_TARGETS
        for match in pattern.finditer(program)
    )


def _head_writes(
    *, head: str, arguments: list[str], stdin: str | None, cwd_is_memory: bool
) -> bool:
    """Whether this command head, with these arguments, writes into a memory directory."""
    if head in _DESTINATION_HEADS:
        return _writes_to_memory(
            destination=_destination(arguments=arguments), cwd_is_memory=cwd_is_memory
        )
    if head in _ANY_OPERAND_HEADS:
        return any(
            _writes_to_memory(destination=operand, cwd_is_memory=cwd_is_memory)
            for operand in operands(arguments=arguments)
        )
    if head == "dd":
        return any(
            argument.startswith("of=")
            and _writes_to_memory(destination=argument[3:], cwd_is_memory=cwd_is_memory)
            for argument in arguments
        )
    if head in ("sed", "perl") and any(_IN_PLACE_FLAG.match(a) for a in arguments):
        found = operands(arguments=arguments)
        return bool(found) and _writes_to_memory(destination=found[-1], cwd_is_memory=cwd_is_memory)
    program = _program(head=head, arguments=arguments, stdin=stdin)
    return program is not None and _program_writes_memory(program=program)


def _unwrapped(*, tokens: list[str]) -> list[str]:
    """The command words past leading assignments, keywords and `env` / `nohup` wrappers."""
    rest = tokens
    while rest:
        start = first_command_index(tokens=rest)
        if start is None:
            return []
        rest = rest[start:]
        head = basename(token=rest[0]).lower()
        if head in SHELL_KEYWORDS_PASS or head in _PASS_THROUGH_WRAPPERS:
            rest = rest[1:]
        elif head in _OPTION_WRAPPERS:
            rest = _past_options(arguments=rest[1:], value_flags=_OPTION_WRAPPERS[head])
        else:
            return rest
    return []


def _past_options(*, arguments: list[str], value_flags: frozenset[str]) -> list[str]:
    index = 0
    while index < len(arguments) and arguments[index].startswith("-"):
        index += 2 if arguments[index] in value_flags else 1
    return arguments[index:]


def _without_redirects(*, tokens: list[str]) -> list[str]:
    """Drop output redirections (`2>/dev/null`, `> log`) so they never read as operands."""
    kept: list[str] = []
    skip = False
    for token in tokens:
        if skip:
            skip = False
        elif _REDIRECT_OPERATOR.match(token):
            skip = True
        elif not _STDERR_OR_FD.match(token):
            kept.append(token)
    return kept


def _segment_writes(
    *, tokens: list[str], stdin: str | None, depth: int, cwd_is_memory: bool
) -> bool:
    if _redirects_into_memory(tokens=tokens, cwd_is_memory=cwd_is_memory):
        return True
    words = _unwrapped(tokens=_without_redirects(tokens=tokens))
    if not words:
        return False
    head = basename(token=words[0]).lower()
    arguments = words[1:]
    if head in SCRIPT_HEADS or head == "eval":
        payload = payload_of(head=head, arguments=arguments, stdin=stdin)
        return payload is not None and _writes(text=payload, depth=depth + 1)
    return _head_writes(
        head=head,
        arguments=arguments,
        stdin=stdin,
        cwd_is_memory=cwd_is_memory,
    )


def _directory_change(*, tokens: list[str]) -> bool | None:
    """The literal cwd after a direct `cd` or `pushd`, or None when it is unchanged."""
    words = _unwrapped(tokens=_without_redirects(tokens=tokens))
    if not words:
        return None
    head = basename(token=words[0]).lower()
    if head == "popd":
        return False
    if head not in ("cd", "pushd"):
        return None
    found = operands(arguments=words[1:])
    return bool(found) and names_memory_dir(text=found[-1])


def _writes(*, text: str, depth: int) -> bool:
    if depth > _MAX_DEPTH:
        return False
    stripped, bodies = split_heredocs(command=text)
    cursor = 0
    segments = split_segments_with_separators(command=without_continuations(command=stripped))
    cwd_is_memory = False
    for index, (separator, seg) in enumerate(segments):
        if any(_writes(text=inner, depth=depth + 1) for inner in substitutions(text=seg)):
            return True
        tokens = tokens_or_none(seg=seg)
        if tokens is None:
            continue
        own = bodies[cursor : cursor + heredoc_count(tokens=tokens)]
        cursor += len(own)
        stdin = stdin_text(tokens=tokens, bodies=own, piped=None)
        if _segment_writes(
            tokens=tokens,
            stdin=stdin,
            depth=depth,
            cwd_is_memory=cwd_is_memory,
        ):
            return True
        next_separator = segments[index + 1][0] if index + 1 < len(segments) else ""
        if separator not in ("|", "&") and next_separator not in ("|", "&"):
            changed = _directory_change(tokens=tokens)
            if changed is not None:
                cwd_is_memory = changed
    return False


def writes_memory(*, command: str) -> bool:
    """True only when the command POSITIVELY writes into an agent memory directory."""
    if _PREFILTER not in command:
        return False
    return _writes(text=command, depth=0)
