"""_deny_hint — compose the background guard's deny hint against its VENUE.

Extracted from `pretooluse_background_guard.py` per work-item
livespec-dev-tooling-k169: that module had accreted two concerns — the
hook itself (protocol, deny decision, gate classification) and the
composition of the hint a deny hands back — and the command-token
-position fix pushed the pair into the LLOC soft band. `deny_hint` is
the single public entry point here; every helper below is used only by
it and stays private to this module.

VENUE-AWARE PRESCRIPTION (livespec-dev-tooling-h7qp). The deny used to
prescribe `just gate-start` / `gate-wait` and cite that `.ai/` doc
UNCONDITIONALLY, and both are absent in most venues where this hook
fires. The recipes ship in the worktree pack's `worktree.just`, which a
consumer root justfile pulls in via an OPTIONAL `import?` — the
optional form silently no-ops while the gitignored-and-installed pack
is absent, and a fresh `git worktree add` does not materialize it (the
authoring repo included). The `.ai/` doc is checkout-local to this
repo. So the deny left an agent with the direct path denied, the
prescribed path absent, the rationale unreadable, and the foreground
fallback explicitly foreclosed — which invites engineering AROUND the
guard, the worst available exit. The hint is therefore composed
against the venue: the runner is prescribed directly only where the
recipes actually resolve, otherwise the one-line install command that
makes them resolve is named FIRST. Detection is pure filesystem reads
(no subprocess), keeping the blocking path cheap per this directory's
hook discipline.

THE CITATION IS ADDRESSED, NOT PROBED (livespec-dev-tooling-5ug6).
The doc citation was originally handled the same way — cited only
where the relative path resolved — and that is the wrong instrument
for a path. A repo-relative path inside a message emitted by a SHIPPED
artifact is a PRODUCER-relative path being read in a CONSUMER context:
it names a location that exists, in a repo the reader is not standing
in. Suppressing it there leaves a denied agent with no way to reach
the rationale at all, and citing it bare sends them to a file that is
not there — the shape measured 2026-08-22 in livespec-overseer, where
`.ai/` holds one unrelated file. So the citation now names the owning
repo AND carries the URL, which is correct from every venue and needs
no probe, and it says outright that the remedy above is complete
without it: a reader who cannot follow the link has still been told
exactly what to run.

SELF-INSTALL WAS CONSIDERED AND DECLINED, per the item's pinned
fix-order ruling, which prefers "the deny path detects recipe absence
and EITHER materializes the pack OR names that exact step as the
remedy". Naming it is the arm taken: a `PreToolUse` guard runs on a
DENY path under a cheapness obligation, and having it mutate the
repository it is judging would make a read-only veto into a writer —
a surprising mutation from a hook the agent did not ask to run, and
an unbounded install on a path required to stay sub-second. The
remedy is one line the agent runs deliberately, in the venue, where
its output is visible.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = [
    "deny_hint",
]


# Venue probe constants. The gate recipes resolve only when the pack's
# `worktree.just` fragment is installed AND imported by the root justfile
# AND the `gate-run.sh` body its stanzas invoke is installed beside it —
# any one of the three missing makes `just gate-start` unresolvable.
_PACK_DIR_NAME = "dev-tooling"
_PACK_FRAGMENT_NAME = "worktree.just"
_PACK_RUNNER_NAME = "gate-run.sh"
_JUSTFILE_NAMES: tuple[str, ...] = ("justfile", "Justfile", ".justfile")
_PRESCRIBED_RECIPES: tuple[str, ...] = ("gate-start", "gate-wait")

# The rationale doc is checkout-local to the repo that SHIPS this hook, so
# the citation names that repo and carries the address that resolves from
# ANY venue (livespec-dev-tooling-5ug6).
_OWNING_REPO = "livespec-dev-tooling"
_RATIONALE_DOC = ".ai/gate-runtime-vs-harness-patience.md"
_RATIONALE_DOC_URL = f"https://github.com/thewoolleyman/{_OWNING_REPO}/blob/master/{_RATIONALE_DOC}"

# Further reading, and SAID to be further reading: the remedy above is
# complete on its own, so a reader who cannot reach the doc has still been
# told what to run. That demotion is half the fix; the other half is the
# address, which no longer resolves only from the owning repo.
_CITATION = (
    " The remedy above is complete without it, but for WHY — the measured aggregate "
    f"runtimes against the harness ceiling — see {_RATIONALE_DOC} in the {_OWNING_REPO} "
    f"repo that ships this hook: {_RATIONALE_DOC_URL}"
)

# The one-line repair, spelled as the MODULE invocation rather than as
# `just install-worktree-pack`: the module is guaranteed importable
# wherever this hook runs (the hook itself is a `python -m` entry of the
# same package), whereas the convenience recipe is per-repo.
_INSTALL_COMMAND = "mise exec -- uv run python -m livespec_dev_tooling.install_worktree_pack"

_HINT_PREAMBLE = (
    "Gate commands (just check*, git commit, git push, gh pr ...) must not be "
    "backgrounded BARE: the tool output is then the only record of the verdict, "
    "so a killed task or a turn-end leaves nothing behind. Do NOT answer this by "
    "re-issuing it foreground and waiting — the commit aggregate exceeds "
    "BASH_MAX_TIMEOUT_MS under load, and that kill produces NO verdict at all. "
)

_DISPATCH_CLAUSE = (
    "run_id=$(mise exec -- just gate-start -- <your gate command>) then background "
    '`mise exec -- just gate-wait "$run_id"`. '
)

_RUNNER_PRESENT_CLAUSE = (
    "Dispatch through the sanctioned detached runner instead, which IS allowed here: "
    f"{_DISPATCH_CLAUSE}"
)

# The install command is named BEFORE the recipes it materializes: naming
# an unresolvable recipe first is the defect this clause exists to fix.
_RUNNER_ABSENT_CLAUSE = (
    "The sanctioned detached runner is NOT installed in this working tree, so its gate "
    "recipes do not resolve here yet: the runner ships in the worktree-discipline pack, "
    "which is gitignored-and-installed, and a fresh `git worktree add` does not "
    f"materialize it. Install the pack HERE first, with exactly: {_INSTALL_COMMAND} — "
    f"then dispatch through the runner, which IS allowed here: {_DISPATCH_CLAUSE}"
)

_HINT_TAIL = (
    "The gate then runs in its own session that outlives the tool call, killing the "
    "waiter loses nothing, and the verdict is one of PASSED / FAILED / RUNNING / "
    "DIED_WITHOUT_VERDICT — so a gate that did not finish can never read as a pass. "
    "The wrapper does not exempt the wrapped command from the OTHER guards: a CI wait "
    "must still be a single loop-free call, e.g. `mise exec -- just gate-start -- gh "
    "run watch <run-id> --exit-status --interval 30` rather than an `until`/`sleep` "
    "loop over uncached `gh pr checks`, which the rate-limit guard denies wrapped or not."
)


def _read_text(*, path: Path) -> str:
    """Read `path` as text, degrading an unreadable path to an empty body.

    A venue probe must never raise: the caller's only alternative is the
    hook's fail-open boundary, which would ALLOW the bare backgrounded
    gate that hook exists to deny. An unreadable justfile or fragment
    means "cannot establish that the recipes resolve", which is exactly
    what an empty body yields downstream.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _repo_root(*, start: Path) -> Path | None:
    """Return the nearest ancestor of `start` holding a `.git` entry.

    `.git` is a DIRECTORY in a primary checkout and a FILE in a linked
    worktree — the venue this item is about — so the probe is `exists()`
    rather than `is_dir()`.
    """
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _imports_pack_fragment(*, root: Path) -> bool:
    """True when the root justfile imports the pack's `worktree.just`."""
    target = f"{_PACK_DIR_NAME}/{_PACK_FRAGMENT_NAME}"
    for name in _JUSTFILE_NAMES:
        body = _read_text(path=root / name)
        for line in body.splitlines():
            if line.lstrip().startswith("import") and target in line:
                return True
    return False


