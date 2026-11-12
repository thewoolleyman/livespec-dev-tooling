"""The dev host's `otel-collector.service` is converged, never hand-restarted.

WHY IT EXISTS (2026-10-21, livespec-dev-tooling-x36is7). A change merged to
`thewoolleyman/otel-collector`'s `config.yaml` reached this host's running
collector only by a hand `sudo systemctl restart otel-collector` against a
development checkout — the path that repository's own notes document, and the
one the fleet's GitOps deployment discipline forbids. No committed converge
installed the collector's configuration or its unit, so every configuration
change to it was a by-hand host change that nothing recorded and no drift
report could see.

WHAT THESE TESTS HOLD IT TO, one per assertion of the work-item's Definition
of Done.
- The `dev_hosts` play converges an `otel_collector` role that installs the
  merged collector configuration itself, so one committed converge carries a
  merged change to the running service.
- That converge is idempotent: the configuration and the unit are written by
  content-comparing modules and the restart lives in a handler, so a run over
  an already-matching host reports no drift and leaves the service alone.
- The unit itself is installed by the same converge, from a template in this
  repository, and names only managed paths — so the running service reads no
  development checkout.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_PLAY = _REPO_ROOT / "ansible" / "dev-host.yml"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "otel_collector"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_HANDLERS = _ROLE / "handlers" / "main.yml"
_UNIT_TEMPLATE = _ROLE / "templates" / "otel-collector.service.j2"
_ANSIBLE_README = _REPO_ROOT / "ansible" / "README.md"

# The collector repository owns `config.yaml`; this role only carries the ref
# it reads it at. Asserted so the role can never grow a second source of truth
# for the configuration, which is the defect this converge removes.
_COLLECTOR_RAW_SOURCE = "https://raw.githubusercontent.com/thewoolleyman/otel-collector/"

# The maintainer's development checkout root. A role value under it would put
# the running service back on a tree a `git pull` can change underneath it.
_DEVELOPMENT_CHECKOUT_ROOT = "/data/projects"

# Where a systemd unit has to land for systemd to read it. Held here as the
# documented default the role declares, and compared against the role's
# `defaults/main.yml` text -- nothing in this module reaches the directory.
_SYSTEMD_UNIT_DIRECTORY = "/etc/systemd/system/"

_DRIFT_COMMAND = "just ansible-drift ansible/dev-host.yml --tags otel_collector"
_APPLY_COMMAND = "just ansible-apply ansible/dev-host.yml --tags otel_collector"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")


def _task_blocks(*, body: str) -> list[str]:
    """One string per `- name:`-introduced task or handler in a role file."""
    return [f"- name: {chunk}" for chunk in body.split("\n- name: ")[1:]]


def _role_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(_ROLE.rglob("*")) if path.is_file()
    )


def _task(*, name: str) -> str:
    """Return the one task named ``name`` from the collector role."""
    matches = [
        block
        for block in _task_blocks(body=_TASKS.read_text(encoding="utf-8"))
        if block.startswith(f"- name: {name}\n")
    ]
    assert len(matches) == 1, f"expected one task named {name!r}; got {len(matches)}"
    return matches[0]


def _render_pods_endpoint(*, flannel_subnet: str, override: str = "") -> str:
    """Render the role's exact expression through the pinned Ansible engine."""
    task = _task(name="Name the OTLP pods endpoint for this node")
    expression = task.split("otel_collector_otlp_pods_endpoint_effective: >-\n", 1)[1].split(
        "\n  when:", 1
    )[0]
    pin = _ANSIBLE_CORE_PIN.search(_JUSTFILE.read_text(encoding="utf-8"))
    assert pin is not None, "just ansible-apply must pin ansible-core exactly"

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        rendered = root / "endpoint"
        play = root / "render.yml"
        play.write_text(
            "---\n"
            "- hosts: localhost\n"
            "  gather_facts: false\n"
            "  vars:\n"
            f"    otel_collector_otlp_pods_endpoint: {json.dumps(override)}\n"
            "    otel_collector_flannel_subnet_read:\n"
            f"      stdout: {json.dumps(f'FLANNEL_SUBNET={flannel_subnet}')}\n"
            "  tasks:\n"
            "    - name: Render the committed endpoint expression\n"
            "      ansible.builtin.set_fact:\n"
            "        rendered_endpoint: >-\n"
            f"{textwrap.indent(textwrap.dedent(expression).strip(), '          ')}\n"
            "    - name: Preserve the rendered endpoint for pytest\n"
            "      ansible.builtin.copy:\n"
            f"        content: '{{{{ rendered_endpoint }}}}'\n"
            f"        dest: {json.dumps(str(rendered))}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "uvx",
                "--from",
                pin[0],
                "ansible-playbook",
                "-i",
                "localhost,",
                "-c",
                "local",
                str(play),
            ],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            env=os.environ | {"ANSIBLE_NOCOWS": "1"},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return rendered.read_text(encoding="utf-8")


