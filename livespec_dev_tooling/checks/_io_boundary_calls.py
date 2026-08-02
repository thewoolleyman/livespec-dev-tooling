"""_io_boundary_calls — what one call MEANS: an I/O boundary, an edge, or doubt.

The clause (c) half of livespec v179 member 1, plus the call-graph edges its
clause (d) fixpoint walks. Split from `_no_expected_failure_mode` at the seam
between the two questions: this module answers "what is this call", and that
one answers "what do the clauses conclude".

**THE RECEIVER IS RESOLVED, NEVER THE VERB.** `os.environ.get` is I/O because
`os` is; `settings.get` is not, because the receiver is a parameter. A
terminal-name match once flagged ten total functions in this repo as touching
I/O and only three were real — most hits were exactly `dict.get`. So `get` is
not an I/O verb here, and neither is `run`: `runner.run(...)` on a parameter is
an INJECTED SEAM, the shape this fleet uses to make I/O testable, and it is the
same distinction that convicted `fetch_manifest` under clause (e) rather than
clause (c). `subprocess.run` is still caught, through its resolved module.

**THE ONE PLACE THIS IS NOT CONSERVATIVE, STATED RATHER THAN HIDDEN.** For a
call whose receiver resolves to NOTHING — `path.read_text()`, where `path` is a
parameter — there is no binding to consult and only the verb is left.
`_UNRESOLVED_RECEIVER_IO_VERBS` decides there, and a non-match is treated as
not-I/O. Treating every such call as doubt instead would disqualify any
function that calls a method on any argument, which is nearly all of them: the
member would exempt approximately nothing, defeating the clause rather than
enforcing it. Everywhere else — an unresolvable callee NAME, a call on a call —
doubt DISQUALIFIES, per the ratified direction.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks._import_resolution import (
    module_aliases,
    module_name,
    name_imports,
    top_level_functions,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__: list[str] = ["CallOutcome", "ModuleFacts", "calls_of"]


# Third-party and stdlib modules whose surface IS the filesystem, a process,
# the network, or the environment. A call whose receiver resolves to one of
# these through an `import` binding is an I/O boundary call.
_IO_MODULES: frozenset[str] = frozenset(
    {
        "asyncio",
        "fileinput",
        "ftplib",
        "glob",
        "http",
        "httpx",
        "importlib",
        "io",
        "multiprocessing",
        "os",
        "pathlib",
        "pkgutil",
        "requests",
        "select",
        "shutil",
        "signal",
        "smtplib",
        "socket",
        "sqlite3",
        "ssl",
        "subprocess",
        "sys",
        "sysconfig",
        "tempfile",
        "urllib",
    }
)

# Builtins that ARE an I/O boundary. Every other builtin is a pure operation.
_IO_BUILTINS: frozenset[str] = frozenset({"input", "open", "print"})

# Members of an `_IO_MODULES` module that touch NOTHING. `_IO_MODULES` decides
# at MODULE granularity, which is right for `subprocess` and `socket` and wrong
# for these: `io.StringIO` is an in-memory buffer and `Path(...)` is a value
# construction. MEASURED — the three they wrongly convicted are
# `_no_except_outside_io_markers.comment_lines`, `.statement_colons` (whose only
# "I/O" is tokenizing a string already in hand) and
# `_subagent_stop_guard_transcript.extract_created_worktree_paths` (string in,
# list of Path out).
#
# ⛔ MATCHED EXACTLY, NEVER AS A PREFIX, and that is what keeps this from being
# a hole. `Path.cwd()` reads the process working directory and resolves to
# `pathlib.cwd` here, which is absent from this set and stays disqualified;
# `Path(x).read_text()` is caught by the unresolved-receiver verb set one step
# later. A member added here must be pure on EVERY receiver, not merely usually.
#
# ⛔ THE SPELLING IS THE TRAP, AND IT IS MUTATION-PROVEN. Entries are matched
# against the dotted form rebuilt from the IMPORT BINDING below, never against
# the runtime module. `os.path` IS `posixpath` at runtime, and entries spelled
# `posixpath.<member>` are INERT: measured, they moved `livespec-overseer`
# 194 -> 194 while the `os.path.` spelling moved it 194 -> 173. Do not "tidy"
# these to the runtime identity — `test_a_lexical_os_path_member_is_not_an_io_
# boundary` reds if you do.
#
# ⚠️ AND ONE IMPORT FORM IS A MEASURED, DELIBERATE GAP. `from os import path`
# binds `path -> os`, so the rendered form is `os.<member>` with NO middle
# segment and misses this set; closing it needs a second entry per member. Those
# are NOT added because that form appears in ZERO first-party files across all
# eight code-carrying repos, while `import os` appears in 141. Seven inert
# entries would enlarge a set that reads as coverage while covering nothing.
# Pinned by `test_the_from_os_import_path_spelling_is_a_measured_gap_not_a_hole`.
_PURE_IO_MODULE_MEMBERS: frozenset[str] = frozenset(
    {
        "io.BytesIO",
        "io.StringIO",
        "pathlib.PurePath",
        "pathlib.PurePosixPath",
        "pathlib.PureWindowsPath",
        "pathlib.Path",
        # `os.path`'s LEXICAL half — string in, string out, touching nothing.
        # Each was driven with adverse input on CPython 3.10.16, the fleet's
        # `requires-python` FLOOR, over the empty string, `/`, `//`, `..`, `.`,
        # an embedded NUL, a lone surrogate, a 4096-character path, a backslash
        # and `~nosuchuser`. NONE raised.
        #
        # ⛔ THE BAR HERE IS PURITY, NOT MERELY NON-FAILABILITY, AND THAT
        # DISTINCTION IS WHAT KEEPS THIS SET FROM WIDENING WRONGLY. Measured on
        # the same floor, `os.path.exists`, `.isfile` and `.isdir` do not raise
        # either — they swallow `OSError` — but they READ THE FILESYSTEM, so
        # their answer depends on the world. That is the in-band conflation the
        # railway exists to remove. Cannot-fail is NECESSARY AND NOT SUFFICIENT.
        #
        # DELIBERATELY ABSENT, each with the reason it is absent:
        #   `realpath`   raises `ValueError` on an embedded NUL; resolves links.
        #   `relpath`    raises `ValueError` on the empty string.
        #   `getsize`    raises `FileNotFoundError`.
        #   `abspath`    does NOT raise on any adverse input above — it is out
        #                because it calls `os.getcwd()`, so it READS PROCESS
        #                STATE and can fail when the cwd is unlinked. It looks
        #                purer than these seven; that is why the reason is here.
        #   `expanduser` does NOT raise on `~nosuchuser` on the floor — it
        #                returns the path unchanged. It is out for reading
        #                `HOME` and the passwd database: ENVIRONMENT access.
        #                ⚠️ `pathlib.Path.expanduser` DOES raise `RuntimeError`.
        #                That is a DIFFERENT function sharing a name, and
        #                importing its result here would be this module's own
        #                defect one line down: the NAME IS NOT THE FUNCTION.
        "os.path.basename",
        "os.path.dirname",
        "os.path.isabs",
        "os.path.join",
        "os.path.normpath",
        "os.path.split",
        "os.path.splitext",
    }
)

# Verbs that decide an attribute call whose RECEIVER cannot be resolved. Every
# member is unambiguously a filesystem, process or socket operation on any
# plausible receiver.
#
# MEMBERSHIP NEEDS BOTH HALVES, AND THE SECOND IS WHAT THIS SET ADDS. livespec
# v184 section "ROP composition" section "What counts as an I/O boundary" makes FAILABILITY the
# criterion — a boundary is a primitive at which a failure can ORIGINATE — and
# every member below was driven with adverse input on CPython 3.10.16, the
# fleet's `requires-python` FLOOR, and raises for at least one. But failability
# is NECESSARY AND NOT SUFFICIENT here: with the receiver unresolved only the
# VERB is left, so the name must also be unambiguously an I/O surface.
#
# Deliberately ABSENT: `get`, `run`, `send`, `post`, `close`, `poll` — each is at
# least as often a mapping lookup or an injected seam in this codebase as it is
# I/O, and a name match on them is the exact defect that mis-flagged ten total
# functions.
#
# ⛔ AND `group` IS ABSENT FOR THAT SAME REASON DESPITE BEING FAILABLE — the
# third instance of that defect, measured. `Path.group()` raises
# `FileNotFoundError`, so it passes the failability half; `re.Match.group()` is a
# pure string operation that dominates the name here. Adding it moved this repo
# 24 -> 34 offenders and ALL TEN additions were `match.group(...)` sites, while
# `open` / `readlink` / `owner` / `truncate` together added ZERO. Pinned by
# `test_group_is_refused_despite_being_failable`.
#
# ⛔ ABSENT BY MEASURED DETERMINATION, not oversight — v184 requires the
# determination recorded WITH its evidence. `chown`, `walk`, `listdir` and
# `scandir` have NO `Path` method on the floor (`Path.walk` is 3.12+), so they
# are only ever reached as `os.<verb>(...)`, whose receiver RESOLVES through the
# import binding and is already caught by `_IO_MODULES`. Listing them would be
# inert.
#
# ⚠️ `truncate`'s RECEIVER IS A FILE OBJECT, NOT A PATH. `Path.truncate` does not
# exist on any supported version, so a reader checking `dir(Path)` would conclude
# the verb is inert and drop it. `handle.truncate()` is the live shape, and a
# handle held in a parameter is exactly the unresolved receiver this set governs.
#
# ⛔ THE FILESYSTEM PREDICATES ARE NOT TOTAL AND MUST NOT BE REMOVED. An earlier
# reading held that `exists` / `is_file` / `is_dir` "cannot fail" and belonged
# out; that premise is REFUTED and was retracted in livespec v185. `pathlib`
# swallows only `(ENOENT, ENOTDIR, EBADF, ELOOP)` and re-raises everything else,
# so each RAISES `PermissionError` on a path under an unreadable directory. Total
# with respect to four errnos is strictly weaker than total. Pinned by
# `test_the_filesystem_predicates_are_not_removed`.
_UNRESOLVED_RECEIVER_IO_VERBS: frozenset[str] = frozenset(
    {
        "accept",
        "bind",
        "chmod",
        "connect",
        "exists",
        "expanduser",
        "glob",
        "hardlink_to",
        "is_dir",
        "is_fifo",
        "is_file",
        "is_socket",
        "is_symlink",
        "iterdir",
        "listen",
        "lstat",
        "mkdir",
        "open",
        "owner",
        "read",
        "read_bytes",
        "read_text",
        "readline",
        "readlines",
        "readlink",
        "recv",
        "rename",
        "replace",
        "resolve",
        "rglob",
        "rmdir",
        "samefile",
        "sendall",
        "stat",
        "symlink_to",
        "touch",
        "truncate",
        "unlink",
        "urlopen",
        "write",
        "write_bytes",
        "write_text",
        "writelines",
    }
)

_BUILTIN_NAMES: frozenset[str] = frozenset(dir(builtins))


@dataclass(frozen=True, kw_only=True)
class CallOutcome:
    """What one call contributes: first-party edges, and whether it disqualifies."""

    edges: frozenset[tuple[Path, str]]
    disqualifies: bool


def _root_name(*, node: ast.expr) -> str | None:
    """The leftmost `Name` of a dotted expression, or None if it has none."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