def _gate_recipes_resolve(*, root: Path | None) -> bool:
    """True when `just gate-start` / `gate-wait` actually resolve at `root`."""
    if root is None:
        return False
    pack_dir = root / _PACK_DIR_NAME
    fragment = _read_text(path=pack_dir / _PACK_FRAGMENT_NAME)
    declared = all(
        re.search(rf"(?m)^{re.escape(name)}\b", fragment) is not None
        for name in _PRESCRIBED_RECIPES
    )
    runner_installed = (pack_dir / _PACK_RUNNER_NAME).is_file()
    return declared and runner_installed and _imports_pack_fragment(root=root)


def deny_hint(*, cwd: Path) -> str:
    """Compose the deny hint against the venue the hook is firing in.

    Every command the hint names resolves in `cwd`, and the one path it
    cites is addressed by the repo that OWNS it — the minimum bar the
    guard's own prescription has to clear before it can demand the agent
    follow it. The prescription is venue-probed because a recipe either
    resolves here or does not; the citation is not, because a
    repo-qualified address is correct from every venue.
    """
    root = _repo_root(start=cwd)
    prescription = (
        _RUNNER_PRESENT_CLAUSE if _gate_recipes_resolve(root=root) else _RUNNER_ABSENT_CLAUSE
    )
    return f"{_HINT_PREAMBLE}{prescription}{_HINT_TAIL}{_CITATION}"
