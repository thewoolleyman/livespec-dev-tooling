"""work_item_interpolation_delimiters — non-closed ledger records must stay dispatchable.

A work item whose own TEXT reproduces a literal doubled-brace
template-interpolation delimiter pair makes ITSELF undispatchable: dispatch graph
construction fails on an undefined template variable whose name appears only in
the item record and never in the workflow. The escaper in the Dispatcher is
correct but SELF-CANCELLING — rendering its output once restores the original
delimiter, and the goal is rendered twice (file inlining writes the rendered
value back, variable expansion parses it again) — so the failure survives an
escaper that visibly runs.

Manual repair does not hold. A 2026-08-20 sweep repaired nine non-closed records
in this tenant and the population regenerated within roughly a day: one record
filed contaminated from birth, one previously-clean record poisoned by comments.
That is the argument for a check rather than another sweep.

TWO VERDICTS, because the remedies differ. A pair in an EDITABLE field
(`title` / `description` / `design` / `acceptance_criteria` / `notes` /
`metadata`) is repairable in place. A pair in a COMMENT is not: comments are
append-only and are assembled verbatim into future dispatch briefs, so the
record is permanently poisoned and the remedy is a clean-text successor or a
non-dispatchable hold — NEVER evidence deletion. Collapsing the two into one
verdict would tell an operator to do the impossible.

POPULATION: non-closed records only. Closed items are never dispatched and
historical ones still carry the pair, so scoping to non-closed is what makes
arming safe rather than a repeat of arming-ahead-of-adoption.

FALSE POSITIVES ARE THE NORMAL CASE — every contaminated record measured was
legitimately ABOUT CI or about interpolation syntax. A bare ban would punish
writing about workflow syntax, so this check ships WITH the substitution
convention (`docs/work-item-interpolation-delimiters.md`): the literal opener
written as U+27E6, the literal closer as U+27E7, plus a short legend on the
record. Without that convention there is no conforming way to file such an item.

ARMED-ONLY: self-skips unless `LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS`
is truthy and `BEADS_DOLT_PASSWORD` is present, because it reads ledger state.
Arm it only after a measured sweep reports zero non-closed offenders. An EMPTY
ledger read while armed is a FAILURE, not a clean sweep: an armed check
inspecting nothing is a misconfiguration, and reading it as a pass would be the
fail-open this check exists to remove.

This module never writes the hazardous token, in its source or in its
diagnostics. The delimiters are BUILT from single braces at import time, and a
finding reports the delimiter by NAME (`open` / `close`) rather than echoing it —
otherwise the check's own output would poison whatever assembles it.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at import time.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._plan_ledger import (  # noqa: E402
    ItemReader,
    bd_items_reader,
    parse_records,
    record_id,
)

__all__: list[str] = []


_RUN_LEVER = "LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS"
_CRED_ENV = "BEADS_DOLT_PASSWORD"
_CLOSED_STATUSES = frozenset({"closed", "done"})
_COMMENTS_FIELD = "comments"

# The editable prose carriers, in the order a dispatch brief assembles them.
# Every one is repairable in place, which is what separates them from a comment.
_EDITABLE_FIELDS = (
    "title",
    "description",
    "design",
    "acceptance_criteria",
    "notes",
    "metadata",
)

# BUILT, never written literally: this file must not carry the token it bans,
# because a goal that inlines it would re-poison the very brief it is inlined
# into. Each delimiter is reported by NAME for the same reason.
_BRACE_OPEN = "{"
_BRACE_CLOSE = "}"
_DELIMITERS = ((_BRACE_OPEN * 2, "open"), (_BRACE_CLOSE * 2, "close"))

_CONVENTION_DOC = "docs/work-item-interpolation-delimiters.md"
_EDITABLE_REMEDIATION = (
    "rewrite the pair with the substitution characters U+27E6 (opener) and "
    f"U+27E7 (closer) and add the legend line; see {_CONVENTION_DOC}. The field "
    "is editable, so repairing it in place is the whole remedy."
)
_COMMENT_REMEDIATION = (
    "comments are append-only and are assembled verbatim into future dispatch "
    "briefs, so this record is permanently poisoned: file a clean-text successor "
    "using the substitution characters, or put the item on a non-dispatchable "
    f"hold. NEVER delete the evidence. See {_CONVENTION_DOC}."
)
_EMPTY_LEDGER_REMEDIATION = (
    "the armed check read zero ledger records, so it inspected nothing and could "
    "only ever pass. Supply the tenant credential through the installed wrapper "
    "and re-run; a silent empty read is the fail-open this check exists to remove."
)


class CommentReader(Protocol):
    """Return a work item's append-only comment timeline."""

    def __call__(self, *, repo: Path, item_id: str) -> list[dict[str, object]]:
        """Return comment records for `item_id` under `repo`."""
        ...


def _is_armed() -> bool:
    """True iff the RUN lever is truthy AND the beads credential is present."""
    return bool(os.environ.get(_RUN_LEVER)) and bool(os.environ.get(_CRED_ENV))


