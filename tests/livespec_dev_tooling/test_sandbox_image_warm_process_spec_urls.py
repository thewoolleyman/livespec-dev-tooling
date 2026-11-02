"""The containerd warm's process_spec URLs name each sandbox host's host_vars file.

WHAT BROKE, MEASURED. PR #3082 (bd-ib-kogktm part 1) derived
`sandbox_image_warm_process_spec_urls` with
`map('regex_replace', '^(.*)$', base ~ '/\\1.yml')`. Under the pinned
ansible-core 2.21.4, the replacement's back-reference rendered as a literal
backslash-one. So the rendered unit read `.../host_vars/\\1.yml` once per sandbox
host. The 2026-11-02 drift read (gate 20261102T033125Z-567141, `ansible/ci-pool.yml
--tags sandbox_image_warm_containerd`) showed exactly that on all three factory
nodes. A warm with those URLs fetches nothing that exists, so it fails loudly and
pulls nothing, and the tag the factory pods need is never pre-pulled.

WHY THIS RENDERS THROUGH REAL ANSIBLE. The role's other tests use a substitution
renderer that replaces `{{ name }}` and evaluates no filter. That renderer passed
the broken expression through all 81 commit-gate targets. A shape assertion on
the expression text would be just as blind: it passes any string that looks
right. So this test renders the role's own `defaults/main.yml` through the SAME
pinned ansible-core the `ansible-apply` recipe runs (resolved through `uvx`,
exactly as `test_restart_k3s_agent_playbook` runs its playbook), against a
throwaway inventory, and asserts on the rendered list itself.
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
_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "sandbox_image_warm" / "defaults" / "main.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
# The debug callback prints the message as a JSON string: `"msg": "RENDERED=[...]"`.
_RENDERED = re.compile(r'^\s*"msg": (?P<msg>"RENDERED=.*")$', re.MULTILINE)
_BASE = "https://raw.githubusercontent.com/thewoolleyman/livespec-dev-tooling/master/ansible/inventory/host_vars"
# Generous: a cold `uvx` resolves and caches ansible-core before the play runs.
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


def _render(*, tmp_path: Path, store: str) -> list[str]:
    """Render the role default through the pinned ansible-core; return the list."""
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[sandbox_hosts]\nhp-xubuntu\ngmktec-xubuntu\n", encoding="utf-8")
    playbook = tmp_path / "render.yml"
    playbook.write_text(
        "- hosts: localhost\n"
        "  connection: local\n"
        "  gather_facts: false\n"
        f"  vars_files: ['{_DEFAULTS}']\n"
        "  tasks:\n"
        "    - ansible.builtin.debug:\n"
        '        msg: "RENDERED={{ sandbox_image_warm_process_spec_urls | to_json }}"\n',
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
            # An extra var, because vars_files outrank play vars and the role
            # default would otherwise decide the store.
            "-e",
            f"sandbox_image_warm_store={store}",
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
    assert found is not None, f"the render play must print the rendered list;\noutput={output}"
    return json.loads(json.loads(found["msg"]).removeprefix("RENDERED="))


def test_a_containerd_warm_reads_each_sandbox_hosts_own_host_vars_file(*, tmp_path: Path) -> None:
    urls = _render(tmp_path=tmp_path, store="containerd")
    assert urls == [f"{_BASE}/gmktec-xubuntu.yml", f"{_BASE}/hp-xubuntu.yml"], (
        "a containerd warm must read one host_vars URL per sandbox_hosts member, each "
        f"naming that host, sorted; rendered={urls!r}"
    )


def test_a_docker_warm_reads_no_process_spec_urls(*, tmp_path: Path) -> None:
    assert (
        _render(tmp_path=tmp_path, store="docker") == []
    ), "the docker store keeps reading the release pin, so it renders no process_spec URLs"
