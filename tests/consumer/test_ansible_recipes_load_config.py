"""Consumer-tier proof that provisioning recipes load their committed configuration."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_CONFIG = _REPO_ROOT / "ansible" / "ansible.cfg"
_ANSIBLE_CONFIG_FILE = re.compile(r"^\s*config file = (?P<path>.+)$", re.MULTILINE)
_ANSIBLE_PIPELINING = re.compile(r"^ANSIBLE_PIPELINING\([^)]*\) = True$", re.MULTILINE)


def _ansible_core_pin() -> str:
    recipe = _JUSTFILE.read_text(encoding="utf-8")
    pin = re.search(r"ansible-core==[0-9][0-9A-Za-z.]*", recipe)
    assert pin is not None, "the ansible recipes must pin ansible-core exactly"
    return pin[0]


def _environment() -> dict[str, str]:
    """Keep the test's configuration answer owned by the recipe under test."""
    return {
        key: value
        for key, value in os.environ.items()
        if key != "ANSIBLE_CONFIG" and not key.startswith(("COVERAGE_", "COV_CORE_"))
    }


@pytest.mark.parametrize("recipe", ["ansible-drift", "ansible-apply"])
def test_ansible_recipes_load_the_provisioning_configuration(*, recipe: str) -> None:
    """Each root-run recipe resolves the config whose pipelining Ansible reports."""
    environment = _environment()
    recipe_run = subprocess.run(
        ["just", recipe, "--version"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=120,
    )
    output = recipe_run.stdout + recipe_run.stderr
    assert recipe_run.returncode == 0, output
    config_file = _ANSIBLE_CONFIG_FILE.search(output)
    assert config_file is not None, output
    assert Path(config_file["path"]).resolve() == _CONFIG.resolve()

    config_run = subprocess.run(
        ["uvx", "--from", _ansible_core_pin(), "ansible-config", "dump", "--only-changed"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        env=environment | {"ANSIBLE_CONFIG": config_file["path"]},
        text=True,
        timeout=120,
    )
    config_output = config_run.stdout + config_run.stderr
    assert config_run.returncode == 0, config_output
    assert _ANSIBLE_PIPELINING.search(config_output) is not None, config_output
