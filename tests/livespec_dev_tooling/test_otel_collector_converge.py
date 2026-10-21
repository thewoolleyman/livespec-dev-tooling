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

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
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


def _task_blocks(*, body: str) -> list[str]:
    """One string per `- name:`-introduced task or handler in a role file."""
    return [f"- name: {chunk}" for chunk in body.split("\n- name: ")[1:]]


def _role_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(_ROLE.rglob("*")) if path.is_file()
    )


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
    assert "Reload systemd for the collector unit" in install, install
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
