"""Whether a change to a `.py` path is comment/docstring-only.

Shared by the two gates that must agree about it: `commit_pairs_source_and_test`
(which waives its paired-test requirement) and `check_coverage_incremental`
(which drops the path from its changed-impl set). They compare DIFFERENT pairs
of revisions — HEAD-vs-index at commit time, `origin/master`-vs-HEAD over a
branch range — so the comparison is parameterized by full `<ref>:<path>`
specs rather than hardcoding either pair.

One rule, one implementation: a second copy would let the two gates drift into
disagreeing about the same edit, which is the defect this module was extracted
to fix.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

__all__: list[str] = ["is_docs_only_change"]


def _dump_without_docstrings(*, source: str) -> str | None:
    """Return `ast.dump` of `source` with every docstring stripped, or None if unparseable.

    Comments are already absent from the AST, so `ast.dump` ignores them;
    docstrings are NOT — the leading string-literal statement of a module,
    class, or (async) function IS an `Expr`/`Constant`-str node in the tree,
    so a docstring-only edit would still change the dump unless removed. This
    strips those leading statements before dumping so both comment- and
    docstring-only edits compare equal. `include_attributes` defaults to
    False, so line/column shifts from added or removed comment lines do not
    affect the dump. Returns None when the source does not parse (a syntax
    error or embedded NUL), the carve-out's fail-closed signal.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:]
    return ast.dump(tree)


def _git_blob(*, ref_and_path: str, cwd: Path) -> str | None:
    """Return the blob at `<ref>:<path>`, or None when git cannot produce it."""
    # S603/S607: argv is a fixed list of literal git args; no shell input.
    result = subprocess.run(
        ["git", "show", ref_and_path],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def is_docs_only_change(*, before: str, after: str, cwd: Path) -> bool:
    """Whether two `<ref>:<path>` revisions differ only in comments/docstrings.

    True iff BOTH revisions exist, BOTH parse, and their
    docstring-stripped ASTs are identical. False — fail closed, so the
    caller's gate applies — for a revision git cannot produce (a new
    file, a deletion, a rename whose new path is absent from the base),
    an unparseable version on either side, or any real source change.
    """
    before_source = _git_blob(ref_and_path=before, cwd=cwd)
    if before_source is None:
        return False
    after_source = _git_blob(ref_and_path=after, cwd=cwd)
    if after_source is None:
        return False
    before_dump = _dump_without_docstrings(source=before_source)
    if before_dump is None:
        return False
    after_dump = _dump_without_docstrings(source=after_source)
    if after_dump is None:
        return False
    return before_dump == after_dump
