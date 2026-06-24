"""no_direct_destructive_cli — agent-facing trees must wrap destructive-default CLIs.

Per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Destructive-default CLI wrapping" (li-1f5 item 5, preservation
split): destructive-default external CLIs — those whose default
behavior writes, commits, deletes, or otherwise mutates persistent
state without explicit opt-in — MUST be invoked through project-local
scripted wrappers that pin safe flags, and agent-facing prose MUST
refer to the wrapper, not the underlying CLI.

The check greps every text file in the three agent-facing trees —
`dev-tooling/`, `.claude-plugin/`, and `.claude/plugins/` — for
direct invocations of known-destructive-default CLIs:

- `bd init` (auto-commits to master during bootstrap)
- `git push --force` (any force-push spelling: `--force`,
  `--force-with-lease`, or the `-f` short flag in the same shell
  command)
- `git reset --hard`
- `gh repo delete`

The banned tuple is the extension point: when a new
destructive-default tool joins the fleet toolchain, add its
invocation pattern here.

Allowlist: a file whose repo-root-relative POSIX path starts with an
entry of `[tool.livespec_dev_tooling].destructive_cli_allowlist`
(loaded via `livespec_dev_tooling.config`) is exempt — e.g., a
research-notes subtree that legitimately documents a destructive
CLI's behavior. Absent key → empty allowlist (nothing exempt).

Skips: a repo with none of the scanned trees passes vacuously;
binary files (NUL byte present) and `_vendor`/`__pycache__` subtrees
are skipped. Non-UTF-8 text decodes with replacement characters so
the scan still applies.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this package. Diagnostics
flow through structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at
module import time.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import load_destructive_cli_allowlist  # noqa: E402

__all__: list[str] = []


_SCANNED_TREES = (
    Path("dev-tooling"),
    Path(".claude-plugin"),
    Path(".claude") / "plugins",
)
_VENDOR_MARKER = "_vendor"
_PYCACHE_MARKER = "__pycache__"

# (cli, pattern) pairs; `cli` names the destructive-default CLI category
# in the structured finding. The force-push pattern stops at shell
# command separators / comment starts so an unrelated `-f` later on the
# same line (e.g., a chained `rm -f`) is not attributed to `git push`.
_BANNED_INVOCATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bd init", re.compile(r"\bbd\s+init\b")),
    (
        "git push --force",
        re.compile(r"\bgit\s+push\b[^;&|#]*\s(--force(-with-lease)?|-f)\b"),
    ),
    ("git reset --hard", re.compile(r"\bgit\s+reset\s+--hard\b")),
    ("gh repo delete", re.compile(r"\bgh\s+repo\s+delete\b")),
)


def _iter_scanned_files(*, root: Path) -> Iterator[Path]:
    """Yield every regular file under `root` (sorted), skipping `_vendor`/`__pycache__`.

    The caller guarantees `root` exists (absent trees are filtered out
    before the walk).
    """
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if _VENDOR_MARKER in path.parts or _PYCACHE_MARKER in path.parts:
            continue
        yield path


def _is_allowlisted(*, rel_path: str, allowlist: tuple[str, ...]) -> bool:
    return any(rel_path.startswith(entry) for entry in allowlist)


def _find_offenders(*, source: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        for cli, pattern in _BANNED_INVOCATIONS:
            if pattern.search(line):
                out.append((lineno, cli))
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
    log = structlog.get_logger("no_direct_destructive_cli")
    cwd = Path.cwd()
    present_trees = [tree for tree in _SCANNED_TREES if (cwd / tree).is_dir()]
    if not present_trees:
        log.info(
            "none of the scanned agent-facing trees exist; check passes vacuously",
            scanned_trees=[str(tree) for tree in _SCANNED_TREES],
        )
        return 0
    allowlist = load_destructive_cli_allowlist(repo_root=cwd) or ()
    offenders: list[tuple[str, int, str]] = []
    for tree in present_trees:
        for path in _iter_scanned_files(root=cwd / tree):
            rel_path = path.relative_to(cwd).as_posix()
            if _is_allowlisted(rel_path=rel_path, allowlist=allowlist):
                continue
            data = path.read_bytes()
            if b"\x00" in data:
                continue
            source = data.decode("utf-8", errors="replace")
            for lineno, cli in _find_offenders(source=source):
                offenders.append((rel_path, lineno, cli))
    if offenders:
        for rel_path, lineno, cli in offenders:
            log.error(
                "direct destructive-default CLI invocation banned "
                "(invoke it through a project-local wrapper that pins safe flags, "
                "or allowlist the path via "
                "`[tool.livespec_dev_tooling].destructive_cli_allowlist`)",
                file=rel_path,
                line=lineno,
                cli=cli,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
