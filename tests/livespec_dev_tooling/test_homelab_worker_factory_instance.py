"""A homelab worker takes factory dispatches through a Fabro instance of its own.

Plan homelab-k8s-worker-nodes, livespec-dev-tooling-a3brdf; SPECIFICATION
non-functional-requirements.md "Homelab worker nodes". The plugin reads tolerations
from its config file alone, so the placement that keeps these sandboxes on the worker,
and every other sandbox off it, is exactly what the rendered file says. That is why
this renders the role's own template, under the role's own task overrides, through the
same pinned ansible-core the `ansible-apply` recipe runs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

if sys.version_info >= (3, 11):  # pragma: no cover — 3.11 path unused on the 3.10 floor.
    import tomllib as _toml
else:
    import tomli as _toml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "sandbox_driver_kubernetes"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_TEMPLATE = _ROLE / "templates" / "plugin-config.toml.j2"
_HOST_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_JUSTFILE = _REPO_ROOT / "justfile"
_WORKER = "homelab-worker-arm64"
_UNIT = f"fabro-server-{_WORKER}"
_TAINT = "homelab-worker.livespec.dev/class"
_RENDERED = re.compile(r'^\s*"msg": (?P<msg>"RENDERED=.*")$', re.MULTILINE)
_PLAYBOOK_TIMEOUT_SECONDS = 600


def _host_vars() -> dict[str, Any]:
    return yaml.safe_load(_HOST_VARS.read_text(encoding="utf-8"))


def _instance() -> dict[str, Any]:
    found = [i for i in _host_vars()["fabro_server_instances"] if i["unit_name"] == _UNIT]
    assert len(found) == 1, f"{_HOST_VARS} must declare exactly one {_UNIT}"
    return found[0]


def _render_task_vars() -> dict[str, Any]:
    tasks = yaml.safe_load(_TASKS.read_text(encoding="utf-8"))
    found = [
        t
        for t in tasks
        if t["name"] == "Render each homelab worker instance's plugin configuration"
    ]
    assert len(found) == 1
    return found[0]["vars"]


def _render(*, tmp_path: Path, overrides: dict[str, Any]) -> dict[str, Any]:
    pin = re.search(
        r"ansible-core==[0-9][0-9A-Za-z.]*",
        _JUSTFILE.read_text(encoding="utf-8").split("ansible-apply *args:", 1)[1],
    )
    assert pin is not None
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("localhost ansible_connection=local\n", encoding="utf-8")
    playbook = tmp_path / "render.yml"
    play = {
        "hosts": "localhost",
        "connection": "local",
        "gather_facts": False,
        "vars_files": [str(_DEFAULTS)],
        "vars": {
            "fabro_server_host_user": "worker",
            "fabro_server_host_group": "worker",
            "fabro_server_host_home": "/home/worker",
        },
        "tasks": [
            {
                "ansible.builtin.debug": {
                    "msg": "RENDERED={{ lookup('ansible.builtin.template', '"
                    + str(_TEMPLATE)
                    + "') | to_json }}"
                },
                # The role's defaults derive paths from role_path, which a bare play lacks.
                "vars": {"role_path": str(_ROLE), **overrides},
            }
        ],
    }
    playbook.write_text(yaml.safe_dump([play]), encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {"ANSIBLE_NOCOWS": "1", "ANSIBLE_STDOUT_CALLBACK": "default"}
    done = subprocess.run(
        ["uvx", "--from", pin[0], "ansible-playbook", "-i", str(inventory), str(playbook)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    output = done.stdout + done.stderr
    assert done.returncode == 0, output
    found = _RENDERED.search(output)
    assert found is not None, output
    rendered = json.loads(json.loads(found["msg"]).removeprefix("RENDERED="))
    return _toml.loads(rendered)


def test_a_worker_instances_plugin_config_selects_the_class_and_architecture_and_no_host(
    *, tmp_path: Path
) -> None:
    entry = _host_vars()["sandbox_driver_kubernetes_worker_config_homes"][0]
    assert entry["name"] == _WORKER
    config = _render(tmp_path=tmp_path, overrides={"item": entry, **_render_task_vars()})
    assert config["node_selector"] == {
        "homelab-worker.livespec.dev/class": "worker",
        "kubernetes.io/arch": "arm64",
    }
    assert "homelab-worker.livespec.dev/admission" not in [
        t.get("key") for t in config["tolerations"]
    ]
    assert {
        "key": _TAINT,
        "operator": "Equal",
        "value": "worker",
        "effect": "NoSchedule",
    } in config["tolerations"]
    assert config["factory"] == _WORKER


def test_a_worker_instance_never_selects_another_architecture(*, tmp_path: Path) -> None:
    entry = {**_host_vars()["sandbox_driver_kubernetes_worker_config_homes"][0], "arch": "amd64"}
    config = _render(tmp_path=tmp_path, overrides={"item": entry, **_render_task_vars()})
    assert config["node_selector"]["kubernetes.io/arch"] == "amd64"
    assert "homelab-worker.livespec.dev/host" not in config["node_selector"]


def test_no_other_homes_plugin_config_tolerates_the_worker_taint(*, tmp_path: Path) -> None:
    config = _render(tmp_path=tmp_path, overrides={})
    assert _TAINT not in [t.get("key") for t in config["tolerations"]]
    assert "homelab-worker.livespec.dev/host" not in config["node_selector"]


def test_the_workers_instance_keeps_the_toolchain_id_on_a_native_image() -> None:
    instance = _instance()
    assert [e["id"] for e in instance["environments"]] == ["factory-python"]
    assert instance["environments"][0]["provider"] == "kubernetes"
    provider = instance["sandbox_providers"]["kubernetes"]
    assert re.search(r":python-agent-[^:]*-arm64$", provider["process_spec"]["image"])


def test_the_workers_instance_serves_one_run_under_its_own_home() -> None:
    instance = _instance()
    assert instance["max_concurrent_runs"] == 1
    homes = _host_vars()["sandbox_driver_kubernetes_worker_config_homes"]
    assert instance["home_env"] == homes[0]["home"]
    state_dir = instance["sandbox_providers"]["kubernetes"]["env"][
        "SANDBOX_DRIVER_KUBERNETES_STATE_DIR"
    ]
    assert state_dir.startswith(instance["home_env"] + "/"), (
        "a shared record store would make this instance report and act on another "
        "instance's sandboxes"
    )
