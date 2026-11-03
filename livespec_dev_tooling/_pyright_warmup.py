"""Serial first-run provisioning of a consumer's locked pyright.

pyright's first run downloads Node and a bundled typeshed into
`~/.cache/pyright-python`. Two pyright-invoking check targets that start
together type-check against a partial typeshed, so the parallel dispatcher
completes this install before it fans out.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import tomli  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = ["warm_locked_pyright"]


def _dev_group_pins_pyright(*, lock_text: str) -> bool:
    """True when the lock's root package pins pyright in its `dev` group."""
    packages = cast("list[dict[str, object]]", tomli.loads(lock_text).get("package", []))
    roots = [
        package
        for package in packages
        if "." in cast("dict[str, object]", package.get("source", {})).values()
    ]
    return any(
        entry.get("name") == "pyright"
        for root in roots
        for entry in cast(
            "dict[str, list[dict[str, object]]]", root.get("dev-dependencies", {})
        ).get("dev", [])
    )


def warm_locked_pyright(*, cwd: Path, already_warmed: bool) -> int:
    """Run locked pyright once before a caller fans out check targets."""
    if already_warmed or not (cwd / "uv.lock").is_file():
        return 0
    if not _dev_group_pins_pyright(lock_text=(cwd / "uv.lock").read_text(encoding="utf-8")):
        return 0
    return subprocess.call(  # noqa: S603
        ["uv", "run", "--frozen", "pyright", "--version"],  # noqa: S607
    )
