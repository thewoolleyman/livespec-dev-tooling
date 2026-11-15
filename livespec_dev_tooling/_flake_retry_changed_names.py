"""Names a changed path contributes to flake-retry closure matching."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = ["changed_names"]


def changed_names(*, paths: set[Path]) -> set[str]:
    """Produce whole literal spellings that can identify changed code or data paths."""
    names: set[str] = set()
    for path in paths:
        names.update((path.as_posix(), path.name))
        names.update(parent.as_posix() for parent in path.parents if parent != Path())
        if path.suffix == ".py":
            names.add(".".join(path.with_suffix("").parts))
    return names
