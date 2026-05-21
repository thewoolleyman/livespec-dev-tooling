"""Smoke test for the empty Phase-G.2 scaffold.

Exercises both package __init__.py files so coverage reports the
true 100% line + branch result against the source tree. Phase G.4
will replace this with real per-check paired tests as the
enforcement-suite scripts migrate.
"""

from __future__ import annotations

import livespec_dev_tooling
import livespec_dev_tooling.checks


def test_package_init_has_empty_public_surface() -> None:
    assert livespec_dev_tooling.__all__ == []


def test_checks_subpackage_init_has_empty_public_surface() -> None:
    assert livespec_dev_tooling.checks.__all__ == []
