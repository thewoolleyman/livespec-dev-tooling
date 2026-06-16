"""Shared pytest fixtures for the livespec-dev-tooling suite.

Hosts an autouse fixture that resets structlog's PROCESS-GLOBAL configuration
after every test, so the suite is order- and worker-independent under
`pytest -n auto --cov` (the `check-per-file-coverage` invocation).

Root cause of the isolation bug this fixes: modules such as
`livespec_dev_tooling/fleet/wire_fleet_member.py` call
`structlog.configure(logger_factory=PrintLoggerFactory(file=sys.stderr))`, which
snapshots `sys.stderr` at configure time into structlog's global config. Under
pytest capture (especially each xdist worker's per-test capture), that stream is
a buffer closed at the test's teardown; a later test on the same worker that
inherits the stale global config then writes to the closed buffer and raises
`ValueError: I/O operation on closed file`. The failure was order-dependent —
the affected fleet tests pass in isolation but fail after a polluting test runs
first. Resetting structlog's defaults at each test's teardown removes the
cross-test leakage.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# structlog ships vendored; resolve the bare `import structlog` the same way the
# product modules do (each inserts this dir onto sys.path before importing it).
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "livespec_dev_tooling" / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.


@pytest.fixture(autouse=True)
def _reset_structlog_global_config() -> Iterator[None]:
    """Reset structlog's process-global config after each test (isolation)."""
    yield
    structlog.reset_defaults()
