"""Clause (c) must not convict a PURE member of an I/O module.

`_IO_MODULES` classifies at MODULE granularity, so every callable reached
through `io` or `pathlib` reads as a boundary. Two of those are not:

  - `io.StringIO(...)` is an IN-MEMORY buffer. It convicted
    `_no_except_outside_io_markers.comment_lines` and `.statement_colons`,
    whose only "I/O" is tokenizing a string already in hand.
  - `Path(...)` is a value CONSTRUCTION that touches nothing. It convicted
    `_subagent_stop_guard_transcript.extract_created_worktree_paths`, which is
    string-in / list-of-Path-out.

⛔ THIS IS FIDELITY IN THE SAME SENSE AS THE ALIAS FIX, AND THE MIRROR OF THE
`_`-FILE SKIP. Clause (c) is "a call to an I/O boundary"; a module NAMED `io`
is not the same claim. A check enforcing something WIDER than its ratified
clause is non-conformant in the tightening direction.

⚠️ THE BOUND MATTERS MORE THAN THE FIX. `Path(x).read_text()` and `Path.cwd()`
must STAY disqualifying — the exemption is for the constructor alone, matched
EXACTLY, never for the module. Both are pinned below, because a fix that
exempted `pathlib` wholesale would silently un-convict every filesystem walk in
the fleet.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from livespec_dev_tooling.checks._import_resolution import suffix_index
from livespec_dev_tooling.checks._io_boundary_calls import ModuleFacts, calls_of

__all__: list[str] = []


_REL = Path("pkg/a.py")

# `os.path`'s LEXICAL half: string in, string out, touching nothing. Each was
# driven with adverse input on CPython 3.10.16 — the fleet's `requires-python`
# FLOOR — over the empty string, `/`, `//`, `..`, `.`, an embedded NUL, a lone
# surrogate, a 4096-character path, a backslash and `~nosuchuser`. NONE raised.
_PURE_OS_PATH_MEMBERS = (
    "normpath",
    "basename",
    "dirname",
    "join",
    "split",
    "splitext",
    "isabs",
)

# The bound, and it is WIDER than failability. Each of these is reached through
# the same `os.path` module and must STAY convicted, for the reason beside it:
#
#   realpath   RAISES `ValueError` on an embedded NUL, and resolves symlinks.
#   relpath    RAISES `ValueError` on the empty string.
#   getsize    RAISES `FileNotFoundError`, and `ValueError` on an embedded NUL.
#   abspath    Does NOT raise on any adverse input above — it is excluded
#              because it calls `os.getcwd()`, so it READS PROCESS STATE and
#              can fail when the working directory is unlinked. ⛔ It looks
#              purer than the seven; this is why it is out.
#   expanduser Does NOT raise on `~nosuchuser` on the FLOOR — it returns the
#              path unchanged. It is out because it reads `HOME` and the passwd
#              database, which is ENVIRONMENT access.
#              ⚠️ `pathlib.Path.expanduser` DOES raise `RuntimeError` there. That
#              is a DIFFERENT function sharing a name, and importing its result
#              here would be this module's own defect: the name is not the
#              function.
#   exists     Cannot raise — it swallows `OSError` — and READS THE FILESYSTEM
#   isfile     anyway, so its answer depends on the world. ⛔ THESE THREE ARE
#   isdir      THE REASON THE BAR IS PURITY AND NOT MERELY NON-FAILABILITY:
#              cannot-fail is NECESSARY AND NOT SUFFICIENT for this set, whose
#              own name is `_PURE_IO_MODULE_MEMBERS` — members that touch
#              NOTHING. A later reader applying only v184's failability
#              criterion would wrongly add them.
_IMPURE_OS_PATH_MEMBERS = (
    "realpath",
    "relpath",
    "getsize",
    "abspath",
    "expanduser",
    "exists",
    "isfile",
    "isdir",
)


def _disqualifies(*, source: str, function: str = "probe") -> bool:
    sources = {_REL: source}
    trees = {rel: ast.parse(text) for rel, text in sources.items()}
    index = suffix_index(sources=sources)
    modules = {rel: ModuleFacts(rel=rel, tree=tree, index=index) for rel, tree in trees.items()}
    node = next(
        item
        for item in trees[_REL].body
        if isinstance(item, ast.FunctionDef) and item.name == function
    )
    return calls_of(
        func=node, facts=modules[_REL], index=index, modules=modules, io_trees=()
    ).disqualifies


def test_an_in_memory_string_buffer_is_not_an_io_boundary() -> None:
    """`io.StringIO` — the `comment_lines` / `statement_colons` conviction.

    Shaped after the real call: those two pass `io.StringIO(source).readline`
    to `tokenize.generate_tokens` as an ATTRIBUTE, never calling a read verb.
    A fixture that called `.read()` would stay disqualified after this fix —
    correctly, via the unresolved-receiver verb set — and would therefore be
    testing that set rather than the module-granularity defect.
    """
    source = (
        "import io\n"
        "\n"
        "\n"
        "def probe(*, text: str) -> int:\n"
        "    buffer = io.StringIO(text)\n"
        "    return len(buffer.getvalue())\n"
    )
    assert not _disqualifies(source=source, function="probe")


def test_constructing_a_path_is_not_an_io_boundary() -> None:
    """`Path(raw)` — the `extract_created_worktree_paths` conviction."""
    source = "from pathlib import Path\n\n\ndef probe(*, raw: str) -> Path:\n    return Path(raw)\n"
    assert not _disqualifies(source=source, function="probe")


def test_reading_through_a_constructed_path_is_still_an_io_boundary() -> None:
    """The bound: the constructor is pure, the read is not.

    Without this the fix would look correct while un-convicting every
    filesystem read in the fleet.
    """
    source = (
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def probe(*, raw: str) -> str:\n"
        "    return Path(raw).read_text(encoding='utf-8')\n"
    )
    assert _disqualifies(source=source, function="probe")


def test_a_path_classmethod_that_touches_the_process_is_still_an_io_boundary() -> None:
    """`Path.cwd()` reads the process working directory — the exemption is EXACT.

    Only the bare constructor is pure. A prefix or module match would let this
    through.
    """
    source = "from pathlib import Path\n\n\ndef probe() -> Path:\n    return Path.cwd()\n"
    assert _disqualifies(source=source, function="probe")


def test_an_io_module_member_that_is_not_in_memory_is_still_an_io_boundary() -> None:
    """`io.open` is the real thing, in the same module as the buffer."""
    source = "import io\n\n\ndef probe(*, at: str) -> str:\n    return io.open(at).read()\n"
    assert _disqualifies(source=source, function="probe")


@pytest.mark.parametrize("member", _PURE_OS_PATH_MEMBERS)
def test_a_lexical_os_path_member_is_not_an_io_boundary(member: str) -> None:
    """`os.path`'s string half touches nothing, and `os` is at MODULE granularity.

    ⛔ THIS TEST ALSO PINS THE SPELLING, AND THAT IS ITS SHARPEST JOB. The set is
    matched EXACTLY on the dotted form `calls_of` rebuilds from the IMPORT
    BINDING — `os` + `path` + the attribute — so the entry must read
    `os.path.<member>`. **`os.path` IS `posixpath` at runtime, and an entry
    spelled `posixpath.<member>` is INERT**: measured, the `posixpath` spelling
    moved `livespec-overseer` 194 -> 194 while `os.path` moved it 194 -> 173.
    A later reader who "tidies" the spelling to the runtime identity reds this.

    ⚠️ AND THE FIXTURE'S IMPORT FORM IS LOAD-BEARING — `import os`, never
    `import os.path`. Measured: under bare `import os.path` the local root `os`
    is NOT in `import_roots`, the receiver does not resolve at all, and the call
    falls through to the unresolved-receiver VERB branch. A fixture written that
    way passes this assertion WITHOUT the fix, for the wrong reason — it tests
    the verb set instead of the module-granularity defect. It was written that
    way first, and running it is what caught it.
    """
    source = (
        "import os\n"
        "\n"
        "\n"
        f"def probe(*, raw: str) -> object:\n    return os.path.{member}(raw)\n"
    )
    assert not _disqualifies(source=source, function="probe")


@pytest.mark.parametrize("member", _IMPURE_OS_PATH_MEMBERS)
def test_an_os_path_member_that_touches_the_world_is_still_an_io_boundary(member: str) -> None:
    """The bound: the exemption is the LEXICAL half, matched exactly, never `os.path`.

    Without this a fix that exempted the module would silently un-convict every
    filesystem probe in the fleet — and three of these (`exists`, `isfile`,
    `isdir`) cannot raise at all, so they are the cases that keep the bar at
    PURITY rather than at failability.
    """
    source = (
        "import os\n"
        "\n"
        "\n"
        f"def probe(*, raw: str) -> object:\n    return os.path.{member}(raw)\n"
    )
    assert _disqualifies(source=source, function="probe")


def test_the_from_os_import_path_spelling_is_a_measured_gap_not_a_hole() -> None:
    """`from os import path` yields a DIFFERENT dotted form, and stays convicted.

    Measured: that form binds `path -> os`, so `calls_of` renders `os.normpath`
    with no middle segment — NOT `os.path.normpath` — and misses the set. Closing
    it needs a SECOND entry per member, spelled `os.<member>`.

    ⛔ THOSE ENTRIES ARE DELIBERATELY NOT ADDED, and the reason is measured rather
    than assumed: `from os import path` appears in **ZERO** first-party files
    across all eight code-carrying repos (`import os` appears in 141). Adding
    seven inert entries would enlarge a set that reads as coverage while covering
    nothing — this thread's own founding shape.

    This test pins the gap so it is a FACT with a spelling attached rather than a
    sentence in a commit message. It stays green either way; it reds only if the
    resolution changes shape.
    """
    source = (
        "from os import path\n"
        "\n"
        "\n"
        "def probe(*, raw: str) -> object:\n    return path.normpath(raw)\n"
    )
    assert _disqualifies(source=source, function="probe")
