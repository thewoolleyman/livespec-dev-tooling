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

THE COMPOSITION IS NOT TOTAL, AND NOW SAYS SO (livespec-dev-tooling
-qndn.10). The prescription is chosen by READING files in the venue, so
a path that refuses to be read establishes NEITHER arm. That non-answer
used to be spelled as the absent-runner arm — an empty body from
`_read_text`, indistinguishable from the file simply not being there —
which left the hint asserting "the runner is NOT installed in this
working tree" on the strength of a justfile nobody could read. That is
the same class of defect the venue-awareness above exists to fix, one
level down: a claim about the venue that the venue never supported. It
is now the FAILURE track. ABSENCE stays on the success track, because
absence IS the answer the probe is looking for; only a path that is
there and unreadable — a permission refusal, a directory where a file
belongs — rides the rail.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# `returns` is VENDORED, not installed, so a bare import resolves only if some
# EARLIER import in the same process already put `_vendor/` on `sys.path`. This
# module is imported directly by its own tests as well as through the guard, so
# it establishes the path itself rather than relying on whichever importer
# happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "VenueUnreadable",
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

# The negative verdict, NAMED: `flake8-boolean-trap` (FBT003) refuses a bare
# boolean literal at a call site, and lifting one onto the railway is a call —
# the spelling `_docs_only_change._ABSENT_REVISION_IS_NOT_DOCS_ONLY` already
# established for this. It is ONE name rather than one per site because every
# site below means the same thing by it: nothing established that the
# prescribed recipes resolve here.
_UNRESOLVED: bool = False

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


@dataclass(frozen=True, kw_only=True)
class VenueUnreadable:
    """A path the venue probe had to read, and could not.

    Deliberately NOT inhabited by "the path is not there": absence is the
    ANSWER the probe is looking for and travels the success track as the
    empty body every caller already reads as "the recipes do not resolve".
    What lands here is a path that exists and refuses to yield its content,
    which establishes neither prescription arm.
    """

    path: str
    detail: str

    @property
    def hint(self) -> str:
        """The deny hint for a venue whose prescription could not be probed.

        THE DENY STANDS. This is a hook whose only other verdict is the
        fail-open ALLOW, so a failure that reached the boundary would let
        through the bare backgrounded gate the hook exists to deny; the
        agent gets a complete remedy on this track too. What changes is the
        CLAIM: the two probed arms assert the runner is present or absent,
        neither was established here, so this one names the path that could
        not be read and prescribes the step that is correct either way —
        installing the pack, which no-ops where it is already installed.
        """
        # The path is placed at the END of its sentence deliberately: a
        # sentence CONTINUING after it would read as part of it, and the
        # venue paths this hint names routinely end in `.just`.
        prescription = (
            "Whether the sanctioned detached runner resolves in this working tree could NOT be "
            f"established — a path the venue probe had to read is there and refused to yield "
            f"its content ({self.detail}): {self.path}. So take the step that is correct either "
            "way — install the worktree-discipline pack HERE, which no-ops where it is already "
            f"installed, with exactly: {_INSTALL_COMMAND} — then dispatch through the runner, "
            f"which IS allowed here: {_DISPATCH_CLAUSE}"
        )
        return f"{_HINT_PREAMBLE}{prescription}{_HINT_TAIL}{_CITATION}"


def _read_text(*, path: Path) -> IOResult[str, VenueUnreadable]:
    """Read `path` as text; an ABSENT path answers, an unreadable one does not.

    A venue probe must never raise: the caller's only alternative is the
    hook's fail-open boundary, which would ALLOW the bare backgrounded
    gate that hook exists to deny. So both non-answers are values — but
    they are no longer the SAME value. A path that is not there is the
    probe's ordinary finding and stays on the success track as the empty
    body callers read as "the recipes do not resolve"; every other
    `OSError` establishes nothing at all and rides the failure track.
    """
    try:
        return IOSuccess(path.read_text(encoding="utf-8", errors="replace"))
    except (FileNotFoundError, NotADirectoryError):
        return IOSuccess("")
    except OSError as exc:
        return IOFailure(VenueUnreadable(path=str(path), detail=type(exc).__name__))


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


def _imports_pack_fragment(*, root: Path) -> IOResult[bool, VenueUnreadable]:
    """True when the root justfile imports the pack's `worktree.just`."""
    target = f"{_PACK_DIR_NAME}/{_PACK_FRAGMENT_NAME}"
    for name in _JUSTFILE_NAMES:
        body = _read_text(path=root / name)
        if not is_successful(body):
            return IOFailure(unsafe_perform_io(body.failure()))
        imported = any(
            line.lstrip().startswith("import") and target in line
            for line in unsafe_perform_io(body.unwrap()).splitlines()
        )
        if imported:
            return IOSuccess(imported)
    return IOSuccess(_UNRESOLVED)


def _gate_recipes_resolve(*, root: Path | None) -> IOResult[bool, VenueUnreadable]:
    """True when `just gate-start` / `gate-wait` actually resolve at `root`."""
    if root is None:
        return IOSuccess(_UNRESOLVED)
    pack_dir = root / _PACK_DIR_NAME
    fragment = _read_text(path=pack_dir / _PACK_FRAGMENT_NAME)
    if not is_successful(fragment):
        return IOFailure(unsafe_perform_io(fragment.failure()))
    body = unsafe_perform_io(fragment.unwrap())
    declared = all(
        re.search(rf"(?m)^{re.escape(name)}\b", body) is not None for name in _PRESCRIBED_RECIPES
    )
    runner_installed = (pack_dir / _PACK_RUNNER_NAME).is_file()
    # The justfile is read only where the fragment already answered YES, which
    # keeps the short-circuit the plain-bool version had: a venue with no pack
    # at all resolves to False without any justfile read to fail on.
    if not (declared and runner_installed):
        return IOSuccess(_UNRESOLVED)
    return _imports_pack_fragment(root=root)


def deny_hint(*, cwd: Path) -> IOResult[str, VenueUnreadable]:
    """Compose the deny hint against the venue the hook is firing in.

    Every command the hint names resolves in `cwd`, and the one path it
    cites is addressed by the repo that OWNS it — the minimum bar the
    guard's own prescription has to clear before it can demand the agent
    follow it. The prescription is venue-probed because a recipe either
    resolves here or does not; the citation is not, because a
    repo-qualified address is correct from every venue.

    The probe can also fail to answer, and the return is a railway value
    for exactly that third case — see this module's docstring. The failure
    renders its own hint, so consuming the failure track is not a licence
    to hand the denied agent nothing.
    """
    return _gate_recipes_resolve(root=_repo_root(start=cwd)).map(
        lambda resolves: f"{_HINT_PREAMBLE}"
        f"{_RUNNER_PRESENT_CLAUSE if resolves else _RUNNER_ABSENT_CLAUSE}"
        f"{_HINT_TAIL}{_CITATION}"
    )
