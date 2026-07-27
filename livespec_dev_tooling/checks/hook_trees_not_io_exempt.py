"""hook_trees_not_io_exempt — an agent-runtime hook tree may not be declared `io_trees`.

`io_trees` grants a WHOLESALE exemption from the catch-position and
domain-raise rules. That is correct for a layered `io/` package tree,
whose broad catches are the architecture. It is NOT available to a
`.claude/hooks` or `.claude-plugin/hooks` tree, and livespec
`SPECIFICATION/non-functional-requirements.md` says so in terms that
name the situation exactly: there is no "thin repo" exemption, a repo
whose only Python is fail-open hooks still composes those hooks' bodies
on the railway beneath a single boundary, and the sole exemption is a
governed repo with ZERO first-party Python. The same file adds that the
io-tree exemption is a LAYERED-architecture concern, and that a repo
without a layered io tree — it names a hook-only Driver — must still be
scanned rather than no-op.

WHY THIS IS A CHECK AND NOT A NOTE. The prohibition was already explicit
in ratified prose. Three sessions of the `rop-sweep-fleet-policy` thread
reached for the exemption anyway; the third built it, merged it in six
repositories, and was caught only by after-the-fact review. Each of the
three validated the design against a check's test suite and against
per-repo ruff config comments — never against the contract. A rule that
is not enforced where the edit happens is a rule that gets re-derived
wrongly, so this one fires at the edit.

The diagnostic deliberately carries three things, because a bare
rejection is a thing to route around rather than learn from: the clause
QUOTED (so a reader who has not opened the spec still learns the rule),
why the exemption is unnecessary (the same clause GRANTS the one
fail-open boundary catch — the posture is not at risk), and the
conforming route with a shipped reference to copy.

NOT CONFIGURABLE, deliberately. A lever to silence this would recreate
the escape it exists to close. If a future case genuinely needs a hook
tree exempt, the answer is a proposed change against the clause, not a
flag.

The rule is NARROW on purpose. Only `.claude` / `.claude-plugin` hook
trees are refused; a package directory that merely happens to be named
`hooks` is not making the thin-repo claim, and a genuine layered `io/`
tree is untouched.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow
through structlog (JSON to stderr).
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import load_config  # noqa: E402

__all__: list[str] = []


# The agent-runtime directories whose `hooks/` subtree is a hook tree.
_AGENT_RUNTIME_DIRS = frozenset({".claude", ".claude-plugin"})
_HOOKS_SEGMENT = "hooks"

_CLAUSE = (
    "livespec SPECIFICATION/non-functional-requirements.md: \"There is NO 'thin repo' "
    "exemption — a repo whose only Python is fail-open hooks still composes those hooks' "
    "bodies on the railway beneath that single boundary. The SOLE exemption is a governed "
    'repo with ZERO first-party Python."'
)

_WHY_UNNECESSARY = (
    "The fail-open posture is NOT at risk: that same clause GRANTS a hook one boundary "
    "catch — the fail-open silent pass-through its Driver hook contract already requires. "
    "The spec does not ask hooks to stop being fail-open; it asks their BODIES to sit "
    "beneath that ONE marked boundary. A wholesale io_trees exemption buys nothing and "
    "costs the coverage."
)

_ROUTE = (
    "Conforming route, per file: (1) restructure so the sole broad catch is a DIRECT CHILD "
    "of `main()` carrying the closed-set wording `# noqa: BLE001 — sole fail-open hook "
    "boundary: silent pass-through, exit 0`, with `main() -> int` and a module-level "
    "`raise SystemExit(main())`; (2) declare the hook path in `supervisor_entry_files`, "
    "which is what makes the marker consulted, exempts the file from `no_write_direct`, "
    "and exempts its `sys.exit` from `check-supervisor-discipline`; (3) write via "
    "`sys.stdout.write` rather than `print`; (4) drop any wholesale `.claude/hooks/**` ruff "
    "`extend-exclude` and use a NARROW per-file-ignore instead, so the BLE001 backstop "
    "stays live. Shipped reference to copy: livespec-driver-claude's "
    "`.claude/hooks/livespec_footgun_guard.py`."
)

_EVENT = "agent-runtime hook tree declared in io_trees — wholesale exemption is foreclosed"


def is_hook_tree(*, rel_path: Path) -> bool:
    """True iff `rel_path` is an agent-runtime hook tree, or lives beneath one.

    Matched structurally on adjacent path segments — an `.claude` or
    `.claude-plugin` segment immediately followed by `hooks` — so a
    subtree (`.claude/hooks/guards`) is caught as the same claim one
    level down, while an unrelated directory that merely ends in `hooks`
    (`pkg/io/hooks`) is not.
    """
    parts = rel_path.parts
    return any(
        parts[i] in _AGENT_RUNTIME_DIRS and parts[i + 1] == _HOOKS_SEGMENT
        for i in range(len(parts) - 1)
    )


def find_hook_tree_declarations(*, io_trees: tuple[Path, ...]) -> tuple[Path, ...]:
    """Return every declared io tree that is really a hook tree."""
    return tuple(tree for tree in io_trees if is_hook_tree(rel_path=tree))


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("hook_trees_not_io_exempt")
    config = load_config(repo_root=Path.cwd())
    # Every offender is reported, not just the first, so one fix-and-rerun
    # cycle sees the whole set.
    offenders = find_hook_tree_declarations(io_trees=config.io_trees)
    for tree in offenders:
        log.error(
            _EVENT,
            check_id="hook_trees_not_io_exempt",
            role="io_trees",
            path=tree.as_posix(),
            clause=_CLAUSE,
            why_unnecessary=_WHY_UNNECESSARY,
            conforming_route=_ROUTE,
        )
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
