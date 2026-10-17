"""`ansible/restart-k3s-agent.yml` — the one committed way to restart a pool agent's k3s agent.

WHY THE PLAYBOOK EXISTS (livespec-dev-tooling-mbj3kz, found live 2026-10-14).
`ansible/roles/k3s_config` renders an agent's whole START configuration — its
node taints, its data-directory ordering and its own `kubelet-arg+` reservations
— and deliberately restarts nothing, because a restart kills every CI job
running on the pool. So the rendered file is an opinion until the next k3s start.
On hp-xubuntu that gap was measured: the role wrote
`/etc/rancher/k3s/config.yaml.d/20-kubelet-args.yaml` (system-reserved
`cpu=14500m,memory=25088Mi`) at 19:38 PDT 2026-10-13 while `k3s-agent` had been
running since 19:19, so the live node kept reporting allocatable `cpu=16`,
`memory=32176236Ki` instead of the few hundred millicores and ~3Gi the
coexistence budget in `ansible/roles/docker_sandbox_slice/HOST_VARS.md` derives.
The only committed restart path was `ansible/reboot-ci-server.yml`, which reboots
the SERVER; a hand `systemctl restart k3s-agent` over ssh is exactly what the
Driver's `fleet_host_guard.py` refuses, and hp-xubuntu is the Fabro factory host,
which must not be rebooted for this. An agent whose start configuration had
changed therefore had NO sanctioned way to reach its next start.

WHAT THESE TESTS HOLD IT TO. A playbook that restarts a pool node's kubelet can
take a running workload with it, so both Definition-of-Done assertions are
REFUSALS, and each is asserted by RUNNING the committed playbook rather than by
reading it — a reading would assert a model of ansible's `when`, `until` and
check-mode semantics, and it is exactly those semantics that decide whether a
node's agent restarts:

1. A run whose confirmation does not name this host's own `ci_pool` agent entry
   reaches NOTHING on it, on an apply and under `--check` alike; and a
   confirmation that names a host which is not one of the pool's agents — the
   control-plane server above all — is a LOUD refusal rather than a quiet skip.
2. A confirmed run against a node that is running any pod no DaemonSet owns
   refuses BEFORE it restarts anything, naming the pods that held it.

AND THE EXEMPTION IS FALSIFIED, NOT ASSUMED. "Refuses unless every pod on the
node is DaemonSet-owned" is only half a claim: a play that counted a
DaemonSet-owned pod as busy would satisfy assertion 2 and never restart anything
at all. So the idle fixture keeps a DaemonSet-owned pod and a finished Job pod on
the node THROUGHOUT, and the restart is asserted to happen anyway.

HOW THEY RUN IT. By the same `ansible-core` pin `just ansible-apply` executes
(read out of the justfile rather than restated, so the two cannot drift), against
a three-host local inventory — a server, a plain agent, and an agent that is also
a Fabro factory host — and a scratch PATH carrying stand-in `kubectl`, `systemctl`
and `sudo`. No cluster is reached and no host is mutated; the stand-ins log every
invocation they receive into ONE shared log, which is how the tests below prove
both WHAT the run asked and WHEN it asked it relative to the restart.

THE FACTORY HOST IS A LEGITIMATE TARGET HERE, and that is the one place this
playbook's fence differs from `ansible/node-loss-drill.yml`'s. That drill refuses
every member of `sandbox_hosts` because a Fabro factory host runs the very server
the drill is being observed by. This playbook exists FOR that host: hp-xubuntu is
the node whose kubelet reservations never took effect. What protects it is the
pod gate, not a group refusal — a factory sandbox pod is a bare pod no DaemonSet
owns, so a run attempted while one is executing is refused by assertion 2.

THE STAND-IN NODE IS NotReady UNTIL THE RESTART IS ISSUED, which is STRONGER
than the live node and deliberately so. A real kubelet restart completes in a few
seconds, well inside the node controller's monitor grace period, so a live node's
Ready condition may never flip at all. A fixture that reported Ready throughout
would make "it waits for the node to report Ready again" unfalsifiable — the wait
would pass whether it ran before the restart, after it, or not at all. Coupling
the condition to the restart marker the stand-in `systemctl` writes makes the
wait's placement observable. The allocatable figures move with it for the
opposite reason: that transition — capacity-equals-allocatable before the
restart, the profile's reservations after it — is exactly what was measured on
hp-xubuntu, and it is what the run's own report must be read from.

Work-item: livespec-dev-tooling-mbj3kz. Plan: livespec `factory-worker-nodes-gitops`
(epic livespec-sqvj7p).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_PLAYBOOK = _REPO_ROOT / "ansible" / "restart-k3s-agent.yml"

# The `ansible-apply` recipe's own tool pin, so these tests exercise the
# interpreter the sanctioned invocation exercises. Restating the version here
# would let the recipe move to an ansible whose `when` / `until` / check-mode
# semantics nothing had tested.
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

# The unit the whole playbook exists to restart.
_AGENT_UNIT = "k3s-agent"

# The three hosts this suite restarts nothing on. Named for the playbook rather
# than for real pool nodes so no output of this suite can be mistaken for a
# record of hp-xubuntu, gmktec-xubuntu or poweredge-xubuntu having been touched.
# `_FACTORY_AGENT` is in BOTH `ci_pool` and `sandbox_hosts`, which is
# hp-xubuntu's real shape and the host this playbook is FOR.
_SERVER = "restart-k3s-agent-server"
_AGENT = "restart-k3s-agent-agent"
_FACTORY_AGENT = "restart-k3s-agent-factory-agent"

# The pods on the target node, as the play's own read renders them:
# `<namespace>/<name>=<phase>=owners:<owner kinds>`.
#
# TWO OF THE FOUR ARE ON THE NODE IN EVERY MODE, and they are the exemptions:
# the DaemonSet-owned pod (every node runs these and no restart can ever wait
# for them) and the Job pod that has already finished (work this node is no
# longer doing). The other two appear only in the busy mode and are the two
# shapes that must hold a restart: a BARE pod no controller owns, which is what
# a Fabro factory sandbox is, and a running Job pod, which is what a CI job and
# an offloaded gate are.
_DAEMONSET_POD = "kube-system/svclb-traefik-7s4mp-k2xvn"
_COMPLETED_GATE_POD = "gates/livespec-dev-tooling-gate-7f4kd-pzn2w"
_SANDBOX_POD = "factory/livespec-dev-tooling-sandbox-9bqdn"
_RUNNER_POD = "arc-runners/livespec-dev-tooling-k3s-vwxyz-runner-2fkpt"

_IDLE_POD_READ = (
    f"{_DAEMONSET_POD}=Running=owners:DaemonSet\n{_COMPLETED_GATE_POD}=Succeeded=owners:Job\n"
)
_BUSY_POD_READ = (
    f"{_IDLE_POD_READ}{_SANDBOX_POD}=Running=owners:\n{_RUNNER_POD}=Running=owners:Job\n"
)

# The node's capacity, and the two allocatable readings either side of the
# restart. These are hp-xubuntu's measured figures: the stale state the
# work-item found (allocatable equal to capacity, because the rendered
# reservations had never been read) and the state the restart produces.
_CAPACITY_CPU = "16"
_CAPACITY_MEMORY = "32176236Ki"
_RESERVED_CPU = "500m"
_RESERVED_MEMORY = "3176236Ki"

# The playbook's OWN task names, which are the vocabulary a run is read in: an
# operator scanning the output matches these strings, so a test that asserts a
# status against them is asserting what the operator sees.
_UNCONFIRMED_NOTE_TASK = "Report a run that carries no agent-restart confirmation for this host"
_NOT_AN_AGENT_REFUSAL_TASK = (
    "Refuse an agent restart on a host that is not one of the pool's agents"
)
_POD_READ_TASK = "Read every pod the target node is running"
_BUSY_REFUSAL_TASK = "Refuse an agent restart on a node running a pod no DaemonSet owns"
_CHECK_NOTE_TASK = "Note that a check run withholds the agent restart itself"
_RESTART_TASK = "Restart the node's k3s agent"
_READY_WAIT_TASK = "Wait until the API reports the node Ready again"
_REPORT_TASK = "Report the node's Ready condition and its kubelet reservations"

# Generous: a cold `uvx` resolves and caches ansible-core before the first play
# runs. Bounded all the same, so a hung play fails this test rather than the
# suite's whole budget.
_PLAYBOOK_TIMEOUT_SECONDS = 600

_TASK_HEADER = re.compile(r"^TASK \[(?P<name>.+?)\] \**$")
_HOST_STATUS = re.compile(r"^(?P<status>ok|changed|skipping|failed|fatal|unreachable): \[")

# A stand-in `sudo` that drops its option flags and its `-u <user>` and execs
# the rest. The play escalates at the play level because the admin kubeconfig it
# reads is root-owned on a real node and restarting a unit is root's; this suite
# runs as whoever invoked pytest, with no sudo guaranteed on the image. So
# become is SATISFIED rather than switched off, which keeps the executed task
# shape the same as the operator's.
_SUDO_STAND_IN = """#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    -u) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
exec "$@"
"""

# The stand-in `kubectl`. It logs every invocation FIRST, into the log the
# stand-in `systemctl` shares, so a test can prove both WHAT the run asked the
# cluster and WHEN it asked it relative to the unit it restarted. It exits
# non-zero on anything it was not written to answer rather than returning a
# plausible empty string — an unexpected invocation must break a test, not
# quietly read as an empty pod list and let a restart through.
#
# THE NODE READ IS DERIVED FROM THE RESTART MARKER the stand-in `systemctl`
# writes, never canned: see this module's header for why a fixture that reported
# the node Ready throughout would make the Ready wait unfalsifiable.
# `RESTART_K3S_AGENT_READY_AFTER_RESTART=never` breaks that coupling on purpose,
# which is the only way to reach the one path an operator most needs bounded: an
# agent that was restarted and whose node never came back.
_KUBECTL_STAND_IN = f"""#!/bin/sh
printf 'kubectl %s\\n' "$*" >> "${{RESTART_K3S_AGENT_COMMAND_LOG}}"
agent_state="$(cat "${{RESTART_K3S_AGENT_AGENT_STATE}}" 2>/dev/null || printf 'unrestarted')"
case "$*" in
  *'get pods'*)
    cat "${{RESTART_K3S_AGENT_PODS}}"
    exit 0 ;;
  *'get node'*jsonpath*)
    if [ "${{agent_state}}" = restarted ] \
       && [ "${{RESTART_K3S_AGENT_READY_AFTER_RESTART}}" != never ]; then
      printf 'ready=True capacity-cpu={_CAPACITY_CPU} capacity-memory={_CAPACITY_MEMORY}'
      printf ' allocatable-cpu={_RESERVED_CPU} allocatable-memory={_RESERVED_MEMORY}'
    else
      printf 'ready=Unknown capacity-cpu={_CAPACITY_CPU} capacity-memory={_CAPACITY_MEMORY}'
      printf ' allocatable-cpu={_CAPACITY_CPU} allocatable-memory={_CAPACITY_MEMORY}'
    fi
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""

