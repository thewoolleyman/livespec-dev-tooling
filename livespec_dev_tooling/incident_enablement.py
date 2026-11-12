"""Controller-owned enablement records for expedited incident execution."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = ["EnablementState"]


@dataclass(frozen=True, kw_only=True)
class EnablementState:
    """One controller installation's durable enablement record."""

    directory: Path
    repository: str

    def enable(self, *, manifest_sha256: str) -> dict[str, str]:
        """Retain an exact confirmed identity without rewriting an exact retry."""
        record = {"repository": self.repository, "manifest_sha256": manifest_sha256}
        path = self.directory / "enablement.json"
        encoded = _encoded(record=record)
        if path.exists() and path.read_bytes() == encoded:
            return {"status": "enabled", **record}
        _save(path=path, encoded=encoded)
        return {"status": "enabled", **record}


def _encoded(*, record: dict[str, str]) -> bytes:
    return (
        '{"manifest_sha256": "'
        + record["manifest_sha256"]
        + '", "repository": "'
        + record["repository"]
        + '"}\n'
    ).encode()


def _save(*, path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            _ = stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _ = Path(temporary).replace(path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
