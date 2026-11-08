"""Each sandbox's first pod is spread across the factory nodes by hostname.

WHAT WAS MEASURED. On 2026-11-02, after hp-xubuntu was re-sized as a factory
worker, 3 of 3 new factory sandbox pods scheduled on one node while two other
factory nodes stood idle. The plugin config this role renders carried only
`node_selector` and `tolerations`, so nothing asked the scheduler to spread
sandboxes (livespec-orchestrator-beads-fabro `bd-ib-kogktm`, plan epic
`bd-ib-nmuyjc`). Plugin v0.5.0 adds `topology_spread`.

WHY THIS RENDERS THROUGH REAL ANSIBLE. A text assertion on the template passes
any string that looks right, and the substitution renderer the role's other
tests use evaluates no filter (see `test_sandbox_image_warm_process_spec_urls`).
So this test renders the role's own `plugin-config.toml.j2` against its own
`defaults/main.yml` through the SAME pinned ansible-core the `ansible-apply`
recipe runs, and parses the result as the TOML the plugin reads.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):  # pragma: no cover — 3.11 path unused on the 3.10 floor.
    import tomllib as _toml
else:
    import tomli as _toml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "sandbox_driver_kubernetes"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TEMPLATE = _ROLE / "templates" / "plugin-config.toml.j2"
_WORKLOAD_ARCH_CONF = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "workload-arch.conf"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_RENDERED = re.compile(r'^\s*"msg": (?P<msg>"RENDERED=.*")$', re.MULTILINE)
_PLAYBOOK_TIMEOUT_SECONDS = 600


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, f"{_JUSTFILE} must carry an `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _render_plugin_config(
    *, tmp_path: Path, arch_conf: Path = _WORKLOAD_ARCH_CONF
) -> dict[str, object]:
    """Render the plugin config through the pinned ansible-core and parse it."""
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("localhost ansible_connection=local\n", encoding="utf-8")
    playbook = tmp_path / "render.yml"
    playbook.write_text(
        "- hosts: localhost\n"
        "  connection: local\n"
        "  gather_facts: false\n"
        f"  vars_files: ['{_DEFAULTS}']\n"
        "  vars:\n"
        "    fabro_server_host_user: worker\n"
        "    fabro_server_host_group: worker\n"
        "    fabro_server_host_home: /home/worker\n"
        "  tasks:\n"
        "    - ansible.builtin.debug:\n"
        f"        msg: \"RENDERED={{{{ lookup('ansible.builtin.template', '{_TEMPLATE}') | to_json }}}}\"\n",
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_LOCALHOST_WARNING": "False",
            "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
            "ANSIBLE_STDOUT_CALLBACK": "default",
        }
    )
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(inventory),
            "-e",
            f"sandbox_driver_kubernetes_workload_arch_conf={arch_conf}",
            str(playbook),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, f"the render play must succeed;\noutput={output}"
    found = _RENDERED.search(output)
    assert found is not None, f"the render play must print the rendered config;\noutput={output}"
    rendered = json.loads(json.loads(found["msg"]).removeprefix("RENDERED="))
    assert isinstance(rendered, str)
    return _toml.loads(rendered)


def test_the_rendered_plugin_config_spreads_first_pods_by_hostname(*, tmp_path: Path) -> None:
    config = _render_plugin_config(tmp_path=tmp_path)
    assert config.get("topology_spread") == [
        {
            "topology_key": "kubernetes.io/hostname",
            "max_skew": 1,
            "when_unsatisfiable": "ScheduleAnyway",
        }
    ], (
        "the plugin config must ask for a hostname spread with max skew 1 as a scoring "
        "preference (ScheduleAnyway), so sandboxes spread without ever being left Pending; "
        f"rendered={config.get('topology_spread')!r}"
    )
    tolerations = config.get("tolerations")
    assert isinstance(tolerations, list) and len(tolerations) == 3, (
        "rendering the spread must leave the three tolerations in place; "
        f"rendered={tolerations!r}"
    )
    node_selector = config.get("node_selector")
    assert isinstance(node_selector, dict) and node_selector.get("ci-runner.io/factory") == "true"


def test_the_rendered_node_selector_carries_the_factory_class_architecture(
    *, tmp_path: Path
) -> None:
    """The provider selects the architecture its image publishes, read from the list.

    The list is mocked, so the assertion is the rule, never a committed value
    (livespec-dev-tooling-ko26ez.6).
    """
    conf = tmp_path / "workload-arch.conf"
    conf.write_text(
        "# mocked\nfactory python-agent riscv64 other arches lack it\n", encoding="utf-8"
    )
    config = _render_plugin_config(tmp_path=tmp_path, arch_conf=conf)
    assert config.get("node_selector") == {
        "ci-runner.io/factory": "true",
        "kubernetes.io/arch": "riscv64",
        "ci-runner.io/factory-admit": "true",
    }
