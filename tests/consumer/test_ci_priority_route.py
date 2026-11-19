"""Consumer-tier coverage for the reusable CI-priority route Action.

The Action is the fleet-facing boundary for `CI_PRIORITY_RECORD`: a consumer
passes its event and record to this stable path, then uses the emitted band to
select its priority runner set.  This test exercises the Action's helper with
the real GitHub output-file protocol rather than asserting a private parser.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION_DIR = _REPO_ROOT / ".github" / "actions" / "ci-priority-route"
_HELPER = _ACTION_DIR / "route.js"


def test_high_band_pr_item_routes_to_the_priority_band(*, tmp_path: Path) -> None:
    """A PR head naming a high-band item receives the Action's `high` output."""
    assert _HELPER.is_file(), (
        "the reusable CI-priority route Action must ship its helper at "
        f"{_HELPER.relative_to(_REPO_ROOT)}"
    )

    event_path = tmp_path / "event.json"
    output_path = tmp_path / "github-output"
    _ = event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "head": {"ref": "feat/livespec-dev-tooling-5wewi2"},
                    "title": "CI priority routing (livespec-dev-tooling-5wewi2)",
                }
            }
        ),
        encoding="utf-8",
    )
    record = {
        "schema": 1,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "radar_commit": "0123456789abcdef0123456789abcdef01234567",
        "items": {"livespec-dev-tooling-5wewi2": "high"},
        "default": "low",
    }
    environment = {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_OUTPUT": str(output_path),
        "INPUT_CI_PRIORITY_RECORD": json.dumps(record, separators=(",", ":")),
        "PATH": os.environ["PATH"],
    }

    completed = subprocess.run(
        ["node", str(_HELPER)],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.read_text(encoding="utf-8").splitlines() == ["band=high"]