def test_one_committed_converge_carries_a_merged_config_to_the_running_service() -> None:
    """The play wires the role, and the role installs the merged config itself."""
    assert _TASKS.is_file(), "the otel_collector role has no tasks/main.yml"

    dev_hosts = _PLAY.read_text(encoding="utf-8").split("hosts: dev_hosts", 1)[1]
    assert re.search(r"^    - role: otel_collector$", dev_hosts, re.MULTILINE), dev_hosts
    assert re.search(r"^      tags: \[otel_collector\]$", dev_hosts, re.MULTILINE), dev_hosts

    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert _COLLECTOR_RAW_SOURCE in defaults, defaults
    assert "otel_collector_config_ref:" in defaults, defaults

    tasks = _TASKS.read_text(encoding="utf-8")
    install = next(
        block
        for block in _task_blocks(body=tasks)
        if 'dest: "{{ otel_collector_config_path }}"' in block
    )
    assert "ansible.builtin.copy:" in install, install
    assert "otel_collector_merged_config" in install, install

    # The converge restarts the service; nothing in the role tells an operator
    # to do it by hand, and no role value reaches the development checkout.
    role_text = _role_text()
    assert "state: restarted" in role_text, role_text
    assert "systemctl restart" not in role_text, role_text
    assert _DEVELOPMENT_CHECKOUT_ROOT not in role_text, role_text

    readme = _ANSIBLE_README.read_text(encoding="utf-8")
    assert _DRIFT_COMMAND in readme, readme
    assert _APPLY_COMMAND in readme, readme


def test_a_converge_over_an_already_matching_host_restarts_nothing() -> None:
    """The restart is a handler, so an unchanged run notifies it and it never fires."""
    assert _HANDLERS.is_file(), "the otel_collector role has no handlers/main.yml"

    handlers = _HANDLERS.read_text(encoding="utf-8")
    restart = next(block for block in _task_blocks(body=handlers) if "state: restarted" in block)
    assert 'name: "{{ otel_collector_unit_name }}"' in restart, restart

    tasks = _TASKS.read_text(encoding="utf-8")
    assert "state: restarted" not in tasks, (
        "a restart outside a handler fires on every converge, including one that "
        f"changed nothing:\n{tasks}"
    )

    # The one task that holds the service up starts a stopped collector and
    # leaves a running one exactly as it is.
    service = next(
        block
        for block in _task_blocks(body=tasks)
        if "ansible.builtin.systemd_service:" in block and "state:" in block
    )
    assert "state: started" in service, service

    # Each managed write compares content, reports no change when the host
    # already matches, and therefore notifies the restart on change only.
    config_install = next(
        block
        for block in _task_blocks(body=tasks)
        if 'dest: "{{ otel_collector_config_path }}"' in block
    )
    assert "notify:" in config_install, config_install
    for forbidden in ("ansible.builtin.get_url:", "ansible.builtin.shell:", "ansible.builtin.raw:"):
        assert forbidden not in tasks, f"{forbidden} cannot report a converged host as converged"

    # A read the role performs on the target is a read: it must never be able
    # to report a change of its own on an already-matching host.
    for block in _task_blocks(body=tasks):
        if "ansible.builtin.command:" not in block:
            continue
        assert "changed_when: false" in block, block


