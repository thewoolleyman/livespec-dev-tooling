"""shipped_path_release_guard_check — the runnable half of the shipped-path release guard.

Slice B of the R6 guard (work-item `livespec-dev-tooling-l42g`). A sibling in
spirit to `livespec_dev_tooling.checks.commit_pairs_source_and_test`: a
commit-scoped gate that reads the pending commit and the staged diff and exits
non-zero on a violation.

⛔ THIS MODULE DECIDES NOTHING. The rule lives in
`livespec_dev_tooling.shipped_path_release_guard_core.is_violation` and is
delegated to, never restated. That module's docstring assigns this one its whole
scope — RESOLVING the rule's inputs "from a real repository (its release-please
config, its plugin manifests, its staged diff)" — precisely "so that ONE RULE HAS
EXACTLY ONE IMPLEMENTATION". A second copy of the releasing-type grammar or of
the shipped-path prefix match HERE would silently defeat the split that is the
whole point of the two slices. The only thing this file adds to the decision is
the OVERRIDE MECHANISM, which the core's `is_violation` docstring likewise
assigns here: the core takes the override as a bare `bool`, and what an operator
must write to obtain one is policy rather than decision.

WHY IT IS COMMIT-MSG-SCOPED rather than pre-commit-scoped, which is structural
and not a preference: both the commit TYPE and the override marker live in the
COMMIT MESSAGE, and at pre-commit time no message exists yet. Git's `commit-msg`
hook passes the message file as `$1`; this check takes it as its one positional
argument and falls back to `<git-dir>/COMMIT_EDITMSG`.

NEITHER PER-REPO INPUT IS A FLEET CONSTANT, and each resolution site states where
its value was read from — both in the returned `_Resolved.source` and in the
structured log line every run emits:

- The RELEASING TYPES come from the repository's own release-please config
  (`changelog-sections`, the entries not marked `hidden: true`), falling back to
  release-please's defaults when the repo declares none. The per-repo-ness runs
  in BOTH directions: release-please hides `refactor` by default, so a repo
  declaring no sections does NOT release on it while livespec, which declares it
  `hidden: false`, DOES. Hardcoding either answer is the refuted premise slice A
  was amended to escape.
- The SHIPPED PREFIXES are DERIVED from the repository's plugin manifests —
  every `.claude-plugin/` directory carrying a `plugin.json` or
  `marketplace.json`, at the repo root or one level below it. A repo with no such
  manifest ships no plugin bytes and its derived set is legitimately EMPTY; the
  empty derivation is logged with its own source string rather than passing
  silently.

Wiring this gate into `lefthook.yml` and the `just check` aggregate is a
separate work-item (`livespec-dev-tooling-sxdz`) and is deliberately absent here.
Operator-facing documentation of the override trailer lives in
livespec-dev-tooling's `docs/shipped-path-release-guard.md`.

Output discipline: `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned here. Diagnostics flow through structlog
(JSON to stderr); the vendored copy under `livespec_dev_tooling/_vendor` is added
to `sys.path` at module import time.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.shipped_path_release_guard_core import (  # noqa: E402
    is_violation,
    touches_shipped_path,
)

__all__: list[str] = []


_CHECK_ID = "shipped-path-release-guard"

# Both spellings release-please accepts for its config file, in the order it
# looks for them.
_RELEASE_PLEASE_CONFIG_NAMES = ("release-please-config.json", ".release-please-config.json")
# release-please's OWN defaults — what a repo declaring no `changelog-sections`
# gets. `refactor`, `docs`, `chore`, `ci`, `build`, `style` and `test` are hidden
# by default, which is exactly why this set and livespec's declared set differ
# and why neither may be hardcoded as "the" releasing set.
_RELEASE_PLEASE_DEFAULT_RELEASING_TYPES = frozenset({"feat", "feature", "fix", "perf", "revert"})

# A plugin's shipped bytes are the directory carrying its manifest. Searched at
# the repo root and one level below it — the two layouts the fleet uses.
_MANIFEST_DIR_NAME = ".claude-plugin"
_MANIFEST_NAMES = ("plugin.json", "marketplace.json")

# The override marker: a commit-message trailer carrying a NON-EMPTY reason. The
# `\S` is load-bearing — a bare `Shipped-Path-Release-Waived:` records nothing,
# and a marker that records nothing is a bypass flag with a longer name. Matched
# per-line anywhere in the message so it survives an amend or a reflowing rebase.
_OVERRIDE_TRAILER = "Shipped-Path-Release-Waived"
_OVERRIDE_LINE = re.compile(rf"^{_OVERRIDE_TRAILER}:[ \t]*\S.*$", re.MULTILINE)


@dataclass(frozen=True, kw_only=True)
class _Resolved:
    """A per-repo input together with the SOURCE it was read from.

    The source travels WITH the value rather than being reconstructed at the log
    site, so a value can never be reported against a source that did not produce
    it.
    """

    values: frozenset[str]
    source: str


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("shipped_path_release_guard_check")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shipped-path-release-guard",
        description=(
            "Refuse a commit that edits SHIPPED bytes under a commit type this "
            "repository cuts no release on, unless the commit message carries a "
            f"`{_OVERRIDE_TRAILER}: <why>` trailer."
        ),
    )
    _ = parser.add_argument(
        "message_file",
        nargs="?",
        default=None,
        help=(
            "Path to the pending commit's message file — what git's `commit-msg` "
            "hook passes as $1. Relative paths resolve against the current "
            "working directory. Defaults to <git-dir>/COMMIT_EDITMSG."
        ),
    )
    return parser


def _visible_types(*, sections: list[object]) -> frozenset[str]:
    """The `changelog-sections` entries release-please does NOT hide.

    An entry with no `hidden` key is visible, so the test is `is not True`
    rather than a truthiness read of a possibly-absent key. Malformed entries
    are skipped rather than raising: this parses a file the CONSUMER maintains
    for release-please, and a future schema change there must not turn this
    guard into a crash.
    """
    visible: set[str] = set()
    for raw in sections:
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        name = entry.get("type")
        if isinstance(name, str) and entry.get("hidden") is not True:
            visible.add(name)
    return frozenset(visible)


def _resolve_releasing_types(*, repo_root: Path) -> _Resolved:
    """Resolve THIS repository's releasing-type set, and say where it came from."""
    for name in _RELEASE_PLEASE_CONFIG_NAMES:
        path = repo_root / name
        if not path.is_file():
            continue
        parsed = json.loads(path.read_text(encoding="utf-8"))
        document = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
        sections = document.get("changelog-sections")
        if isinstance(sections, list):
            return _Resolved(
                values=_visible_types(sections=cast("list[object]", sections)),
                source=f"{name} `changelog-sections` (the entries without `hidden: true`)",
            )
        break
    return _Resolved(
        values=_RELEASE_PLEASE_DEFAULT_RELEASING_TYPES,
        source=(
            "release-please's built-in defaults — this repository declares no "
            "`changelog-sections`, so `refactor` is hidden and does not release here"
        ),
    )


