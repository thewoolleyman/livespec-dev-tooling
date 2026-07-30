"""The CENTRAL-vantage row: a declared public surface checked against reality.

livespec v178 declares public API to be CONSUMED ACROSS A BOUNDARY, measured
FLEET-WIDE, and `721o` had each repo DECLARE the surface its siblings reach in
`cross_repo_public_api`. A declaration nobody verifies is `pure_trees = []`
wearing a new name, so this row re-measures the fleet's ACTUAL consumption
graph and fails a member whose declaration omits a name another member imports.

A repo-local check STRUCTURALLY CANNOT SEE A SIBLING'S IMPORT. That is not a
gap to be closed from inside a checkout — it is why this row exists, and it is
the mechanism that would have prevented `livespec-dev-tooling-dx8l`, where
`parse_manifest` was converted on a repo-local reading that found no importer
and a sibling's hook turned that repo's master red within minutes.

THE CRITERION HAS THREE CLAUSES, AND THE THIRD IS LOAD-BEARING. A name is owed
a declaration when it is (1) consumed by ANOTHER member, (2) not declared, and
(3) not ALREADY public by a repo-LOCAL v178 form. Without (3) the row would
demand declarations for names the local check already scopes — manufacturing
work, which is the failure mode that discredits a row on its first real run.

⛔ THIS ROW IS NOT YET REGISTERED IN `OBLIGATION_ROWS`, AND THAT IS DELIBERATE
RATHER THAN FORGOTTEN. Registration is the step that makes it gate; Phase 3
proved an unregistered row is walked by neither engine. It ships inert because
the pre-registration measurement (2026-07-30, all nine members, 0 skipped —
`plan/rop-railway-enforcement/5cai-fleet-measurement.md`) found TWENTY genuine
undeclared consumptions: NINE in `livespec-dev-tooling` and ELEVEN in
`livespec-runtime`. Registering at error today fires both blocking modes — this
repo's own failing row would fail the registering PR's OWN CI so it could not
land, and the sibling's would break the scheduled sweep and the release fan-out
preflight fleet-wide. The severity is NOT softened to get around that; the
sequence is REMEDIATE-THEN-FLIP, this repo's own ratified doctrine (v034
carve-out 1). See `livespec-dev-tooling-wdn7` and `-nkkv`.

WHAT THE ROW PUTS IN ITS OWN OUTPUT RATHER THAN IN THIS DOCSTRING, because an
operator reads the finding and not the source:

- **The GUARD WARNING.** Finding the import is NOT finding the guard. A
  consumer's `if x is None` does not FAIL against a `Result` — the test is
  permanently False, so the guard silently STOPS BEING A GUARD and control
  flows on into attribute access. On an access gate the marker then goes STALE
  rather than failing closed. This row can name the consumption SITES; a human
  must read each site's guard.
- **The STATIC BLIND SPOT.** The oracle cannot see `getattr` / `importlib` /
  string dispatch, and it cannot see a file it failed to parse.
- **v037 BOUND 4** — the `total_absence_returns` count per repo AND fleet-wide.
  It is the only bound of v179 member 2 that no repo-local check can supply,
  because no checkout can see the other eight.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._public_api_consumption import (  # noqa: E402
    repo_local_public_names,
)
from livespec_dev_tooling.config import ConfigParseError, load_config  # noqa: E402
from livespec_dev_tooling.fleet._context import (  # noqa: E402
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._member_sources import read_member_sources  # noqa: E402
from livespec_dev_tooling.fleet._public_api_graph import (  # noqa: E402
    ConsumptionEdge,
    FleetConsumption,
    MemberSources,
    cross_member_consumption,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.config import Config

__all__: list[str] = [
    "assert_cross_repo_public_api_declared",
    "fleet_consumption",
]


_CACHE_KEY = "fleet-public-api-consumption"
_GUARD_WARNING = (
    "FINDING THE IMPORT IS NOT FINDING THE GUARD: a consumer's `if x is None` "
    "does not FAIL against a Result -- it is permanently False, so the guard "
    "stops being a guard and control flows into attribute access. Read each "
    "consumption site named above before converting anything."
)
_BLIND_SPOT = (
    "STATIC BLIND SPOT: this oracle cannot see getattr / importlib / string "
    "dispatch, so absence from this list is not proof of no consumer."
)


def _build(*, ctx: FleetContext) -> FleetConsumption:
    """Read every roster member's tree and compute the fleet consumption graph."""
    sources: dict[str, MemberSources] = {}
    configs: dict[str, Config] = {}
    unavailable: dict[str, str] = {}
    for member in ctx.members:
        snapshot = ctx.member_tree_snapshot(repo=member.repo)
        if isinstance(snapshot, IOFailure):
            unavailable[member.repo] = (
                f"tree unreadable ({unsafe_perform_io(snapshot.failure()).kind})"
            )
            continue
        root = unsafe_perform_io(snapshot.unwrap()).root
        try:
            config = load_config(repo_root=root)
        except ConfigParseError as invalid:
            # NARROW, and the arm is genuinely inhabited: a member whose
            # `[tool.livespec_dev_tooling]` block does not parse is exactly the
            # state the v033 hard-error introduced, and it must reach this row
            # as a NAMED skip rather than as a raise through a nine-member sweep.
            unavailable[member.repo] = f"pyproject unparseable ({invalid})"
            continue
        read = read_member_sources(root=root, config=config)
        if isinstance(read, IOFailure):
            unavailable[member.repo] = (
                f"sources unreadable ({unsafe_perform_io(read.failure()).file})"
            )
            continue
        configs[member.repo] = config
        sources[member.repo] = unsafe_perform_io(read.unwrap())
    return FleetConsumption(
        graph=cross_member_consumption(members=sources),
        sources=sources,
        configs=configs,
        unavailable=unavailable,
    )


