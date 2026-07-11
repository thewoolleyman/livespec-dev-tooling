"""no_fmt_directives — ban formatter-suppression directives in first-party files.

A `# fmt: off` / `# fmt: on` / `# fmt: skip` directive tells the
formatter (Black / ruff format) to leave a region alone. In the livespec
fleet that is a `file_lloc` counter-shaving vector: `file_lloc` counts
distinct physical lines carrying code tokens, so packing many `__all__`
entries (or any collection) onto fewer physical lines lowers the count
DISHONESTLY, while the formatter's honest one-element-per-line expansion
is suppressed. Banning the directives across the first-party universe
keeps that expansion un-suppressable, so `file_lloc` measures the honest
physical-line count and the "≤200 LLOC" target cannot be gamed by
line-packing.

Walks the git-derived first-party `.py` universe
(`resolve_check_universe`, the same choke point every applies-to-all
check uses), extracts `#` comment tokens via `tokenize`, and matches
each against the formatter-suppression regex — robust to the ruff/black
spacing variants (`# fmt:off`, `#fmt: off`) and any trailing text. A
benign comment that merely contains the word "fmt" does NOT match.
Vendored libraries, the configured test tree, `templates/`, and
`@generated`-marked files are already outside `resolve_check_universe`,
so their legitimate directives are never flagged.

Warn-vs-fail severity lever (the blessed pattern, mirroring
`ci_matrix_completeness` / `no_todo_registry` / `no_lloc_soft_warnings`):
the scan ALWAYS runs — the lever controls warn-vs-fail ONLY, never
run-vs-skip. This is a NET-NEW check, so NOTHING is "legacy" (the
delta-WARN `config.target_dirs` classifier the sibling structural checks
use means "already historically covered", which is false here); every
finding is Phase-0 newly-covered. When
`LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST` is set to a non-empty value (a
repo sets it in its CI once it is clean), findings emit at ERROR level
and the check exits 1. When the lever is unset (or empty), the SAME
findings emit at WARNING level with `phase="0-warn"`,
`newly_covered=True` and the check exits 0 — so the slug propagates
fleet-wide and warns each not-yet-clean repo without reddening it before
its own fix-forward lands. Each repo flips to fail in its own PR.

Output discipline: per spec, `print` and direct `sys.stderr.write` are
banned in this package; diagnostics flow through structlog (JSON to
stderr) per the vendor-path-aware import below.
"""

from __future__ import annotations

import os
import re
import sys
import tokenize
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import resolve_check_universe  # noqa: E402

__all__: list[str] = []


# Matches a formatter-suppression directive at the start of a `#` comment
# token, robust to the ruff/black spacing variants (`# fmt: off`,
# `# fmt:off`, `#fmt: off`) and any trailing text. The trailing `\b`
# means `# fmt: offset = 3` does NOT match — there is no word boundary
# between `off` and `set` — while a benign comment whose text merely
# contains "fmt" never reaches the `fmt:` literal.
_FMT_DIRECTIVE_RE = re.compile(r"^#\s*fmt:\s*(?:off|on|skip)\b")
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST"
_EXIT_VIOLATIONS = 1
_HINT = (
    "Formatter-suppression directives (`# fmt: off` / `# fmt: on` / "
    "`# fmt: skip`) are banned in the first-party universe: suppressing "
    "the formatter's one-element-per-line expansion is the mechanism of "
    "`file_lloc` counter-shaving (packing `__all__` or any collection onto "
    "fewer physical lines to dodge the LLOC target). Let the formatter "
    "expand collections one element per line; a verbatim third-party port "
    "that genuinely needs the directive should be marked `@generated` so it "
    "drops out of the first-party universe entirely."
)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("no_fmt_directives")


def _comment_hits(*, source: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    tokens = list(
        tokenize.generate_tokens(iter(source.splitlines(keepends=True)).__next__),
    )
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        match = _FMT_DIRECTIVE_RE.match(tok.string)
        if match is not None:
            hits.append((tok.start[0], match.group(0)))
    return hits


def _scan_file(*, path: Path) -> list[tuple[int, str]]:
    return _comment_hits(source=path.read_text(encoding="utf-8"))


def main() -> int:
    log = _configure_logger()
    root, universe = resolve_check_universe()
    # Warn-vs-fail lever ONLY (never run-vs-skip): a repo arms
    # `LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST` in its CI once it is clean.
    # Unset/empty → WARN + exit 0 (Phase-0 propagation); set → ERROR + exit 1.
    fail = bool(os.environ.get(_FAIL_ENV_VAR))
    findings = 0
    for rel in universe:
        for lineno, matched in _scan_file(path=root / rel):
            findings += 1
            emit = log.error if fail else log.warning
            # A net-new check has no legacy coverage, so every finding is
            # newly-covered; the `phase`/`newly_covered` markers ride the WARN
            # path, `failing` rides the armed path — mirroring the peer
            # `ci_matrix_completeness` structured-diagnostic shape.
            extra = {"failing": True} if fail else {"phase": "0-warn", "newly_covered": True}
            emit(
                "formatter-suppression directive in a first-party file",
                check_id="no-fmt-directives",
                path=str(rel),
                lineno=lineno,
                directive=matched,
                hint=_HINT,
                fail_env_var=_FAIL_ENV_VAR,
                **extra,
            )
    if fail and findings:
        return _EXIT_VIOLATIONS
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
