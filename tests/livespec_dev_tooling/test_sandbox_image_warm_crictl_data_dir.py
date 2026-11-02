"""The containerd warm reaches k3s's CRI on a node whose k3s data directory moved.

WHAT BROKE, MEASURED. After the 2026-11-02 apply of the containerd warm
(`ansible/ci-pool.yml --tags sandbox_image_warm_containerd`, gate
20261102T044846Z-1566607), the warm succeeded on gmktec-xubuntu and
poweredge-xubuntu. On hp-xubuntu it failed every pull with `load config file:
stat /var/lib/rancher/k3s/data/<hash>/bin/crictl.yaml: no such file or
directory`. hp's profile sets NODE_DATA_DIR=/srv/sandbox-storage/k3s, so its
crictl.yaml lives under /srv/sandbox-storage/k3s/agent/etc/. A bare `k3s crictl`
looks only under the default data directory. Measured on hp the same minute:
`k3s --data-dir /srv/sandbox-storage/k3s crictl images` lists the node's images,
and the bare form fails exactly as the unit did.

WHAT THIS HOLDS THE FIX TO. The role derives its CRI client from a
`sandbox_image_warm_k3s_data_dir` input, so a node with a moved data directory
gets `k3s --data-dir <dir> crictl` and a node on the default gets the bare form.
ci-pool.yml supplies that input from the same profile key NODE_DATA_DIR that the
k3s_config role already reads. The role default is rendered through the pinned
ansible-core, in a subprocess, as the sibling
`test_sandbox_image_warm_process_spec_urls` does. The substitution renderers
evaluate no filter or conditional (livespec-dev-tooling-ugi26g).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_CI_POOL = _REPO_ROOT / "ansible" / "ci-pool.yml"
_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "sandbox_image_warm" / "defaults" / "main.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
# The debug callback prints the message as a JSON string: `"msg": "RENDERED=..."`.
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


def _render_crictl(*, tmp_path: Path, extra_vars: tuple[str, ...]) -> str:
    """Render the role's `sandbox_image_warm_crictl` default through the pinned ansible-core."""
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[sandbox_hosts]\n", encoding="utf-8")
    playbook = tmp_path / "render.yml"
    playbook.write_text(
        "- hosts: localhost\n"
        "  connection: local\n"
        "  gather_facts: false\n"
        f"  vars_files: ['{_DEFAULTS}']\n"
        "  tasks:\n"
        "    - ansible.builtin.debug:\n"
        '        msg: "RENDERED={{ sandbox_image_warm_crictl | string | trim }}"\n',
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
    argv = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", "-i", str(inventory)]
    for extra in extra_vars:
        argv += ["-e", extra]
    argv.append(str(playbook))
    completed = subprocess.run(
        argv,
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
    assert found is not None, f"the render play must print the rendered value;\noutput={output}"
    return json.loads(found["msg"]).removeprefix("RENDERED=")


def test_a_node_with_a_moved_k3s_data_dir_reaches_crictl_through_that_dir(
    *, tmp_path: Path
) -> None:
    crictl = _render_crictl(
        tmp_path=tmp_path,
        extra_vars=("sandbox_image_warm_k3s_data_dir=/srv/sandbox-storage/k3s",),
    )
    assert crictl == "/usr/local/bin/k3s --data-dir /srv/sandbox-storage/k3s crictl", (
        "a node whose profile moves k3s's data directory must reach the CRI through "
        f"that directory's crictl.yaml; rendered={crictl!r}"
    )


def test_a_node_on_the_default_k3s_data_dir_uses_the_bare_k3s_crictl(*, tmp_path: Path) -> None:
    crictl = _render_crictl(tmp_path=tmp_path, extra_vars=())
    assert (
        crictl == "/usr/local/bin/k3s crictl"
    ), f"a node on k3s's default data directory keeps the bare form; rendered={crictl!r}"


def test_ci_pool_supplies_the_data_dir_from_the_node_profile() -> None:
    text = _CI_POOL.read_text(encoding="utf-8")
    assert (
        "regex_findall('^NODE_DATA_DIR=(.*)$', multiline=True)" in text
    ), "ci-pool.yml must read each node's NODE_DATA_DIR from its committed profile"
    assert (
        'sandbox_image_warm_k3s_data_dir: "{{ ci_pool_node_data_dir }}"' in text
    ), "and pass it to the containerd warm, so hp's moved data directory reaches its crictl"
