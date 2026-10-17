"""The hp OTel receiver is installed by a committed role, from a pinned release.

WHY IT EXISTS (2026-10-17, livespec-dev-tooling-jvem). Every Fabro instance on hp
exports its spans to `http://172.17.0.1:4318`. The receiver listening there was a
hand-placed, untracked `otel_receiver_daemon.py` running out of the factory's
shared livespec-orchestrator-beads-fabro checkout, left at release 0.140.0. That
build's attribute allowlist predates the Petri-era run_turn names, so it stripped
`run_turn.command`, `run_turn.command.digest`, `run_turn.env.keys` and
`run_turn.status` from every hp-candidate span (0 of 134 in seven days carried a
command). No committed automation deployed it, so nothing could move it forward.

WHAT THESE TESTS HOLD IT TO.
- The `sandbox_hosts` play converges an `otel_receiver` role, and hp's host_vars
  turn it on.
- The receiver runs a daemon entry point tracked in this repository, from the
  role's OWN orchestrator clone pinned to a release tag at or after v0.210.0 (the
  first build whose allowlist admits those names), never from
  `fabro_server_host_checkout`, which a live factory runs from.
- The role never writes the ingest-key environment file; it only names it.
- A converge restarts the running receiver only when the operator passes
  `otel_receiver_restart_allowed=true`, because a restart drops every instance's
  spans while it is down.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAY = _REPO_ROOT / "ansible" / "fabro-hosts.yml"
_HP_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars" / "hp-xubuntu.yml"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "otel_receiver"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_UNIT = _ROLE / "templates" / "otel-receiver.service.j2"
_DAEMON = _ROLE / "files" / "otel_receiver_daemon.py"
_FLOOR = (0, 210, 0)


def _scalar(*, text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}: (?P<value>.+)$", text, re.MULTILINE)
    assert match is not None, f"{name} is not declared:\n{text}"
    return match["value"].strip().strip('"')


def _tasks() -> list[str]:
    body = _TASKS.read_text(encoding="utf-8")
    return [f"- name: {chunk}" for chunk in body.split("\n- name: ")[1:]]


def test_the_sandbox_hosts_play_converges_the_receiver_and_hp_enables_it() -> None:
    play = _PLAY.read_text(encoding="utf-8")
    sandbox = play.split("hosts: sandbox_hosts", 1)[1].split("\n- name: ", 1)[0]
    assert re.search(r"^    - role: otel_receiver$", sandbox, re.MULTILINE), sandbox
    assert re.search(r"^      tags: \[otel_receiver\]$", sandbox, re.MULTILINE), sandbox
    hp_vars = _HP_VARS.read_text(encoding="utf-8")
    assert _scalar(text=hp_vars, name="otel_receiver_enabled") == "true"
    assert (
        _scalar(text=_DEFAULTS.read_text(encoding="utf-8"), name="otel_receiver_enabled") == "false"
    )


def test_the_receiver_runs_a_pinned_release_at_or_after_the_floor() -> None:
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    version = _scalar(text=defaults, name="otel_receiver_orchestrator_version")
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
    assert match is not None, f"the pin must be a release tag, got {version!r}"
    assert tuple(int(part) for part in match.groups()) >= _FLOOR, version
    assert _scalar(text=defaults, name="otel_receiver_orchestrator_floor") == "0.210.0"
    assert _scalar(text=defaults, name="otel_receiver_orchestrator_remote").endswith(
        "thewoolleyman/livespec-orchestrator-beads-fabro.git"
    )
    clone = next(task for task in _tasks() if "ansible.builtin.git:" in task)
    assert 'dest: "{{ otel_receiver_orchestrator_dir }}"' in clone, clone
    assert 'version: "{{ otel_receiver_orchestrator_version }}"' in clone, clone


def test_the_clone_is_the_roles_own_never_the_factory_checkout() -> None:
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    role_text = "\n".join(path.read_text(encoding="utf-8") for path in (_DEFAULTS, _TASKS, _UNIT))
    assert "fabro_server_host_checkout" not in role_text.replace(
        "never fabro_server_host_checkout", ""
    )
    home = _scalar(text=_HP_VARS.read_text(encoding="utf-8"), name="otel_receiver_home")
    install_root = _scalar(text=defaults, name="otel_receiver_install_root").replace(
        "{{ otel_receiver_home }}", home
    )
    orchestrator_dir = _scalar(text=defaults, name="otel_receiver_orchestrator_dir").replace(
        "{{ otel_receiver_install_root }}", install_root
    )
    factory_checkout = _scalar(
        text=_HP_VARS.read_text(encoding="utf-8"), name="fabro_server_host_checkout"
    )
    assert Path(orchestrator_dir) != Path(factory_checkout)
    assert Path(factory_checkout) not in Path(orchestrator_dir).parents


def test_the_unit_runs_the_tracked_entry_point_from_that_clone() -> None:
    unit = _UNIT.read_text(encoding="utf-8")
    assert re.search(
        r"^ExecStart=\{\{ otel_receiver_python \}\} \{\{ otel_receiver_entry_point \}\}$",
        unit,
        re.MULTILINE,
    ), unit
    assert (
        "Environment=LIVESPEC_OTEL_RECEIVER_ORCHESTRATOR_ROOT={{ otel_receiver_orchestrator_dir }}"
        in unit
    ), unit
    assert _DAEMON.is_file()
    assert "LIVESPEC_OTEL_RECEIVER_ORCHESTRATOR_ROOT" in _DAEMON.read_text(encoding="utf-8")
    install = next(task for task in _tasks() if "src: otel_receiver_daemon.py" in task)
    assert 'dest: "{{ otel_receiver_entry_point }}"' in install, install
    assert "WorkingDirectory={{ otel_receiver_state_dir }}" in unit, unit


def test_the_role_never_writes_the_environment_file() -> None:
    unit = _UNIT.read_text(encoding="utf-8")
    assert "EnvironmentFile={{ otel_receiver_env_file }}" in unit, unit
    for task in _tasks():
        if "otel_receiver_env_file" not in task:
            continue
        writes = re.search(
            r"^  ansible\.builtin\.(copy|template|file|lineinfile|blockinfile):", task, re.MULTILINE
        )
        assert writes is None, f"a task that names the env file writes something:\n{task}"
        targets = re.findall(r"^    (?:path|dest): (.+)$", task, re.MULTILINE)
        assert all("otel_receiver_env_file" not in target for target in targets) or (
            "ansible.builtin.stat:" in task
        ), task


def test_a_restart_needs_the_operators_lever() -> None:
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert _scalar(text=defaults, name="otel_receiver_restart_allowed") == "false"
    restarts = [
        task for task in _tasks() if re.search(r"^    state: restarted$", task, re.MULTILINE)
    ]
    assert restarts, "the role must carry the operator-allowed restart"
    for task in restarts:
        assert "- otel_receiver_restart_allowed | bool" in task, task
    deferral = next(
        task
        for task in _tasks()
        if "otel_receiver_restart_pending_marker" in task and "content:" in task
    )
    assert "- not (otel_receiver_restart_allowed | bool)" in deferral, deferral
