#!/usr/bin/env python3
"""
Where a command's stdin comes from, and what it hands to another interpreter.

The classifier in `_host_mutation` judges shell TEXT, and some of that text
reaches a command by a side channel rather than as its operands. This module
owns those channels so the classifier can read them as the commands they are:

  - **Stdin a command reads.** A here-doc body (`ssh host bash -s <<'EOF'`), a
    here-string (`bash <<< "…"`), or the text a DATA producer piped in
    (`echo 'put x /etc/y' | sftp host`, `cat <<'EOF' | ssh host bash -s`).
    `produced_text` says what a segment writes to stdout when that is
    readable — `echo`/`printf` operands, or the stdin a `tee` or an
    operand-less `cat` passes through — and `stdin_text` assembles what the
    next segment reads. `cat file | bash` produces text the guard cannot read.
  - **Payloads handed to an interpreter.** `sh -c '<script>'`, `script -c`,
    `su -c`, a shell fed by stdin, `eval <words>`, `watch '<cmd>'`, and tmux
    `new-session '<cmd>'` / `send-keys '<cmd>'` — each is a command line in
    its own right, returned by `payload_of` for re-classification.
  - **Stdin redirections stripped** before a remote command is re-read
    (`without_stdin_redirects`), so `ssh host <<EOF` does not re-open a
    here-doc inside the payload.

Self-contained by contract: the plugin installer ships this file under bare
system `python3` with no virtualenv and no third-party packages, so every
import here is the standard library or a sibling module shipped beside it.
"""

from __future__ import annotations

from _shell_lex import SHELLS, basename, first_command_index, operands, shell_payload

__all__: list[str] = [
    "DATA_HEADS",
    "PAYLOAD_HEADS",
    "SCRIPT_HEADS",
    "payload_of",
    "produced_text",
    "stdin_text",
    "without_stdin_redirects",
]

# Heads that hand a script to another interpreter: a shell (`-c`, a here-string,
# a pipe), `script -c`, `su -c`; and heads whose OPERANDS are a command line —
# `eval`, `watch`, and tmux `new-session '…'` / `send-keys '…'`.
SCRIPT_HEADS = SHELLS | {"script", "su"}
PAYLOAD_HEADS = frozenset({"eval", "watch", "tmux"})
# Heads whose operands are printed, never run — data even when unquoted.
DATA_HEADS = frozenset({"echo", "printf"})


def without_stdin_redirects(*, tokens: list[str]) -> list[str]:
    """Drop `<<EOF`, `<<< word`, and `< file` so a re-scanned command does not re-read them."""
    kept: list[str] = []
    skip = False
    for token in tokens:
        if skip:
            skip = False
            continue
        if token.startswith("<<") or token == "<":
            skip = token == "<<<" or token == "<"
            continue
        kept.append(token)
    return kept


def produced_text(*, tokens: list[str], stdin: str | None) -> str | None:
    """What a segment writes to stdout for a pipe into the next one, when readable.

    `echo`/`printf` write their operands; `tee [files]` and a `cat` with no
    file operand pass their readable stdin through (`cat <<'EOF' | tee /tmp/x
    | ssh host bash -s`). Anything else (`cat file`, `curl …`) produces text
    the guard cannot read.
    """
    start = first_command_index(tokens=tokens)
    if start is None:
        return None
    head = basename(token=tokens[start]).lower()
    arguments = without_stdin_redirects(tokens=tokens[start + 1 :])
    if head in DATA_HEADS:
        return " ".join(operands(arguments=arguments)).replace("\\n", "\n")
    if head == "tee" or (
        head == "cat" and not [o for o in operands(arguments=arguments) if o != "-"]
    ):
        return stdin
    return None


def stdin_text(*, tokens: list[str], bodies: list[str], piped: str | None) -> str | None:
    """The readable stdin of a segment: its here-doc bodies, a here-string, a data pipe."""
    parts = list(bodies)
    if "<<<" in tokens:
        index = tokens.index("<<<")
        parts.extend(tokens[index + 1 : index + 2])
    if piped is not None:
        parts.append(piped)
    return "\n".join(parts) if parts else None


def payload_of(*, head: str, arguments: list[str], stdin: str | None) -> str | None:
    """The script a SCRIPT or PAYLOAD head hands to another interpreter, when visible."""
    if head in SCRIPT_HEADS:
        return shell_payload(arguments=arguments) or stdin
    if head == "eval":
        return " ".join(arguments) or None
    if head == "watch":
        return " ".join(operands(arguments=arguments)) or None
    return "\n".join(a for a in operands(arguments=arguments) if " " in a) or None
