"""The POSIX-sh compatibility lexicon the justfile-recipe policy reads.

`_shell_quality_recipes` decides which recipes violate policy; this module
answers the one policy-neutral question that decision needs and nothing else —
**does this line use syntax that only Bash understands?** The seam is real: the
lexicon is a property of the shells, not of the fleet's recipe conventions, so
it belongs beside the policy rather than inside it.

WHY THE QUESTION MATTERS. A justfile that declares no `set shell` gets `just`'s
default `sh`, which on Ubuntu is dash. A Bash-only construct in a NON-shebang
recipe body is therefore a parse-time abort on EVERY invocation — the recipe
never runs at all, and nothing surfaces that. `livespec-f3tf` (fixed 2026-08-06,
`livespec` PR #2085) was exactly this: `reap-stale-worktrees` passed `${@:2}`, a
Bash array slice, and died with `Bad substitution` for the whole life of the
recipe while master CI stayed green, because the recipe-SHAPE rules the
shell-quality check enforced said nothing about whether the conforming line
could actually RUN.

TWO EXEMPTIONS, both owned by the caller because both are file- or
recipe-scoped rather than line-scoped: a recipe whose body opens with `#!`
picks its own interpreter, and a justfile whose `set shell` names a
Bash-compatible interpreter is not running dash at all.

THE PATTERNS DISCRIMINATE, they do not merely grep. Every entry below has a
POSIX near-neighbour that MUST NOT match, and each is the reason its pattern is
shaped the way it is rather than as the obvious substring:

- `array-slice` — `${v:2}` is a Bash slice, but `${v:-d}`, `${v:=d}`, `${v:?d}`
  and `${v:+d}` are POSIX parameter expansions. The offset is therefore matched
  only as a digit, or as a `-`-signed digit that Bash itself requires be
  separated by a space or wrapped in parens.
- `pattern-substitution` — `${v//a/b}` is Bash, but `${p#*/}`, `${p%/*}` and
  `${p##*/}` are POSIX prefix/suffix removals that also carry a `/` inside the
  braces. The `/` is matched only where it directly follows the PARAMETER, so a
  removal operator between the two blocks the match.
- `case-conversion` — `${v^^}` and `${v,,}` are matched only as the whole
  operator immediately before the closing brace, so a `,` inside an ordinary
  default value cannot fire it.

The remaining five (`[[`, `<<<`, `$'…'`, `v=(`, `function`) have no POSIX
spelling to confuse them with. All eight key on the CONSTRUCT and never on a
repo's own spelling of a command.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

__all__: list[str] = [
    "bash_only_constructs",
    "shell_is_bash_compatible",
]

_PARAMETER = r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?"
_EXPANSION_HEAD = rf"(?:[#!]?(?:{_PARAMETER}|[@*0-9]))"

_BASH_ONLY_CONSTRUCTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("array-slice", re.compile(r"\$\{[^{}]*:(?:\s*\d|\s+-\s*\d|\s*\(\s*-)")),
    ("double-bracket-test", re.compile(r"\[\[")),
    ("here-string", re.compile(r"<<<")),
    ("ansi-c-quoting", re.compile(r"\$'")),
    ("pattern-substitution", re.compile(rf"\$\{{{_EXPANSION_HEAD}/")),
    ("case-conversion", re.compile(rf"\$\{{{_PARAMETER}(?:\^\^?|,,?)\}}")),
    ("array-assignment", re.compile(r"(?:^|[\s;&|(])[A-Za-z_][A-Za-z0-9_]*=\(")),
    ("function-keyword", re.compile(r"(?:^|[\s;&|])function\s+[A-Za-z_]")),
)

_BASH_COMPATIBLE_SHELLS = frozenset({"bash", "ksh", "ksh93", "mksh", "pdksh", "zsh"})


def bash_only_constructs(*, line: str) -> tuple[str, ...]:
    """Name every Bash-only construct in `line`, in lexicon order.

    An empty tuple means the line carries none of them — an ABSENCE, not a
    failure, so it rides a plain return rather than a Result rail.
    """
    return tuple(
        name for name, pattern in _BASH_ONLY_CONSTRUCTS if pattern.search(line) is not None
    )


def shell_is_bash_compatible(*, command: str) -> bool:
    """Does a `set shell` command name an interpreter that understands the lexicon?

    Matched on the basename so an absolute path (`/usr/bin/env` aside) and a
    bare name resolve alike. Anything unrecognised is treated as POSIX sh: the
    conservative direction is to KEEP checking, because the cost of a false
    finding is a visible one, while the cost of a wrongly-granted exemption is
    the silent recipe death this lexicon exists to prevent.
    """
    return PurePosixPath(command).name in _BASH_COMPATIBLE_SHELLS