# The stand-in `systemctl`, answering the shape `ansible.builtin.systemd_service`
# reads: a `show` of the unit's load and active state, then the `restart`. It is
# the WRITER of the restart marker the stand-in `kubectl` reads, so the restart
# is observable both in the shared log and in what the API then says about the
# node.
#
# IT REFUSES ANY OTHER VERB, `stop` and `start` INCLUDED. This playbook's whole
# contract is that it changes nothing else on the host: a future edit that
# stopped a timer, disabled a unit or reloaded the manager would break every
# test here rather than passing quietly.
_SYSTEMCTL_STAND_IN = """#!/bin/sh
printf 'systemctl %s\\n' "$*" >> "${RESTART_K3S_AGENT_COMMAND_LOG}"
case "$1" in
  show)
    printf 'LoadState=loaded\\nUnitFileState=enabled\\n'
    printf 'ActiveState=active\\nSubState=running\\n'
    exit 0 ;;
  is-active)
    exit 0 ;;
  is-enabled)
    printf 'enabled\\n'
    exit 0 ;;
  restart)
    printf 'restarted' > "${RESTART_K3S_AGENT_AGENT_STATE}"
    exit 0 ;;
esac
printf 'stand-in systemctl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    """One test's isolated world: its stand-in binaries, its shared log, its pod read."""

    root: Path
    bin_dir: Path
    command_log: Path
    agent_state: Path
    pods: Path


