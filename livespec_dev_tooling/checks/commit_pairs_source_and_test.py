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

Since `livespec-dev-tooling-8o8e.9` the shared rule returns an
`IOResult`, which splits that list in two. A new file, a deletion
and a rename are ANSWERS — `git` was asked for the blob and said
there is none — while an unparseable revision, an unreadable
checkout, and a `git` that will not run are UNDECIDABLE and arrive
on the failure track. The direction is identical either way (the
carve-out never applies), but an undecidable outcome is now logged
as itself instead of reaching the author as "you changed source
without a paired test".

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

import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._docs_only_change import (  # noqa: E402
    is_docs_only_change,
)
from livespec_dev_tooling.config import (  # noqa: E402
    derive_source_prefixes,
    is_vendored_path,
    load_config,
    role_path,
)

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


def _is_docs_only_change(*, path: str, cwd: Path, log: structlog.stdlib.BoundLogger) -> bool:
    """Whether a staged source path differs from HEAD only in comments/docstrings.

    Delegates to the shared rule so this gate and
    `check_coverage_incremental` cannot drift into disagreeing about the
    same edit. The staged (index) revision is spelled `:<path>`.

    An UNDECIDABLE comparison keeps the gate armed — the fail-closed
    DIRECTION is unchanged — but is now reported as itself. Before the
    rule went on the railway a `git` that could not read the checkout,
    and a staged file that does not parse, both reached the author as
    "source change staged without paired test change": a definitive
    verdict about their commit, manufactured from a read that never
    produced one.
    """
    decided = is_docs_only_change(before=f"HEAD:{path}", after=f":{path}", cwd=cwd)
    if isinstance(decided, IOFailure):
        undecidable = unsafe_perform_io(decided.failure())
        log.error(
            "docs-only carve-out undecidable; the pairing requirement applies unchanged",
            check_id="commit-pairs-source-and-test-docs-only-undecidable",
            source=path,
            reason=undecidable.reason,
            detail=undecidable.detail,
        )
        return False
    return unsafe_perform_io(decided.unwrap())


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
    neutral_hook_body = role_path(role=config.neutral_hook_body_path)
    exempt_paths = frozenset(
        {neutral_hook_body.as_posix()} if neutral_hook_body is not None else set()
    )
    # Scoped to `.py` deliberately. The pairing contract is defined on Python —
    # the mirror transform maps `<name>.py` to `test_<name>.py` — so a
    # non-Python file under a source tree (an orientation `CLAUDE.md`, a shell
    # helper) has no paired test that could exist, and demanding one is
    # unsatisfiable rather than merely strict. The docs-only carve-out below
    # cannot rescue it either: it compares docstring-stripped ASTs, and a
    # non-Python file does not parse, so it fails closed into exactly the
    # requirement it can never meet.
    #
    # Vendored `.py` is excluded for the SAME reason, via the same predicate
    # the first-party universe uses (`is_vendored_path`): upstream code a
    # governed repo does not author has no paired test that could exist, so
    # demanding one made vendoring any new library uncommittable.
    # Derived, never read straight off `config.source_tree_prefixes`: an empty
    # declared prefix set would otherwise empty this comprehension's universe
    # by construction (`str.startswith(())` is False for every input) and make
    # the pairing branch below unreachable. `derive_source_prefixes` unions in
    # `source_trees`, which is populated in every Python-bearing fleet repo.
    source_prefixes = derive_source_prefixes(config=config)
    source_changes = [
        path
        for path in staged
        if path.startswith(source_prefixes)
        and path.endswith(".py")
        and path not in exempt_paths
        and not is_vendored_path(rel_path=Path(path))
    ]
    test_changes = [path for path in staged if path.startswith(config.tests_tree_prefix)]

    if source_changes and not test_changes:
        unpaired = [
            path for path in source_changes if not _is_docs_only_change(path=path, cwd=cwd, log=log)
        ]
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
