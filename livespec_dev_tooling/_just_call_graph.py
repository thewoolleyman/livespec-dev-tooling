"""The static call graph of a repository's justfile recipes and the scripts they call.

`delegated_job_authority_skip` has to answer "which aggregate does this gate Job
recipe reach, and by what route?" without running anything: a gate Job runs on a
cluster the checking host cannot reach, and the question is a fact about the
committed tree. This module owns the reading half of that answer, the edges.
`_delegated_job_routes` owns the judging half.

THE GRAPH IS STATIC AND DELIBERATELY SHALLOW, which is the direction a check
shipped warn-default can afford. A node is a justfile recipe or a repository
script (`.sh`, `.bash`, `.py`) that a recipe or another script names by path. An
edge is one of three things: a recipe dependency from the recipe's header, a
`just <recipe>` invocation, or a script path. What it does NOT follow is a
computed one: `just "$target"`, `bash "$(pick_script)"`, a `python -m` module.
A route the reader cannot see is a route the check cannot convict, so an
unreadable shape reads as no finding rather than as a guess.

Two guards keep prose from being read as a call. A line that begins with `echo`
or `printf` calls nothing, and a `just` word inside an open quote is text rather
than an invocation. Without them a message such as "run `just check-x` to see"
would make the recipe it names look reachable from every script that prints it.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "CallGraph",
    "Node",
    "Recipe",
    "build_call_graph",
    "callees",
    "invoked_nodes",
    "node_text",
]

_JUSTFILE_NAME = "justfile"
_IMPORT_LINE = re.compile(r"^import\??[ \t]+['\"](?P<path>[^'\"]+)['\"]", re.MULTILINE)
_IMPORT_DEPTH_LIMIT = 4

# `name param *rest: dep other`. The negative lookahead keeps `name := value`
# assignments and `set shell := [...]` settings from reading as recipes.
_RECIPE_HEADER = re.compile(
    "".join(
        (
            r"^@?(?P<name>[A-Za-z_][A-Za-z0-9_-]*)",
            r"(?P<params>(?:[ \t]+[*+$]*[A-Za-z_][A-Za-z0-9_-]*(?:=[^\s:]+)?)*)",
            r"[ \t]*:(?!=)[ \t]*(?P<dependencies>[^#\n]*)",
        )
    )
)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_JUST_WORD = re.compile(r"(?<![\w./$-])just[ \t]+(?P<rest>[^\n;&|)<>`]*)")
_SCRIPT_PATH = re.compile(
    r"(?<![\w./-])(?P<path>(?:\$\{?\w+\}?/)?(?:\.{1,2}/)?(?:[\w.-]+/)*[\w.-]+\.(?:sh|bash|py))(?![\w-])"
)
_VARIABLE_PREFIX = re.compile(r"^\$\{?\w+\}?/")
_PROSE_COMMANDS = ("echo ", "printf ")


@dataclass(frozen=True, kw_only=True)
class Node:
    """A justfile recipe or a repository script, named the way a route names it."""

    kind: str
    name: str

    def label(self) -> str:
        """The name a finding prints for this node."""
        return f"just {self.name}" if self.kind == "recipe" else self.name


@dataclass(frozen=True, kw_only=True)
class Recipe:
    """One justfile recipe as the graph reads it."""

    name: str
    parameter_count: int
    variadic: bool
    dependencies: tuple[str, ...]
    body: str


@dataclass(frozen=True, kw_only=True)
class CallGraph:
    """The recipes of one repository's justfile, plus the root its scripts live under."""

    repo_root: Path
    recipes: dict[str, Recipe]


def build_call_graph(*, repo_root: Path) -> CallGraph | None:
    """Read the repository's justfile and its imports, or `None` when it has none."""
    justfile_text = _read_with_imports(
        path=repo_root / _JUSTFILE_NAME, repo_root=repo_root, depth=0
    )
    if justfile_text is None:
        return None
    return CallGraph(repo_root=repo_root, recipes=_parse_recipes(justfile_text=justfile_text))


