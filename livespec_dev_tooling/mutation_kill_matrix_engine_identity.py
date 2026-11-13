"""Content identity for executing mutation code, independent of installed metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

__all__: list[str] = ["source_digest"]

_SOURCE_UNAVAILABLE = "executing engine source is unavailable"


def source_digest(*, root: Path) -> str:
    """Digest the executing engine's source files without depending on their location."""
    files = sorted(root.glob("mutation_kill_matrix*.py"))
    if not files:
        raise RuntimeError(_SOURCE_UNAVAILABLE)
    parts = [(path.name, hashlib.sha256(path.read_bytes()).hexdigest()) for path in files]
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode("utf-8")).hexdigest()
