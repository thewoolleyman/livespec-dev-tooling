"""commit_pairs_source_and_test — every source-touching commit also touches tests/ (v033 D3).

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-commit-pairs-source-and-test` row,
added at v033) and the v033 D3 revision file, every commit
modifying any `.claude-plugin/scripts/livespec/**`,
`.claude-plugin/scripts/bin/**`, or `<repo-root>/dev-tooling/
checks/**` source file MUST also modify a `tests/**` file in
the same commit. Enforced as a lefthook pre-commit gate that
inspects the staged state; it is ALSO one of the `just check`
aggregate targets, where it passes VACUOUSLY — a `just check`
run against a clean working tree stages nothing, so `git diff
--cached` is empty, no source change is seen, and the check
no-ops. Its load-bearing enforcement is therefore the
per-commit pre-commit gate, not the vacuous aggregate pass.

Pre-commit invocation context: lefthook runs the check before
the commit lands. The script reads `git diff --cached
--name-only` to enumerate staged files, applies the source-tree
filter, and verifies a `tests/**` co-staging.

**v034 D2-D3 amend-pattern coexistence.** When HEAD's
commit message carries `TDD-Red-Test-File-Checksum:` trailers
WITHOUT paired `TDD-Green-Verified-At:` trailers, the next
operation is structurally guaranteed by the v034 contract to
be `git commit --amend` adding the impl. During that amend,
`git diff --cached --name-only` shows only the impl files
(the Red commit's test is already in HEAD, unchanged), so the
naive staged-only enforcement would reject the amend. The
check skips itself in that case — the Red→Green replay contract
enforces pairing structurally (Red commit MUST stage a test;
Green amend MUST land impl and pass the test). The "every
feat/fix commit must also touch tests/**" contract is satisfied
by the post-amend commit (which contains BOTH the Red commit's
test and the Green amend's impl). Once the amend lands, HEAD carries both Red AND Green
trailers and the next commit's pre-commit sees the
"complete" state — the check resumes normal enforcement.

Cycle 1 implemented the bare rejection: any staged source-tree
file without a co-staged tests/-tree file fails the check.
Cycle 2.7 added the v034 amend-mode skip described above.

**The declared neutral hook body is exempt.** A consumer that
declares `neutral_hook_body_path` may stage that ONE file with no
paired `tests/**` change. It is a generated carrier — written
verbatim from the packaged `CANONICAL_NO_SHADOW_LEDGER_BODY` by
`just install-no-shadow-ledger` and already gated for byte-identity
by `check-no-shadow-ledger-body-identical` — so its re-render
touches no test by construction, while having to travel in the SAME
commit as the dev-tooling pin bump. Unexempted, this gate made a
producer-side carrier change impossible to propagate by any route:
the fan-out rewrites pins only, and the hand repair was refused
here. The exemption is path-scoped, never prefix-wide.

**Content-keyed docs-only carve-out (livespec-dev-tooling-5eow).**
Beyond that one declared carrier path, a staged source-tree file
WITHOUT a co-staged test is now also allowed when — and only
when — its staged version is AST-equivalent to its HEAD version
modulo comments AND docstrings, so a comments/docstring-only edit
is committable without a paired test. The carve-out is keyed on
CONTENT, not on commit-subject prefix or a `## Type:` marker (per
the repo's fix-the-gate-not-the-bypass discipline):
`_is_docs_only_change` compares `ast.dump` of both sides after
stripping every module, class, and (async) function docstring —
comments never reach the AST, but the leading string statement of
each of those bodies does, so it must be removed before the compare
or a docstring-only edit would still block. It FAILS CLOSED — the
pairing requirement applies unchanged — when the file is absent in
HEAD (a new file), is a staged deletion or rename, is unparseable
on either side, or carries ANY non-comment/docstring difference.
When several source files are staged, the carve-out applies only if
EVERY one is docs-only; a single real change re-arms the
requirement for the whole commit.

Subsequent cycles will add the rest of the closed carve-out set
(refactor: prefix, ## Type: refactor / config, deletion-only
commits, config-only filenames like pyproject.toml / justfile /
lefthook.yml / .mise.toml / .vendor.jsonc / .gitignore).

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import
time.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import load_config  # noqa: E402

__all__: list[str] = []


_RED_TRAILER_TOKEN: str = "TDD-Red-Test-File-Checksum:"
_GREEN_TRAILER_TOKEN: str = "TDD-Green-Verified-At:"


def _staged_files(*, cwd: Path) -> list[str]:
    # S603/S607: argv is a fixed list (literal git binary + literal flags);
    # bare `git` resolves via PATH; no untrusted shell input.
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _head_has_unpaired_red_trailers(*, cwd: Path) -> bool:
    """Detect HEAD = v034 D2-D3 Red commit pending Green amend.

    Returns True iff HEAD's commit message contains
    `TDD-Red-Test-File-Checksum:` AND does NOT contain
    `TDD-Green-Verified-At:` — the canonical "amend-pending"
    state. After the Green amend lands, HEAD's message
    carries both trailers and this function returns False.

    On a fresh repo with no commits, `git log -1` exits
    non-zero; the resulting `subprocess.CalledProcessError`
    is caught and treated as "no Red trailers" (returns
    False). The check then applies its normal enforcement.
    """
    # S603/S607: argv is a fixed list (literal git binary + literal flags);
    # bare `git` resolves via PATH; no untrusted shell input.
    result = subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    message = result.stdout
    has_red = _RED_TRAILER_TOKEN in message
    has_green = _GREEN_TRAILER_TOKEN in message
    return has_red and not has_green


def _git_blob(*, ref_and_path: str, cwd: Path) -> str | None:
    """Return the text of a git object (`git show <ref>:<path>`), or None on failure.

    `ref_and_path` is a `git show` object spec — `HEAD:<path>` for the
    committed version, `:<path>` for the staged (index, stage-0) version.
    A non-zero exit means the object does not exist (the path is absent in
    HEAD — a new file — or has no stage-0 entry — a staged deletion), which
    the carve-out treats as a fail-closed signal, so None is returned rather
    than raising.
    """
    # S603/S607: argv is a fixed list (literal git binary + literal flags);
    # bare `git` resolves via PATH; no untrusted shell input.
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


def _is_docs_only_change(*, path: str, cwd: Path) -> bool:
    """Whether a staged source path differs from HEAD only in comments/docstrings.

    True iff BOTH the HEAD version and the staged (index) version exist, BOTH
    parse, and their docstring-stripped ASTs are identical — meaning the only
    differences are comments and/or docstrings. False (fail closed → the
    pairing requirement applies) for a new file (absent in HEAD), a staged
    deletion or rename (no stage-0 entry, or the new path is absent in HEAD),
    an unparseable version on either side, or any real (non-comment,
    non-docstring) source change.
    """
    head_source = _git_blob(ref_and_path=f"HEAD:{path}", cwd=cwd)
    if head_source is None:
        return False
    staged_source = _git_blob(ref_and_path=f":{path}", cwd=cwd)
    if staged_source is None:
        return False
    head_dump = _dump_without_docstrings(source=head_source)
    if head_dump is None:
        return False
    staged_dump = _dump_without_docstrings(source=staged_source)
    if staged_dump is None:
        return False
    return head_dump == staged_dump


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("commit_pairs_source_and_test")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)

    if _head_has_unpaired_red_trailers(cwd=cwd):
        log.info(
            "v034 D2-D3 Green amend in progress; commit-pairs check skipped",
            check_id="commit-pairs-source-and-test-amend-skip",
        )
        return 0

    staged = _staged_files(cwd=cwd)
    # The declared neutral hook body is a GENERATED carrier, not authored
    # source: `just install-no-shadow-ledger` writes it verbatim from the
    # packaged CANONICAL_NO_SHADOW_LEDGER_BODY, and
    # `check-no-shadow-ledger-body-identical` already gates it for
    # byte-identity against that constant. Re-rendering it after a producer
    # change touches no `tests/**` file BY CONSTRUCTION, and the re-render
    # MUST travel in the same commit as the dev-tooling pin bump (the body
    # alone would be compared against the old canonical, the pin alone
    # against the new one). Without this exemption such a commit is
    # unmakeable, so a carrier change propagates by neither the pin-only
    # fan-out nor by hand. Exempting exactly the DECLARED path — never the
    # prefix around it — keeps every hand-authored sibling gated.
    exempt_paths = frozenset(
        {config.neutral_hook_body_path} if config.neutral_hook_body_path else set()
    )
    # Scoped to `.py` deliberately. The pairing contract is defined on Python —
    # the mirror transform maps `<name>.py` to `test_<name>.py` — so a
    # non-Python file under a source tree (an orientation `CLAUDE.md`, a shell
    # helper) has no paired test that could exist, and demanding one is
    # unsatisfiable rather than merely strict. The docs-only carve-out below
    # cannot rescue it either: it compares docstring-stripped ASTs, and a
    # non-Python file does not parse, so it fails closed into exactly the
    # requirement it can never meet.
    source_changes = [
        path
        for path in staged
        if path.startswith(config.source_tree_prefixes)
        and path.endswith(".py")
        and path not in exempt_paths
    ]
    test_changes = [path for path in staged if path.startswith(config.tests_tree_prefix)]

    if source_changes and not test_changes:
        unpaired = [path for path in source_changes if not _is_docs_only_change(path=path, cwd=cwd)]
        if unpaired:
            for source_path in unpaired:
                log.error(
                    "source change staged without paired test change",
                    source=source_path,
                    staged_files=staged,
                )
            return 1
        log.info(
            "docs-only carve-out: every staged source change is AST-equivalent to HEAD "
            "modulo comments and docstrings; pairing requirement waived",
            check_id="commit-pairs-source-and-test-docs-only-carveout",
            source_changes=source_changes,
        )
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
