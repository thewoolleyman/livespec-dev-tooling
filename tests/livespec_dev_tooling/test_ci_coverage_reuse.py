"""The coverage-reuse record contract stays available to CI telemetry."""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []

_MODULE = "livespec_dev_tooling.ci_coverage_reuse"
_MODULE_PATH = Path(__file__).resolve().parents[2] / "livespec_dev_tooling" / "ci_coverage_reuse.py"


def test_the_reuse_contract_module_exports_the_coverage_consumer_identifier() -> None:
    """The cohesive contract module is importable after its genuine Red file assertion."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE)

    assert module.COVERAGE_CONSUMER_JOB_ID == "check-coverage"
