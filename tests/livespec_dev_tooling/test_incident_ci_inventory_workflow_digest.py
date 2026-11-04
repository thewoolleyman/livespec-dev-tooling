"""The packaged incident CI inventory tracks every committed edit to ci.yml."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from livespec_dev_tooling import incident_ci_inventory as module


def test_packaged_inventory_digest_tracks_the_committed_ci_workflow():
    # Any edit to ci.yml, even a runs-on change, must regenerate the packaged
    # inventory through render_inventory and bump the module's _SHA256 in the
    # same change, or load_inventory refuses the released bytes.
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_bytes()
    inventory = root / "livespec_dev_tooling/data/incident-ci-inventory.json"
    packaged = json.loads(inventory.read_text())
    assert packaged["workflow_sha256"] == hashlib.sha256(workflow).hexdigest()
    assert module.load_inventory()
