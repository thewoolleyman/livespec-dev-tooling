"""no_except_outside_io — broad catches confined to marked supervisor boundaries.

Per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Supervisor discipline": narrow at the seam; broad only at
the boundary; at most one boundary per process. A NARROW
handler names specific exception types and is permitted
anywhere — it is how a seam handles an expected failure. A
BROAD handler (`except Exception`, `except BaseException`, or
a bare `except:`) is permitted ONLY as the sole boundary
catch: a direct child of `main()` in a declared supervisor
entry file, carrying one of the closed set of sanctioned
`# noqa: BLE001 — …` markers.

The enforcement labor is split: ruff `BLE001` polices catch
BREADTH at the construct level, and this check polices catch
POSITION — which trees a broad catch may live in, and which
`main()` direct-children are exempt. Neither mechanism covers
the whole rule on its own.

Files under `io_trees` are wholesale exempt; with `io_trees`
unset nothing is exempt and every source file is inspected.
The marker lives on the `except …:` clause itself, which
`ast` discards along with every other comment, so each module
is tokenized and only `COMMENT` tokens positioned on the
clause's own lines — up to and including its closing colon —
can legalize a broad catch. A marker in the handler body, or
in a string literal, is inert.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import Config, iter_py_files, load_config  # noqa: E402

__all__: list[str] = []


# The closed set of BLE001 suppression reasons, quoted from
# `livespec/SPECIFICATION/non-functional-requirements.md` §"Linter rule set".
# Any other reason wording marks a violation rather than an escape, so a
# conforming comment must BE the directive plus one sanctioned wording —
# equality, not containment: text before, around, or after a wording
# (which can invert its meaning outright) disqualifies the comment. The
# foreign-code isolation entry is a template matched by an anchored shape
# instead of equality: `<surface>` is per-site free text (non-empty, no
# angle brackets — so the literal unfilled placeholder can never conform),
# `<ErrorType>` names the captured exception type (a possibly-dotted
# identifier, never prose), and the wording ends at the literal
# `, reported`.
_SANCTIONED_FIXED_WORDINGS = frozenset(
    {
        "— sole supervisor bug-catcher: log traceback, exit 1",
        "— sole fail-open hook boundary: silent pass-through, exit 0",
        "— sole fail-closed guard boundary: deny per policy, exit 0",
        "— sole loop-iteration bug-catcher: log traceback, continue",
    }
)
_FOREIGN_CODE_WORDING_SHAPE = re.compile(
    r"\A— foreign-code isolation: [^<>\s][^<>]* crash captured as "
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*, reported\Z"
)
# Built by concatenation so this source line never itself contains the live
# directive text (kept from the containment-era implementation's rationale).
_MARKER_COMMENT_PREFIX = "# " + "noqa: BLE001 "

_BROAD_NAMES = frozenset({"Exception", "BaseException"})
_TRY_STAR_NODE_NAME = "TryStar"

_UNMARKED_REASON = (
    "broad catch at a supervisor boundary without a sanctioned "
    "`# noqa: BLE001 — …` marker is banned"
)
_MISPLACED_REASON = "broad catch outside io/ and the sole supervisor boundary is banned"


_RUFF_BLE001_SETTING = "blind-except (BLE001)"
_RUFF_EXCLUDED_REASON = "inspected file is excluded from Ruff; BLE001 backstop is absent"
_RUFF_NO_BLE_REASON = "Ruff lint select does not enable BLE/BLE001 for inspected file"


def _explicit_ruff_lint_select_configured(*, repo_root: Path) -> bool:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    text = pyproject.read_text(encoding="utf-8")
    return "[tool.ruff.lint]" in text and "select" in text


def _ruff_show_files(*, repo_root: Path, source_trees: tuple[Path, ...]) -> frozenset[Path]:
    result = subprocess.run(
        ["ruff", "check", "--show-files", "--force-exclude", *(str(path) for path in source_trees)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    resolved_root = repo_root.resolve()
    out: set[Path] = set()
    for line in result.stdout.splitlines():
        out.add(Path(line).resolve().relative_to(resolved_root))
    return frozenset(out)


def _ruff_enables_ble001(*, repo_root: Path, rel_path: Path) -> bool:
    result = subprocess.run(
        ["ruff", "check", "--show-settings", str(rel_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and _RUFF_BLE001_SETTING in result.stdout


def _find_ruff_backstop_gaps(
    *, repo_root: Path, source_trees: tuple[Path, ...], inspected_files: tuple[Path, ...]
) -> list[tuple[Path, str]]:
    """Return inspected files that Ruff will not lint with BLE001 enabled."""
    if not _explicit_ruff_lint_select_configured(repo_root=repo_root):
        return []
    ruff_files = _ruff_show_files(repo_root=repo_root, source_trees=source_trees)
    gaps: list[tuple[Path, str]] = []
    for rel_path in inspected_files:
        if rel_path not in ruff_files:
            gaps.append((rel_path, _RUFF_EXCLUDED_REASON))
        elif not _ruff_enables_ble001(repo_root=repo_root, rel_path=rel_path):
            gaps.append((rel_path, _RUFF_NO_BLE_REASON))
    return gaps


def _is_under_any(*, rel_path: Path, trees: tuple[Path, ...]) -> bool:
    return any(tree in rel_path.parents for tree in trees)


def _is_supervisor_main_file(*, rel_path: Path, config: Config) -> bool:
    if rel_path in config.supervisor_entry_files:
        return True
    return _is_under_any(rel_path=rel_path, trees=config.commands_trees)


def _is_try_node(*, node: ast.AST) -> bool:
    return isinstance(node, ast.Try) or node.__class__.__name__ == _TRY_STAR_NODE_NAME


def _supervisor_main_try_lines(*, tree: ast.Module) -> set[int]:
    """Return line numbers of `try` nodes that are direct children of `main()`'s body."""
    out: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            for stmt in node.body:
                if _is_try_node(node=stmt):
                    out.add(stmt.lineno)
    return out


