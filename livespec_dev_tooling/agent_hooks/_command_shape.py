"""_command_shape — read a Bash command's invocations off TOKEN POSITION.

Extracted from `pretooluse_background_guard.py` per work-item
livespec-dev-tooling-zlhnib: that module's classification of a command is
now read by TWO guards — the background-gate refusal it already carried,
and the foreground hook-running-git refusal that work-item adds — and a
private tokenizer cannot cross a module boundary. The paragraph below is
the guard's own rationale for this concern, relocated with the code it
describes.

COMMAND-TOKEN POSITION, NOT SUBSTRING (livespec-dev-tooling-k169).
A command is a gate only where the shell would actually run one:
the recipe word a `just` invocation names, or the subcommand a
`git`/`gh` invocation names. The shapes used to be regexes over the
whole command text — `just check` meant "the word `check` anywhere
after the word `just`" — which matched ARGUMENTS as readily as
commands. A sanctioned `just gate-wait "$(cat .../run-checks.id)"`
was therefore denied for the `checks` in its run-id scratch path,
and a poll loop was denied for the words `just check` inside an
`echo` string that ran no gate at all; each denial then prescribed
the detached runner to a caller already using it, which leaves no
move but engineering AROUND the guard. Classification instead
tokenizes the command, cuts it at shell separators, skips the
transparent prefixes a command word hides behind (`mise exec --`,
`nohup`, `NAME=value`, a control word such as `until`), and reads
the command word and its subcommand from POSITION. A shell runner's
script argument (`bash -c '<text>'`) is itself command text and is
classified recursively, so quoting cannot launder a bare gate —
while an `echo` argument stays an argument, which is exactly what
makes the string case allowed.

THE SHELL-RUNNER RECURSION MOVED IN HERE WITH THE PARSE, and it is a
FLATTENING rather than a per-caller recursion. `_matched_gate` used to
recurse itself, which was sound for one caller and is a trap for two: a
second classifier that forgot the arm would read `bash -c 'git commit'`
as an invocation of `bash` and let the laundered command through. The
runner's script argument is replaced, in place and in order, by the
invocations of the text it carries, so every caller inherits the
property and none can opt out of it. Termination is structural: the
script argument is a TOKEN of its own input, so the recursion is over
strictly shorter text and a single-token command has no argument to
recurse into at all.

THE SPLIT AT THE SUBCOMMAND IS LOAD-BEARING, and reading `-C` without
it is a measured hazard rather than a stylistic one. `-C` is a GLOBAL
git option naming the directory to run in, and it is ALSO `git commit`'s
own `--reuse-message` short form. A scan of the whole argument list for
`-C <value>` therefore reads `git commit -C HEAD~1` as targeting a
repository called `HEAD~1`, and the foreground guard's hook probe would
look for installed hooks somewhere that does not exist. `Invocation`
keeps the global options and the post-subcommand arguments APART so
neither consumer can confuse one for the other.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

__all__: list[str] = [
    "Invocation",
    "invocations",
]

# Shell punctuation that ENDS a command segment: the next command word
# begins after it. This is what keeps `git log && echo push` from reading
# as `git push` (the retired filler class excluded the same characters).
_SEPARATOR: re.Pattern[str] = re.compile(r"^[;&|()<>]+$")

# Fallback tokenizer for command text `shlex` cannot lex — an apostrophe
# in an unquoted word, say. It reproduces the word/separator split above;
# quotes stay glued to their word, which can only make a token FAIL to
# look like a command word, never invent a command position.
_FALLBACK_TOKENS: re.Pattern[str] = re.compile(r"[;&|()<>]+|[^\s;&|()<>]+")

# Tokens that may stand between a segment boundary and the command word:
# shell control words, the `--` an argument-forwarding wrapper puts ahead
# of the command it runs, and the launcher wrappers whose tail IS the real
# command (`mise exec -- git commit`, `nohup just check`).
_TRANSPARENT_PREFIXES: frozenset[str] = frozenset(
    {
        "!",
        "--",
        "command",
        "do",
        "elif",
        "else",
        "env",
        "exec",
        "if",
        "mise",
        "nohup",
        "setsid",
        "sudo",
        "then",
        "time",
        "until",
        "while",
    }
)

# Runners whose first non-option argument is COMMAND TEXT rather than an
# opaque argument, so `bash -c 'just check'` cannot launder a bare gate.
_SHELL_RUNNERS: frozenset[str] = frozenset({"bash", "dash", "sh", "zsh"})

# `NAME=value` — an environment prefix ahead of the command word, and
# equally a `just` argument assignment standing before the recipe word
# (`just skip="check-coverage" check`).
_ASSIGNMENT: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*=")

# Global options that consume the NEXT token as their value, so that token
# is not the subcommand (`git -C <path> push`).
_VALUE_OPTIONS: dict[str, frozenset[str]] = {
    "git": frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}),
    "gh": frozenset({"-R", "--repo"}),
    "just": frozenset({"-f", "--justfile", "-d", "--working-directory", "--chdir", "--shell"}),
}


@dataclass(frozen=True, kw_only=True)
class Invocation:
    """One command the shell would actually run, read off token position.

    `options` are the tokens standing BEFORE the subcommand and `args`
    those standing after it, kept apart for the reason this module's
    docstring records: `-C` means two different things on the two sides of
    that boundary.

    `subcommand` is `None` when the invocation names no subcommand at all
    (`git` alone, `ls -la`) — an absence every consumer reads as "this
    invocation is not one of the shapes I am looking for".
    """

    binary: str
    options: tuple[str, ...]
    subcommand: str | None
    args: tuple[str, ...]


def invocations(*, command: str) -> list[Invocation]:
    """Every command `command` would run, shell-runner scripts flattened.

    In command order, so a consumer that stops at its first match stops at
    the earliest one the shell would reach.
    """
    found: list[Invocation] = []
    for segment in _segments(tokens=_tokenize(command=command)):
        head = _command_word(segment=segment)
        if head is None:
            continue
        binary, tail = head
        options, subcommand, args = _split(binary=binary, tail=tail)
        if binary in _SHELL_RUNNERS and subcommand is not None:
            found.extend(invocations(command=subcommand))
            continue
        found.append(Invocation(binary=binary, options=options, subcommand=subcommand, args=args))
    return found


def _tokenize(*, command: str) -> list[str]:
    """Split `command` into shell words, keeping separator punctuation.

    Quoting is resolved here, which is what demotes the words inside an
    `echo` string to a single argument token: they can no longer occupy a
    command position. Text `shlex` refuses degrades to the coarse
    fallback rather than raising into the hook's fail-open boundary,
    which would ALLOW the bare backgrounded gate this hook exists to deny.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return _FALLBACK_TOKENS.findall(command)