def _ansible_core_pin() -> str:
    """The `ansible-core==<version>` pin the `ansible-apply` recipe resolves."""
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, (
        f"{_JUSTFILE} must carry an `ansible-apply *args:` recipe — it is the "
        f"one sanctioned way to run this playbook, and a test that cannot find "
        f"it is testing some other ansible"
    )
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, (
        "the `ansible-apply` recipe must pin ansible-core exactly, so the "
        "refusals these tests assert are the refusals the operator gets"
    )
    return pin[0]


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    """A scratch root with the three stand-ins on a private bin dir and an idle node."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("sudo", _SUDO_STAND_IN),
        ("kubectl", _KUBECTL_STAND_IN),
        ("systemctl", _SYSTEMCTL_STAND_IN),
    ):
        stand_in = bin_dir / name
        stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    pods = tmp_path / "pods"
    pods.write_text(_IDLE_POD_READ, encoding="utf-8")
    return _Scratch(
        root=tmp_path,
        bin_dir=bin_dir,
        command_log=tmp_path / "command.log",
        agent_state=tmp_path / "agent-state",
        pods=pods,
    )


def _write_inventory(*, scratch: _Scratch) -> Path:
    """A three-host `ci_pool` inventory: a server, an agent, and an agent in `sandbox_hosts`.

    The group memberships and the `cluster_role` values are the inventory facts
    the playbook selects on, so they ride as INVENTORY vars — the precedence an
    operator's own inventory uses. Everything the fixture needs to BOUND (the
    Ready-wait interval, its retry count, the confirmation) rides as
    `--extra-vars` instead, because the playbook declares those as play vars and
    play vars beat inventory.
    """
    inventory = scratch.root / "inventory.yml"
    inventory.write_text(
        "all:\n"
        "  children:\n"
        "    ci_pool:\n"
        "      hosts:\n"
        f"        {_SERVER}:\n"
        "          ansible_connection: local\n"
        "          cluster_role: server\n"
        f"        {_AGENT}:\n"
        "          ansible_connection: local\n"
        "          cluster_role: agent\n"
        f"        {_FACTORY_AGENT}:\n"
        "          ansible_connection: local\n"
        "          cluster_role: agent\n"
        "    sandbox_hosts:\n"
        "      hosts:\n"
        f"        {_FACTORY_AGENT}:\n"
        "          ansible_connection: local\n",
        encoding="utf-8",
    )
    return inventory


def _playbook_environment(*, scratch: _Scratch, ready_after_restart: bool) -> dict[str, str]:
    """The child's environment, built rather than inherited wholesale.

    `COVERAGE_PROCESS_START` and `COV_CORE_*` are scrubbed so the ansible
    interpreter does not self-instrument and race the suite's own coverage data.
    The ansible settings the run relies on are passed as `ANSIBLE_*` rather than
    through a config file, because `ansible/ansible.cfg` is not on ansible's
    search path from the repository root either — which is where
    `just ansible-apply` runs from.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "RESTART_K3S_AGENT_COMMAND_LOG": str(scratch.command_log),
            "RESTART_K3S_AGENT_AGENT_STATE": str(scratch.agent_state),
            "RESTART_K3S_AGENT_PODS": str(scratch.pods),
            # Always SET, never merely absent when unwanted: the stand-in reads
            # it with no `set -u`, so an unset variable would make the knob's
            # off state untested rather than tested.
            "RESTART_K3S_AGENT_READY_AFTER_RESTART": "after" if ready_after_restart else "never",
            # Skipped tasks are SHOWN, as `ansible/ansible.cfg` shows them: a
            # task that vanishes from the output cannot be read as "this was not
            # evaluated", and the unconfirmed cases assert on exactly those lines.
            "ANSIBLE_DISPLAY_SKIPPED_HOSTS": "True",
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
        }
    )
    return env