def _broad_local_names(*, tree: ast.Module) -> frozenset[str]:
    """Every local name that denotes a broad builtin, including aliased imports.

    `from builtins import Exception as Broad` rebinds a broad builtin under
    a name the literal set would miss. Two evasions stay out of reach and
    are accepted as parity with ruff, which misses them too: a plain
    module-level rebinding (`Broad = Exception`) and a catch whose operand
    is a variable holding an exception tuple.
    """
    out: set[str] = set(_BROAD_NAMES)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            if alias.name in _BROAD_NAMES:
                out.add(alias.asname or alias.name)
    return frozenset(out)


def _is_broad(*, handler: ast.ExceptHandler, broad_names: frozenset[str]) -> bool:
    """True for a bare `except:`, a broad builtin, or a tuple containing one.

    The operand is compared on its final dotted component, so the
    fully-qualified `builtins.Exception` classifies as broad. Matching the
    whole rendering instead would let the dotted spelling read as a narrow
    seam catch here while ruff still treats it as broad — the marker
    wording would then go uninspected AND the `BLE001` suppression would
    count as used, so both halves of the enforcement split would fall
    together.
    """
    caught = handler.type
    if caught is None:
        return True
    parts = list(caught.elts) if isinstance(caught, ast.Tuple) else [caught]
    return any(ast.unparse(part).rsplit(".", maxsplit=1)[-1] in broad_names for part in parts)


# The two token scans below deliberately return plain builtins rather than
# sharing one dataclass container. Under `from __future__ import annotations`
# a dataclass resolves its string annotations through
# `sys.modules[cls.__module__]`, which is `None` for a module loaded by path
# via `importlib.util.spec_from_file_location` without being registered — the
# exact shape of this check's standalone-import test, which would fail with
# `AttributeError: 'NoneType' object has no attribute '__dict__'`. Do not
# reintroduce a dataclass here.
def _comment_lines(*, source: str) -> dict[int, tuple[str, ...]]:
    """Map each line number to the comment token texts starting on it.

    Comments are read as TOKENS rather than by scanning raw source lines,
    so marker text inside a string literal cannot be mistaken for a
    marker.
    """
    comments: dict[int, list[str]] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            comments.setdefault(token.start[0], []).append(token.string)
    return {line: tuple(texts) for line, texts in comments.items()}


def _statement_colons(*, source: str) -> tuple[tuple[int, int], ...]:
    """Positions of every `:` operator at bracket depth zero, in source order.

    Depth is tracked so that colons inside a dict display, a slice, or a
    parenthesized exception tuple are skipped; what remains includes the
    `:` that terminates an `except …:` clause.
    """
    colons: list[tuple[int, int]] = []
    depth = 0
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.OP:
            continue
        if token.string in {"(", "[", "{"}:
            depth += 1
        elif token.string in {")", "]", "}"}:
            depth -= 1
        elif token.string == ":" and depth == 0:
            colons.append(token.start)
    return tuple(colons)


