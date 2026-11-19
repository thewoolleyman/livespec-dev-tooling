"""A Fabro catalog image must track its owning workflow's image-layer pin."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "fabro_image_pin_lockstep.py"
_WORKFLOW_PIN_MIRROR = Path("livespec_dev_tooling") / "data" / "fabro_workflow_image_pins.json"
_CATALOG_IMAGE = "ghcr.io/livespec-ai/livespec-fabro-sandbox:python-agent-v1.206.0-arm64"
_WORKFLOW_IMAGE = "python-agent-v1.207.0"


def _load_check_module() -> ModuleType:
    """Load the checked module directly so its cwd-bound main can use a fixture tree."""
    spec = importlib.util.spec_from_file_location("fabro_catalog_image_pin_lockstep", _CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_existing_lockstep_inputs(*, root: Path) -> None:
    """Copy the pre-existing check inputs so this fixture isolates catalog drift."""
    for relative_path in (
        Path("docker") / "fabro-sandbox",
        Path(".mise.toml"),
        Path(".python-version"),
        Path("ci-runner") / "k3s" / "phase2" / "factory" / "factory-reach-image.env",
        Path(".github") / "workflows" / "ci.yml",
    ):
        source = _REPO_ROOT / relative_path
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)


def test_rejects_an_unheld_arm64_catalog_image_behind_its_workflow_layer_pin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An architecture suffix is a variant, not an exemption from layer lockstep."""
    _write_existing_lockstep_inputs(root=tmp_path)
    mirror = tmp_path / _WORKFLOW_PIN_MIRROR
    mirror.parent.mkdir(parents=True)
    _ = mirror.write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "python-agent": _WORKFLOW_IMAGE,
                }
            }
        ),
        encoding="utf-8",
    )
    host_vars = tmp_path / "ansible" / "inventory" / "host_vars" / "factory.yml"
    host_vars.parent.mkdir(parents=True)
    _ = host_vars.write_text(
        "fabro_server_instances:\n"
        "  - unit_name: fabro-server\n"
        "    workflow_pin_member: livespec-orchestrator-beads-fabro\n"
        "    environments:\n"
        "      - id: factory-python\n"
        f"        image: {_CATALOG_IMAGE}\n",
        encoding="utf-8",
    )
    module = _load_check_module()
    monkeypatch.chdir(tmp_path)

    returncode = module.main()
    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert returncode != 0, "an unheld catalog image behind its workflow pin must fail"
    for expected in (
        "factory.yml",
        "fabro-server",
        "factory-python",
        _CATALOG_IMAGE,
        _WORKFLOW_IMAGE,
    ):
        assert expected in output, f"the drift diagnostic must name {expected!r}: {output!r}"