class ModuleFacts:
    """One module's parsed tree plus the bindings a call resolution needs."""

    def __init__(
        self, *, rel: Path, tree: ast.Module, index: Mapping[str, frozenset[Path]]
    ) -> None:
        self.rel = rel
        current = module_name(rel=rel)
        self.aliases = module_aliases(tree=tree, current=current, index=index)
        # `from <first-party module> import name` — the name is bound to a
        # function in a module this repo owns.
        self.imported_names = {
            name: dotted for dotted, name in name_imports(tree=tree, current=current, index=index)
        }
        # Every module this file binds by any `import`, first-party or not,
        # keyed by the local name — so a receiver can be classified.
        self.import_roots: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.import_roots[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    _ = self.import_roots.setdefault(alias.asname or alias.name, node.module)
        self.functions = top_level_functions(tree=tree)
        self.classes = frozenset(node.name for node in tree.body if isinstance(node, ast.ClassDef))


def _module_is_io(*, dotted: str) -> bool:
    """Is this dotted THIRD-PARTY module name an I/O surface?

    Only the stdlib / third-party half of clause (c). The consumer's declared
    `io_trees` half is `_under_io_tree`, which resolves a first-party module to
    its defining PATH — the two limbs ask the same question of different
    namespaces, and keeping one dotted-prefix copy of the second here would be
    the spelling a later editor updates only one of.
    """
    return dotted.split(".", maxsplit=1)[0] in _IO_MODULES


def _first_party_edges(
    *,
    dotted: str,
    attr: str,
    index: Mapping[str, frozenset[Path]],
    modules: Mapping[Path, ModuleFacts],
) -> frozenset[tuple[Path, str]]:
    """Every first-party function `<dotted>.<attr>` could resolve to.

    EVERY candidate of an ambiguous suffix is returned, so an ambiguous module
    contributes MORE call edges rather than fewer — the fixpoint then has more
    ways to disqualify the caller, never fewer.
    """
    return frozenset(
        (defining, attr)
        for defining in index.get(dotted, frozenset())
        if attr in modules[defining].functions
    )


def _under_io_tree(
    *, dotted: str, index: Mapping[str, frozenset[Path]], io_trees: tuple[Path, ...]
) -> bool:
    """Does this first-party module live under a DECLARED `io_trees` prefix?

    Clause (c)'s first limb. Without it a call into the io tree resolves to an
    ordinary first-party edge and the tree's own CONTENTS decide — so a
    declared boundary that happens to hold total helpers stops being a
    boundary, which is the whole point of declaring it.
    """
    return any(
        defining.is_relative_to(tree)
        for defining in index.get(dotted, frozenset())
        for tree in io_trees
    )


def _name_call(
    *,
    name: str,
    facts: ModuleFacts,
    index: Mapping[str, frozenset[Path]],
    modules: Mapping[Path, ModuleFacts],
    io_trees: tuple[Path, ...],
) -> CallOutcome:
    """Classify `name(...)` — a bare call, not an attribute access."""
    dotted = facts.imported_names.get(name)
    if dotted is not None:
        return CallOutcome(
            edges=_first_party_edges(dotted=dotted, attr=name, index=index, modules=modules),
            disqualifies=_under_io_tree(dotted=dotted, index=index, io_trees=io_trees),
        )
    if name in facts.functions:
        return CallOutcome(edges=frozenset({(facts.rel, name)}), disqualifies=False)
    if name in _IO_BUILTINS:
        return CallOutcome(edges=frozenset(), disqualifies=True)
    bound = facts.import_roots.get(name)
    if bound is not None:
        # `from pathlib import Path` binds the MEMBER, so the dotted target is
        # the module it came from plus the bound name itself.
        return CallOutcome(
            edges=frozenset(),
            disqualifies=_module_is_io(dotted=bound)
            and f"{bound}.{name}" not in _PURE_IO_MODULE_MEMBERS,
        )
    if name in facts.classes or name in _BUILTIN_NAMES:
        return CallOutcome(edges=frozenset(), disqualifies=False)
    # An unresolvable callee: a parameter holding a callable, a local binding, a
    # decorator-produced name. Ratified direction — doubt DISQUALIFIES, so the
    # analysis demands a `Result` that may not have been needed rather than
    # excusing one that was.
    return CallOutcome(edges=frozenset(), disqualifies=True)


def _attribute_call(
    *,
    target: ast.Attribute,
    facts: ModuleFacts,
    index: Mapping[str, frozenset[Path]],
    modules: Mapping[Path, ModuleFacts],
    io_trees: tuple[Path, ...],
) -> CallOutcome:
    """Classify `<receiver>.<attr>(...)` by resolving the RECEIVER, not the verb."""
    first_party = facts.aliases.get(ast.unparse(target.value))
    if first_party is not None and first_party in index:
        return CallOutcome(
            edges=_first_party_edges(
                dotted=first_party, attr=target.attr, index=index, modules=modules
            ),
            disqualifies=_under_io_tree(dotted=first_party, index=index, io_trees=io_trees),
        )
    root = _root_name(node=target.value)
    bound = facts.import_roots.get(root) if root is not None else None
    if bound is not None:
        # Rebuild the dotted target with the RESOLVED root substituted for the
        # local one, so `import io as _io` reaches the same answer as `import
        # io`. A deeper receiver (`os.path.join`) keeps its middle segments and
        # simply misses the pure set, which is the safe direction.
        rendered = ast.unparse(target.value)
        middle = rendered.split(".", maxsplit=1)[1] if "." in rendered else ""
        dotted = ".".join(part for part in (bound, middle, target.attr) if part)
        return CallOutcome(
            edges=frozenset(),
            disqualifies=_module_is_io(dotted=bound) and dotted not in _PURE_IO_MODULE_MEMBERS,
        )
    # The receiver resolves to nothing — see the module docstring for why the
    # verb decides here, and why that is the one non-conservative step.
    return CallOutcome(edges=frozenset(), disqualifies=target.attr in _UNRESOLVED_RECEIVER_IO_VERBS)


def calls_of(
    *,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    facts: ModuleFacts,
    index: Mapping[str, frozenset[Path]],
    modules: Mapping[Path, ModuleFacts],
    io_trees: tuple[Path, ...],
) -> CallOutcome:
    """Fold every call in `func` into its edges plus one disqualification bit.

    The bit folds clause (c) together with the DOUBT half of clause (d): both
    mean the same thing to the caller — this function cannot be SHOWN to have
    no expected failure mode.
    """
    edges: set[tuple[Path, str]] = set()
    disqualifies = False
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            outcome = _name_call(
                name=node.func.id,
                facts=facts,
                index=index,
                modules=modules,
                io_trees=io_trees,
            )
        elif isinstance(node.func, ast.Attribute):
            outcome = _attribute_call(
                target=node.func,
                facts=facts,
                index=index,
                modules=modules,
                io_trees=io_trees,
            )
        else:
            # A call on a call, a subscript, a lambda — unresolvable by
            # construction, so doubt disqualifies.
            outcome = CallOutcome(edges=frozenset(), disqualifies=True)
        edges |= outcome.edges
        disqualifies = disqualifies or outcome.disqualifies
    return CallOutcome(edges=frozenset(edges), disqualifies=disqualifies)
