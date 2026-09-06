"""worktree_pack_wiring — the wiring predicate the `worktree-pack-wired` row asks.

The PURE half of the central `worktree-pack-wired` obligation: given the four
committed file texts, which wiring lines are missing. The half that READS a
member's committed master to obtain those texts — a vantage, a credential, a
tree that may be truncated or unreadable — is `_rows_worktree_pack.py`, and
the split is what lets a sibling repo import this one over its own bytes.

THE GAP THIS CLOSES. The worktree-discipline pack is asserted today only by
the repo-LOCAL verifier (the `primary_checkout_commit_refuse_hook_installed`
pack arm) and the repo-LOCAL `worktree-pack` bootstrap row, and both assert
the pack's BYTES in a checkout that already runs them. A member whose root
justfile never `import?`s the fragments, whose `lefthook.yml` never installs
the pack before the gate, or whose `.livespec.jsonc` never declares the
policy, is a member that never fails a check it does not run — the exact hole
livespec v108 section "Fleet membership contract" names as the central
vantage's reason to exist. This row asserts the WIRING from the central
vantage, over every member's committed master, so an unwired repo is a fleet
finding rather than an invisible one.

THE FIVE FACTS, and which committed file carries each:

1. `justfile` — both `import? 'dev-tooling/<fragment>.just'` lines, without
   which a byte-perfect pack is invisible to `just --list`;
2. `justfile` — an `install-worktree-pack:` recipe delegating to this
   package's installer module, which is what materializes the pack at all;
3. `.gitignore` — a root ignore entry per installed pack file;
4. `lefthook.yml` — `just install-worktree-pack` as the FIRST command of BOTH
   `pre-commit` and `pre-push`, so a worktree created by a raw
   `git worktree add` installs the pack before any gate reads it;
5. `.livespec.jsonc` — a `worktree_discipline` declaration, so the pack policy
   is a decision the repo STATED rather than the verifier's silent default.

ONE ENUMERATION, DERIVED — not a fourth hand-written copy. The import lines
and the ignore entries are computed from `WORKTREE_PACK_FILES`, the
installer's single enumeration of the pack's shape (livespec-dev-tooling-l5gypl
landed that constant precisely because three hand-written copies of the file
SET had drifted apart). Adding a `.just` fragment to the pack therefore adds
its `import?` obligation here automatically, and adding any pack file adds its
ignore-entry obligation, with no edit to this module.

SEVERITY IS SPLIT, AND THE SPLIT IS A JUDGEMENT ABOUT CONSEQUENCE. Facts 1,
2, 4 and 5 are error-severity: each one missing BREAKS the mechanism — the
fragments are unreachable, the pack is never installed, the gate reads a stale
or absent pack, or the policy is never stated. Fact 3 is WARNING-severity,
because since `l5gypl` the installer also writes a generated
`dev-tooling/.gitignore` that ignores every pack file in place: a missing root
entry is real drift from the fleet convention and worth reporting, but the
file it names is still ignored, so it is not an untracked-file risk and must
not red the fleet. Measured 2026-09-06 across all ten manifest members, that
is not a hypothetical distinction: the four error legs have an offender count
of ZERO (so the row is armed at birth, per the standing constraint
`plan/rop-railway-enforcement/` records — measure BEFORE arming), and the
ignore leg has exactly one, `livespec-runtime`, whose root `.gitignore` lists
five of the six pack files and omits `/dev-tooling/gate-run.sh`.

THE PREDICATE IS PUBLIC ON PURPOSE. `worktree_pack_wiring_gaps` is a pure
function over the four file TEXTS, with no `FleetContext` and no network, so
a sibling repo's test can import it and run it over bytes this repo never
sees — specifically livespec's copier-template lockstep test, which renders
the template and asserts the rendered shape has zero gaps. That is why this
module is public (no leading underscore) while its sibling row modules are
not: a `_rows_*` module is importable only from inside this package.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling.install_worktree_pack import WORKTREE_PACK_FILES

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "GITIGNORE_PATH",
    "JUSTFILE_PATH",
    "LEFTHOOK_PATH",
    "LIVESPEC_JSONC_PATH",
    "WIRING_FILES",
    "WiringGap",
    "worktree_pack_wiring_gaps",
]


JUSTFILE_PATH = "justfile"
GITIGNORE_PATH = ".gitignore"
LEFTHOOK_PATH = "lefthook.yml"
LIVESPEC_JSONC_PATH = ".livespec.jsonc"

# The four committed files the wiring lives in, in the order the row reads
# them. Public so a sibling's lockstep test renders exactly this set rather
# than re-deriving which files it must supply.
WIRING_FILES: tuple[str, ...] = (
    JUSTFILE_PATH,
    GITIGNORE_PATH,
    LEFTHOOK_PATH,
    LIVESPEC_JSONC_PATH,
)

_INSTALL_RECIPE_HEADER = "install-worktree-pack:"
_INSTALL_RECIPE_DELEGATION = "python -m livespec_dev_tooling.install_worktree_pack"
_INSTALL_HOOK_COMMAND = "just install-worktree-pack"
# The two hooks that MUST install the pack before anything reads it. Both, not
# either: a pre-commit-only wiring leaves `git push` gating against whatever
# pack the worktree happened to have.
_GATED_HOOKS = ("pre-commit", "pre-push")
_WORKTREE_DISCIPLINE_KEY = "worktree_discipline"
_WORKTREE_DISCIPLINE_LINE = '"worktree_discipline": { "pack": "required" }'

# DERIVED from the installer's one enumeration, never re-listed. A `.just`
# fragment is `import?`ed by the consumer root justfile (it is never executed),
# so the pack's `.just` members are exactly the set of required import lines.
_IMPORT_LINES: tuple[str, ...] = tuple(
    f"import? 'dev-tooling/{pack_file.name}'"
    for pack_file in WORKTREE_PACK_FILES
    if pack_file.name.endswith(".just")
)
# Likewise for the root ignore entries — every installed pack file EXCEPT the
# pack's own generated `dev-tooling/.gitignore`, which ignores itself in place
# and is therefore never named by the consumer's root ignore file.
_GITIGNORE_ENTRIES: tuple[str, ...] = tuple(
    f"/dev-tooling/{pack_file.name}"
    for pack_file in WORKTREE_PACK_FILES
    if pack_file.name != GITIGNORE_PATH
)


@dataclass(frozen=True, kw_only=True)
class WiringGap:
    """One wiring line a member's committed file does not carry.

    `missing` is the EXACT line an operator adds to `path` — not a
    description of the class of thing that is absent. That is what lets
    `wire_fleet_member` surface a hint naming the lines rather than a
    restatement of the obligation, and what lets a sibling's lockstep test
    print something actionable when a rendered template drifts.
    """

    path: str
    missing: str
    severity: str = "error"


def _recipe_body(*, text: str, header: str) -> tuple[str, ...] | None:
    """A justfile recipe's body lines (stripped), or None when it has no header.

    A recipe body is the indented run of lines following the header, so the
    scan ends at the first non-indented non-blank line — the next recipe,
    import, or assignment.
    """
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line == header), None)
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith((" ", "\t")):
            break
        body.append(line.strip())
    return tuple(body)


def _justfile_gaps(*, text: str) -> tuple[WiringGap, ...]:
    """Facts 1 and 2 — the two `import?` lines and the installer recipe.

    The import lines are matched as WHOLE LINES rather than as substrings, so
    a justfile that merely MENTIONS `dev-tooling/worktree.just` in a comment
    (several fleet members do, right above the real import) never satisfies
    the obligation by talking about it.
    """
    lines = frozenset(text.splitlines())
    gaps = [
        WiringGap(path=JUSTFILE_PATH, missing=import_line)
        for import_line in _IMPORT_LINES
        if import_line not in lines
    ]
    body = _recipe_body(text=text, header=_INSTALL_RECIPE_HEADER)
    delegates = body is not None and any(
        _INSTALL_RECIPE_DELEGATION in line for line in body if not line.startswith("#")
    )
    if not delegates:
        gaps.append(
            WiringGap(
                path=JUSTFILE_PATH,
                missing=(
                    f"an `{_INSTALL_RECIPE_HEADER}` recipe delegating to "
                    f"`uv run {_INSTALL_RECIPE_DELEGATION}`"
                ),
            )
        )
    return tuple(gaps)


def _gitignore_gaps(*, text: str) -> tuple[WiringGap, ...]:
    """Fact 3 — a root ignore entry per installed pack file (warning severity).

    Both the anchored spelling (`/dev-tooling/<name>`, what every fleet member
    uses) and the unanchored one (`dev-tooling/<name>`) satisfy the entry:
    they ignore the same path from a repo-root `.gitignore`, and reporting a
    working ignore rule as missing would be a finding about style.
    """
    entries = {line.strip() for line in text.splitlines()}
    return tuple(
        WiringGap(path=GITIGNORE_PATH, missing=entry, severity="warning")
        for entry in _GITIGNORE_ENTRIES
        if entry not in entries and entry.removeprefix("/") not in entries
    )


def _hook_block(*, text: str, hook: str) -> tuple[str, ...]:
    """The indented lines under a top-level `<hook>:` key; empty when absent."""
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.rstrip() == f"{hook}:"), None)
    if start is None:
        return ()
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith((" ", "\t")):
            break
        block.append(line)
    return tuple(block)


def _run_value(*, inline: str, rest: tuple[str, ...]) -> str:
    """A `run:` value: the inline text, or a block scalar's first line."""
    if inline.startswith(("|", ">")):
        return rest[0].strip() if rest else ""
    return inline


