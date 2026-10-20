"""_tests_host_path_reach — which real host paths one expression in a test NAMES.

The resolver half of `tests_host_path_free`: it answers "what host paths does
this expression name", and nothing about whether naming one is a violation.
That question — which USES are filesystem targets — belongs to the check
module, which reads this one.

A host path is an absolute path under `/etc`, `/var`, `/usr`, `/opt` or `/run`.
A literal is followed through plain name bindings to a fixed point, so a
module-level `Path("/etc/…")` constant resolves wherever the name reaches, and
the check can report the line where it is USED rather than where it was spelled.

WHAT RESOLVES TO NOTHING. A path DERIVED from the `tmp_path` fixture carries no
host-path literal at all, so it never matches; an expression that merely MIXES
the fixture in is treated as derived from it too, because that is the sanctioned
shape and a test writing under its own `tmp_path` tree judges the tree rather
than the machine.

Output discipline: this module emits nothing; it is pure resolution.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator, Mapping

__all__: list[str] = [
    "bound_names",
    "named_paths",
    "string_constants",
]


_HOST_ROOT = re.compile(r"^/(?:etc|opt|run|usr|var)(?:/|$)")

# The fixtures a path may be derived FROM. An expression that reaches one of
# these is the sanctioned shape, whatever else it names.
_DERIVING_NAMES = frozenset({"tmp_path", "tmp_path_factory"})


def _host_paths(*, node: ast.AST) -> frozenset[str]:
    """Every host-path string literal anywhere inside one expression."""
    return frozenset(
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and _HOST_ROOT.match(child.value) is not None
    )


def _reached_names(*, node: ast.AST) -> frozenset[str]:
    return frozenset(child.id for child in ast.walk(node) if isinstance(child, ast.Name))


def named_paths(*, node: ast.expr, bound: Mapping[str, frozenset[str]]) -> frozenset[str]:
    """The host paths this expression names, or NOTHING when it derives from a fixture."""
    names = _reached_names(node=node)
    if names & _DERIVING_NAMES:
        return frozenset()
    return _host_paths(node=node).union(*(bound.get(name, frozenset()) for name in names))


def _assignments(
    *, tree: ast.Module, bound: Mapping[str, frozenset[str]]
) -> Iterator[tuple[str, frozenset[str]]]:
    """Each plain name binding, with the host paths its value names under `bound`."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        value = node.value
        if value is None:
            continue
        paths = named_paths(node=value, bound=bound)
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            for name in _reached_names(node=target):
                yield name, paths


def bound_names(*, tree: ast.Module) -> Mapping[str, frozenset[str]]:
    """Resolve name bindings to the host paths they name, to a fixed point.

    Iterated rather than single-pass because the binding that names the literal
    and the binding that carries it to the filesystem are often two statements
    apart (`_ROOT = "/etc/livespec"` then `_REGISTRY = Path(_ROOT) / "x.json"`),
    and `ast.walk` visits them in breadth-first order rather than in source
    order. Monotone — every round only ever ADDS paths — so it terminates.
    """
    bound: dict[str, frozenset[str]] = {}
    changed = True
    while changed:
        changed = False
        for name, paths in _assignments(tree=tree, bound=bound):
            merged = bound.get(name, frozenset()) | paths
            if merged != bound.get(name, frozenset()):
                bound[name] = merged
                changed = True
    return bound


def string_constants(*, tree: ast.Module) -> Mapping[str, str]:
    """Module-level `NAME = "literal"` bindings, so a mapping KEY held in one resolves."""
    constants: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in node.targets:
            for name in _reached_names(node=target):
                constants[name] = value.value
    return constants
