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

THE RULE IS ON THE `IOResult` RAILWAY — livespec-dev-tooling-8o8e.9, the
per-repo arming child. It shells out to `git` directly rather than through an
injected seam, so it IS the I/O boundary and `IOResult` rather than `Result`
is the honest container (the same direct-call-versus-injected-seam reading
that put `fleet/_origin_remote.py` and `checks/_primary_checkout_git_probes.py`
there).

WHAT THE OLD `bool` COULD NOT SAY. Its docstring called the collapse "fail
closed", and fail-closed is the safe DIRECTION but not an answer: a caller
could not tell a VERDICT from a NON-READ.

- A blob `git` could not produce for an environmental reason — not a
  repository, a corrupt object store — returned the same `False` as a real
  source change, so a broken checkout was reported as "you changed source
  without a paired test".
- A revision that does not PARSE returned that same `False`, so a staged file
  with a syntax error was reported as a missing test rather than as a file
  that does not compile.
- `git` absent from PATH did not arrive as a `False` at all: the
  `subprocess.run` was UNGUARDED, so it raised `OSError` straight out of a
  function whose annotation promised `bool`. One of the three arms the
  docstring called fail-closed did not fail closed; it crashed.

WHAT IS AND IS NOT A FAILURE HERE, because that split is the substance of the
conversion rather than the type change. **A REVISION THAT DOES NOT CONTAIN THE
PATH IS AN ANSWER, NOT A FAILURE.** `git` was asked whether there is a blob at
`<ref>:<path>`, it looked, and there is not — a new file, a deletion, a rename
whose new path is absent from the base. That read HAPPENED, and no
comment-only edit can relate a revision holding the file to one that does not,
so `False` is a verdict rather than a placeholder. A failure is `git` not
answering at all.

That is also why this module does not separate "the ref is bogus" from "the
path is absent from a good ref". `git` gives one answer to one question, and
which refs a caller has a right to expect is the CALLER's precondition to
assert rather than this function's to infer from an exit code.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Carried rather than inherited from an importer: without it the vendored
# `returns` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this
# file. The module that broke the fleet's release fan-out for seven hours on
# 2026-07-30 was in exactly that state until it became a process entry point.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = ["DocsOnlyUndecidable", "is_docs_only_change"]

# `git rev-parse --verify --quiet <spec>` exits 1, silently, for a spec that
# does not resolve — and only for that. Every OTHER non-zero exit (128 for
# "not a git repository", for a corrupt object store) means `git` could not
# establish whether the object is there, which is the failure this constant
# separates from the answer.
_SPEC_DOES_NOT_RESOLVE: int = 1

# The verdict for a revision that does not contain the path: no comment-only
# edit can relate a revision holding the file to one that does not. Named
# rather than written inline because `flake8-boolean-trap` (FBT003) refuses a
# bare boolean literal at a call site — the same spelling
# `_primary_checkout_git_probes._UNSET_KEY_RESOLVES_TO` uses — and because the
# name carries WHY it is False, which is the whole ruling of this conversion.
_ABSENT_REVISION_IS_NOT_DOCS_ONLY: bool = False


@dataclass(frozen=True, kw_only=True)
class DocsOnlyUndecidable:
    """The docs-only comparison could not be MADE, and WHICH of three reasons.

    `reason` is the discriminator a caller branches on; `detail` is the
    operator-facing evidence, and the two are deliberately separate so a
    diagnostic can name the cause without the caller parsing prose.

    The three are kept apart because they want DIFFERENT operator responses:
    `git-not-run` is a broken environment, `repository-unreadable` is a
    checkout `git` cannot read the requested object out of, and
    `revision-unparseable` is a Python file that does not compile. Collapsed
    onto `False` all three were reported as whatever the caller's gate says
    about a real source change.
    """

    reason: Literal["git-not-run", "repository-unreadable", "revision-unparseable"]
    detail: str


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
    error or embedded NUL) — ONE meaning, which its caller lifts onto the
    failure track as `revision-unparseable`.
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


