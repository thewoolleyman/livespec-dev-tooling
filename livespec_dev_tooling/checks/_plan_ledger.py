"""Ledger JSON readers, tenant identity, and descendant checks for plan parity.

Shared by every plan-lifecycle check that reads the ledger rather than the
checkout: `plan_epic_parity` (the lifecycle binding) and
`plan_record_conformance` (the eleven plan-record conformance verdicts). The
tenant prefix and its id matcher live here for the same reason the readers do —
two checks resolving "which records are ours" from two copies of the same
`.livespec.jsonc` read is how they come to disagree about the tenant.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

_CLOSED_STATUSES = frozenset({"closed", "done"})
_COMPLETION_RESOLUTIONS = frozenset({"completed", "merged", "released", "shipped"})
_ISSUES_JSONL = Path(".beads") / "issues.jsonl"
_LIVESPEC_CONFIG = ".livespec.jsonc"
_COMMENTS_FIELD = "comments"

__all__: list[str] = [
    "CommentReader",
    "ItemReader",
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


class ItemReader(Protocol):
    """Return ledger issue records for forward dependency scans."""

    def __call__(self, *, repo: Path) -> list[dict[str, object]]:
        """Return ledger records under `repo`."""
        ...


class CommentReader(Protocol):
    """Return one work item's append-only comment timeline."""

    def __call__(self, *, repo: Path, item_id: str) -> list[dict[str, object]]:
        """Return comment records for `item_id` under `repo`."""
        ...


def store_prefix(*, cwd: Path) -> str:
    """Return the repo store prefix from `.livespec.jsonc`'s connection block."""
    parsed = cast(
        "dict[str, object]",
        jsoncomment.loads((cwd / _LIVESPEC_CONFIG).read_text(encoding="utf-8")),
    )
    implementation = cast("dict[str, object]", parsed["implementation"])
    plugin = cast("str", implementation["plugin"])
    block = cast("dict[str, object]", parsed[plugin])
    connection = cast("dict[str, object]", block["connection"])
    return cast("str", connection["prefix"])


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


def bd_items_reader(*, repo: Path) -> list[dict[str, object]]:
    """Read ledger items from the local export when present, else `bd list --json`.

    The fallback passes `--status all` because `bd list` defaults to the OPEN
    statuses: without it every closed epic vanishes from the population, and a
    plan record whose anchor epic is closed — the archived half of the lifecycle
    binding, and the whole population of the close-evidence verdict — reads as
    having no anchor at all (`livespec-dev-tooling-aqmr`).
    """
    exported = repo / _ISSUES_JSONL
    if exported.is_file():
        return [
            cast("dict[str, object]", json.loads(line))
            for line in exported.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    completed = subprocess.run(
        ("bd", "-C", str(repo), "list", "--status", "all", "--json"),
        check=False,
        capture_output=True,
        text=True,
    )
    return parse_records(text=completed.stdout) if completed.returncode == 0 else []


def bd_comments_reader(*, repo: Path, item_id: str) -> list[dict[str, object]]:
    """Read a record's comment timeline via `bd -C <repo> show <id> --json`."""
    completed = subprocess.run(
        ("bd", "-C", str(repo), "show", item_id, "--json"),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return []
    records = parse_records(text=completed.stdout)
    comments = records[0].get(_COMMENTS_FIELD) if records else None
    if not isinstance(comments, list):
        return []
    items = cast("list[object]", comments)
    return [cast("dict[str, object]", item) for item in items if isinstance(item, dict)]


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
) -> list[tuple[Path, str, str]]:
    """Return archived anchors whose forward replacement descendants are incomplete."""
    offenders: list[tuple[Path, str, str]] = []
    closed_statuses = [item for item in statuses if item[2] in _CLOSED_STATUSES]
    if not closed_statuses:
        return offenders
    records = item_reader(repo=repo)
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
    return offenders