def test_the_same_converge_installs_the_services_systemd_unit() -> None:
    """The unit is a template in this repository, installed by the same apply."""
    assert _UNIT_TEMPLATE.is_file(), "the otel_collector role ships no unit template"

    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert "otel_collector_unit_name: otel-collector.service" in defaults, defaults
    assert _SYSTEMD_UNIT_DIRECTORY in defaults, defaults
    assert "otel_collector_environment_path:" in defaults, defaults

    tasks = _TASKS.read_text(encoding="utf-8")
    install = next(
        block for block in _task_blocks(body=tasks) if "src: otel-collector.service.j2" in block
    )
    assert "ansible.builtin.template:" in install, install
    assert 'dest: "{{ otel_collector_unit_path }}"' in install, install
    assert "Reload systemd for the managed collector units" in install, install
    assert "Restart the collector onto its managed configuration" in install, install

    handlers = _HANDLERS.read_text(encoding="utf-8")
    assert "daemon_reload: true" in handlers, handlers

    # The unit names managed variables only, so the running service reads
    # nothing a development checkout can change underneath it. The companion
    # assertion -- that no role value sits under that checkout at all -- is in
    # the first test above, over the whole role tree including this template.
    unit = _UNIT_TEMPLATE.read_text(encoding="utf-8")
    assert (
        "ExecStart={{ otel_collector_binary }} --config={{ otel_collector_config_path }}" in unit
    ), unit
    assert "EnvironmentFile={{ otel_collector_environment_path }}" in unit, unit

    # The ingest keys that unit names are a precondition the converge asserts.
    # It never writes, reads back or prints one, so no apply of this role needs
    # a credential on the control node.
    environment_blocks = [
        block for block in _task_blocks(body=tasks) if "otel_collector_environment_path" in block
    ]
    assert environment_blocks, tasks
    for block in environment_blocks:
        for writer in (
            "ansible.builtin.copy:",
            "ansible.builtin.template:",
            "ansible.builtin.slurp:",
        ):
            assert writer not in block, block


def test_k3s_agents_render_their_own_otlp_pods_gateway_from_flannel() -> None:
    """The same role variables give each agent its own flannel gateway bind."""
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert "otel_collector_flannel_subnet_path: /run/flannel/subnet.env" in defaults, defaults

    read = _task(name="Read this node's flannel subnet for the OTLP pods endpoint")
    assert "ansible.builtin.command:" in read, read
    assert '"{{ otel_collector_flannel_subnet_path }}"' in read, read
    assert "'OTLP_PODS_ENDPOINT' in otel_collector_required_environment_keys" in read, read
    assert "otel_collector_otlp_pods_endpoint | length == 0" in read, read
    assert "changed_when: false" in read, read
    assert "failed_when: false" in read, read

    refusal = _task(name="Refuse an OTLP pods configuration without this node's flannel subnet")
    assert "ansible.builtin.assert:" in refusal, refusal
    assert "otel_collector_flannel_subnet_path" in refusal, refusal
    assert "FLANNEL_SUBNET" in refusal, refusal

    assert _render_pods_endpoint(flannel_subnet="10.42.5.1/24") == "10.42.5.1:4319"
    assert _render_pods_endpoint(flannel_subnet="10.42.1.1/24") == "10.42.1.1:4319"


def test_otlp_pods_endpoint_override_wins_over_the_flannel_gateway() -> None:
    """A host-specific override is deliberate and is what the role writes."""
    write = _task(name="Write the OTLP pods endpoint the merged configuration reads")
    assert "ansible.builtin.lineinfile:" in write, write
    assert 'regexp: "^OTLP_PODS_ENDPOINT="' in write, write
    assert "otel_collector_otlp_pods_endpoint_effective" in write, write
    # A rewritten endpoint must restart a running collector onto it.
    assert "notify: Restart the collector onto its managed configuration" in write, write

    assert (
        _render_pods_endpoint(flannel_subnet="10.42.5.1/24", override="192.0.2.8:4319")
        == "192.0.2.8:4319"
    )


def test_otlp_pods_endpoint_refuses_missing_flannel_before_writing_an_endpoint() -> None:
    """A configuration that reads the key fails closed when no override can supply it."""
    refusal = _task(name="Refuse an OTLP pods configuration without this node's flannel subnet")
    write = _task(name="Write the OTLP pods endpoint the merged configuration reads")
    tasks = _task_blocks(body=_TASKS.read_text(encoding="utf-8"))

    assert "otel_collector_flannel_subnet_read.rc == 0" in refusal, refusal
    assert "FLANNEL_SUBNET" in refusal, refusal
    assert tasks.index(refusal) < tasks.index(
        write
    ), "the missing flannel assertion must run before the endpoint writer"
