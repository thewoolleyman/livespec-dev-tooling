"""Tests that the kill matrix's result cache file is always one writer's whole document.

The cache lives on a volume that outlasts the Job writing it, and a later Job
resumes from it.  So a save must survive a node crash right after its rename,
two runs saving to one path must never mix their bytes, and a failed save
must leave nothing behind.
"""

from __future__ import annotations

import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.mutation_kill_matrix_cache_store"


def test_a_save_syncs_its_bytes_to_disk_before_it_renames_them_into_place(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash right after the rename finds whole bytes: they were synced while still temporary."""
    module = importlib.import_module(_MODULE)
    path = tmp_path / "reports" / "cache.json"
    entries = {"k": module.CachedOutcome(unapplied=True, killed_by=())}
    in_place_at_sync: list[bool] = []
    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        in_place_at_sync.append(path.exists())
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)

    module.save_cache(path=path, entries=entries)

    assert in_place_at_sync == [False]
    assert module.load_cache(path=path) == entries
    assert path.stat().st_mode & 0o777 == 0o644


def test_concurrent_saves_to_one_path_each_leave_a_whole_cache(*, tmp_path: Path) -> None:
    """Two writers never share a temporary file, so the cache is always one writer's document."""
    module = importlib.import_module(_MODULE)
    path = tmp_path / "cache.json"
    documents = [
        {
            f"writer-{writer}-{key}": module.CachedOutcome(unapplied=True, killed_by=())
            for key in range(50)
        }
        for writer in range(4)
    ]

    def write(entries: dict[str, object]) -> list[object]:
        seen: list[object] = []
        for _round in range(25):
            module.save_cache(path=path, entries=entries)
            seen.append(module.load_cache(path=path))
        return seen

    with ThreadPoolExecutor(max_workers=len(documents)) as pool:
        seen = [document for found in pool.map(write, documents) for document in found]

    assert all(document in documents for document in seen)
    assert [entry.name for entry in tmp_path.iterdir()] == ["cache.json"]


def test_a_save_that_cannot_rename_leaves_no_temporary_file_behind(*, tmp_path: Path) -> None:
    """A failed save raises and removes its own temporary file."""
    module = importlib.import_module(_MODULE)
    path = tmp_path / "cache.json"
    (path / "occupied").mkdir(parents=True)

    with pytest.raises(OSError, match=r"cache\.json"):
        module.save_cache(path=path, entries={})

    assert [entry.name for entry in tmp_path.iterdir()] == ["cache.json"]
