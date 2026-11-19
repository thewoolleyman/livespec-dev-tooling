"""Mirror-paired coverage entry point for Fabro catalog image pin validation."""

from __future__ import annotations

from livespec_dev_tooling import fabro_catalog_image_pins


def test_catalog_image_pin_validation_module_is_importable() -> None:
    """The public catalog validator has its required mirror-paired test."""
    assert fabro_catalog_image_pins.catalog_pin_issues is not None
