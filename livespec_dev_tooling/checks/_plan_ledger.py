"""Ledger JSON readers, tenant identity, and descendant checks for plan parity.

Shared by every plan-lifecycle check that reads the ledger rather than the
checkout: `plan_epic_parity` (the lifecycle binding) and
`plan_record_conformance` (the eleven plan-record conformance verdicts). The
tenant prefix and its id matcher live here for the same reason the readers do —
two checks resolving "which records are ours" from two copies of the same
`.livespec.jsonc` read is how they come to disagree about the tenant.

THE READERS ARE ON THE `IOResult` RAILWAY — `livespec-dev-tooling-qndn.4`. Every
one of them reaches something (a config file, a `.beads/` export, a `bd`
subprocess) rather than projecting over a record the caller already holds, so
`IOResult` rather than `Result` is the honest container.

WHAT THE OLD SPELLING COULD NOT SAY. Each reader answered with a bare `list`,
and both `bd` readers returned `[]` on a non-zero exit — so "the tenant holds
nothing matching this query" and "the tenant was never reached" arrived at the
caller spelled identically. That is not hypothetical here: a missing
`BEADS_DOLT_PASSWORD` produces exactly that shape (`Error 1045` on stderr, a
non-zero exit, an empty answer), and `livespec-dev-tooling-7b6l` is the SAME
empty list arriving from a missing `--include-comments` — it made 8 of the 10
findings from the first armed console run false positives, each a definitive
`plan_close_evidence` verdict about a timeline nothing had read.

WHAT IS AND IS NOT A FAILURE. An invocation that COMPLETES and answers stays on
the success track whatever it answers: a `bd list` that exits 0 holding no
records, and a `bd show` payload carrying no `comments` key now that
`--include-comments` is passed unconditionally, are both ANSWERS. A failure is a
read that did not happen.

THE PROJECTIONS ARE DELIBERATELY LEFT OFF IT. `parse_status`, `record_id`,
`parse_records`, `depends_on` and `is_completion_closed` each project over text
or a record the CALLER ALREADY HOLDS and reach nothing, so none of them can
have a read that did not happen — the state this railway exists to name.
`parse_status` and `record_id` carry `X | None` returns and are settled on the
member-2 declaration lane rather than here; converting them was explicitly out
of scope for `qndn.4`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

_CLOSED_STATUSES = frozenset({"closed", "done"})
_COMPLETION_RESOLUTIONS = frozenset({"completed", "merged", "released", "shipped"})
_ISSUES_JSONL = Path(".beads") / "issues.jsonl"
_LIVESPEC_CONFIG = ".livespec.jsonc"
_COMMENTS_FIELD = "comments"
_BD_PATH_ENV = "LIVESPEC_BD_PATH"
_BD_ON_PATH = "bd"

__all__: list[str] = [
    "CommentReader",
    "ItemReader",
    "LedgerReadFailed",
    "bd_comments_reader",
    "bd_items_reader",
    "depends_on",
    "descendant_offenders",
    "parse_records",
    "parse_status",
    "record_id",
    "store_prefix",
    "tenant_id_re",
]


@dataclass(frozen=True, kw_only=True)
class LedgerReadFailed:
    """A ledger-side read that did NOT HAPPEN, and WHICH of seven reasons.

    `reason` is the discriminator a caller branches on; `detail` is the
    operator-facing evidence, and the two are deliberately separate so a
    diagnostic can name the cause without the caller parsing prose.

    The reasons are kept apart because they want DIFFERENT operator responses.
    `config-unreadable` / `config-malformed` say the repo has no resolvable
    TENANT IDENTITY, so nothing downstream can say which records are ours.
    `export-*` name a local `.beads/issues.jsonl` that exists and could not be
    turned into records. `bd-unavailable` is a broken environment (no `bd` on
    PATH), while `bd-failed` is a `bd` that ran and refused — overwhelmingly an
    absent `BEADS_DOLT_PASSWORD`, fixed by projecting the credential through
    the installed wrapper rather than by repairing the toolchain.
    `bd-output-unparseable` is a `bd` that exited 0 and printed something this
    module cannot read, which is a version skew rather than either of those.
    """

    reason: Literal[
        "config-unreadable",
        "config-malformed",
        "export-unreadable",
        "export-unparseable",
        "bd-unavailable",
        "bd-failed",
        "bd-output-unparseable",
    ]
    detail: str


class ItemReader(Protocol):
    """Return ledger issue records for forward dependency scans."""

    def __call__(self, *, repo: Path) -> IOResult[list[dict[str, object]], LedgerReadFailed]:
        """Return ledger records under `repo`, or the read that did not happen."""
        ...


class CommentReader(Protocol):
    """Return one work item's append-only comment timeline."""

    def __call__(
        self, *, repo: Path, item_id: str
    ) -> IOResult[list[dict[str, object]], LedgerReadFailed]:
        """Return comment records for `item_id` under `repo`, or the failed read."""
        ...


