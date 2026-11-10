"""Rewrite one clone's orchestrator install record, then verify it held.

Every `claude plugin` command rewrites `installed_plugins.json` whole, so the
tag adopt changes exactly one record and nothing else: it writes through a
temporary file and an atomic rename, re-reads the file immediately before the
rename, and re-applies its one change to newly read content at most three
times. It compares builds by `gitCommitSha`, never by `version`, which the CLI
writes in more than one form. A write by another process can still revert the
clone's record after the rename, which is why the record is re-read
immediately and again after a settle period; running the tag adopt again is
the recovery.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._orchestrator_hold import ORCHESTRATOR_PLUGIN
from livespec_dev_tooling.fleet._tag_adopt_build import carries_required
from livespec_dev_tooling.fleet._tag_adopt_checks import json_object

__all__: list[str] = [
    "MAX_REAPPLIES",
    "SETTLE_SECONDS",
    "RecordCheck",
    "clone_record_refusal",
    "differs_only_in_clone",
    "verify_record",
    "write_record",
]

MAX_REAPPLIES = 3
SETTLE_SECONDS = 60.0


def _is_clone_record(*, entry: object, clone: str) -> bool:
    if not isinstance(entry, dict):
        return False
    record = cast("dict[str, object]", entry)
    return record.get("scope") == "project" and record.get("projectPath") == clone


def _orchestrator_records(*, registry: Mapping[str, object]) -> list[object]:
    plugins = registry.get("plugins")
    records = (
        cast("dict[str, object]", plugins).get(ORCHESTRATOR_PLUGIN)
        if isinstance(plugins, dict)
        else None
    )
    return cast("list[object]", records) if isinstance(records, list) else []


def clone_record_refusal(*, registry: Mapping[str, object], clone: str) -> str:
    """Why the clone lacks exactly one project-scope orchestrator record, or ''."""
    count = sum(
        _is_clone_record(entry=entry, clone=clone)
        for entry in _orchestrator_records(registry=registry)
    )
    if count == 1:
        return ""
    return (
        f"{clone} has {count} project-scope {ORCHESTRATOR_PLUGIN} install records, "
        "not exactly one; nothing was moved"
    )


def _rewritten(
    *, registry: Mapping[str, object], clone: str, fields: Mapping[str, str]
) -> dict[str, object]:
    """The registry with only the clone's record carrying the new fields."""
    updated = json.loads(json.dumps(registry))
    records = _orchestrator_records(registry=updated)
    for index, entry in enumerate(records):
        if _is_clone_record(entry=entry, clone=clone):
            records[index] = {**cast("dict[str, object]", entry), **fields}
    return cast("dict[str, object]", updated)


def _without_clone(*, registry: Mapping[str, object], clone: str) -> object:
    stripped = json.loads(json.dumps(registry))
    records = _orchestrator_records(registry=stripped)
    records[:] = [entry for entry in records if not _is_clone_record(entry=entry, clone=clone)]
    return stripped


def differs_only_in_clone(
    *, before: Mapping[str, object], after: Mapping[str, object], clone: str
) -> bool:
    """Whether two parsed registries are equal once the clone's record is set aside."""
    return _without_clone(registry=before, clone=clone) == _without_clone(
        registry=after, clone=clone
    )


def write_record(
    *, registry_path: Path, clone: str, fields: Mapping[str, str], read_text: Callable[[Path], str]
) -> str:
    """Atomically rewrite only the clone's record; the empty string on success, else the cause."""
    temporary = registry_path.with_name(f"{registry_path.name}.livespec-adopt.tmp")
    text = read_text(registry_path)
    for _attempt in range(1 + MAX_REAPPLIES):
        registry = json_object(text=text)
        refusal = clone_record_refusal(registry=registry, clone=clone)
        if refusal:
            return refusal
        payload = json.dumps(_rewritten(registry=registry, clone=clone, fields=fields), indent=2)
        payload += "\n" if text.endswith("\n") else ""
        _ = temporary.write_text(payload, encoding="utf-8")
        current = read_text(registry_path)
        if current == text:
            _ = temporary.replace(registry_path)
            wrote = json_object(text=payload)
            only_clone = differs_only_in_clone(before=registry, after=wrote, clone=clone)
            return (
                ""
                if only_clone
                else f"the write to {registry_path} changed more than {clone}'s record"
            )
        text = current
    temporary.unlink(missing_ok=True)
    return (
        f"{registry_path} kept changing under the write; re-applied {MAX_REAPPLIES} times "
        "and wrote nothing"
    )


@dataclass(frozen=True, kw_only=True)
class RecordCheck:
    """What the clone's record must still name when it is re-read."""

    clone: str
    commit: str
    required: tuple[str, ...]


def _record_cause(*, registry_text: str, check: RecordCheck) -> str:
    """Why the clone's record no longer names the adopted build, or ''."""
    records = [
        cast("dict[str, object]", entry)
        for entry in _orchestrator_records(registry=json_object(text=registry_text))
        if _is_clone_record(entry=entry, clone=check.clone)
    ]
    if len(records) != 1:
        return f"{check.clone} has {len(records)} project-scope install records"
    sha, install_path = records[0].get("gitCommitSha"), records[0].get("installPath")
    if not isinstance(sha, str) or sha.strip().lower() != check.commit:
        return f"{check.clone}'s install record names {sha}, not the tag's commit {check.commit}"
    if not isinstance(install_path, str) or not carries_required(
        directory=Path(install_path), required=check.required
    ):
        return f"{install_path} no longer carries every required path"
    return ""


def verify_record(
    *,
    registry_path: Path,
    check: RecordCheck,
    read_text: Callable[[Path], str],
    sleep: Callable[[float], None],
    settle_seconds: float,
) -> str:
    """Re-read the clone's record immediately and after the settle period; '' when it held."""
    cause = _record_cause(registry_text=read_text(registry_path), check=check)
    if cause:
        return f"re-read immediately after the write: {cause}"
    sleep(settle_seconds)
    cause = _record_cause(registry_text=read_text(registry_path), check=check)
    if cause:
        return (
            f"re-read after a {settle_seconds:g} s settle period: {cause}; run the tag adopt again"
        )
    return ""