def _run_playbook(
    *,
    scratch: _Scratch,
    confirm: str | None,
    check_mode: bool = False,
    ready_after_restart: bool = True,
) -> tuple[int, str]:
    """Run the committed playbook; return its exit code and its callback output."""
    assert _PLAYBOOK.is_file(), (
        f"{_PLAYBOOK} must exist — it is the only committed way to restart a "
        f"pool agent's k3s agent, and without it an agent whose start "
        f"configuration changed can only reach its next start by a hand change "
        f"to a fleet host or by rebooting the Fabro factory host"
    )
    inventory = _write_inventory(scratch=scratch)
    argv = [
        "uvx",
        "--from",
        _ansible_core_pin(),
        "ansible-playbook",
        "-i",
        str(inventory),
        # The Ready wait, bounded to nothing: no gap between reads, and ONE
        # retry (ansible's `retries` is ADDITIONAL attempts, so this is two
        # attempts). Two rather than one on purpose — it exercises the retry
        # loop, which is the half of the bounded wait that decides whether a
        # node that never returns ends in a failure or in a pass.
        "-e",
        "restart_k3s_agent_status_interval=0",
        "-e",
        "restart_k3s_agent_status_retries=1",
        *(["-e", f"restart_k3s_agent_confirm={confirm}"] if confirm is not None else []),
        *(["--check"] if check_mode else []),
        str(_PLAYBOOK),
    ]
    completed = subprocess.run(
        argv,
        cwd=scratch.root,
        env=_playbook_environment(scratch=scratch, ready_after_restart=ready_after_restart),
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _task_statuses(*, output: str, host: str) -> dict[str, str]:
    """Each task's first reported status for one host, keyed on the task name."""
    statuses: dict[str, str] = {}
    task = ""
    for line in output.splitlines():
        header = _TASK_HEADER.match(line)
        if header is not None:
            task = header["name"]
            continue
        status = _HOST_STATUS.match(line)
        if status is not None and f"[{host}" in line and task not in statuses:
            statuses[task] = status["status"]
    assert statuses, (
        f"no per-task status for {host} was parsed out of the run; this reader "
        f"cannot assert anything about a run it cannot read:\n{output}"
    )
    return statuses


def _status_of(*, statuses: dict[str, str], task: str) -> str:
    """One task's reported status, refusing a task the run never carried.

    Asked through a helper rather than by subscript so the absence of the task is
    an ASSERTION about the run — "nothing in this play reports that" — rather
    than a `KeyError` whose message names only the key.
    """
    assert (
        task in statuses
    ), f"the run carried no task named `{task}`; it carried: {sorted(statuses)}"
    return statuses[task]


def _recap_changed(*, output: str, host: str) -> int:
    """One host's `changed=` count in the PLAY RECAP — the line an operator reads."""
    recap = re.search(
        rf"^{re.escape(host)}\s+: .*?\bchanged=(?P<changed>\d+)\b", output, re.MULTILINE
    )
    assert recap is not None, f"the run carried no PLAY RECAP for {host}:\n{output}"
    return int(recap["changed"])


def _commands(*, scratch: _Scratch) -> list[str]:
    """Every argv the stand-ins were called with, across both tools, in order."""
    log = scratch.command_log
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _first_index(*, commands: list[str], needle: str) -> int:
    """The index of the first logged command containing `needle`, or -1.

    Returned as an INDEX rather than a boolean because the ordering claims below
    are claims about position in one shared log: "the restart came after the pod
    read" is `restart index > last pod-read index`, and nothing weaker
    establishes it.
    """
    return next((index for index, command in enumerate(commands) if needle in command), -1)


def _last_index(*, commands: list[str], needle: str) -> int:
    """The index of the LAST logged command containing `needle`, or -1."""
    return next(
        (index for index in range(len(commands) - 1, -1, -1) if needle in commands[index]),
        -1,
    )


@pytest.mark.parametrize("check_mode", [False, True], ids=["apply", "check"])
@pytest.mark.parametrize("confirm", [None, "some-other-host"], ids=["absent", "wrong-value"])
def test_a_run_whose_confirmation_names_no_host_of_this_inventory_changes_nothing(
    *, scratch: _Scratch, confirm: str | None, check_mode: bool
) -> None:
    """The consent half of the first Definition-of-Done assertion, run rather than modelled.

    This is what keeps a playbook that restarts a node's kubelet safe to leave in
    the tree: a bare apply, a drift sweep, or a typo'd confirmation reaches
    NOTHING on any host. Asserted on four axes, because any one of them passing
    alone would still leave a way to restart an agent by accident — every host
    reports zero changes, the pod read and the restart both report `skipping`
    rather than running, neither the cluster nor the service manager is asked
    anything at all, and that holds for the confirmation being absent and for it
    naming a host outside this inventory. `--check` is asserted beside the apply
    because a drift sweep runs in check mode, and check mode is NOT what makes
    this safe: the confirmation gate is.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=confirm, check_mode=check_mode)

    assert exit_code == 0, (
        f"an unconfirmed run must END, not fail — a refusal that errored would "
        f"redden every sweep that includes this playbook:\n{output}"
    )
    for host in (_SERVER, _AGENT, _FACTORY_AGENT):
        statuses = _task_statuses(output=output, host=host)
        assert _status_of(statuses=statuses, task=_UNCONFIRMED_NOTE_TASK) == "ok"
        assert _status_of(statuses=statuses, task=_NOT_AN_AGENT_REFUSAL_TASK) == "skipping", (
            f"{host} must not be REFUSED by a run that does not name it — it "
            f"must simply not be acted on; a refusal here would fail every run "
            f"that names some other host:\n{output}"
        )
        assert _status_of(statuses=statuses, task=_POD_READ_TASK) == "skipping"
        assert _status_of(statuses=statuses, task=_RESTART_TASK) == "skipping"
        assert _status_of(statuses=statuses, task=_READY_WAIT_TASK) == "skipping"
        assert (
            _recap_changed(output=output, host=host) == 0
        ), f"an unconfirmed run must report zero changes for {host}:\n{output}"
    assert _commands(scratch=scratch) == [], (
        f"an unconfirmed run must reach the cluster and the service manager with "
        f"NOTHING; it issued: {_commands(scratch=scratch)}"
    )


def test_a_confirmation_naming_one_agent_changes_nothing_on_the_other_hosts(
    *, scratch: _Scratch
) -> None:
    """The same fence, against the confirmation most likely to be a typo.

    The confirmation names a host that IS in this inventory — the plain agent —
    so the two hosts it does not name must still reach nothing, and must not be
    refused either: a refusal on an unnamed host would fail every run aimed at
    some other node. The run's own commands are asserted never to mention them,
    which is the half a per-host status cannot establish — a read field-selected
    to the wrong node would still report `ok` on the right one.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT)

    assert exit_code == 0, f"a confirmed run against an idle node must not fail:\n{output}"
    for host in (_SERVER, _FACTORY_AGENT):
        statuses = _task_statuses(output=output, host=host)
        assert _status_of(statuses=statuses, task=_UNCONFIRMED_NOTE_TASK) == "ok"
        assert _status_of(statuses=statuses, task=_NOT_AN_AGENT_REFUSAL_TASK) == "skipping"
        assert _status_of(statuses=statuses, task=_POD_READ_TASK) == "skipping"
        assert _status_of(statuses=statuses, task=_RESTART_TASK) == "skipping"
        assert (
            _recap_changed(output=output, host=host) == 0
        ), f"a run naming {_AGENT} must report zero changes for {host}:\n{output}"
    for command in _commands(scratch=scratch):
        assert _SERVER not in command and _FACTORY_AGENT not in command, (
            f"a run naming {_AGENT} asked about another host: `{command}` (full "
            f"log: {_commands(scratch=scratch)})"
        )