def _resolve_shipped_prefixes(*, repo_root: Path) -> _Resolved:
    """Derive THIS repository's shipped-path prefixes, and say where they came from.

    DERIVED rather than declared, from the artifact that already answers the
    question: a plugin's shipped bytes are the directory carrying its manifest.
    An empty derivation is an ANSWER (this repo ships no plugin bytes), and it
    carries its own source string so an empty set is never reported as if a
    manifest had produced it.
    """
    prefixes: set[str] = set()
    for parent in (repo_root, *sorted(p for p in repo_root.iterdir() if p.is_dir())):
        manifest_dir = parent / _MANIFEST_DIR_NAME
        if any((manifest_dir / name).is_file() for name in _MANIFEST_NAMES):
            prefixes.add(f"{manifest_dir.relative_to(repo_root).as_posix()}/")
    if not prefixes:
        return _Resolved(
            values=frozenset(),
            source=(
                f"derived: no `{_MANIFEST_DIR_NAME}/` manifest at the repository root or one "
                "level below it, so this repository ships no plugin bytes"
            ),
        )
    return _Resolved(
        values=frozenset(prefixes),
        source=(
            f"derived from the `{_MANIFEST_DIR_NAME}/` manifest directories "
            f"({', '.join(sorted(prefixes))})"
        ),
    )


def _staged_paths(*, repo_root: Path) -> tuple[str, ...]:
    """The paths staged for the pending commit."""
    # S603/S607: argv is a fixed list (literal git binary + literal flags);
    # bare `git` resolves via PATH; no untrusted shell input.
    result = subprocess.run(  # noqa: S603
        ["git", "diff", "--cached", "--name-only"],  # noqa: S607
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def _message_path(*, repo_root: Path, message_file: str | None) -> Path:
    """Where the pending commit message lives — the hook's `$1`, or the git-dir default."""
    if message_file is not None:
        return repo_root / message_file
    # S603/S607: argv is a fixed list (literal git binary + literal flags);
    # bare `git` resolves via PATH; no untrusted shell input.
    result = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--absolute-git-dir"],  # noqa: S607
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()) / "COMMIT_EDITMSG"


