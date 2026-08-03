"""`replace` is ambiguous, and ARITY is what separates its two meanings.

`_UNRESOLVED_RECEIVER_IO_VERBS` carries `replace` for `Path.replace()`, the
atomic rename. On an unresolved receiver the SAME verb is also
`str.replace(old, new[, count])` and `datetime.replace(**fields)`, both pure and
both far commoner. Matching the verb alone therefore convicts pure total
functions of touching a filesystem — the fourth instance of the terminal-name
defect this module already records for `get`, `run` and `group`.

⛔ `replace` CANNOT BE HANDLED THE WAY `group` WAS. `group` was simply dropped,
because no fleet code calls `Path.group()`. Genuine `Path.replace` on an
UNRESOLVED receiver DOES exist here and in siblings — `temp_path.replace(path)`
in livespec's `spec_governance/config_edit.py` and `proposal_edit.py`,
`tmp.replace(path)` in beads-fabro's `_dispatcher_cost_sink.py` — so dropping
the verb would stop detecting three real atomic renames. That is a softening,
and the charter refuses it.

**ARITY SEPARATES THEM CLEANLY, and every observed call site agrees:**

    Path.replace(target)              1 positional, no keywords  -> I/O
    str.replace(old, new)             2 positional               -> pure
    str.replace(old, new, count)      3 positional               -> pure
    datetime.replace(tzinfo=...)      0 positional, keywords     -> pure

So `.replace(...)` on an unresolved receiver is an I/O boundary ONLY at exactly
one positional argument and no keywords. Every call that could be a rename stays
convicted, which makes this FIDELITY rather than a relaxation — the same shape
as dropping `_scan`'s `_`-prefixed FILE skip.

Measured fleet-wide before the change: 3 functions convicted on the false
premise (`livespec-runtime` `github_auth/signing.py::normalize_pem`;
beads-fabro's `_dispatcher_host_only.py::is_host_only_item` and
`::declares_workflow_scope_refusal`), and 0 offenders gained anywhere by the
repair. Work item `livespec-dev-tooling-l5pw`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_dev_tooling.checks._import_resolution import suffix_index
from livespec_dev_tooling.checks._io_boundary_calls import ModuleFacts, calls_of

__all__: list[str] = []

_REL = Path("pkg/a.py")


def _disqualifies(*, call: str) -> bool:
    """Is `subject.<call>` an I/O boundary when `subject` is a PARAMETER?

    A parameter receiver resolves to nothing, so the verb — and now its arity —
    is all that is left to decide with.
    """
    source = f"def probe(*, subject: object) -> object:\n    return subject.{call}\n"
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


def test_one_positional_replace_is_still_an_io_boundary() -> None:
    """`temp_path.replace(path)` is the atomic-rename shape and MUST stay convicted.

    This is the assertion that makes the change fidelity rather than a
    softening: the repair may not let a real rename through.
    """
    assert _disqualifies(call="replace(other)")


def test_two_positional_replace_is_a_string_operation() -> None:
    """`raw.replace("\\n", "\\n")` — `str.replace`, pure, and the commonest by far."""
    assert not _disqualifies(call='replace("a", "b")')


def test_three_positional_replace_is_a_string_operation() -> None:
    """`text.replace(needle, replacement, 1)` — the bounded-count `str.replace`."""
    assert not _disqualifies(call='replace("a", "b", 1)')


def test_keyword_replace_is_a_datetime_operation() -> None:
    """`parsed.replace(tzinfo=timezone.utc)` — `datetime.replace`, pure."""
    assert not _disqualifies(call="replace(tzinfo=utc)")


def test_a_starred_replace_argument_stays_convicted() -> None:
    """DOUBT DISQUALIFIES: `subject.replace(*args)` has unknowable arity.

    The ratified direction is that doubt demands a `Result` that may not have
    been needed rather than excusing one that was, so an argument list the
    analysis cannot count keeps the conservative answer.
    """
    assert _disqualifies(call="replace(*args)")