@pytest.mark.parametrize("check_mode", [False, True], ids=["apply", "check"])
def test_a_confirmed_run_refuses_a_host_that_is_not_one_of_the_pools_agents(
    *, scratch: _Scratch, check_mode: bool
) -> None:
    """The refusal half of the first Definition-of-Done assertion.

    Consent is necessary and NOT sufficient. The pool's control-plane node must
    never be restarted through this playbook however explicitly an operator asks:
    its unit is `k3s`, not `k3s-agent`, and taking the control plane down is a
    cluster outage rather than an agent's start configuration taking effect —
    `ansible/reboot-ci-server.yml` owns that host. The refusal must be LOUD, a
    confirmed run that silently did nothing reads exactly like a restart that
    silently failed, and it must land before anything is read, so the run is
    asserted to carry no cluster and no service-manager call at all.

    The server is identified by its inventory `cluster_role`, never by a host
    name spelled in the play — what `just check-ansible-hostname-free` requires
    of every play in this tree — and the predicate is FAIL-CLOSED: it admits
    `agent` rather than excluding `server`, so a `ci_pool` entry whose role is
    missing or misspelled is refused too, instead of being restarted on the
    strength of a typo.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_SERVER, check_mode=check_mode)

    assert exit_code != 0, (
        f"a confirmed run against {_SERVER} must FAIL — an operator who reads a "
        f"zero exit concludes the restart is under way:\n{output}"
    )
    statuses = _task_statuses(output=output, host=_SERVER)
    assert _status_of(statuses=statuses, task=_NOT_AN_AGENT_REFUSAL_TASK) == "fatal"
    assert _POD_READ_TASK not in statuses and _RESTART_TASK not in statuses, (
        f"a refused host must stop BEFORE the pod read and the restart; it "
        f"reached: {sorted(statuses)}\n{output}"
    )
    assert (
        _recap_changed(output=output, host=_SERVER) == 0
    ), f"a refused run must report zero changes for {_SERVER}:\n{output}"
    assert _commands(scratch=scratch) == [], (
        f"a refused run must reach the cluster and the service manager with "
        f"NOTHING; it issued: {_commands(scratch=scratch)}"
    )


@pytest.mark.parametrize("check_mode", [False, True], ids=["apply", "check"])
def test_a_confirmed_run_refuses_a_node_running_a_pod_no_daemonset_owns(
    *, scratch: _Scratch, check_mode: bool
) -> None:
    """The second Definition-of-Done assertion, run.

    The confirmation names the Fabro factory agent — the host this playbook
    exists for, and the host whose running workload is most expensive to lose —
    and its node carries a bare sandbox pod and a running CI runner pod beside
    the DaemonSet-owned and already-finished pods every node has. Four things are
    then true and all four are asserted: the play FAILS; it refuses BEFORE
    reaching the restart, so the service manager is never touched; the refusal
    NAMES both pods that held it, because an operator who cannot see which
    workload is in the way cannot know what to wait for; and it does not name
    the two exempt pods, because a refusal that blamed a DaemonSet pod or a
    finished Job would send the operator after something that is never going to
    leave.

    `--check` is asserted beside the apply because the pod gate is a READ, and a
    drift report of this playbook — given the confirmation — must answer whether
    the node's workload would let the restart through rather than skip the
    question. A check run that reported a clean would-be restart over a node
    holding a live sandbox is the one output an operator must not get.
    """
    scratch.pods.write_text(_BUSY_POD_READ, encoding="utf-8")

    exit_code, output = _run_playbook(
        scratch=scratch, confirm=_FACTORY_AGENT, check_mode=check_mode
    )

    assert exit_code != 0, (
        f"a confirmed run against a node running a pod no DaemonSet owns must " f"fail:\n{output}"
    )
    statuses = _task_statuses(output=output, host=_FACTORY_AGENT)
    assert _status_of(statuses=statuses, task=_BUSY_REFUSAL_TASK) == "fatal"
    assert _RESTART_TASK not in statuses, (
        f"the restart was reached on a node still running a workload; it must "
        f"never be:\n{output}"
    )
    for named in (_SANDBOX_POD, _RUNNER_POD):
        assert named in output, (
            f"the refusal must name `{named}` — an operator who cannot see WHICH "
            f"pod held the restart cannot know what to wait for:\n{output}"
        )
    for exempt in (_DAEMONSET_POD, _COMPLETED_GATE_POD):
        assert exempt not in output, (
            f"`{exempt}` is owned by a DaemonSet or has already finished, so it "
            f"must never be counted as holding a restart:\n{output}"
        )
    commands = _commands(scratch=scratch)
    assert commands, f"a confirmed run must read the target node's pods:\n{output}"
    for command in commands:
        assert command.startswith("kubectl get pods "), (
            f"a run refused at the pod gate must only ASK the cluster about pods "
            f"and must never reach the service manager; it issued `{command}` "
            f"(full log: {commands})"
        )
        assert f"spec.nodeName={_FACTORY_AGENT}" in command, (
            f"every pod read must be field-selected to the restart's own target, "
            f"or the gate refuses a restart for a workload on another node; it "
            f"read `{command}`"
        )


def test_an_idle_node_is_restarted_after_the_pod_read_and_waited_for(*, scratch: _Scratch) -> None:
    """The DaemonSet exemption falsified, and the restart itself, run end to end.

    Assertion 2 alone is satisfied by a play that never restarts anything, so
    this is the case that makes it a real exemption rather than a blanket
    refusal: the node keeps a DaemonSet-owned pod and a finished Job pod
    THROUGHOUT, and the restart must happen anyway. The ordering is then asserted
    in the ONE shared command log, by POSITION, because the whole claim is an
    ordering claim:

    1. the restart comes AFTER the last pod read, so the gate is a precondition
       of the restart and not a report beside it;
    2. the node's Ready condition is read AFTER the restart, which it can only
       be satisfied by — the stand-in `kubectl` derives that condition from the
       marker the stand-in `systemctl` writes;
    3. the run reports the node's allocatable CPU and memory as they stand
       AFTER the restart, which is the evidence the whole playbook exists to
       produce: the reservations the rendered start configuration had never been
       read for.

    And `changed=1` on the target with `changed=0` everywhere else is the
    "changes nothing else" claim in the line an operator actually reads.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT)

    assert exit_code == 0, f"a confirmed run against an idle node must succeed:\n{output}"
    statuses = _task_statuses(output=output, host=_AGENT)
    assert _status_of(statuses=statuses, task=_POD_READ_TASK) == "ok"
    assert _status_of(statuses=statuses, task=_BUSY_REFUSAL_TASK) == "skipping", (
        f"a node whose only pods are DaemonSet-owned or already finished is "
        f"IDLE: a refusal here would mean no agent could ever be restarted, "
        f"which satisfies the refusal assertion and defeats the playbook:\n{output}"
    )
    assert _status_of(statuses=statuses, task=_RESTART_TASK) == "changed"
    assert _status_of(statuses=statuses, task=_READY_WAIT_TASK) == "ok"
    assert _status_of(statuses=statuses, task=_REPORT_TASK) == "ok"
    assert _recap_changed(output=output, host=_AGENT) == 1, (
        f"the restart must be the ONE change this playbook makes on its target; "
        f"the recap reports more:\n{output}"
    )
    for host in (_SERVER, _FACTORY_AGENT):
        assert (
            _recap_changed(output=output, host=host) == 0
        ), f"a run naming {_AGENT} must report zero changes for {host}:\n{output}"

    commands = _commands(scratch=scratch)
    pod_read = _last_index(commands=commands, needle="get pods")
    restart = _first_index(commands=commands, needle=f"systemctl restart {_AGENT_UNIT}")
    ready_read = _last_index(commands=commands, needle="get node")
    assert pod_read >= 0 and restart >= 0 and ready_read >= 0, (
        f"the run must read the node's pods, restart {_AGENT_UNIT}, and read "
        f"the node back; it issued: {commands}"
    )
    assert pod_read < restart, (
        f"the restart was issued before the pod read finished, so the gate "
        f"gated nothing: {commands}"
    )
    assert restart < ready_read, (
        f"the node's Ready condition must be read AFTER the restart — a wait "
        f"placed before it proves nothing about the node coming back: {commands}"
    )
    assert f"allocatable-cpu={_RESERVED_CPU}" in output, (
        f"the run must report the node's allocatable CPU as it stands after the "
        f"restart — the reservations taking effect ARE the outcome this playbook "
        f"exists for, and a report taken before the restart would carry the "
        f"stale `{_CAPACITY_CPU}`:\n{output}"
    )
    assert f"allocatable-memory={_RESERVED_MEMORY}" in output, (
        f"the run must report the node's allocatable memory as it stands after "
        f"the restart:\n{output}"
    )


