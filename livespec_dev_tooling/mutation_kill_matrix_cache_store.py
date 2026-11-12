"""The Rule-26 kill matrix's result cache file: load it, and save it whole.

The cache lives on a volume that outlasts the Job writing it, and the next
Job resumes from it (see `mutation_kill_matrix_checkpoint`).  A save therefore
writes a temporary file of its own beside the cache, syncs it to disk, and
renames it over the cache.  A run killed mid-save, or a node that crashes
right after the rename, leaves a whole cache: the earlier one or the new one.
Two runs saving to one path never share a temporary file, and a save that
fails removes its own.  What an entry's key means is
`mutation_kill_matrix_cache`'s concern.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "CACHE_SCHEMA",
    "CachedOutcome",
    "load_cache",
    "save_cache",
    "write_whole",
]


CACHE_SCHEMA = "rule-26-kill-matrix-cache/1"
# mkstemp creates an owner-only file; the cache keeps the mode it always had.
_CACHE_MODE = 0o644


@dataclass(frozen=True, kw_only=True)
class CachedOutcome:
    """One mutant's reusable outcome: unapplied, or the tests that killed it."""

    unapplied: bool
    killed_by: tuple[str, ...]


def load_cache(*, path: Path | None) -> dict[str, CachedOutcome] | None:
    """Load a cache, or None when there is none, it is unreadable, or its schema is foreign."""
    if path is None or not path.is_file():
        return None
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(loaded, dict):
        return None
    document = cast("dict[str, object]", loaded)
    if document.get("schema") != CACHE_SCHEMA:
        return None
    entries = cast("dict[str, dict[str, object]]", document.get("entries", {}))
    return {
        key: CachedOutcome(
            unapplied=bool(entry.get("unapplied", False)),
            killed_by=tuple(str(test) for test in cast("list[object]", entry.get("killed_by", []))),
        )
        for key, entry in entries.items()
    }


def write_whole(*, path: Path, text: str) -> None:
    """Replace `path` with `text` at once: a synced temporary file of its own, then a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, partial = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".", suffix=".partial"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            _ = handle.write(text)
            handle.flush()
            os.fchmod(handle.fileno(), _CACHE_MODE)
            os.fsync(handle.fileno())
        _ = Path(partial).replace(path)
    finally:
        Path(partial).unlink(missing_ok=True)


def save_cache(*, path: Path, entries: dict[str, CachedOutcome]) -> None:
    """Write the cache holding exactly these outcomes, replacing any earlier file at once."""
    document = {
        "schema": CACHE_SCHEMA,
        "entries": {
            key: {"unapplied": outcome.unapplied, "killed_by": list(outcome.killed_by)}
            for key, outcome in sorted(entries.items())
        },
    }
    write_whole(path=path, text=json.dumps(document, indent=2, sort_keys=True) + "\n")
