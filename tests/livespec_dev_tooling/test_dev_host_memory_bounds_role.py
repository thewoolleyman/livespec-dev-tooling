"""dev_host_memory_bounds renders through Ansible's own templater as systemd needs it.

The first converge of this role (2026-11-13 20:04Z) wrote its scratchpad mount
unit as `tmp-claude\\\\x2d1000.mount`, with two literal backslashes. A plain
jinja2 render of the role had produced the single backslash systemd needs, but
Ansible's templater re-escaped the Jinja-spelled `'\\\\x2d'`. So systemd refused
the unit, and the apply stopped before it enabled the bind, installed the
slices and published the per-loop bound.

Two guards follow from that:

- No Jinja expression in the role's tasks or defaults spells a backslash. That
  is the class that bit, and the unit name now comes from `systemd-escape`.
- The role's derived values and its unit templates are rendered by the
  `ansible-apply` recipe's pinned ansible-core (its `Templar`, run through
  `uvx` as `just ansible-apply` runs it), never by plain jinja2. The test
  asserts the exact bytes systemd will read.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "dev_host_memory_bounds"
_JUSTFILE = _REPO_ROOT / "justfile"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
_ENGINE_TIMEOUT_SECONDS = 600
# What `systemd-escape --path --suffix=mount /tmp/claude-1000` prints: ONE
# backslash before x2d.
_MOUNT_UNIT = "tmp-claude\\x2d1000.mount"

# The engine runs as its own interpreter: ansible-core 2.21 needs Python 3.12,
# above this repository's floor, so it is invoked, never imported (ansible/README.md).
_ENGINE = r"""
import json
import sys

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template


def trusted(value):
    # Ansible trusts every string it reads from a role or vars file as a template.
    if isinstance(value, str):
        return trust_as_template(value)
    if isinstance(value, list):
        return [trusted(item) for item in value]
    if isinstance(value, dict):
        return {key: trusted(item) for key, item in value.items()}
    return value


case = json.load(sys.stdin)
templar = Templar(loader=DataLoader(), variables=trusted(case["variables"]))
json.dump({name: str(templar.template(trusted(text))) for name, text in case["templates"].items()}, sys.stdout)
"""


def _yaml(*, relative: str) -> Any:
    return yaml.safe_load((_ROLE / relative).read_text(encoding="utf-8"))


def _strings(*, node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [text for item in node for text in _strings(node=item)]
    if isinstance(node, dict):
        return [text for item in node.values() for text in _strings(node=item)]
    return []


def ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, "the justfile must carry the `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _render(*, variables: dict[str, Any], templates: dict[str, str]) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    completed = subprocess.run(
        ["uvx", "--from", ansible_core_pin(), "python", "-I", "-c", _ENGINE],
        input=json.dumps({"variables": variables, "templates": templates}),
        env=env,
        capture_output=True,
        text=True,
        timeout=_ENGINE_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    rendered = json.loads(completed.stdout)
    assert isinstance(rendered, dict)
    return rendered


@pytest.fixture(scope="module")
def rendered() -> dict[str, str]:
    """The role's derived values and unit templates, rendered once by ansible-core."""
    variables: dict[str, Any] = {
        **_yaml(relative="defaults/main.yml"),
        "ansible_managed": "Ansible managed",
        "dev_host_memory_bounds_rt_scratch_ram_dir": "/tmp/claude-1000",
        "dev_host_memory_bounds_rt_scratch_disk_dir": "/var/tmp/claude-1000",
        "dev_host_memory_bounds_rt_mount_unit": _MOUNT_UNIT,
        "item": {
            "name": "factory-dispatch.slice",
            "description": "Every per-run factory dispatcher loop and its launcher",
            "memory_high": "{{ dev_host_memory_bounds_dispatch_memory_high }}",
            "memory_max": "{{ dev_host_memory_bounds_dispatch_memory_max }}",
        },
    }
    templates = {
        "dispatch_max": "{{ dev_host_memory_bounds_dispatch_memory_max }}",
        "dispatch_high": "{{ dev_host_memory_bounds_dispatch_memory_high }}",
        "unit_path": "{{ dev_host_memory_bounds_system_unit_dir }}/{{ dev_host_memory_bounds_rt_mount_unit }}",
        "stray_glob": "{{ dev_host_memory_bounds_scratch_ram_root[1:] }}-claude*.mount",
        "mount_unit": (_ROLE / "templates" / "scratch-bind.mount.j2").read_text(encoding="utf-8"),
        "slice_unit": (_ROLE / "templates" / "memory-slice.slice.j2").read_text(encoding="utf-8"),
        "tmp_dropin": (_ROLE / "templates" / "tmp-mount-bounds.conf.j2").read_text(
            encoding="utf-8"
        ),
        "reconcile_dropin": (_ROLE / "templates" / "reconcile-memory-bounds.conf.j2").read_text(
            encoding="utf-8"
        ),
    }
    return _render(variables=variables, templates=templates)


