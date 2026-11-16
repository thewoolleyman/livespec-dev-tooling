"""Tests for the shared CI job-container image reader."""

from __future__ import annotations

from livespec_dev_tooling.ci_container_images import container_images

__all__: list[str] = []


def test_reads_a_block_image_after_comments_and_blanks() -> None:
    """A comment never ends the direct-child `container:` block."""
    source = (
        "jobs:\n"
        "  check:\n"
        "    container:\n"
        "      # The image is intentionally explained here.\n"
        "\n"
        "      image: ghcr.io/example/check:latest\n"
    )

    assert container_images(source=source) == [(6, "ghcr.io/example/check:latest")]


def test_reads_distinct_scalar_and_block_images_without_nested_image_keys() -> None:
    """Only direct `container:` image values are job-container images."""
    source = (
        "jobs:\n"
        "  scalar:\n"
        "    container: ghcr.io/example/scalar:latest # pin\n"
        "  block:\n"
        "    container:\n"
        "      image: 'ghcr.io/example/block:latest'\n"
        "      credentials:\n"
        "        image: must-not-count\n"
    )

    assert container_images(source=source) == [
        (3, "ghcr.io/example/scalar:latest"),
        (6, "ghcr.io/example/block:latest"),
    ]