def _configure_logging() -> structlog.stdlib.BoundLogger:
    """Configure structlog for JSON-to-stderr diagnostics and return the logger."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("work_item_interpolation_delimiters")


def _delimiter_names(*, text: str) -> tuple[str, ...]:
    """Return the NAMES of the literal interpolation delimiters present in `text`."""
    return tuple(name for pair, name in _DELIMITERS if pair in text)


def _reachable_strings(*, prefix: str, value: object) -> list[tuple[str, str]]:
    """Return `(field_path, text)` pairs for every string reachable from `value`.

    Only STRINGS are collected. A `metadata` block is never serialized to JSON
    first: a nested object's own closing punctuation would read as the banned
    pair and manufacture a violation out of well-formed structure.
    """
    if isinstance(value, str):
        return [(prefix, value)]
    if isinstance(value, dict):
        mapping = cast("dict[str, object]", value)
        return [
            found
            for key in sorted(mapping)
            for found in _reachable_strings(prefix=f"{prefix}.{key}", value=mapping[key])
        ]
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [
            found
            for index, item in enumerate(items)
            for found in _reachable_strings(prefix=f"{prefix}[{index}]", value=item)
        ]
    return []


def _editable_texts(*, record: dict[str, object]) -> list[tuple[str, str]]:
    """Return `(field_path, text)` pairs for every editable prose carrier."""
    return [
        found
        for field in _EDITABLE_FIELDS
        for found in _reachable_strings(prefix=field, value=record.get(field))
    ]


def _comment_delimiter_names(*, comment: dict[str, object]) -> tuple[str, ...]:
    """Return the delimiter names carried anywhere in one comment record."""
    names: list[str] = []
    for _path, text in _reachable_strings(prefix=_COMMENTS_FIELD, value=comment):
        names.extend(name for name in _delimiter_names(text=text) if name not in names)
    return tuple(names)


def _comment_field(*, key: str, comment: dict[str, object]) -> str:
    """Return a comment's identifying string field, or an empty string when absent."""
    value = comment.get(key)
    return value if isinstance(value, str) else ""


def _comments_of(*, records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return the comment records carried by the first ledger record, if any."""
    comments = records[0].get(_COMMENTS_FIELD) if records else None
    if not isinstance(comments, list):
        return []
    items = cast("list[object]", comments)
    return [cast("dict[str, object]", item) for item in items if isinstance(item, dict)]


def _bd_comment_reader(*, repo: Path, item_id: str) -> list[dict[str, object]]:
    """Read a record's comment timeline via `bd -C <repo> show <id> --json`."""
    completed = subprocess.run(
        ("bd", "-C", str(repo), "show", item_id, "--json"),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return []
    return _comments_of(records=parse_records(text=completed.stdout))


def _is_non_closed(*, record: dict[str, object]) -> bool:
    """True when a record is still dispatchable — closed items leave the population."""
    return record.get("status") not in _CLOSED_STATUSES


def _report_editable(
    *, log: structlog.stdlib.BoundLogger, item_id: str, record: dict[str, object]
) -> int:
    """Log one finding per contaminated editable field and return the finding count."""
    findings = 0
    for field, text in _editable_texts(record=record):
        for name in _delimiter_names(text=text):
            findings += 1
            log.error(
                "non-closed work item carries a literal interpolation delimiter "
                "in an editable field",
                work_item=item_id,
                field=field,
                delimiter=name,
                verdict="editable-repair-in-place",
                remediation=_EDITABLE_REMEDIATION,
            )
    return findings


def _report_comments(
    *,
    log: structlog.stdlib.BoundLogger,
    item_id: str,
    comments: list[dict[str, object]],
) -> int:
    """Log one finding per contaminated comment and return the finding count."""
    findings = 0
    for comment in comments:
        comment_id = _comment_field(key="id", comment=comment)
        created_at = _comment_field(key="created_at", comment=comment)
        for name in _comment_delimiter_names(comment=comment):
            findings += 1
            log.error(
                "non-closed work item carries a literal interpolation delimiter "
                "in an append-only comment",
                work_item=item_id,
                field=f"{_COMMENTS_FIELD}:{comment_id}",
                comment_id=comment_id,
                comment_created_at=created_at,
                delimiter=name,
                verdict="append-only-successor-or-hold",
                remediation=_COMMENT_REMEDIATION,
            )
    return findings


def main(
    *,
    item_reader: ItemReader | None = None,
    comment_reader: CommentReader | None = None,
) -> int:
    """Run the armed ledger-backed interpolation-delimiter sweep."""
    log = _configure_logging()
    if not _is_armed():
        log.info(
            "skipped — set LIVESPEC_RUN_WORK_ITEM_INTERPOLATION_DELIMITERS and provide "
            "BEADS_DOLT_PASSWORD to arm",
            run_lever=_RUN_LEVER,
            credential=_CRED_ENV,
            convention=_CONVENTION_DOC,
        )
        return 0
    cwd = Path.cwd()
    read_items: ItemReader = bd_items_reader if item_reader is None else item_reader
    read_comments: CommentReader = _bd_comment_reader if comment_reader is None else comment_reader
    records = read_items(repo=cwd)
    if not records:
        log.error(
            "armed interpolation-delimiter sweep read zero ledger records",
            repo=str(cwd),
            remediation=_EMPTY_LEDGER_REMEDIATION,
        )
        return 1
    findings = 0
    for record in records:
        item_id = record_id(record=record)
        if item_id is None or not _is_non_closed(record=record):
            continue
        findings += _report_editable(log=log, item_id=item_id, record=record)
        findings += _report_comments(
            log=log, item_id=item_id, comments=read_comments(repo=cwd, item_id=item_id)
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