def _segments(*, tokens: list[str]) -> list[list[str]]:
    """Cut the token list into command segments at shell separators."""
    segments: list[list[str]] = [[]]
    for token in tokens:
        if _SEPARATOR.match(token):
            segments.append([])
        else:
            segments[-1].append(token)
    return segments


def _command_word(*, segment: list[str]) -> tuple[str, list[str]] | None:
    """Return the segment's command word and its tail, or None.

    Transparent prefixes are skipped so the wrapper forms this guard has
    always tolerated still resolve to the command they run
    (`mise exec -- git commit` → `git`, `until gh pr checks` → `gh`), and
    the word is taken by basename so `/usr/bin/git push` is not a way out.
    """
    for index, token in enumerate(segment):
        word = token.rsplit("/", maxsplit=1)[-1]
        if word in _TRANSPARENT_PREFIXES or _ASSIGNMENT.match(token):
            continue
        return word, segment[index + 1 :]
    return None


def _split(*, binary: str, tail: list[str]) -> tuple[tuple[str, ...], str | None, tuple[str, ...]]:
    """Cut `binary`'s tail at the token occupying its subcommand position."""
    value_options = _VALUE_OPTIONS.get(binary, frozenset())
    skip_next = False
    for index, token in enumerate(tail):
        if skip_next:
            skip_next = False
        elif token in value_options:
            skip_next = True
        elif not token.startswith("-") and _ASSIGNMENT.match(token) is None:
            return tuple(tail[:index]), token, tuple(tail[index + 1 :])
    return tuple(tail), None, ()
