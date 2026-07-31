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

from livespec_dev_tooling.checks._import_resolution import suffix_index
from livespec_dev_tooling.checks._io_boundary_calls import ModuleFacts, calls_of

__all__: list[str] = []


_REL = Path("pkg/a.py")


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
