"""Controller-owned enablement records for expedited incident execution."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_enablement_records_a_confirmed_identity_once_and_retries_without_rewriting(
    tmp_path: Path,
) -> None:
    """The control route retains one exact, durable enablement receipt."""
    enablement = importlib.import_module("livespec_dev_tooling.incident_enablement")
    state = enablement.EnablementState(directory=tmp_path, repository="owner/repo")

    first = state.enable(manifest_sha256="a" * 64)
    record = tmp_path / "enablement.json"

    assert first == {"status": "enabled", "repository": "owner/repo", "manifest_sha256": "a" * 64}
    assert (
        record.read_bytes()
        == b'{"manifest_sha256": "' + b"a" * 64 + b'", "repository": "owner/repo"}\n'
    )
    assert state.enable(manifest_sha256="a" * 64) == first
    assert (
        record.read_bytes()
        == b'{"manifest_sha256": "' + b"a" * 64 + b'", "repository": "owner/repo"}\n'
    )
