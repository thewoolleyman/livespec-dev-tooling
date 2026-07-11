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

Delta-WARN severity (identical to `comment_line_anchors`): a file under
one of this repo's legacy trees (`config.target_dirs`) emits at ERROR and
contributes to exit 1; a newly-git-derived file outside every legacy tree
emits at WARNING with `phase="0-warn"` and does NOT fail the check. A
blanket hard-fail would redden every repo still carrying a pre-existing
counter-shave the moment the pin bumps — before its fix-forward lands;
delta-WARN surfaces the offender loudly in `just check` output without
breaking CI mid-sequence, exactly like every other Phase-0 reroute.

Output discipline: per spec, `print` and direct `sys.stderr.write` are
banned in this package; diagnostics flow through structlog (JSON to
stderr) per the vendor-path-aware import below.
"""

from __future__ import annotations

import re
import sys
import tokenize
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    is_under_any_tree,
    load_config,
    resolve_check_universe,
)

__all__: list[str] = []


# Matches a formatter-suppression directive at the start of a `#` comment
# token, robust to the ruff/black spacing variants (`# fmt: off`,
# `# fmt:off`, `#fmt: off`) and any trailing text. The trailing `\b`
# means `# fmt: offset = 3` does NOT match — there is no word boundary
# between `off` and `set` — while a benign comment whose text merely
# contains "fmt" never reaches the `fmt:` literal.
_FMT_DIRECTIVE_RE = re.compile(r"^#\s*fmt:\s*(?:off|on|skip)\b")
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
    config = load_config(repo_root=root)
    # Legacy classifier: `config.target_dirs`, the SAME classifier
    # `comment_line_anchors` uses. This check is that check's direct
    # structural sibling — both scan `#` comment tokens across the one
    # git-derived first-party universe — so sharing the classifier keeps
    # the two uniform: a file that is "legacy" for one is "legacy" for
    # the other.
    legacy_offenders = 0
    for rel in universe:
        is_legacy = is_under_any_tree(rel=rel, trees=config.target_dirs)
        for lineno, matched in _scan_file(path=root / rel):
            emit = log.error if is_legacy else log.warning
            extra = {} if is_legacy else {"phase": "0-warn", "newly_covered": True}
            emit(
                "formatter-suppression directive in a first-party file",
                check_id="no-fmt-directives",
                path=str(rel),
                lineno=lineno,
                directive=matched,
                hint=_HINT,
                **extra,
            )
            if is_legacy:
                legacy_offenders += 1
    if legacy_offenders:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
