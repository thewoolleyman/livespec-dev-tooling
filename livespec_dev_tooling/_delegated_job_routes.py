"""Which routes from a delegated gate Job recipe reach an authority member unskipped.

`_gate_authority_skip` makes the delegated client name the authority members
under the repository's own skip variable, so a gate Job leaves them to the
pushing host. That works only when the recipe the Job runs actually reads the
variable. A route that reaches the aggregate another way runs the member in a
pod that holds no credential, where it correctly fails closed, so every correct
tree reads red and nobody sees why. This module walks the static call graph of
`_just_call_graph` from a Job recipe and reports each such route.

THREE KINDS OF NODE END A ROUTE, and each is judged differently:

- The repository's `check` recipe. It reads the skip variable by definition,
  because that read is how the variable is resolved in the first place, so a
  route arriving here honours it unless something on the way overwrote the list
  with a literal instead of appending to it.
- An AGGREGATE RUNNER: a script or recipe the `check` recipe hands its target or
  skip array to. A route reaching one WITHOUT passing through `check` has
  bypassed the read. It is honoured only when a node on the route names the skip
  variable (a script that reads it and then passes the list on), or when the
  runner itself skips every authority member under the gate Job's context
  variable `LIVESPEC_GATE_CONTEXT`.
- A recipe that IS a declared authority member, run directly. Judged the same
  way, for that one member.

A route that ends in none of these runs no authority member by any path this
reader can see, which is how a fixed list of other members passes.

NAMING THE VARIABLE IS TAKEN AS HONOURING THE LIST. The reader sees that a node
mentions the variable, not what the node does with it, so a script that reads it
and then drops it would pass. That is the direction a warn-default check can
afford, and the alternative, flagging every script that mentions the variable
without proving it forwards the list, would convict the shapes the fleet
actually ships.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling._just_call_graph import (
    CallGraph,
    Node,
    build_call_graph,
    callees,
    invoked_nodes,
    node_text,
)

__all__: list[str] = ["RouteFinding", "job_recipe_name", "unhonoured_routes"]

_CHECK_RECIPE = "check"
_GATE_CONTEXT = "LIVESPEC_GATE_CONTEXT"
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*")
# An array expansion named for the targets or the skip list, handed to a runner:
# `"${skip_targets[@]}"` or `"${targets[@]}"`.
_LIST_HANDED_ON = re.compile(r"\$\{[A-Za-z_]\w*(?:targets|skip)\w*\[[@*]\]\}", re.IGNORECASE)


@dataclass(frozen=True, kw_only=True)
class RouteFinding:
    """One authority member a Job recipe reaches without honouring the skip variable."""

    job_recipe: str
    member: str
    route: tuple[str, ...]


def job_recipe_name(*, entry: str) -> str | None:
    """The recipe a suite entry names: its first token that is not a `name=value` assignment."""
    for token in entry.split():
        if _ASSIGNMENT.fullmatch(token) is None:
            return token
    return None


def unhonoured_routes(
    *, repo_root: Path, job_recipes: tuple[str, ...], members: tuple[str, ...], skip_variable: str
) -> list[RouteFinding]:
    """Every route from a Job recipe to an authority member that leaves the skip list unread."""
    graph = build_call_graph(repo_root=repo_root)
    if graph is None:
        return []
    runners = _aggregate_runners(graph=graph)
    findings: dict[tuple[str, str, Node], RouteFinding] = {}
    for job_recipe in job_recipes:
        start = Node(kind="recipe", name=job_recipe)
        if job_recipe not in graph.recipes:
            continue
        for terminal, route, reached in _terminal_routes(
            graph=graph, start=start, runners=runners, members=members
        ):
            if _honoured(graph=graph, terminal=terminal, route=route, variable=skip_variable):
                continue
            for member in reached:
                key = (job_recipe, member, terminal)
                labels = tuple(node.label() for node in route)
                _ = findings.setdefault(
                    key, RouteFinding(job_recipe=job_recipe, member=member, route=labels)
                )
    return list(findings.values())


def _aggregate_runners(*, graph: CallGraph) -> frozenset[Node]:
    """The nodes the `check` recipe hands its target or skip array to."""
    check = graph.recipes.get(_CHECK_RECIPE)
    if check is None:
        return frozenset()
    check_node = Node(kind="recipe", name=_CHECK_RECIPE)
    handed_on = (line for line in check.body.splitlines() if _LIST_HANDED_ON.search(line))
    return frozenset(
        reached
        for line in handed_on
        for reached in invoked_nodes(graph=graph, node=check_node, text=line)
    )


def _terminal_routes(
    *, graph: CallGraph, start: Node, runners: frozenset[Node], members: tuple[str, ...]
) -> list[tuple[Node, tuple[Node, ...], tuple[str, ...]]]:
    """Each (terminal node, route to it, authority members it runs), depth first."""
    found: list[tuple[Node, tuple[Node, ...], tuple[str, ...]]] = []
    pending: list[tuple[Node, ...]] = [(start,)]
    while pending:
        route = pending.pop()
        node = route[-1]
        ran = _members_run_by(node=node, runners=runners, members=members)
        if ran:
            found.append((node, route, ran))
            continue
        pending.extend(
            (*route, callee)
            for callee in reversed(callees(graph=graph, node=node))
            if callee not in route
        )
    return found


def _members_run_by(
    *, node: Node, runners: frozenset[Node], members: tuple[str, ...]
) -> tuple[str, ...]:
    """The authority members a route ending at `node` runs, empty when it ends nowhere."""
    if node in runners or (node.kind == "recipe" and node.name == _CHECK_RECIPE):
        return members
    if node.kind == "recipe" and node.name in members:
        return (node.name,)
    return ()


def _honoured(*, graph: CallGraph, terminal: Node, route: tuple[Node, ...], variable: str) -> bool:
    """Whether the route carries the skip list to the aggregate it reaches."""
    mentions = re.compile(rf"\b{re.escape(variable)}\b")
    texts = [node_text(graph=graph, node=node) for node in route]
    if terminal.kind == "recipe" and terminal.name == _CHECK_RECIPE:
        return not any(_overwrites(text=text, variable=variable) for text in texts[:-1])
    if any(mentions.search(text) for text in texts):
        return True
    return _GATE_CONTEXT in texts[-1]


def _overwrites(*, text: str, variable: str) -> bool:
    """Whether a node assigns the variable a value without reading its inherited one."""
    name = re.escape(variable)
    assigned = re.search(rf"(?:^|[\s;&(])(?:export[ \t]+)?{name}=", text, re.MULTILINE)
    return assigned is not None and not re.search(rf"\$\{{?{name}\b", text)