def fleet_consumption(*, ctx: FleetContext) -> FleetConsumption:
    """The fleet graph for this run, computed at most ONCE.

    The row is called once per MEMBER and needs every member's tree each time,
    so an unmemoized build would read the whole fleet once per member — the
    9-to-81 multiplication `livespec-dev-tooling-k76y` exists to prevent.
    """
    cached = ctx.consumption_cache.get(_CACHE_KEY)
    if cached is not None:
        return cached
    built = _build(ctx=ctx)
    ctx.consumption_cache[_CACHE_KEY] = built
    return built


def _absence_note(*, state: FleetConsumption, repo: str) -> str:
    """v037 bound 4: the `total_absence_returns` count here and fleet-wide."""
    here = len(state.configs[repo].total_absence_returns)
    fleet = sum(len(config.total_absence_returns) for config in state.configs.values())
    return f"total_absence_returns declared: {here} here, {fleet} fleet-wide"


def _unparsed_note(*, state: FleetConsumption, repo: str) -> str:
    """Name the member's files the oracle could not read, or say none."""
    unreadable = sorted(
        item.file.as_posix() for item in state.graph.unparsed if item.member == repo
    )
    if not unreadable:
        return ""
    return f" UNPARSED (measured as holding nothing): {', '.join(unreadable)}."


def _undeclared(*, state: FleetConsumption, repo: str) -> tuple[ConsumptionEdge, ...]:
    """Edges into `repo` that its declaration owes and does not carry."""
    sources = state.sources[repo]
    unparsed = {item.file for item in state.graph.unparsed if item.member == repo}
    parseable = {rel: text for rel, text in sources.defining.items() if rel not in unparsed}
    declared = {(entry.file, entry.function) for entry in state.configs[repo].cross_repo_public_api}
    local = repo_local_public_names(sources=parseable)
    return tuple(
        edge
        for edge in state.graph.edges
        if edge.defining_member == repo
        and (edge.defining_file, edge.function) not in declared
        and (edge.defining_file, edge.function) not in local
    )


def _finding_lines(*, undeclared: tuple[ConsumptionEdge, ...]) -> str:
    """One line per undeclared name, naming every consumption SITE."""
    by_name: dict[str, list[str]] = {}
    for edge in undeclared:
        key = f"{edge.defining_file.as_posix()}::{edge.function}"
        site = f"{edge.consuming_member}:{edge.consuming_file.as_posix()}"
        by_name.setdefault(key, []).append(
            site if edge.uniquely_resolved else f"{site} [AMBIGUOUS]"
        )
    return "; ".join(
        f"{name} <- {', '.join(sorted(sites))}" for name, sites in sorted(by_name.items())
    )


def assert_cross_repo_public_api_declared(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`cross_repo_public_api` names every function a SIBLING actually consumes."""
    if not ctx.members:
        return RowSkip(
            reason=f"{member.repo}: fleet roster absent from the context; "
            "the cross-member consumption graph is not computable from one member"
        )
    state = fleet_consumption(ctx=ctx)
    if member.repo in state.unavailable:
        return RowSkip(reason=f"{member.repo}: {state.unavailable[member.repo]}")
    if member.repo not in state.sources:
        return RowSkip(reason=f"{member.repo}: not present in this run's fleet roster")
    absence = _absence_note(state=state, repo=member.repo)
    context = f"{absence}.{_unparsed_note(state=state, repo=member.repo)}"
    undeclared = _undeclared(state=state, repo=member.repo)
    if not undeclared:
        return RowPass(note=f"{context} {_BLIND_SPOT}")
    return RowFinding(
        message=(
            f"{member.repo}: cross_repo_public_api omits "
            f"{len({(e.defining_file, e.function) for e in undeclared})} function(s) a sibling "
            f"consumes: {_finding_lines(undeclared=undeclared)}. {context} "
            f"{_GUARD_WARNING} {_BLIND_SPOT}"
        )
    )