def _git(*, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one `git` invocation in `cwd`, never raising on a non-zero exit.

    The `OSError` a missing or unexecutable `git` raises is deliberately NOT
    caught here: `_revision_source` catches it once around BOTH of its calls,
    so the lift happens in one place and neither call has an arm that only a
    `git` vanishing mid-function could reach.
    """
    # S603/S607: argv is a fixed list of literal git args; no shell input.
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _revision_source(*, ref_and_path: str, cwd: Path) -> IOResult[str | None, DocsOnlyUndecidable]:
    """The blob at `<ref>:<path>`, or None when that revision does not contain the path.

    `None` on the SUCCESS track carries exactly one meaning — `git` resolved
    the question and there is no such object — and the module docstring argues
    why that is an answer rather than a failure.

    The `rev-parse` probe runs only when `git show` has already failed, so the
    hot path stays one subprocess per revision. The catch is NARROW and
    ENUMERATED (`OSError`), the sanctioned hand-rolled seam lift: `git` absent
    from PATH, a `git` that cannot be exec'd, a `cwd` that is not a directory,
    a fork failure. A bug raised in here still propagates.
    """
    try:
        shown = _git(args=["show", ref_and_path], cwd=cwd)
        if shown.returncode == 0:
            return IOSuccess(shown.stdout)
        verified = _git(args=["rev-parse", "--verify", "--quiet", ref_and_path], cwd=cwd)
    except OSError as unusable:
        return IOFailure(DocsOnlyUndecidable(reason="git-not-run", detail=str(unusable)))
    if verified.returncode == _SPEC_DOES_NOT_RESOLVE:
        return IOSuccess(None)
    # Both arms reaching here are the same fact and take the same reason:
    # `git` could not produce the blob AND could not tell us it is absent.
    # Exit 128 is the unreadable checkout; exit 0 is the rarer corrupt object
    # store, where the tree still names an object `git show` cannot read.
    # Neither is a verdict about the source, so neither may answer as one.
    return IOFailure(
        DocsOnlyUndecidable(
            reason="repository-unreadable",
            detail=(
                f"{ref_and_path}: git show exited {shown.returncode}"
                f" ({shown.stderr.strip()}); git rev-parse --verify exited"
                f" {verified.returncode}"
            ),
        )
    )


def _comparable_dump(*, ref_and_path: str, cwd: Path) -> IOResult[str | None, DocsOnlyUndecidable]:
    """One revision's docstring-stripped dump, or None when the path is absent there."""
    read = _revision_source(ref_and_path=ref_and_path, cwd=cwd)
    if isinstance(read, IOFailure):
        return read
    source = unsafe_perform_io(read.unwrap())
    if source is None:
        return IOSuccess(None)
    dumped = _dump_without_docstrings(source=source)
    if dumped is None:
        return IOFailure(DocsOnlyUndecidable(reason="revision-unparseable", detail=ref_and_path))
    return IOSuccess(dumped)


def is_docs_only_change(
    *, before: str, after: str, cwd: Path
) -> IOResult[bool, DocsOnlyUndecidable]:
    """Whether two `<ref>:<path>` revisions differ only in comments/docstrings.

    `IOSuccess(True)` iff both revisions exist and their docstring-stripped
    ASTs are identical. `IOSuccess(False)` for any real source change, and for
    a revision that does not contain the path at all (a new file, a deletion,
    a rename whose new path is absent from the base) — a verdict `git`
    answered rather than one this function assumed.

    `IOFailure` says the comparison could not be MADE. A caller that gates on
    the answer should still not waive its gate on a failure — the direction is
    unchanged — but it can now report the failure as itself instead of as the
    verdict it is not.
    """
    before_dump = _comparable_dump(ref_and_path=before, cwd=cwd)
    if isinstance(before_dump, IOFailure):
        return before_dump
    after_dump = _comparable_dump(ref_and_path=after, cwd=cwd)
    if isinstance(after_dump, IOFailure):
        return after_dump
    left = unsafe_perform_io(before_dump.unwrap())
    right = unsafe_perform_io(after_dump.unwrap())
    if left is None or right is None:
        return IOSuccess(_ABSENT_REVISION_IS_NOT_DOCS_ONLY)
    return IOSuccess(left == right)
