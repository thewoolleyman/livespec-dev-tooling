"""The unresolved-receiver verb set must carry every failable I/O primitive.

livespec **v184** section "ROP composition" section "What counts as an I/O boundary" makes
FAILABILITY the criterion. `_UNRESOLVED_RECEIVER_IO_VERBS` decides every call
whose receiver resolves to nothing, so a failable I/O primitive missing from it
is a boundary the check structurally cannot see.

**FOUR WERE MISSING.** Measured on CPython 3.10.16 — the fleet's
`requires-python` FLOOR, not a newer interpreter:

    open()      a DIR          -> IsADirectoryError    missing -> FileNotFoundError
    readlink()  not a symlink  -> OSError              missing -> FileNotFoundError
    owner()     missing        -> FileNotFoundError
    truncate()  missing        -> FileNotFoundError

⚠️ **`truncate`'s RECEIVER IS A FILE OBJECT, NOT A PATH.** `Path.truncate` does
not exist on any supported version, so a reader checking `dir(Path)` would
conclude the verb is inert and drop it. `handle.truncate()` is the live shape,
and a handle held in a parameter is exactly the unresolved receiver this set
governs.

## ⛔ `group` IS FAILABLE AND IS STILL REFUSED — THE MEASUREMENT, NOT THE TASTE

`Path.group()` raises `FileNotFoundError`, so it passes the failability test.
**It is still excluded, because failability is NECESSARY AND NOT SUFFICIENT: the
primitive must also BE an I/O surface**, and this set matches on the VERB alone
whenever the receiver is unresolved. `re.Match.group()` is a pure string
operation that dominates the name in this codebase.

**MEASURED, and the number is the point:** adding `group` moved this repo's
offender count **24 -> 34**, and **all ten** additions were `match.group(...)`
call sites. Dropping `group` alone returns it to **24**, while `open`,
`readlink`, `owner` and `truncate` together add **zero**.

**That is the same defect this module's own docstring already records** — a
terminal-name match "once flagged ten total functions in this repo as touching
I/O and only three were real", which is why `get` and `run` are refused. `group`
is that verb's third instance, and it mis-flagged exactly ten again. The last
test pins the refusal so a later editor reading only the failability half cannot
re-add it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_dev_tooling.checks._import_resolution import suffix_index
from livespec_dev_tooling.checks._io_boundary_calls import ModuleFacts, calls_of
from livespec_dev_tooling.fleet._local_context import LocalContext

__all__: list[str] = []


_REL = Path("pkg/a.py")


def _disqualifies_on_unresolved_receiver(*, verb: str) -> bool:
    """Is `subject.<verb>()` an I/O boundary when `subject` is a PARAMETER?

    A parameter receiver resolves to nothing, so only the verb is left and
    `_UNRESOLVED_RECEIVER_IO_VERBS` alone decides — precisely the surface under
    test.
    """
    source = f"def probe(*, subject: object) -> object:\n    return subject.{verb}()\n"
    sources = {_REL: source}
    trees = {rel: ast.parse(text) for rel, text in sources.items()}
    index = suffix_index(sources=sources)
    modules = {rel: ModuleFacts(rel=rel, tree=tree, index=index) for rel, tree in trees.items()}
    node = next(
        item
        for item in trees[_REL].body
        if isinstance(item, ast.FunctionDef) and item.name == "probe"
    )
    return calls_of(
        func=node, facts=modules[_REL], index=index, modules=modules, io_trees=()
    ).disqualifies


def test_open_on_an_unresolved_receiver_is_an_io_boundary() -> None:
    """`Path.open()` raises `IsADirectoryError` on a directory — the commonest read."""
    assert _disqualifies_on_unresolved_receiver(verb="open")


def test_readlink_on_an_unresolved_receiver_is_an_io_boundary() -> None:
    """`Path.readlink()` raises `OSError` when the path is not a symlink."""
    assert _disqualifies_on_unresolved_receiver(verb="readlink")


def test_owner_on_an_unresolved_receiver_is_an_io_boundary() -> None:
    """`Path.owner()` raises `FileNotFoundError` on a missing path."""
    assert _disqualifies_on_unresolved_receiver(verb="owner")


def test_truncate_on_an_unresolved_receiver_is_an_io_boundary() -> None:
    """The receiver is a FILE OBJECT, which is why `dir(Path)` misleads here."""
    assert _disqualifies_on_unresolved_receiver(verb="truncate")


def test_a_non_io_verb_on_an_unresolved_receiver_is_not_an_io_boundary() -> None:
    """NEGATIVE CONTROL — the instrument must be able to answer NO.

    Without it every assertion above would pass under a set that convicted every
    attribute call, which is the defect the receiver-resolving design avoids.
    """
    assert not _disqualifies_on_unresolved_receiver(verb="strip")


def test_group_is_refused_despite_being_failable() -> None:
    """`Path.group()` raises, yet the verb stays OUT — measured, not preferred.

    Failability is necessary and NOT sufficient; the primitive must also be an
    I/O surface, and this set sees only the verb. `re.Match.group()` dominates
    the name here: adding it moved the repo 24 -> 34 offenders, all ten of them
    `match.group(...)` sites. Same class as the refused `get` and `run`.
    """
    assert not _disqualifies_on_unresolved_receiver(verb="group")


def test_the_filesystem_predicates_are_not_removed() -> None:
    """REGRESSION PIN for the livespec v185 retraction.

    `exists` / `is_file` / `is_dir` are NOT total — they swallow only
    `(ENOENT, ENOTDIR, EBADF, ELOOP)` and raise `PermissionError` otherwise — so
    they are failable and MUST stay. This pins the retracted removal so a later
    editor reading the original "wrong in both directions" finding cannot
    re-attempt it silently.
    """
    assert _disqualifies_on_unresolved_receiver(verb="exists")
    assert _disqualifies_on_unresolved_receiver(verb="is_file")
    assert _disqualifies_on_unresolved_receiver(verb="is_dir")


def test_the_injected_seam_names_never_collide_with_this_set() -> None:
    """⛔ THE NAMING TRAP, CLOSED MECHANICALLY RATHER THAN IN PROSE.

    A row reaches a `LocalContext` seam through `ctx`, a PARAMETER, so the
    receiver resolves to NOTHING and this set alone decides. A seam named after
    the primitive it wraps therefore leaves every caller convicted exactly as
    before — **the fix looks done while changing nothing.** Measured twice: for
    `read_text` when the file seam was built, and again for `is_dir`/`is_file`
    when the predicate seam was.

    ⛔ THIS ASSERTION LIVES HERE, BESIDE THE SET, ON PURPOSE. It was first
    written as prose in a commit message, and a true record nobody re-reads is
    this thread's own signature defect — a finding filed as an observation
    outlives the epic built to close it. An editor renaming a seam, or widening
    this set, now fails a test instead of silently reproducing the trap.

    It asserts BOTH directions: no seam name is decided by the set, AND the
    primitives they wrap still are. Without the second half the test would still
    pass if the set were emptied.

    ⚠️ It probes through this file's own `_disqualifies_on_unresolved_receiver`
    helper rather than importing the set: the helper asks the SHIPPED analysis
    the question a row's call actually asks, so it cannot drift from the set the
    way a second reader of the same constant would.
    """
    seam_names = [
        name
        for name in dir(LocalContext)
        if not name.startswith("_") and callable(getattr(LocalContext, name, None))
    ]
    collisions = sorted(
        name for name in seam_names if _disqualifies_on_unresolved_receiver(verb=name)
    )
    assert not collisions, (
        f"a LocalContext seam is named after an I/O verb this set decides on, so every "
        f"caller stays convicted and the seam buys nothing: {collisions}"
    )
    assert all(
        _disqualifies_on_unresolved_receiver(verb=verb)
        for verb in ("read_text", "is_dir", "is_file", "exists")
    )