def store_prefix(*, cwd: Path) -> IOResult[str, LedgerReadFailed]:
    """Return the repo store prefix from `.livespec.jsonc`'s connection block.

    An ABSENT or unreadable config and a MALFORMED one are told apart because
    the repairs differ, and neither may be spelled as a prefix: every
    same-tenant verdict downstream rests on this string, so answering with a
    guess would grade one tenant's records against another's.

    Both catches are NARROW and ENUMERATED, the sanctioned hand-rolled seam
    lift: `OSError` for the read itself, and the three exceptions a config that
    parses to the wrong SHAPE raises out of the projection below. A bug raised
    in here still propagates.
    """
    try:
        text = (cwd / _LIVESPEC_CONFIG).read_text(encoding="utf-8")
    except OSError as unreadable:
        return IOFailure(LedgerReadFailed(reason="config-unreadable", detail=str(unreadable)))
    try:
        parsed = cast("dict[str, object]", jsoncomment.loads(text))
        implementation = cast("dict[str, object]", parsed["implementation"])
        plugin = cast("str", implementation["plugin"])
        block = cast("dict[str, object]", parsed[plugin])
        connection = cast("dict[str, object]", block["connection"])
        return IOSuccess(cast("str", connection["prefix"]))
    except (ValueError, KeyError, TypeError) as malformed:
        return IOFailure(LedgerReadFailed(reason="config-malformed", detail=repr(malformed)))


def tenant_id_re(*, tenant_prefix: str) -> re.Pattern[str]:
    """Return the same-tenant work-item id matcher for `tenant_prefix`."""
    return re.compile(rf"^{re.escape(tenant_prefix)}-[a-z0-9]+$")


def parse_status(*, text: str) -> str | None:
    """Extract the `status` field from `bd show --json` output, tolerating a preamble."""
    starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
    if not starts:
        return None
    parsed: object = json.loads(text[min(starts) :])
    if isinstance(parsed, list):
        parsed_list = cast("list[object]", parsed)
        record: object = parsed_list[0] if parsed_list else cast("dict[str, object]", {})
    else:
        record = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    status = cast("dict[str, object]", record).get("status")
    return status if isinstance(status, str) else None


def parse_records(*, text: str) -> list[dict[str, object]]:
    """Extract issue records from legacy or envelope `bd --json` output."""
    starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
    if not starts:
        return []
    parsed: object = json.loads(text[min(starts) :])
    parsed_dict = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    data: object = parsed_dict.get("data", cast("object", parsed))
    if isinstance(data, dict):
        return [cast("dict[str, object]", data)]
    data_list = cast("list[object]", data) if isinstance(data, list) else []
    return [cast("dict[str, object]", item) for item in data_list if isinstance(item, dict)]


def _bd_executable() -> str:
    """Return the `bd` binary the comment reader shells out to.

    The same resolution the worktree-discipline pack's
    `dev-tooling/check-no-workflow-edits.sh` performs (`resolve_bd`, in THIS
    repo — `livespec-dev-tooling`): `LIVESPEC_BD_PATH` names the
    lifecycle-guard entry point when it is set and executable, otherwise `bd`
    on PATH. Reading the override here keeps this reader on the one guarded
    binary the fleet pins rather than on whatever a caller's PATH resolves.
    """
    override = os.environ.get(_BD_PATH_ENV)
    if override and os.access(override, os.X_OK):
        return override
    return _BD_ON_PATH


