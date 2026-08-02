"""Resolve a first-party reach through re-export shims (`livespec-dev-tooling-8sc1`).

A facade that re-exports a name DEFINES nothing, so a reach that lands on it
must be re-resolved to the module the name comes FROM. Without that walk,
`_io_boundary_calls._first_party_edges` produced NO edge for such a reach — and
`_name_call`'s `dotted is not None` branch never falls through to its
doubt-disqualifies arm, which is only reached for a name that was not imported
at all. So clause (d) ACQUITTED a caller whose callee is disqualified, which is
the fail-open direction the ratified design forecloses everywhere else.

MEASURED in `livespec-orchestrator-beads-fabro` at `73f225d`: three functions
reaching disqualified callees through `commands/_dispatcher_plan.py` — a
277-line aggregator re-exporting `parse_run_status` from
`_dispatcher_run_status` — escaped conviction, and the fixpoint gained 4
disqualified functions once the walk landed.

⚠️ AND IT MOVED ZERO OFFENDERS. All four are `_`-prefixed, so none is itself a
public offender, and their public callers were already disqualified by other
paths. The standing claim that the fleet's 321 was "a FLOOR" pending this fix
was directionally right and quantitatively empty — recorded here because the
next reader of that claim deserves the magnitude beside it.

This lives in its own module rather than inside `_io_boundary_calls` because
that file sits above the 200-LLOC soft ceiling and the walk is a separable
concern; it is exempt from tests-mirror-pairing as a `_`-prefixed private
helper (v033 D1 exemption (a)) and is exercised through
`test_no_expected_failure_mode_edges.py`.

⛔ THE FLEET NOW CARRIES THIS RESOLUTION TWICE — here and in
`fleet/_public_api_graph._through_reexports`, which fixed the same defect on
the consumption side first. That is the `i04f` shape (one analysis, two copies,
historically only one repaired), and it is why this port was owed. Unifying
them is a separate, larger change: the fleet-side walk carries an ambiguity
verdict this one has no consumer for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.checks._io_boundary_calls import ModuleFacts

__all__: list[str] = ["first_party_edges"]


def first_party_edges(
    *,
    dotted: str,
    attr: str,
    index: Mapping[str, frozenset[Path]],
    modules: Mapping[Path, ModuleFacts],
) -> frozenset[tuple[Path, str]]:
    """Every first-party function `<dotted>.<attr>` could resolve to.

    EVERY candidate of an ambiguous suffix is followed, so an ambiguous module
    contributes MORE call edges rather than fewer — the fixpoint then has more
    ways to disqualify the caller, never fewer.

    The walk is bounded by a VISITED SET rather than a hop limit, for the reason
    `_public_api_graph._through_reexports` records: a re-export cycle is a real
    shape (two modules importing each other's names), and an arbitrary depth cap
    would silently stop resolving a legitimate chain — fail-open wearing a
    safety measure's clothing.
    """
    definers: set[tuple[Path, str]] = set()
    seen: set[Path] = set()
    frontier = list(index.get(dotted, frozenset()))
    while frontier:
        candidate = frontier.pop()
        if candidate in seen:
            continue
        seen.add(candidate)
        facts = modules[candidate]
        if attr in facts.functions:
            definers.add((candidate, attr))
        else:
            # `.get(attr, "")` rather than a `None` guard: an unbound name
            # yields an empty dotted target, which indexes to no candidate and
            # ends that branch of the walk without a second conditional.
            frontier.extend(index.get(facts.imported_names.get(attr, ""), frozenset()))
    return frozenset(definers)