def _hook_commands(*, block: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Each `(name, run-value)` pair under the hook block's `commands:` key.

    A deliberately small YAML reader rather than a dependency: this package
    vendors no YAML parser, and the shape being read is two levels of a
    fixed-form lefthook file. Comments and blank lines are dropped first, so a
    commented-out command name can neither become a command nor set the
    indentation the real names are recognised at.
    """
    at = next((index for index, line in enumerate(block) if line.strip() == "commands:"), None)
    if at is None:
        return ()
    body = tuple(
        line for line in block[at + 1 :] if line.strip() and not line.strip().startswith("#")
    )
    if not body:
        return ()
    name_indent = len(body[0]) - len(body[0].lstrip())
    pairs: list[tuple[str, str]] = []
    name = ""
    for index, line in enumerate(body):
        stripped = line.strip()
        if len(line) - len(line.lstrip()) == name_indent and stripped.endswith(":"):
            name = stripped[:-1]
        elif name and stripped.startswith("run:"):
            inline = stripped.removeprefix("run:").strip()
            pairs.append((name, _run_value(inline=inline, rest=body[index + 1 :])))
            name = ""
    return tuple(pairs)


def _lefthook_gaps(*, text: str) -> tuple[WiringGap, ...]:
    """Fact 4 — the pack installer is the FIRST command of both gated hooks.

    First means first BY NAME, not by file position: lefthook runs a hook's
    commands in name-sorted order, so the `00-`-prefixed convention every
    fleet member uses is what makes the file order and the run order agree.
    Asserting file order would pass a member whose install step is written
    first but named `99-`.
    """
    gaps: list[WiringGap] = []
    for hook in _GATED_HOOKS:
        commands = _hook_commands(block=_hook_block(text=text, hook=hook))
        first = min(commands, key=lambda pair: pair[0], default=None)
        if first is None or first[1] != _INSTALL_HOOK_COMMAND:
            gaps.append(
                WiringGap(
                    path=LEFTHOOK_PATH,
                    missing=(
                        f"`{hook}` whose name-sorted FIRST command is "
                        f"`run: {_INSTALL_HOOK_COMMAND}`"
                    ),
                )
            )
    return tuple(gaps)


def _livespec_jsonc_gaps(*, text: str) -> tuple[WiringGap, ...]:
    """Fact 5 — the repo STATED its worktree-discipline policy.

    The key's VALUE is not asserted: `optional` is the sanctioned, reviewable
    opt-out, and this row asserts that the repo CHOSE — the same shape as the
    sibling `foreman-valve-declared` row. An unparseable config is a gap
    rather than a skip because the bytes were read: this is a definitive
    statement about the committed file, not a failed read.
    """
    try:
        parsed = jsoncomment.loads(text)
    except ValueError:
        return (WiringGap(path=LIVESPEC_JSONC_PATH, missing=_WORKTREE_DISCIPLINE_LINE),)
    if isinstance(parsed, dict) and _WORKTREE_DISCIPLINE_KEY in cast("dict[str, object]", parsed):
        return ()
    return (WiringGap(path=LIVESPEC_JSONC_PATH, missing=_WORKTREE_DISCIPLINE_LINE),)


def worktree_pack_wiring_gaps(
    *,
    justfile_text: str,
    gitignore_text: str,
    lefthook_text: str,
    livespec_jsonc_text: str,
) -> tuple[WiringGap, ...]:
    """Every worktree-pack wiring line these four file texts do not carry.

    THE public entry point, and a pure function by construction: it takes
    TEXTS, so the same predicate answers for a member's committed master (via
    `_rows_worktree_pack.assert_worktree_pack_wired`), for a rendered copier
    template in
    livespec's lockstep test, and for a checkout on disk. An empty tuple means
    fully wired.
    """
    return (
        *_justfile_gaps(text=justfile_text),
        *_gitignore_gaps(text=gitignore_text),
        *_lefthook_gaps(text=lefthook_text),
        *_livespec_jsonc_gaps(text=livespec_jsonc_text),
    )