def _clause_colon_line(*, handler: ast.ExceptHandler, colons: tuple[tuple[int, int], ...]) -> int:
    """Line of the `:` that closes this handler's `except …:` clause.

    The first statement-level colon at or after the handler's own start
    position is that clause's colon; anything later belongs to the body.
    Every `except …:` clause is closed by such a colon in any module
    `ast.parse` accepted, so the handler's own line is a floor that only
    a malformed parse could reach.
    """
    start = (handler.lineno, handler.col_offset)
    return min((position[0] for position in colons if position >= start), default=handler.lineno)


def _is_sanctioned_marker_comment(*, text: str) -> bool:
    """True when a comment IS the directive plus one sanctioned wording.

    Equality, not containment: the four fixed wordings must run to the
    comment's end, and the templated foreign-code wording must fill both
    slots with per-site facts — a bracket-free surface and an identifier
    ErrorType — ending at the literal `, reported`. A comment that merely
    contains a wording is prose, not a marker.
    """
    if not text.startswith(_MARKER_COMMENT_PREFIX):
        return False
    wording = text[len(_MARKER_COMMENT_PREFIX) :]
    if wording in _SANCTIONED_FIXED_WORDINGS:
        return True
    return _FOREIGN_CODE_WORDING_SHAPE.fullmatch(wording) is not None


def _carries_sanctioned_marker(
    *,
    handler: ast.ExceptHandler,
    comments: dict[int, tuple[str, ...]],
    colons: tuple[tuple[int, int], ...],
) -> bool:
    """True when a clause-line comment is exactly a sanctioned marker.

    The span ends at the clause's closing colon, so a comment BELOW it —
    inside the handler body — is inert. Ending the span at the first body
    STATEMENT instead would admit a body comment sitting above that
    statement, since such a comment is not itself a statement.
    """
    last = _clause_colon_line(handler=handler, colons=colons)
    for line in range(handler.lineno, last + 1):
        for text in comments.get(line, ()):
            if _is_sanctioned_marker_comment(text=text):
                return True
    return False


def _find_offending_handlers(*, source: str, position_exempt: bool) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    comments = _comment_lines(source=source)
    colons = _statement_colons(source=source)
    broad_names = _broad_local_names(tree=tree)
    boundary_try_lines = _supervisor_main_try_lines(tree=tree) if position_exempt else set[int]()
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not _is_try_node(node=node):
            continue
        try_node = cast(ast.Try, node)
        at_boundary = try_node.lineno in boundary_try_lines
        for handler in try_node.handlers:
            if not _is_broad(handler=handler, broad_names=broad_names):
                continue
            if at_boundary and _carries_sanctioned_marker(
                handler=handler, comments=comments, colons=colons
            ):
                continue
            out.append((handler.lineno, _UNMARKED_REASON if at_boundary else _MISPLACED_REASON))
    return out


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("no_except_outside_io")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    if not config.source_trees:
        log.info(
            "role key absent — check no-ops",
            check_id="no_except_outside_io",
            role="source_trees",
        )
        return 0
    offenders: list[tuple[Path, int, str]] = []
    inspected_files: list[Path] = []
    for tree_rel in config.source_trees:
        for py_file in iter_py_files(root=cwd / tree_rel):
            rel = py_file.relative_to(cwd)
            if _is_under_any(rel_path=rel, trees=config.io_trees):
                continue
            inspected_files.append(rel)
            source = py_file.read_text(encoding="utf-8")
            exempt = _is_supervisor_main_file(rel_path=rel, config=config)
            for lineno, reason in _find_offending_handlers(source=source, position_exempt=exempt):
                offenders.append((rel, lineno, reason))
    # An inspected count of zero otherwise reads exactly like a clean pass, so
    # it is reported on every run rather than inferred from silence.
    log.info(
        "inspection complete",
        check_id="no_except_outside_io",
        files_inspected=len(inspected_files),
        offenses=len(offenders),
    )
    backstop_gaps = _find_ruff_backstop_gaps(
        repo_root=cwd,
        source_trees=config.source_trees,
        inspected_files=tuple(inspected_files),
    )
    if backstop_gaps:
        for path, reason in backstop_gaps:
            log.error(reason, file=str(path))
        return 1
    if offenders:
        for path, lineno, reason in offenders:
            log.error(reason, file=str(path), line=lineno)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
