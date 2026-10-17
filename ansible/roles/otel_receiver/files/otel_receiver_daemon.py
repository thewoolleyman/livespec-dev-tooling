#!/usr/bin/env python3
"""Persistent OTel receiver for a Fabro factory host.

Installed by livespec-dev-tooling's `ansible/roles/otel_receiver`. It gives the
host's Fabro servers a receiver that is always listening, instead of one a
dispatch process arms only for its own run.

It adds no product logic. It runs the `OtelReceiver` and `HoneycombHttpExporter`
of the livespec-orchestrator-beads-fabro release named by
`LIVESPEC_OTEL_RECEIVER_ORCHESTRATOR_ROOT`, so that release's attribute
allowlist decides what reaches Honeycomb. Its journal, heartbeat and cost
files live in `LIVESPEC_OTEL_RECEIVER_STATE_DIR`, outside the source tree.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

ORCHESTRATOR_ROOT = Path(os.environ["LIVESPEC_OTEL_RECEIVER_ORCHESTRATOR_ROOT"])
STATE_DIR = Path(os.environ["LIVESPEC_OTEL_RECEIVER_STATE_DIR"])
SCRIPTS_DIR = ORCHESTRATOR_ROOT / ".claude-plugin" / "scripts"
VENDOR_DIR = SCRIPTS_DIR / "_vendor"
for _path in (SCRIPTS_DIR, VENDOR_DIR):
    sys.path.insert(0, str(_path))

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (  # noqa: E402
    DEFAULT_DISPATCH_COST_MODEL_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink  # noqa: E402
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (  # noqa: E402
    cost_sink_path,
    heartbeat_path,
)
from livespec_orchestrator_beads_fabro.commands._otel_enrich import (  # noqa: E402
    HoneycombHttpExporter,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import (  # noqa: E402
    HeartbeatSink,
    OtelReceiver,
    resolve_receiver_config,
)

_HONEYCOMB_INGEST_KEY_ENV = "HONEYCOMB_INGEST_KEY_LIVESPEC"


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    args = SimpleNamespace(journal=str(STATE_DIR / "otel-receiver-daemon.jsonl"))
    config = resolve_receiver_config(environ=dict(os.environ))
    exporter = HoneycombHttpExporter(ingest_key=os.environ.get(_HONEYCOMB_INGEST_KEY_ENV, ""))
    heartbeat = HeartbeatSink(path=heartbeat_path(args=args, repo=ORCHESTRATOR_ROOT))
    cost = CostSink(path=cost_sink_path(args=args, repo=ORCHESTRATOR_ROOT))
    default_model = os.environ.get(DEFAULT_DISPATCH_COST_MODEL_ENV, "").strip() or None
    receiver = OtelReceiver(
        config=config,
        exporter=exporter,
        heartbeat=heartbeat,
        cost=cost,
        default_model=default_model,
    )
    receiver.start()
    sys.stdout.write(f"otel-receiver-daemon: listening on {config.host}:{receiver.bound_port}\n")
    sys.stdout.flush()
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