def _exported_records(*, path: Path) -> IOResult[list[dict[str, object]], LedgerReadFailed]:
    """Read the local `.beads/issues.jsonl` export as one record per non-blank line.

    The two failures are separate because an export the process cannot READ is
    an environment fault, while one it cannot PARSE is a corrupt or
    half-written file — and neither is an export holding no records, which is
    the answer an empty file legitimately gives.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as unreadable:
        return IOFailure(LedgerReadFailed(reason="export-unreadable", detail=str(unreadable)))
    try:
        return IOSuccess(
            [
                cast("dict[str, object]", json.loads(line))
                for line in text.splitlines()
                if line.strip()
            ]
        )
    except ValueError as unparseable:
        return IOFailure(LedgerReadFailed(reason="export-unparseable", detail=str(unparseable)))


def _bd_records(*, args: tuple[str, ...]) -> IOResult[list[dict[str, object]], LedgerReadFailed]:
    """Spawn `bd`, READ ITS EXIT CODE, and parse the records it printed.

    Shared by both `bd` readers rather than copied into each: the returncode
    reading is the whole point of the conversion, and a second copy of the body
    is a second place for it to be dropped.

    An exit of 0 is the ONLY outcome that answers, and its record list may
    legitimately be empty. The catch is NARROW and ENUMERATED (`OSError`), the
    sanctioned hand-rolled seam lift: `bd` absent from PATH, a `bd` that cannot
    be exec'd, a fork failure.
    """
    try:
        completed = subprocess.run(args, check=False, capture_output=True, text=True)
    except OSError as unusable:
        return IOFailure(LedgerReadFailed(reason="bd-unavailable", detail=str(unusable)))
    if completed.returncode != 0:
        return IOFailure(
            LedgerReadFailed(
                reason="bd-failed",
                detail=f"exit {completed.returncode}: {completed.stderr.strip()}",
            )
        )
    try:
        return IOSuccess(parse_records(text=completed.stdout))
    except ValueError as unparseable:
        return IOFailure(LedgerReadFailed(reason="bd-output-unparseable", detail=str(unparseable)))


def bd_items_reader(*, repo: Path) -> IOResult[list[dict[str, object]], LedgerReadFailed]:
    """Read ledger items from the local export when present, else `bd list --json`.

    The fallback passes `--status all` because `bd list` defaults to the OPEN
    statuses: without it every closed epic vanishes from the population, and a
    plan record whose anchor epic is closed — the archived half of the lifecycle
    binding, and the whole population of the close-evidence verdict — reads as
    having no anchor at all (`livespec-dev-tooling-aqmr`).
    """
    exported = repo / _ISSUES_JSONL
    if exported.is_file():
        return _exported_records(path=exported)
    return _bd_records(args=("bd", "-C", str(repo), "list", "--status", "all", "--json"))


def bd_comments_reader(
    *, repo: Path, item_id: str
) -> IOResult[list[dict[str, object]], LedgerReadFailed]:
    """Read a record's comment timeline via `bd -C <repo> show <id> --json`.

    `--include-comments` is LOAD-BEARING, exactly as `--status all` is for the
    item reader above: without it the pinned `bd` omits the `comments` key
    entirely, so this reader answered `[]` for EVERY record and reported no
    error doing it. Every post-cutoff closed plan epic then failed
    `plan_close_evidence` with its evidence comment sitting unread in the
    tenant — 8 of the 10 findings from the first armed console run were that
    false positive (`livespec-dev-tooling-7b6l`).

    BOTH empty answers below stay on the SUCCESS track and are honest only
    because that flag is passed unconditionally: a payload carrying no
    `comments` key, and a payload carrying no record at all, each mean "this
    record has no timeline". The `bd` that never answered is the arm that moved.
    """
    read = _bd_records(
        args=(_bd_executable(), "-C", str(repo), "show", item_id, "--json", "--include-comments")
    )
    if isinstance(read, IOFailure):
        return IOFailure(unsafe_perform_io(read.failure()))
    records = unsafe_perform_io(read.unwrap())
    comments = records[0].get(_COMMENTS_FIELD) if records else None
    if not isinstance(comments, list):
        return IOSuccess([])
    items = cast("list[object]", comments)
    return IOSuccess([cast("dict[str, object]", item) for item in items if isinstance(item, dict)])


def record_id(*, record: dict[str, object]) -> str | None:
    """Return a ledger record's string id, if present."""
    value = record.get("id")
    return value if isinstance(value, str) else None


def depends_on(*, record: dict[str, object], epic_id: str) -> bool:
    """Return True when `record` depends on `epic_id` through a known JSON shape."""
    direct = record.get("depends_on")
    if isinstance(direct, list) and epic_id in direct:
        return True
    dependencies = record.get("dependencies")
    if not isinstance(dependencies, list):
        return False
    dependency_items = cast("list[object]", dependencies)
    for item in dependency_items:
        dependency = cast("dict[str, object]", item) if isinstance(item, dict) else {}
        blocked_by = dependency.get("depends_on_id") or dependency.get("id")
        if blocked_by == epic_id:
            return True
    return False


def is_completion_closed(*, record: dict[str, object]) -> bool:
    """Return True when a descendant is closed with a completion-shaped resolution."""
    status = record.get("status")
    resolution = record.get("resolution")
    return status in _CLOSED_STATUSES and resolution in _COMPLETION_RESOLUTIONS


def descendant_offenders(
    *,
    statuses: list[tuple[Path, str, str | None]],
    item_reader: ItemReader,
    tenant_id_re: re.Pattern[str],
    repo: Path,
) -> IOResult[list[tuple[Path, str, str]], LedgerReadFailed]:
    """Return archived anchors whose forward replacement descendants are incomplete.

    The reader's failure is carried THROUGH rather than absorbed: an unread
    ledger is not "no incomplete descendants", and before the conversion the
    two were the same empty list. The no-closed-anchor arm resolves with NO
    read at all, so it stays an answer even when the reader would have refused.
    """
    offenders: list[tuple[Path, str, str]] = []
    closed_statuses = [item for item in statuses if item[2] in _CLOSED_STATUSES]
    if not closed_statuses:
        return IOSuccess(offenders)
    read = item_reader(repo=repo)
    if isinstance(read, IOFailure):
        return IOFailure(unsafe_perform_io(read.failure()))
    records = unsafe_perform_io(read.unwrap())
    for path, anchor, _status in closed_statuses:
        for record in records:
            issue_id = record_id(record=record)
            if (
                issue_id
                and tenant_id_re.match(issue_id)
                and depends_on(record=record, epic_id=anchor)
                and not is_completion_closed(record=record)
            ):
                offenders.append((path, anchor, issue_id))
    return IOSuccess(offenders)
