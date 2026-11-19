"""A declared catalog hold must name its work item even when the image is in lockstep."""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling import fabro_catalog_image_pins

__all__: list[str] = []


_IMAGE = "ghcr.io/livespec-ai/livespec-fabro-sandbox:python-agent-v1.207.0"
_PIN_MIRROR = {"member": {"python-agent": "python-agent-v1.207.0"}}


def _issues(*, root: Path, hold_lines: str) -> list[str]:
    host_vars = root / "ansible" / "inventory" / "host_vars"
    host_vars.mkdir(parents=True)
    _ = (host_vars / "factory.yml").write_text(
        "fabro_server_instances:\n"
        "  - unit_name: fabro-server\n"
        "    workflow_pin_member: member\n"
        "    environments:\n"
        "      - id: factory-python\n"
        f"        image: {_IMAGE}\n"
        f"{hold_lines}",
        encoding="utf-8",
    )
    return fabro_catalog_image_pins.catalog_pin_issues(
        cwd=root, pin_mirror=_PIN_MIRROR, architectures={"arm64"}
    )


@pytest.mark.parametrize(
    "hold_lines",
    ['        image_pin_hold: ""\n', "        image_pin_hold:\n", "        image_pin_hold: nope\n"],
)
def test_rejects_an_invalid_declared_hold_on_an_in_lockstep_catalog_image(
    *, tmp_path: Path, hold_lines: str
) -> None:
    """Equal versions do not excuse a declared hold that names no work-item id."""
    issues = _issues(root=tmp_path, hold_lines=hold_lines)

    assert len(issues) == 1, issues
    assert "factory-python" in issues[0]
    assert "image_pin_hold must name a work-item id" in issues[0]


def test_accepts_an_in_lockstep_catalog_image_with_a_valid_declared_hold(*, tmp_path: Path) -> None:
    """A stale but well-formed hold on an equal image is not itself a finding."""
    issues = _issues(
        root=tmp_path, hold_lines="        image_pin_hold: livespec-dev-tooling-pedcoq\n"
    )

    assert issues == []