def _read_with_imports(*, path: Path, repo_root: Path, depth: int) -> str | None:
    """A justfile's text with every readable `import` appended, bounded in depth."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if depth >= _IMPORT_DEPTH_LIMIT:
        return text
    parts = [text]
    for matched in _IMPORT_LINE.finditer(text):
        imported = _read_with_imports(
            path=path.parent / matched.group("path"), repo_root=repo_root, depth=depth + 1
        )
        if imported is not None:
            parts.append(imported)
    return "\n".join(parts)


def _parse_recipes(*, justfile_text: str) -> dict[str, Recipe]:
    """Every recipe in `justfile_text`, keyed by name; a later definition wins."""
    recipes: dict[str, Recipe] = {}
    lines = justfile_text.splitlines()
    index = 0
    while index < len(lines):
        header = _RECIPE_HEADER.match(lines[index])
        index += 1
        if header is None:
            continue
        body_lines: list[str] = []
        while index < len(lines) and (not lines[index] or lines[index][0] in " \t"):
            body_lines.append(lines[index])
            index += 1
        params = header.group("params").split()
        recipe = Recipe(
            name=header.group("name"),
            parameter_count=len(params),
            variadic=any(param.startswith(("*", "+")) for param in params),
            dependencies=_dependencies(header_tail=header.group("dependencies")),
            body=_strip_comments(text="\n".join(body_lines)),
        )
        recipes[recipe.name] = recipe
    return recipes


def _dependencies(*, header_tail: str) -> tuple[str, ...]:
    """The recipe names a header's dependency list names, before and after `&&`."""
    names = (word.strip("()") for word in header_tail.split() if word != "&&")
    return tuple(name for name in names if _NAME.fullmatch(name))


def _strip_comments(*, text: str) -> str:
    """The text without its full-line comments, so prose cannot read as a call."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def node_text(*, graph: CallGraph, node: Node) -> str:
    """The comment-stripped text a node's reads and calls are judged on."""
    if node.kind == "recipe":
        recipe = graph.recipes.get(node.name)
        return "" if recipe is None else recipe.body
    try:
        raw = (graph.repo_root / node.name).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    return _strip_comments(text=raw)


def callees(*, graph: CallGraph, node: Node) -> list[Node]:
    """The nodes `node` reaches in one step, in the order they are named."""
    reached: list[Node] = []
    if node.kind == "recipe":
        recipe = graph.recipes.get(node.name)
        if recipe is None:
            return []
        reached.extend(
            Node(kind="recipe", name=name) for name in recipe.dependencies if name in graph.recipes
        )
    reached.extend(invoked_nodes(graph=graph, node=node, text=node_text(graph=graph, node=node)))
    return list(dict.fromkeys(reached))


def invoked_nodes(*, graph: CallGraph, node: Node, text: str) -> list[Node]:
    """The recipes and scripts the lines of `text` invoke, as seen from `node`."""
    reached: list[Node] = []
    for line in text.splitlines():
        if line.lstrip().startswith(_PROSE_COMMANDS):
            continue
        reached.extend(_recipes_invoked(graph=graph, line=line))
        reached.extend(_scripts_named(graph=graph, node=node, line=line))
    return reached


def _recipes_invoked(*, graph: CallGraph, line: str) -> list[Node]:
    """The recipes `just ...` invocations on one line run, consuming each one's arguments."""
    reached: list[Node] = []
    for matched in _JUST_WORD.finditer(line):
        before = line[: matched.start()]
        if before.count('"') % 2 or before.count("'") % 2:
            continue
        reached.extend(_recipes_in_argv(graph=graph, argv=_split(text=matched.group("rest"))))
    return reached


def _split(*, text: str) -> list[str]:
    """Shell-split `text`, falling back to whitespace when its quotes do not balance."""
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _recipes_in_argv(*, graph: CallGraph, argv: list[str]) -> list[Node]:
    """Walk a `just` argv: skip flags and assignments, then name each recipe in turn."""
    reached: list[Node] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        index += 1
        if token.startswith("-") or "=" in token:
            continue
        recipe = graph.recipes.get(token)
        if recipe is None:
            break
        reached.append(Node(kind="recipe", name=recipe.name))
        if recipe.variadic:
            break
        index += recipe.parameter_count
    return reached


def _scripts_named(*, graph: CallGraph, node: Node, line: str) -> list[Node]:
    """The repository scripts a line names by path, resolved from the root or the caller."""
    reached: list[Node] = []
    caller_dir = (graph.repo_root / node.name).parent if node.kind == "script" else None
    root = graph.repo_root.resolve()
    for matched in _SCRIPT_PATH.finditer(line):
        relative = _VARIABLE_PREFIX.sub("", matched.group("path"))
        candidates = [graph.repo_root / relative]
        if caller_dir is not None:
            candidates.append(caller_dir / relative)
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_file() and resolved.is_relative_to(root):
                reached.append(Node(kind="script", name=resolved.relative_to(root).as_posix()))
                break
    return reached