def test_a_check_run_reads_the_targets_pods_and_withholds_the_restart(*, scratch: _Scratch) -> None:
    """The `--check` half of the first Definition-of-Done assertion, for the named host.

    A drift report must answer the question it CAN answer — would this node's
    workload let the restart through — and withhold the one thing it must not
    do. So the pod read runs, the note says in words that the restart is being
    withheld, the restart and the Ready wait report `skipping`, the service
    manager is never reached at all, and the recap reports zero changes. The
    service-manager assertion is the load-bearing one: `--check` makes ansible
    withhold a module's changes, and a task that reached `systemctl` anyway —
    through a `shell`, or with `check_mode: false` — would be invisible in the
    recap and visible only here.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, check_mode=True)

    assert exit_code == 0, f"a confirmed check run against an idle node must not fail:\n{output}"
    statuses = _task_statuses(output=output, host=_AGENT)
    assert _status_of(statuses=statuses, task=_POD_READ_TASK) == "ok"
    assert _status_of(statuses=statuses, task=_CHECK_NOTE_TASK) == "ok"
    assert _status_of(statuses=statuses, task=_RESTART_TASK) == "skipping"
    assert _status_of(statuses=statuses, task=_READY_WAIT_TASK) == "skipping"
    assert (
        _recap_changed(output=output, host=_AGENT) == 0
    ), f"a check run must report zero changes for its own target:\n{output}"
    commands = _commands(scratch=scratch)
    assert commands, f"a confirmed check run must still read the node's pods:\n{output}"
    for command in commands:
        assert command.startswith("kubectl get pods "), (
            f"a check run must ask the cluster about pods and reach the service "
            f"manager with nothing; it issued `{command}` (full log: {commands})"
        )


def test_a_restarted_node_that_never_reports_ready_fails_the_run(*, scratch: _Scratch) -> None:
    """The Ready wait is a real wait with a bounded end, not a formality.

    The node is restarted and never reports Ready again. The play must spend its
    bounded window and FAIL: an operator who restarts an agent to make its
    kubelet reservations take effect and gets a zero exit concludes the node is
    back, and a node that is not back takes every pod scheduled to it with it.
    The restart itself is asserted to have happened, so this is the wait failing
    rather than the gate refusing earlier for some other reason.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, ready_after_restart=False)

    assert exit_code != 0, (
        f"a run whose node never reported Ready again must fail; a zero exit "
        f"tells the operator the node is back:\n{output}"
    )
    statuses = _task_statuses(output=output, host=_AGENT)
    assert _status_of(statuses=statuses, task=_RESTART_TASK) == "changed"
    assert _status_of(statuses=statuses, task=_READY_WAIT_TASK) == "fatal"
    commands = _commands(scratch=scratch)
    assert _first_index(commands=commands, needle=f"systemctl restart {_AGENT_UNIT}") >= 0, (
        f"this case must reach the restart — a run that failed before it would "
        f"prove nothing about the Ready wait: {commands}"
    )
