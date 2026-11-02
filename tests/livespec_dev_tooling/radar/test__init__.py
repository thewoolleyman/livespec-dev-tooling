"""Tests for the radar package boundary."""

from __future__ import annotations

import livespec_dev_tooling.radar


def test_radar_package_documents_its_committed_data() -> None:
    """The package boundary describes the data it owns."""
    assert livespec_dev_tooling.radar.__doc__ == "Committed, typed maintainer radar data."
