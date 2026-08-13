"""Ledger JSON readers and descendant checks for plan-thread parity."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Protocol, cast

_CLOSED_STATUSES = frozenset({"closed", "done"})
_COMPLETION_RESOLUTIONS = frozenset({"completed", "merged", "released", "shipped"})
_ISSUES_JSONL = Path(".beads") / "issues.jsonl"

__all__: list[str] = [
    "ItemReader",
    "bd_items_reader",
    "bd_status_reader",
    "descendant_offenders",
    "parse_records",
    "parse_status",
]


class ItemReader(Protocol):
    """Return ledger issue records for forward dependency scans."""

    def __call__(self, *, repo: Path) -> list[dict[str, object]]:
        """Return ledger records under `repo`."""
        ...


def parse_status(*, text: str) -> str | None:
    """Extract the `status` field from `bd show --json` output, tolerating a preamble."""
    starts = [pos for pos in (text.find("{"), text.find("[")) if pos >= 0]
    if not starts:
        return None
    parsed: object = json.loads(text[min(starts) :])
    if isinstance(parsed, list):
        parsed_list = cast("list[object]", parsed)
        record: object = parsed_list[0] if parsed_list else {}
    else:
        record = parsed
    if not isinstance(record, dict):
        return None
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


def bd_status_reader(*, epic_id: str, repo: Path) -> str | None:
    """Read a ledger epic's status via `bd -C <repo> show <id> --json`."""
    completed = subprocess.run(
        ("bd", "-C", str(repo), "show", epic_id, "--json"),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return parse_status(text=completed.stdout)


def bd_items_reader(*, repo: Path) -> list[dict[str, object]]:
    """Read ledger items from the local export when present, else `bd list --json`."""
    exported = repo / _ISSUES_JSONL
    if exported.is_file():
        return [
            cast("dict[str, object]", json.loads(line))
            for line in exported.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    completed = subprocess.run(
        ("bd", "-C", str(repo), "list", "--json"),
        check=False,
        capture_output=True,
        text=True,
    )
    return parse_records(text=completed.stdout) if completed.returncode == 0 else []


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
