"""no_lloc_soft_warnings — 201-250 LLOC soft-band scan with a severity lever.

Per `SPECIFICATION/constraints.md` section "File LLOC ceiling" (post-v008),
this is the soft-band analog of `check-no-todo-registry`: it flags any
first-party `.py` file in the 201-250 LLOC soft band, forcing refactor
work before a release.

The scan ALWAYS runs (no skip carve-out). A self-documenting severity
lever controls only the release-context behavior: when
`LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST` is set to a non-empty value
(CI sets it to `true` for the release context), soft-band offenders
fail the check (exit 1, error-level diagnostics). When the lever is
unset (or empty), the SAME findings are logged at WARNING level and the
check exits 0, so soft-band files surface during authoring without
blocking per-commit `just check`. This replaces the prior
`LIVESPEC_RELEASE_GATE` skip carve-out (epic li-cvaudit, cvtodo) — the
old carve-out SILENTLY skipped the scan entirely when the gate was unset.

The check tokenizes each `.py` via the same algorithm as
`file_lloc.py` (the per-commit two-tier check). Helpers are
duplicated rather than imported because each `dev-tooling/checks/
<name>.py` is a self-contained Python module per the directory's
CLAUDE.md.

MARKER LIVENESS IS RESOLVED BY THE SHARED RESOLVER. The ownership
marker is a STAND-DOWN on an explicitly named work-item id, so it
falls under the one exception this repository's
`SPECIFICATION/spec.md` §"Non-goals" carves to the network-I/O
prohibition — and that clause requires "one shared mechanism, not
per-gate hand-rolls". `checks/_work_item_liveness` IS that
mechanism; this check reaches it through `main`'s `ledger_reader`
seam, so a unit test supplies a deterministic double and no test
needs a reachable tracker.

Until this adoption the seam here was a local `_probe_marker_liveness`
that returned `None` unconditionally, so the branch convicting a
dead owner was UNREACHABLE in every consuming repository and the
release tier passed BY CONSTRUCTION. Where the store now answers, an
owner that is closed or that the store does not hold resolves False
and IS convicted, naming the id and its resolved status. Where it
does not answer — no `bd` on the host, no credential projection, a
release on hosted CI that cannot reach a loopback ledger — the
snapshot is `None`, the file PASSES, and a `liveness_unverified`
diagnostic says so. An unreachable tracker is not a passing liveness
check, and the two must never be indistinguishable.

That default is what makes the teeth landable: a repo whose host
cannot reach its own tenant is byte-behaviour-identical to before
the resolver existed, so arming the mechanism reddens nothing on
merge. Liveness stays confined to the RELEASE tier for the same
reason `checks/no_todo_registry` confines it there — a per-commit
verdict depending on mutable external state could flip master red
with no commit, which livespec core's `.ai/ci-gate-discipline.md`
treats as a real broken state rather than a notification.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import tokenize
from io import BytesIO
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult  # noqa: E402  — vendor-path-aware import.
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._config_load import resolve_check_context_or_report  # noqa: E402
from livespec_dev_tooling.checks._work_item_liveness import (  # noqa: E402
    LedgerReader,
    LedgerUnreachable,
    bd_status_reader,
    resolve_liveness,
    resolved_status,
)
from livespec_dev_tooling.config import is_under_any_tree  # noqa: E402

__all__: list[str] = []


_LLOC_SOFT_CEILING = 200
_LLOC_HARD_CEILING = 250
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST"
_OWNER_MARKER_RE = re.compile(r"^#\s*livespec-lloc-soft-band-owner:\s*(\S+)\s*$")


def _owner_marker(*, source: str) -> str | None:
    """Return the ledger item id owning this soft-band file, or `None`.

    Read from tokenize COMMENT tokens rather than by scanning raw text, so
    a marker appearing inside a string literal cannot forge ownership.
    Non-marker comments are skipped, so a real file's ordinary commentary
    neither confers nor blocks ownership.

    The marker is carried as a COMMENT because a comment is FREE: LLOC
    excludes blank lines, comment-only lines, and docstrings, so declaring
    ownership cannot push a file deeper into the band it is declaring.
    """
    tokens = tokenize.tokenize(BytesIO(source.encode("utf-8")).readline)
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        match = _OWNER_MARKER_RE.match(tok.string.strip())
        if match is not None:
            return match.group(1)
    return None


_NON_LLOC_TOKEN_TYPES = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)


def _docstring_lines(*, source: str) -> set[int]:
    tree = ast.parse(source)
    out: set[int] = set()
    holders: list[ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            holders.append(node)
    for holder in holders:
        body = holder.body
        if (
            len(body) > 0
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            first = body[0]
            assert first.end_lineno is not None  # noqa: S101 — narrowing for arithmetic
            out.update(range(first.lineno, first.end_lineno + 1))
    return out


def _count_lloc(*, source: str) -> int:
    docstring_lines = _docstring_lines(source=source)
    code_lines: set[int] = set()
    tokens = tokenize.tokenize(BytesIO(source.encode("utf-8")).readline)
    for tok in tokens:
        if tok.type in _NON_LLOC_TOKEN_TYPES:
            continue
        line = tok.start[0]
        if line in docstring_lines:
            continue
        code_lines.add(line)
    return len(code_lines)


def _release_tier_failures(
    *,
    offenders: list[tuple[Path, int]],
    root: Path,
    snapshot: IOResult[dict[str, str], LedgerUnreachable],
) -> int:
    """RELEASE tier: count soft-band files that must block the release.

    Rejects an UNOWNED file, and an owned one whose marker id is checkably
    closed or nonexistent. An owned file whose liveness cannot be
    established PASSES, but says so — never a silent pass.

    Carrying the debt is PERMITTED, not blessed: the accepted-file
    diagnostic names the owning item and states the refactor is OWED,
    because a marker that read as mere threshold noise would be an escape
    hatch rather than a narrow, visible concession.

    `snapshot` is the shared resolver's id → status view of the repository's
    own configured store, on the FAILURE track when it did not answer. It is
    read once per run rather than per marker: a per-marker probe would be one
    subprocess
    per soft-band file, and — the load-bearing half — it could not tell "no
    such id" from "the store did not answer", because both exit non-zero.
    Reading the population once separates them structurally, which is what
    lets an id MISSING from an answering store be convicted as nonexistent
    rather than mistaken for a store that never replied.
    """
    emit = structlog.get_logger("no_lloc_soft_warnings")
    failing = 0
    for path, lloc in offenders:
        owner = _owner_marker(source=(root / path).read_text(encoding="utf-8"))
        if owner is None:
            failing += 1
            emit.error(
                "file in 201-250 LLOC soft band with no owning work-item marker",
                file=str(path),
                lloc=lloc,
                soft_ceiling=_LLOC_SOFT_CEILING,
                hard_ceiling=_LLOC_HARD_CEILING,
                fail_env_var=_FAIL_ENV_VAR,
                expected_marker="# livespec-lloc-soft-band-owner: <work-item-id>",
                failing=True,
            )
            continue
        live = resolve_liveness(work_item=owner, snapshot=snapshot)
        if isinstance(live, IOFailure):
            emit.warning(
                "file in 201-250 LLOC soft band accepted: REFACTOR IS OWED by the named "
                "work-item; carrying this debt is permitted, not blessed. Work-item "
                "liveness UNVERIFIED (the repository's configured work-item store did "
                "not answer)",
                file=str(path),
                lloc=lloc,
                work_item=owner,
                liveness_unverified=True,
                unreachable_reason=unsafe_perform_io(live.failure()).reason,
                failing=False,
            )
        elif not unsafe_perform_io(live.unwrap()):
            failing += 1
            emit.error(
                "file in 201-250 LLOC soft band whose owning work-item is closed or "
                "nonexistent; the owed REFACTOR has no live owner",
                file=str(path),
                lloc=lloc,
                work_item=owner,
                resolved_status=resolved_status(work_item=owner, snapshot=snapshot),
                fail_env_var=_FAIL_ENV_VAR,
                failing=True,
            )
        else:
            emit.warning(
                "file in 201-250 LLOC soft band accepted: REFACTOR IS OWED by the named "
                "work-item; carrying this debt is permitted, not blessed",
                file=str(path),
                lloc=lloc,
                work_item=owner,
                failing=False,
            )
    return failing


def main(*, ledger_reader: LedgerReader = bd_status_reader) -> int:
    """Run the soft-band scan; `ledger_reader` is the injectable liveness seam.

    The default reads the repository's own configured work-item store through
    the shared resolver. A test passes a deterministic double instead, so the
    fail-capability cases are proven without a reachable tracker and no unit
    test's verdict depends on the host it runs on.
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("no_lloc_soft_warnings")
    resolved = resolve_check_context_or_report(log=log, check_id="no_lloc_soft_warnings")
    if not is_successful(resolved):
        return 1
    root, universe, config = unsafe_perform_io(resolved.unwrap())
    legacy_soft_offenders: list[tuple[Path, int]] = []
    newly_covered_soft_offenders: list[tuple[Path, int]] = []
    for rel in universe:
        source = (root / rel).read_text(encoding="utf-8")
        lloc = _count_lloc(source=source)
        if not (_LLOC_SOFT_CEILING < lloc <= _LLOC_HARD_CEILING):
            continue
        if is_under_any_tree(rel=rel, trees=config.covered_trees):
            legacy_soft_offenders.append((rel, lloc))
        else:
            newly_covered_soft_offenders.append((rel, lloc))
    fail = bool(os.environ.get(_FAIL_ENV_VAR))
    failing_count = 0
    if not fail:
        # PER-COMMIT tier — unchanged by ownership: every legacy soft-band
        # file warns and the check exits 0. Deliberately identical to the
        # pre-ownership behavior, which is what makes this a strict loosening.
        for path, lloc in legacy_soft_offenders:
            log.warning(
                "file in 201-250 LLOC soft band",
                file=str(path),
                lloc=lloc,
                soft_ceiling=_LLOC_SOFT_CEILING,
                hard_ceiling=_LLOC_HARD_CEILING,
                fail_env_var=_FAIL_ENV_VAR,
                failing=False,
            )
    else:
        failing_count = _release_tier_failures(
            offenders=legacy_soft_offenders, root=root, snapshot=ledger_reader(repo=root)
        )
    for path, lloc in newly_covered_soft_offenders:
        log.warning(
            "file in 201-250 LLOC soft band — newly git-derived coverage; Phase-0 WARN "
            "(hard-fails once this repo is flipped to the hard gate in Phase 2)",
            file=str(path),
            lloc=lloc,
            soft_ceiling=_LLOC_SOFT_CEILING,
            hard_ceiling=_LLOC_HARD_CEILING,
            fail_env_var=_FAIL_ENV_VAR,
            failing=False,
            phase="0-warn",
            newly_covered=True,
        )
    return 1 if failing_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
