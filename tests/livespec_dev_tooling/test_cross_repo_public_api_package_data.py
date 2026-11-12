"""Lock the wheel-carried public API declarations to this tree's TOML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from livespec_dev_tooling.config import load_config

__all__: list[str] = []


def _entries(*, raw: object) -> set[tuple[str, str, str]]:
    """Normalize declaration rows into the TOML configuration's shape."""
    rows = cast("list[object]", raw)
    return {
        (
            cast("dict[str, str]", row)["file"],
            cast("dict[str, str]", row)["function"],
            cast("dict[str, str]", row)["reason"],
        )
        for row in rows
    }


def test_packaged_declarations_match_this_tree_configuration() -> None:
    root = Path(__file__).resolve().parents[2]
    data_file = root / "livespec_dev_tooling/data/cross_repo_public_api.json"
    packaged = _entries(raw=json.loads(data_file.read_text(encoding="utf-8")))
    configured = {
        (entry.file.as_posix(), entry.function, entry.reason)
        for entry in load_config(repo_root=root).cross_repo_public_api
    }
    assert packaged == configured, (
        "cross_repo_public_api package data disagrees with pyproject.toml: "
        f"missing={sorted(configured - packaged)!r}; extra={sorted(packaged - configured)!r}"
    )