def _split_message(*, message: str) -> tuple[str, str]:
    """Split a raw commit message into `(subject, body)`, dropping git's `#` comments.

    Leading blank lines are skipped so a message file that opens with a comment
    block still yields the real subject. A message with no content at all yields
    two empty strings, which the core reads as an untypeable subject that cuts no
    release — the strictest honest reading.
    """
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    while lines and not lines[0].strip():
        _ = lines.pop(0)
    if not lines:
        return "", ""
    return lines[0].strip(), "\n".join(lines[1:])


def _diagnostic_commit_type(*, subject: str) -> str:
    """Echo the subject's leading `type(scope)!` token FOR THE DIAGNOSTIC ONLY.

    ⛔ NOT a second copy of the rule. This string never reaches a decision: the
    release verdict is `commit_releases`'s alone, computed from the subject
    itself inside the core. This is a plain split on the first colon so the
    refusal can name what the author actually typed, and it deliberately does
    NOT restate the core's Conventional-Commit grammar.
    """
    head, separator, _ = subject.partition(":")
    return head if separator else "<no conventional-commit type>"


def main() -> int:
    log = _configure_logger()
    args = _build_parser().parse_args()
    message_file: str | None = args.message_file
    repo_root = Path.cwd()
    path = _message_path(repo_root=repo_root, message_file=message_file)
    if not path.is_file():
        log.error(
            "the pending commit message file is not readable, so neither the commit type "
            "nor an override trailer can be read; pass the message file as the one "
            "positional argument (git's commit-msg hook supplies it as $1)",
            check_id=_CHECK_ID,
            failure_mode="message_file_unreadable",
            message_file=str(path),
            status="fail",
        )
        return 1
    message = path.read_text(encoding="utf-8")
    subject, body = _split_message(message=message)
    releasing = _resolve_releasing_types(repo_root=repo_root)
    shipped = _resolve_shipped_prefixes(repo_root=repo_root)
    changed = _staged_paths(repo_root=repo_root)
    log.info(
        "shipped-path release guard resolved this repository's inputs",
        check_id=_CHECK_ID,
        message_file=str(path),
        releasing_types=sorted(releasing.values),
        releasing_types_source=releasing.source,
        shipped_prefixes=sorted(shipped.values),
        shipped_prefixes_source=shipped.source,
    )
    if not is_violation(
        subject=subject,
        body=body,
        changed_paths=changed,
        shipped_prefixes=shipped.values,
        releasing_types=releasing.values,
        override=_OVERRIDE_LINE.search(message) is not None,
    ):
        return 0
    # Delegated per path rather than re-matched here: the prefix-boundary rule is
    # the core's, and a hand-rolled `startswith` would be the second copy this
    # split exists to prevent.
    offending = [
        p
        for p in changed
        if touches_shipped_path(changed_paths=(p,), shipped_prefixes=shipped.values)
    ]
    # Assembled before the call rather than inside it: ruff's G004 bans an
    # f-string as a logging message, and the trailer's spelling must come from
    # the constant so the remedy can never name a marker the matcher does not
    # accept.
    remedy = (
        "this commit edits SHIPPED bytes under a commit type this repository cuts no "
        "release on, so the edited bytes would reach ZERO running seats while "
        "`just ensure-plugins` reports 'already current' (it compares pins, not served "
        "bytes). Retype the commit to one of the releasing types below, or — if the edit "
        "genuinely warrants no release — record that decision with a "
        f"`{_OVERRIDE_TRAILER}: <why>` trailer on its own line in the commit message. "
        "The trailer's reason must be non-empty."
    )
    log.error(
        remedy,
        check_id=_CHECK_ID,
        failure_mode="shipped_path_edited_without_a_release",
        offending_paths=offending,
        commit_type=_diagnostic_commit_type(subject=subject),
        releasing_types=sorted(releasing.values),
        releasing_types_source=releasing.source,
        shipped_prefixes=sorted(shipped.values),
        shipped_prefixes_source=shipped.source,
        override_trailer=f"{_OVERRIDE_TRAILER}: <why this edit warrants no release>",
        documentation="livespec-dev-tooling's docs/shipped-path-release-guard.md",
        status="fail",
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
