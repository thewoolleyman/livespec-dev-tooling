"""A failed forge call stops the master-health CLI instead of being read as an empty answer.

Work-item livespec-dev-tooling-cslfje, `SPECIFICATION/contracts.md` section "Master-green gate and
external red". The open-issue listing is the guard that stops a duplicate alert, so a listing that
failed must raise rather than read as "no open issue".
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ldizae

from __future__ import annotations

import os
from pathlib import Path

import pytest

from livespec_dev_tooling.master_health_publish import RunRef, build_payload

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"


def test_a_failed_issue_listing_raises_rather_than_reading_as_no_open_issue(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `gh api` that exits non-zero surfaces its stderr; no alert is raised on a guess."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text("#!/bin/sh\necho 'HTTP 502 bad gateway' >&2\nexit 1\n", encoding="utf-8")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    with pytest.raises(RuntimeError, match="HTTP 502 bad gateway"):
        _ = build_payload(
            ci_yaml_text=_WORKFLOW.read_text(encoding="utf-8"),
            gate_job="ci-green",
            run_jobs=None,
            results_dir=tmp_path,
            run=RunRef(head_sha="abc123", run_id=77),
            repo="owner/name",
        )