@pytest.mark.parametrize("relative", ["tasks/main.yml", "defaults/main.yml"])
def test_no_jinja_expression_in_the_role_spells_a_backslash(relative: str) -> None:
    expressions = [
        expression
        for text in _strings(node=_yaml(relative=relative))
        for expression in _JINJA_EXPRESSION.findall(text)
    ]
    assert expressions, f"{relative} must carry Jinja expressions (the scan is not vacuous)"
    spelled = [expression for expression in expressions if "\\" in expression]
    assert (
        spelled == []
    ), f"{relative} spells a backslash inside Jinja, which Ansible's templater re-escapes: {spelled}"


def test_the_mount_unit_lands_under_the_name_systemd_escape_gives(rendered: dict[str, str]) -> None:
    assert rendered["unit_path"] == f"/etc/systemd/system/{_MOUNT_UNIT}"
    assert "\\\\" not in rendered["unit_path"]


def test_the_mount_unit_binds_the_disk_directory_onto_the_ram_path(
    rendered: dict[str, str],
) -> None:
    lines = rendered["mount_unit"].splitlines()
    assert "What=/var/tmp/claude-1000" in lines
    assert "Where=/tmp/claude-1000" in lines
    assert "Options=bind" in lines
    assert "WantedBy=local-fs.target" in lines


def test_the_dispatch_slice_is_derived_from_the_fleet_cap(rendered: dict[str, str]) -> None:
    # MemoryMax = loop_cap x steady + concurrent_peaks x (peak - steady), and
    # MemoryHigh is 90% of it, both read from the committed defaults.
    defaults = _yaml(relative="defaults/main.yml")
    expected_max = defaults["dev_host_memory_bounds_dispatch_loop_cap"] * defaults[
        "dev_host_memory_bounds_dispatch_loop_steady_mib"
    ] + defaults["dev_host_memory_bounds_dispatch_concurrent_peaks"] * (
        defaults["dev_host_memory_bounds_dispatch_loop_peak_mib"]
        - defaults["dev_host_memory_bounds_dispatch_loop_steady_mib"]
    )
    expected_high = int(expected_max * 0.9)
    assert rendered["dispatch_max"] == f"{expected_max}M"
    assert rendered["dispatch_high"] == f"{expected_high}M"
    lines = rendered["slice_unit"].splitlines()
    assert f"MemoryMax={expected_max}M" in lines
    assert f"MemoryHigh={expected_high}M" in lines
    assert "MemorySwapMax=0" in lines


def test_the_tmp_cap_dropin_carries_the_size_and_inode_cap(rendered: dict[str, str]) -> None:
    assert (
        "Options=mode=1777,strictatime,nosuid,nodev,size=8G,nr_inodes=2m"
        in rendered["tmp_dropin"].splitlines()
    )


def test_the_stray_unit_glob_matches_the_scratchpad_mount_units(rendered: dict[str, str]) -> None:
    assert rendered["stray_glob"] == "tmp-claude*.mount"


def test_the_reconcile_dropin_sets_only_what_the_orchestrator_unit_does_not(
    rendered: dict[str, str],
) -> None:
    # One source per value: the orchestrator's committed reconcile-runs.service
    # owns the pass's memory and CPU numbers, so this drop-in must not set them.
    defaults = _yaml(relative="defaults/main.yml")
    directives = [
        line.split("=", 1)[0]
        for line in rendered["reconcile_dropin"].splitlines()
        if "=" in line and not line.startswith("#")
    ]
    assert directives == ["MemorySwapMax", "OOMScoreAdjust"]
    lines = rendered["reconcile_dropin"].splitlines()
    assert f"MemorySwapMax={defaults['dev_host_memory_bounds_memory_swap_max']}" in lines
    assert (
        f"OOMScoreAdjust={defaults['dev_host_memory_bounds_reconcile_oom_score_adjust']}" in lines
    )
