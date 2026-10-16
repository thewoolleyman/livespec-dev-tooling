"""`ansible/node-loss-drill.yml` — the one committed way to hold a pool agent node NotReady.

WHY THE PLAYBOOK EXISTS (work-item livespec-dev-tooling-raynnh, freeze-driver
ruling R71, 2026-10-16). The livespec-orchestrator-beads-fabro plan
`kubernetes-sandbox-backend` proves its sandbox lifecycle assertion `bd-ib-ad6dby`
assertion 3 against ONE NotReady instance of an agent node: a sandbox held by a
long-lived plugin process must see no replacement pod while its node is
NotReady, and must exec again once the node is back. Stopping `k3s-agent` by
hand over ssh is a hand change to a fleet host, which the Driver's
`fleet_host_guard.py` correctly refuses and which this repository's
`SPECIFICATION/non-functional-requirements.md` now forbids outright, where it
governs consent-gated disruption of a pool node. No committed path existed, so
this playbook is that gap closed — the same shape as
`ansible/reboot-ci-server.yml`, which the same rules govern.

WHAT THESE TESTS HOLD IT TO, AND WHY THEY RUN IT. A playbook that takes a pool
node's kubelet away is destructive by construction, so every property asserted
here is asserted by RUNNING the committed playbook rather than by reading it: a
reading would assert a model of ansible's `when`, `until`, `block`/`always` and
check-mode semantics, and it is exactly those semantics that decide whether a
node's agent stops, whether it comes back, and whether the play fails. The one
claim that CANNOT be run is the absence of a task — a run proves what the play
did, never what no run of it would ever do — so the eviction direction is
asserted over the committed file's executable text as well.

HOW THEY RUN IT. By the same `ansible-core` pin `just ansible-apply` executes
(read out of the justfile rather than restated, so the two cannot drift),
against a THREE-host local `ci_pool` inventory — a server, a plain agent, and an
agent that is also a member of `sandbox_hosts` — and a scratch PATH carrying
stand-in `kubectl`, `systemctl` and `sudo`. No cluster is reached and no host is
mutated.

THE STAND-INS ARE A COUPLED STATE MACHINE, WHICH IS WHAT MAKES THE ORDERING
MEASURED RATHER THAN MODELLED. The stand-in `systemctl` records each unit's
simulated state in a file of its own; the stand-in `kubectl` answers the node's
Ready condition `True` while the AGENT's file reads `running` and `Unknown` while
it reads `stopped`. So the drill's NotReady wait can only be satisfied AFTER its
own stop ran, and its Ready wait only after its own start ran — a play that
stopped nothing hangs out its retries and fails, rather than passing on a canned
answer. Both stand-ins append their argv to ONE shared log in invocation order,
so "the agent stopped only after the pod wait finished" is read off that order
rather than off the file's layout.

THE SERVICE MANAGER ALSO HAS TIMERS, because the node's own timers are what undid
this drill's first real run (livespec-dev-tooling-6xki5a). The stand-in answers
the three reads the discovery makes — which timer units the host has, which unit
each triggers, and that unit's `Wants` and `Requires` — out of a table the
fixture writes, so "pause every timer whose unit pulls the agent in, and only
those" is asserted against a host that has one of each kind.

Work-item: livespec-dev-tooling-raynnh. Plan: livespec `factory-worker-nodes-gitops`
(epic livespec-sqvj7p). The governing clause on consent-gated pool-node
disruption lives in this repository's
`SPECIFICATION/non-functional-requirements.md`, and the acceptance scenario for
a node-loss drill that holds one agent node NotReady and restores it without
touching its workloads lives in its `SPECIFICATION/scenarios.md`;
`tests/heading-coverage.json` maps both to the tests below.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

__all__: list[str] = []

# INTEGRATION TIER, declared statically for `heading_coverage` direction 4. The
# scenario heading this module covers lives in `SPECIFICATION/scenarios.md`,
# whose mapped test must resolve at the integration tier or above; this
# repository's `scenario_tiers` prefix is `tests.consumer`, so a module in the
# mirror tree reaches the tier through the marker fallback instead. The label is
# honest: every test below drives the real committed playbook end-to-end through
# the pinned `ansible-core`, against a real inventory and real stand-in
# executables on PATH. NEITHER marker is ever used to select or deselect — no
# recipe or workflow passes `-m`.
pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_PLAYBOOK = _REPO_ROOT / "ansible" / "node-loss-drill.yml"

# The `ansible-apply` recipe's own tool pin, so these tests exercise the
# interpreter the sanctioned invocation exercises. Restating the version here
# would let the recipe move to an ansible whose `when` / `until` / `always`
# semantics nothing had tested.
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

# The two namespaces the drill is allowed to wait on, and the ONLY two: ARC's
# runner pods (one per CI job execution) and the offloaded `just check` gate
# Jobs. A factory sandbox pod lives in neither, which is the point — it is the
# SUBJECT of the drill, so waiting for it would wait forever and evicting it
# would destroy the very observation the drill exists to make.
_RUNNER_NAMESPACE = "arc-runners"
_GATE_NAMESPACE = "gates"

# The three axes the drill must find unchanged after the restore, as this
# repository spells them.
_FACTORY_LABEL = "ci-runner.io/factory"
_CHURN_SLOT = "ci-runner.io/churn-slot"
_FACTORY_TAINT = "ci-runner.io/factory-only"

# The unit the drill takes down. Named here so a rename in the play cannot pass
# by renaming the stand-in's expectations with it.
_AGENT_UNIT = "k3s-agent"

# THE NODE'S OWN TIMERS, which is what undid the first real run of this drill
# (livespec-dev-tooling-6xki5a, measured on gmktec-xubuntu 2026-10-16). The drill
# stopped `k3s-agent` at 22:44:05Z; at 22:44:45Z systemd STARTED it again, with
# no operator session and not by the drill. `agent-rejoin-watchdog.timer` fires
# every minute and its service declares `Wants=k3s-agent.service`, so merely
# ACTIVATING it pulled the stopped agent back up before its own body ran. The
# node controller therefore never saw NotReady and the drill failed its own
# observation — with the node Ready and its posture intact, which is the
# dangerous shape: nothing errored on the host, only the drill.
#
# These four rows are the stand-in service manager's whole world, and each is a
# distinct arm of the claim rather than decoration:
#
#   - a timer whose service WANTS the agent — the watchdog that actually did it;
#   - a timer whose service REQUIRES the agent — `reapply-node-extended-resource`,
#     on a five-minute timer, which would have done the same thing a moment
#     later. Both verbs are present because a discovery that read only one of
#     them would leave the other armed;
#   - a timer whose service pulls NOTHING — a drill that paused the node's whole
#     timer set would pass a one-sided assertion while disarming unrelated
#     maintenance for the length of the hold;
#   - a timer whose service wants the agent but which is ALREADY INACTIVE — the
#     restore must re-arm what IT paused and must never arm a timer the operator
#     had deliberately left down.
#
# Named without a `k3s-agent` prefix on purpose: the ordering assertions below
# read `systemctl stop k3s-agent` out of a shared log by substring, and a timer
# whose name began with the agent's would match it.
_WATCHDOG_TIMER = "agent-rejoin-watchdog.timer"
_EXTENDED_RESOURCE_TIMER = "reapply-node-extended-resource.timer"
_UNRELATED_TIMER = "logrotate.timer"
_DISARMED_TIMER = "agent-rejoin-standby.timer"

# One row per timer: the timer, the unit it triggers, that unit's `Wants`, its
# `Requires`, and the timer's state before the drill. `-` is "no such value",
# which is how the stand-in answers a property a real unit simply does not set.
_TIMER_TABLE = (
    (_WATCHDOG_TIMER, "agent-rejoin-watchdog.service", f"{_AGENT_UNIT}.service", "-", "running"),
    (
        _EXTENDED_RESOURCE_TIMER,
        "reapply-node-extended-resource.service",
        "-",
        f"{_AGENT_UNIT}.service",
        "running",
    ),
    (_UNRELATED_TIMER, "logrotate.service", "-", "-", "running"),
    (_DISARMED_TIMER, "agent-rejoin-standby.service", f"{_AGENT_UNIT}.service", "-", "stopped"),
)

# The two the drill must pause and re-arm, and the two it must leave alone.
_PAUSED_TIMERS = (_WATCHDOG_TIMER, _EXTENDED_RESOURCE_TIMER)
_UNPAUSED_TIMERS = (_UNRELATED_TIMER, _DISARMED_TIMER)

# The three hosts, named for the drill rather than for real pool nodes so no
# output of this suite can be mistaken for a record of a fleet machine having
# been touched. The roles are the two inventory facts the play selects on:
# `cluster_role`, and membership of `sandbox_hosts` — the group `ansible/fabro-hosts.yml`
# targets, which is where a Fabro server and the factory sandbox plugin live.
_SERVER = "node-loss-drill-server"
_AGENT = "node-loss-drill-agent"
_FACTORY_AGENT = "node-loss-drill-factory-agent"

# The busy pods the stand-in answers with when a test asks for a busy node: one
# per waited-on namespace, beside one that has already finished. The finished
# one is not decoration — it is the half of the read that must NOT be counted as
# busy, so a node whose only runner pod has completed still reads idle.
_BUSY_RUNNER_POD = "livespec-dev-tooling-k3s-vwxyz-runner-9bqdn"
_COMPLETED_RUNNER_POD = "livespec-dev-tooling-k3s-vwxyz-runner-2fkpt"
_BUSY_GATE_POD = "livespec-dev-tooling-gate-7f4kd-pzn2w"

# The playbook's OWN task names, which are the vocabulary a run is read in: an
# operator scanning the output matches these strings, so a test that asserts a
# status against them is asserting what the operator sees.
_UNCONFIRMED_NOTE_TASK = "Report a run that carries no node-loss confirmation for this host"
_REFUSAL_TASK = "Refuse a node-loss drill on the control-plane node or a Fabro factory host"
_IDLE_WAIT_TASK = "Wait for two consecutive idle reads of the node's CI runner and gate pods"
_BUSY_REFUSAL_TASK = "Refuse a node-loss drill on a node whose CI pods never went idle"
_POSTURE_BEFORE_TASK = "Read the node's taints, factory label and churn-slot capacity"
_DISCOVER_TASK = "Discover the units whose timers would restart the node's k3s agent"
_PAUSE_TASK = "Pause the timers that would restart the node's k3s agent during the hold"
_REARM_TASK = "Re-arm the timers that were paused for the hold"
_REARM_REPORT_TASK = "Report the timers that were paused for the hold and re-armed after it"
_STOP_TASK = "Stop the node's k3s agent"
_NOTREADY_WAIT_TASK = "Wait until the API first reports the node NotReady"
_HOLD_TASK = "Hold the node NotReady for the configured window"
_START_TASK = "Start the node's k3s agent again"
_READY_WAIT_TASK = "Wait until the API reports the node Ready again"
_POSTURE_AFTER_TASK = "Read the node's posture again and wait for it to match the recorded one"
_REPORT_TASK = "Report the UTC times the API first showed the node NotReady and Ready again"
_VERIFY_TASK = "Fail unless the node's taints, factory label and churn-slot capacity are unchanged"

# The hold every run below is given, in seconds. Read back out of the reported
# instants, so the window is measured rather than taken from the flag.
_TEST_HOLD_SECONDS = 3

# Generous: a cold `uvx` resolves and caches ansible-core before the first play
# runs. Bounded all the same, so a hung play fails this test rather than the
# suite's whole budget.
_PLAYBOOK_TIMEOUT_SECONDS = 600

_TASK_HEADER = re.compile(r"^TASK \[(?P<name>.+?)\] \**$")
_HOST_STATUS = re.compile(r"^(?P<status>ok|changed|skipping|failed|fatal|unreachable): \[")

# The report's two timestamps, as the operator reads them out of the play's
# output. A UTC instant to the second, which is the resolution `date -u` gives
# the play and the resolution the proof record wants.
_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_NOTREADY_AT = re.compile(r"NotReady at (?P<at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")
_READY_AT = re.compile(r"Ready again at (?P<at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")

# A stand-in `sudo` that drops its option flags and its `-u <user>` and execs
# the rest. Every host-acting task of the play carries privilege escalation
# because the admin kubeconfig it reads is root-owned on a real node and
# stopping a unit is root's; this suite runs as whoever invoked pytest, with no
# sudo guaranteed on the image. So become is SATISFIED rather than switched off,
# which keeps the executed task shape the same as the operator's.
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
# cluster and WHEN it asked relative to the unit it stopped. It exits non-zero
# on anything it was not written to answer rather than returning a plausible
# empty string — an unexpected invocation must break a test, not quietly read as
# an idle node and let a stop through.
#
# THE READY CONDITION IS DERIVED FROM THE AGENT STATE FILE the stand-in
# `systemctl` writes, never canned: `True` while the agent reads running,
# `Unknown` once it reads stopped, which is what a real node's Ready condition
# becomes when its kubelet stops posting status. That coupling is what makes the
# drill's two waits real waits.
#
# `NODE_LOSS_DRILL_READY_WHILE_STOPPED` BREAKS THAT COUPLING ON PURPOSE, and it
# is the only way to reproduce the defect this drill was actually undone by: a
# node whose agent is down but which the API keeps reporting Ready, because
# something on the host put the agent back. With it set, the NotReady wait
# exhausts its window and the play fails there — the exact run recorded on
# gmktec-xubuntu — so the restore and re-arm path can be asserted on a run that
# failed AFTER the agent was stopped.
#
# THE NODE OBJECT IS SERVED FROM TWO FILES AND A READ COUNTER: the first
# `-o json` read gets the recorded "before" document, every later one gets the
# "after" document. A test that wants the drill to find a changed node writes a
# different "after"; a test that wants it unchanged writes the same bytes twice.
_KUBECTL_STAND_IN = f"""#!/bin/sh
printf 'kubectl %s\\n' "$*" >> "${{NODE_LOSS_DRILL_COMMAND_LOG}}"
agent_state="$(cat "${{NODE_LOSS_DRILL_AGENT_STATE}}" 2>/dev/null || printf 'running')"
case "$*" in
  *'get pods'*"--namespace {_RUNNER_NAMESPACE}"*)
    if [ "${{NODE_LOSS_DRILL_PODS}}" = busy ]; then
      printf '{_RUNNER_NAMESPACE}/{_BUSY_RUNNER_POD}=Running\\n'
      printf '{_RUNNER_NAMESPACE}/{_COMPLETED_RUNNER_POD}=Succeeded\\n'
    fi
    exit 0 ;;
  *'get pods'*"--namespace {_GATE_NAMESPACE}"*)
    if [ "${{NODE_LOSS_DRILL_PODS}}" = busy ]; then
      printf '{_GATE_NAMESPACE}/{_BUSY_GATE_POD}=Running\\n'
    fi
    exit 0 ;;
  *'get node'*jsonpath*)
    if [ "${{agent_state}}" = running ] \
       || [ "${{NODE_LOSS_DRILL_READY_WHILE_STOPPED}}" = yes ]; then
      printf 'True'
    else
      printf 'Unknown'
    fi
    exit 0 ;;
  *'get node'*'-o json'*)
    reads="$(cat "${{NODE_LOSS_DRILL_NODE_READS}}" 2>/dev/null || printf '0')"
    reads=$((reads + 1))
    printf '%s' "${{reads}}" > "${{NODE_LOSS_DRILL_NODE_READS}}"
    if [ "${{reads}}" -le 1 ]; then
      cat "${{NODE_LOSS_DRILL_NODE_BEFORE}}"
    else
      cat "${{NODE_LOSS_DRILL_NODE_AFTER}}"
    fi
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""

# The stand-in `systemctl`, answering the shape `ansible.builtin.systemd_service`
# reads: a `show` of the unit's load and active state, then `stop` or `start`.
# It is the WRITER of the agent state file the stand-in `kubectl` reads, so a
# stop is observable both in the shared log and in what the API then says about
# the node.
#
# STATE IS PER UNIT, in one file per unit under a state directory, which is what
# lets the drill's timer pause be told apart from its agent stop. One shared
# state file would make stopping a timer read as stopping the agent — the node
# would read NotReady before the drill had taken it down, and the agent's own
# stop would then be a no-op the module declined to issue. The agent's file is
# the one the stand-in `kubectl` derives the node's Ready condition from.
#
# IT ALSO ANSWERS THE THREE READS THE DISCOVERY NEEDS, out of the timer table
# the fixture writes rather than out of anything canned here: which timer units
# the host has, which unit each one triggers, and that unit's `Wants` and
# `Requires`. A timer with no state file of its own starts in the state its
# table row records, so a timer the operator had already stopped is INACTIVE to
# `is-active` on the first read — which is what makes "re-arm only what you
# paused" falsifiable.
_SYSTEMCTL_STAND_IN = """#!/bin/sh
printf 'systemctl %s\\n' "$*" >> "${NODE_LOSS_DRILL_COMMAND_LOG}"
state_dir="${NODE_LOSS_DRILL_STATE_DIR}"
table="${NODE_LOSS_DRILL_TIMER_TABLE}"

table_row() {
  awk -v column="$1" -v wanted="$2" '$column == wanted { print; exit }' "${table}"
}

unit_state() {
  if [ -f "${state_dir}/$1" ]; then
    cat "${state_dir}/$1"
    return 0
  fi
  row="$(table_row 1 "$1")"
  if [ -n "${row}" ]; then
    printf '%s' "${row}" | awk '{ print $5 }'
    return 0
  fi
  printf 'running'
}

case "$*" in
  *'list-unit-files'*'--type=timer'*)
    awk '{ printf "%s enabled enabled\\n", $1 }' "${table}"
    exit 0 ;;
  *'--property=Unit'*)
    table_row 1 "$2" | awk '{ print $2 }'
    exit 0 ;;
  *'--property=Wants'*)
    table_row 2 "$2" | awk '{ if ($3 != "-") print $3; if ($4 != "-") print $4 }'
    exit 0 ;;
esac

case "$1" in
  show)
    printf 'LoadState=loaded\\nUnitFileState=enabled\\n'
    if [ "$(unit_state "$2")" = running ]; then
      printf 'ActiveState=active\\nSubState=running\\n'
    else
      printf 'ActiveState=inactive\\nSubState=dead\\n'
    fi
    exit 0 ;;
  is-active)
    target=''
    shift
    for argument in "$@"; do
      case "${argument}" in -*) ;; *) target="${argument}" ;; esac
    done
    if [ "$(unit_state "${target}")" = running ]; then exit 0; fi
    exit 3 ;;
  stop)
    printf 'stopped' > "${state_dir}/$2"
    exit 0 ;;
  start)
    printf 'running' > "${state_dir}/$2"
    exit 0 ;;
  is-enabled)
    printf 'enabled\\n'
    exit 0 ;;
  daemon-reload)
    exit 0 ;;
esac
printf 'stand-in systemctl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""


def _node_object(
    *, taints: list[dict[str, str]], factory_label: str | None, churn_slots: str | None
) -> str:
    """One `kubectl get node -o json` document, carrying the three verified axes.

    Shaped as the API shapes it — taints under `spec`, the factory label under
    `metadata.labels`, the churn-slot extended resource under `status.capacity` —
    because the play reads those three paths and a fixture that flattened them
    would prove nothing about the paths it reads.
    """
    labels = {"kubernetes.io/hostname": _AGENT}
    if factory_label is not None:
        labels[_FACTORY_LABEL] = factory_label
    capacity = {"cpu": "8", "memory": "32654848Ki"}
    if churn_slots is not None:
        capacity[_CHURN_SLOT] = churn_slots
    return json.dumps(
        {
            "metadata": {"name": _AGENT, "labels": labels},
            "spec": {"taints": taints},
            "status": {"capacity": capacity},
        }
    )


# The node as the drill must find it both before and after: the factory-only
# taint this pool's factory agents carry, the factory label the sandbox
# backend's selector reads, and the churn-slot capacity the pool's admission
# budget is apportioned against.
_BASELINE_TAINTS = [{"key": _FACTORY_TAINT, "value": "true", "effect": "NoSchedule"}]
_BASELINE_NODE = _node_object(taints=_BASELINE_TAINTS, factory_label="true", churn_slots="22")

# The three ways the restore can come back wrong, each a single axis moved. One
# per axis rather than one combined document, because a play that compared only
# two of the three would pass a combined fixture.
#
# Each is the drift this pool ACTUALLY produces. The label and the extended
# resource go ABSENT rather than wrong, because both are patched onto a Node
# object after it registers and k3s re-creates that object from scratch when a
# node re-registers — which is exactly how a control-plane reboot left the
# factory label on one node of three (livespec-dev-tooling-izlx4g). The taint
# arrives EXTRA, and it is the node lifecycle controller's own `unreachable`
# taint, because a taint that outlives the NotReady state that justified it
# repels work from a node that is back.
_DRIFTED_NODES = {
    "taints": _node_object(
        taints=[
            *_BASELINE_TAINTS,
            {"key": "node.kubernetes.io/unreachable", "effect": "NoExecute"},
        ],
        factory_label="true",
        churn_slots="22",
    ),
    "factory-label": _node_object(taints=_BASELINE_TAINTS, factory_label=None, churn_slots="22"),
    "churn-slot": _node_object(taints=_BASELINE_TAINTS, factory_label="true", churn_slots=None),
}


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    """One test's isolated world: its stand-in binaries, its logs, its node documents."""

    root: Path
    bin_dir: Path
    command_log: Path
    state_dir: Path
    agent_state: Path
    timer_table: Path
    node_reads: Path
    node_before: Path
    node_after: Path


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
    """A scratch root with the three stand-ins on a private bin dir and an unchanged node."""
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
    state_dir = tmp_path / "unit-state"
    state_dir.mkdir()
    timer_table = tmp_path / "timer-table"
    timer_table.write_text("".join(f"{' '.join(row)}\n" for row in _TIMER_TABLE), encoding="utf-8")
    node_before = tmp_path / "node-before.json"
    node_after = tmp_path / "node-after.json"
    for document in (node_before, node_after):
        document.write_text(_BASELINE_NODE, encoding="utf-8")
    return _Scratch(
        root=tmp_path,
        bin_dir=bin_dir,
        command_log=tmp_path / "command.log",
        state_dir=state_dir,
        # The AGENT's own state file, inside the per-unit state directory: the
        # one the stand-in `kubectl` derives the node's Ready condition from.
        agent_state=state_dir / _AGENT_UNIT,
        timer_table=timer_table,
        node_reads=tmp_path / "node-reads",
        node_before=node_before,
        node_after=node_after,
    )


def _write_inventory(*, scratch: _Scratch) -> Path:
    """A three-host `ci_pool` inventory: a server, an agent, and an agent in `sandbox_hosts`.

    The group memberships and the `cluster_role` values are the inventory facts
    the playbook selects on, so they ride as INVENTORY vars — the precedence an
    operator's own inventory uses. Everything the fixture needs to BOUND (the
    read intervals, the retry counts, the hold, the confirmation) rides as
    `--extra-vars` instead, because the playbook declares those as play vars and
    play vars beat inventory.

    `node-loss-drill-factory-agent` is in BOTH `ci_pool` and `sandbox_hosts`,
    which is `hp-xubuntu`'s real shape: a Fabro factory host that also joins the
    pool as a factory-only agent. It is the host the drill must refuse without
    any host name being spelled in the play.
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


def _playbook_environment(
    *, scratch: _Scratch, pods: str, ready_while_stopped: bool
) -> dict[str, str]:
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
            "NODE_LOSS_DRILL_COMMAND_LOG": str(scratch.command_log),
            "NODE_LOSS_DRILL_STATE_DIR": str(scratch.state_dir),
            "NODE_LOSS_DRILL_AGENT_STATE": str(scratch.agent_state),
            "NODE_LOSS_DRILL_TIMER_TABLE": str(scratch.timer_table),
            "NODE_LOSS_DRILL_NODE_READS": str(scratch.node_reads),
            "NODE_LOSS_DRILL_NODE_BEFORE": str(scratch.node_before),
            "NODE_LOSS_DRILL_NODE_AFTER": str(scratch.node_after),
            "NODE_LOSS_DRILL_PODS": pods,
            # Always SET, never merely absent when unwanted: the stand-in reads
            # it with no `set -u`, so an unset variable would make the knob's
            # off state untested rather than tested.
            "NODE_LOSS_DRILL_READY_WHILE_STOPPED": "yes" if ready_while_stopped else "no",
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
    pods: str = "idle",
    ready_while_stopped: bool = False,
) -> tuple[int, str]:
    """Run the committed playbook; return its exit code and its callback output."""
    assert _PLAYBOOK.is_file(), (
        f"{_PLAYBOOK} must exist — it is the only committed way to hold a pool "
        f"agent node NotReady, and without it the sandbox backend's lifecycle "
        f"proof can only be driven by a hand change to a fleet host"
    )
    inventory = _write_inventory(scratch=scratch)
    argv = [
        "uvx",
        "--from",
        _ansible_core_pin(),
        "ansible-playbook",
        "-i",
        str(inventory),
        # The waits, bounded to nothing: no gap between the reads of a pair, and
        # ONE retry (ansible's `retries` is ADDITIONAL attempts, so this is two
        # attempts). Two rather than one on purpose — it exercises the retry
        # loop, which is the half of each bounded wait that decides whether a
        # condition that never arrives ends in a refusal or in a pass.
        "-e",
        "node_loss_drill_idle_interval=0",
        "-e",
        "node_loss_drill_idle_retries=1",
        "-e",
        "node_loss_drill_status_interval=0",
        "-e",
        "node_loss_drill_status_retries=1",
        "-e",
        "node_loss_drill_posture_retries=1",
        # A three-second hold: short enough that the suite does not pay for a
        # real NotReady window, long enough that the two reported instants are
        # MEASURABLY apart at the one-second resolution the drill reports in.
        # A zero hold would make "it held the node down for the configured
        # window" unfalsifiable.
        "-e",
        f"node_loss_drill_hold_minutes={_TEST_HOLD_SECONDS / 60}",
        *(["-e", f"node_loss_drill_confirm={confirm}"] if confirm is not None else []),
        *(["--check"] if check_mode else []),
        str(_PLAYBOOK),
    ]
    completed = subprocess.run(
        argv,
        cwd=scratch.root,
        env=_playbook_environment(
            scratch=scratch, pods=pods, ready_while_stopped=ready_while_stopped
        ),
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

    Returned as an INDEX rather than a boolean because every ordering claim
    below is a claim about position in one shared log: "the agent stopped after
    the pod wait finished" is `stop index > last pod-read index`, and nothing
    weaker establishes it.
    """
    return next((index for index, command in enumerate(commands) if needle in command), -1)


def _last_index(*, commands: list[str], needle: str) -> int:
    """The index of the LAST logged command containing `needle`, or -1."""
    return next(
        (index for index in range(len(commands) - 1, -1, -1) if needle in commands[index]),
        -1,
    )


def _executable_lines() -> list[str]:
    """The committed playbook's executable text, with its YAML comments removed.

    The eviction direction below is a claim about what the play DOES, and this
    playbook's rationale — which says at length that it never cordons, drains,
    evicts or deletes anything — is carried in comments. A scan that read those
    comments would convict the play of the very thing they promise it does not
    do, so the comments come out first. Full-line comments and trailing ` #`
    comments both go; no value in this playbook contains a `#`.
    """
    assert _PLAYBOOK.is_file(), (
        f"{_PLAYBOOK} must exist — the claim graded here is a claim about the "
        f"committed playbook's own text, and there is nothing else to read it in"
    )
    lines: list[str] = []
    for raw in _PLAYBOOK.read_text(encoding="utf-8").splitlines():
        if raw.lstrip().startswith("#"):
            continue
        lines.append(re.sub(r"\s+#.*$", "", raw))
    assert lines, f"{_PLAYBOOK} carries no executable text at all"
    return lines


def test_a_run_whose_confirmation_does_not_name_a_host_changes_nothing_on_it(
    *, scratch: _Scratch
) -> None:
    """The consent half of the first Definition-of-Done assertion, run rather than modelled.

    This is what keeps a playbook that takes a node's kubelet away safe to leave
    in the tree: a bare apply, a drift sweep, or a typo'd confirmation reaches
    NOTHING on any host. Asserted on four axes, because any one of them passing
    alone would still leave a way to take a node down by accident — every host
    reports zero changes, the idle wait and the stop both report `skipping`
    rather than running, neither the cluster nor the service manager is asked
    anything at all, and that holds for the confirmation being absent and for it
    naming a host outside this inventory.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=None)

    assert exit_code == 0, (
        f"an unconfirmed run must END, not fail — a refusal that errored would "
        f"redden every sweep that includes this playbook:\n{output}"
    )
    for host in (_SERVER, _AGENT, _FACTORY_AGENT):
        statuses = _task_statuses(output=output, host=host)
        assert _status_of(statuses=statuses, task=_UNCONFIRMED_NOTE_TASK) == "ok"
        assert _status_of(statuses=statuses, task=_IDLE_WAIT_TASK) == "skipping"
        assert _status_of(statuses=statuses, task=_STOP_TASK) == "skipping"
        assert _status_of(statuses=statuses, task=_START_TASK) == "skipping"
        assert (
            _recap_changed(output=output, host=host) == 0
        ), f"an unconfirmed run must report zero changes for {host}:\n{output}"
    assert _commands(scratch=scratch) == [], (
        f"an unconfirmed run must reach the cluster and the service manager with "
        f"NOTHING; it issued: {_commands(scratch=scratch)}"
    )


@pytest.mark.parametrize("check_mode", [False, True], ids=["apply", "check"])
def test_a_confirmation_naming_another_host_changes_nothing_on_this_one(
    *, scratch: _Scratch, check_mode: bool
) -> None:
    """The same fence, against the confirmation that is most likely to be a typo.

    The confirmation names a host that IS in this inventory — the plain agent —
    so the two hosts it does not name must still reach nothing. `--check` is
    asserted beside the apply because a drift sweep runs in check mode, and
    check mode is NOT what makes this safe: the confirmation gate is. Under
    `--check` the run is bounded to the reads, so the confirmed host's own tasks
    change nothing either, which is why this case asserts on the hosts the
    confirmation does not name.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, check_mode=check_mode)

    assert exit_code == 0, f"a confirmed, idle run must not fail:\n{output}"
    for host in (_SERVER, _FACTORY_AGENT):
        statuses = _task_statuses(output=output, host=host)
        assert _status_of(statuses=statuses, task=_UNCONFIRMED_NOTE_TASK) == "ok"
        assert _status_of(statuses=statuses, task=_IDLE_WAIT_TASK) == "skipping"
        assert _status_of(statuses=statuses, task=_STOP_TASK) == "skipping"
        assert _status_of(statuses=statuses, task=_REFUSAL_TASK) == "skipping", (
            f"{host} must not be REFUSED by a run that does not name it — it "
            f"must simply not be acted on; a refusal here would fail every run "
            f"aimed at some other host:\n{output}"
        )
        assert (
            _recap_changed(output=output, host=host) == 0
        ), f"a run naming {_AGENT} must report zero changes for {host}:\n{output}"
    for command in _commands(scratch=scratch):
        assert _SERVER not in command and _FACTORY_AGENT not in command, (
            f"a run naming {_AGENT} asked about another host: `{command}` (full "
            f"log: {_commands(scratch=scratch)})"
        )


@pytest.mark.parametrize(
    "forbidden_host",
    [_SERVER, _FACTORY_AGENT],
    ids=["control-plane", "fabro-factory-host"],
)
def test_a_confirmed_run_refuses_the_control_plane_node_and_every_fabro_factory_host(
    *, scratch: _Scratch, forbidden_host: str
) -> None:
    """The refusal half of the first Definition-of-Done assertion.

    Consent is necessary and NOT sufficient. Two hosts in the pool must never
    have their agent taken down however explicitly an operator asks: the
    control-plane node, whose loss is a cluster outage rather than a node-loss
    drill, and a Fabro factory host, whose Fabro server and sandbox plugin are
    the machinery the drill is being run FOR. The refusal must be LOUD — a
    confirmed run that silently did nothing reads exactly like a drill in
    progress — and it must land before anything is read, so the output is also
    asserted to carry no cluster or service-manager call at all.

    Both hosts are identified from INVENTORY, never from a host name spelled in
    the play: the server by its `cluster_role`, the factory host by its
    membership of `sandbox_hosts`. That is what `just check-ansible-hostname-free`
    requires of every play in this tree, and it is also what makes the refusal
    survive the Fabro cutover — a second pool node joining `sandbox_hosts`
    becomes refused by the same clause, with no edit here.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=forbidden_host)

    assert exit_code != 0, (
        f"a confirmed run against {forbidden_host} must FAIL — an operator who "
        f"reads a zero exit concludes the drill is under way:\n{output}"
    )
    statuses = _task_statuses(output=output, host=forbidden_host)
    assert _status_of(statuses=statuses, task=_REFUSAL_TASK) == "fatal"
    assert _IDLE_WAIT_TASK not in statuses and _STOP_TASK not in statuses, (
        f"a refused host must stop BEFORE the idle wait and the stop; it "
        f"reached: {sorted(statuses)}\n{output}"
    )
    assert (
        _recap_changed(output=output, host=forbidden_host) == 0
    ), f"a refused run must report zero changes for {forbidden_host}:\n{output}"
    assert _commands(scratch=scratch) == [], (
        f"a refused run must reach the cluster and the service manager with "
        f"NOTHING; it issued: {_commands(scratch=scratch)}"
    )


def test_the_drill_waits_on_the_targets_runner_and_gate_pods_and_on_nothing_else(
    *, scratch: _Scratch
) -> None:
    """The first half of the second Definition-of-Done assertion, run.

    The confirmation names the plain agent, so the idle gate is reached; the
    stand-in `kubectl` answers both waited-on namespaces with a Running pod, so
    the gate never opens. Three things are then true and all three are asserted:
    the play FAILS, naming each busy namespace and the pod that made it busy; it
    read ONLY the two CI namespaces, and in each read field-selected the pods to
    the drill's own target, so no other node's workload could have held it; and
    it never reached the service manager, so the agent was not taken down on a
    node whose CI work was still running.

    THE FIELD SELECTOR IS THE LOAD-BEARING HALF, and it is asserted per read
    rather than once. A wait on the namespace as a whole would hold this drill
    open for a CI job executing on a DIFFERENT node — which is not a reason to
    delay this node's drill, and on a busy pool is a wait that never ends.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, pods="busy")

    assert exit_code != 0, (
        f"a confirmed run against a node whose CI pods are still running must " f"fail:\n{output}"
    )
    statuses = _task_statuses(output=output, host=_AGENT)
    assert _status_of(statuses=statuses, task=_BUSY_REFUSAL_TASK) == "fatal"
    assert _STOP_TASK not in statuses, (
        f"the stop was reached on a node still running CI work; it must never " f"be:\n{output}"
    )
    for named in (_RUNNER_NAMESPACE, _BUSY_RUNNER_POD, _GATE_NAMESPACE, _BUSY_GATE_POD):
        assert named in output, (
            f"the refusal must name `{named}` — an operator who cannot see WHICH "
            f"pod held the drill cannot know what to wait for:\n{output}"
        )
    assert _COMPLETED_RUNNER_POD not in output, (
        f"`{_COMPLETED_RUNNER_POD}` has already finished, so it must not be "
        f"counted as busy; a node whose only runner pod has completed is "
        f"idle:\n{output}"
    )
    commands = _commands(scratch=scratch)
    assert commands, f"a confirmed run must read the node's pods:\n{output}"
    for command in commands:
        assert command.startswith("kubectl get pods "), (
            f"a run held at the idle gate must only ASK the cluster about pods "
            f"and must never reach the service manager; it issued `{command}` "
            f"(full log: {commands})"
        )
        assert f"--namespace {_RUNNER_NAMESPACE} " in f"{command} " or (
            f"--namespace {_GATE_NAMESPACE} " in f"{command} "
        ), (
            f"the wait must cover ONLY the CI runner and gate namespaces — a "
            f"factory sandbox pod is the drill's subject, not something to wait "
            f"for; it read `{command}`"
        )
        assert f"spec.nodeName={_AGENT}" in command, (
            f"every pod read must be field-selected to the drill's own target, "
            f"or the drill waits on another node's CI work; it read `{command}`"
        )


def test_no_task_of_the_playbook_cordons_drains_evicts_or_deletes_a_pod() -> None:
    """The second half of the second Definition-of-Done assertion, read rather than run.

    This is the ONE claim in this file a run cannot establish. A run proves what
    the play did on one path; the claim here is that NO path of it ever removes a
    workload from the node — and the reason that matters is specific: the factory
    sandbox pod on the target IS the subject of the drill. The lifecycle proof
    asks whether a held sandbox sees a replacement pod while its node is
    NotReady. Evict it, cordon the node, or drain it, and the drill answers a
    different question with a clean-looking pass.

    So the committed file's executable text — its comments removed, since they
    say at length that it does none of this — must not carry any of these verbs
    at all, and every cluster call it makes must be a `get`. Both directions are
    asserted: the forbidden vocabulary is absent, and the permitted vocabulary is
    an allowlist, so a verb nobody thought to forbid is caught too.
    """
    lines = _executable_lines()
    for verb in ("cordon", "drain", "evict", "delete", "k8s_drain"):
        offenders = [line for line in lines if verb in line.lower()]
        assert not offenders, (
            f"{_PLAYBOOK} must carry no task that would {verb} a pod or a node — "
            f"the factory sandbox pod on the target is the drill's SUBJECT, and "
            f"removing it answers a different question. Found: {offenders}"
        )
    kubectl_lines = [line for line in lines if "kubectl" in line]
    assert kubectl_lines, (
        f"{_PLAYBOOK} must reach the cluster through kubectl; a reader that "
        f"found no call at all is reading the wrong file or the wrong text"
    )
    for line in kubectl_lines:
        assert re.search(r"kubectl\b", line) is not None and (
            "get" in line or line.rstrip().endswith("kubectl")
        ), (
            f"every cluster call this playbook makes must be a read; `{line}` "
            f"is not recognisably a `kubectl get`"
        )


def test_the_drill_stops_the_agent_after_the_wait_holds_it_and_restores_the_node(
    *, scratch: _Scratch
) -> None:
    """The third Definition-of-Done assertion and the governing scenario, run end to end.

    One confirmed run against the plain agent with its CI namespaces idle. Every
    step of the drill is then asserted in the ONE shared command log, by
    POSITION, because the whole claim is an ordering claim:

    1. the agent's stop comes AFTER the last pod read, so the drill never takes
       a node down with CI work still on it;
    2. the API is read for the node's Ready condition BETWEEN the stop and the
       start, which is the NotReady observation the drill exists to produce —
       and it can only succeed there, since the stand-in `kubectl` derives that
       condition from the state file the stand-in `systemctl` writes;
    3. the start comes after the stop, so the node is restored rather than left
       down;
    4. the node's posture is read once before the stop and again after the
       start, which is what the verification compares.

    The run must end with no failure, and its output must carry both UTC
    timestamps — the instant the API first showed the node NotReady, and the
    instant it showed it Ready again — because those two instants ARE the
    artifact a node-loss drill is run to produce.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT)

    assert exit_code == 0, f"an idle, confirmed drill must complete:\n{output}"
    recap = re.search(
        rf"^{re.escape(_AGENT)}\s+: .*?\bfailed=(?P<failed>\d+)\b", output, re.MULTILINE
    )
    assert (
        recap is not None and recap["failed"] == "0"
    ), f"the drill's own host must end with failed=0:\n{output}"
    statuses = _task_statuses(output=output, host=_AGENT)
    for task in (
        _IDLE_WAIT_TASK,
        _POSTURE_BEFORE_TASK,
        _STOP_TASK,
        _NOTREADY_WAIT_TASK,
        _HOLD_TASK,
        _START_TASK,
        _READY_WAIT_TASK,
        _POSTURE_AFTER_TASK,
        _REPORT_TASK,
        _VERIFY_TASK,
    ):
        assert _status_of(statuses=statuses, task=task) in {"ok", "changed"}, (
            f"task `{task}` did not run to a clean status on {_AGENT}: "
            f"{statuses.get(task)}\n{output}"
        )

    commands = _commands(scratch=scratch)
    stop = _first_index(commands=commands, needle=f"systemctl stop {_AGENT_UNIT}")
    start = _first_index(commands=commands, needle=f"systemctl start {_AGENT_UNIT}")
    last_pod_read = _last_index(commands=commands, needle="kubectl get pods ")
    posture_reads = [index for index, command in enumerate(commands) if "-o json" in command]
    status_reads = [index for index, command in enumerate(commands) if "jsonpath" in command]
    assert stop >= 0 and start >= 0, (
        f"the drill must stop and then start `{_AGENT_UNIT}`; the log reads " f"{commands}"
    )
    assert last_pod_read >= 0 and stop > last_pod_read, (
        f"`{_AGENT_UNIT}` was stopped at log position {stop}, before or amid the "
        f"pod wait that ends at {last_pod_read}. The wait is what keeps a CI job "
        f"from dying with the node: {commands}"
    )
    assert start > stop, (
        f"the start must follow the stop, or the drill leaves the node down: " f"{commands}"
    )
    assert any(stop < index < start for index in status_reads), (
        f"the API must be read for the node's Ready condition while the agent is "
        f"down — that read IS the NotReady observation: {commands}"
    )
    assert any(index > start for index in status_reads), (
        f"the API must be read again after the start, so `Ready` is observed "
        f"rather than assumed: {commands}"
    )
    assert len(posture_reads) >= 2, (
        f"the node's posture must be read before the stop and after the " f"restore: {commands}"
    )
    assert posture_reads[0] < stop and posture_reads[-1] > start, (
        f"the recorded posture must be taken BEFORE the agent stops and "
        f"re-read AFTER it is back: {commands}"
    )

    notready_at = _NOTREADY_AT.search(output)
    ready_at = _READY_AT.search(output)
    assert notready_at is not None and ready_at is not None, (
        f"the drill must report the UTC instants at which the API first showed "
        f"the node NotReady and showed it Ready again — those two instants are "
        f"the artifact the drill produces:\n{output}"
    )
    held = (
        datetime.strptime(ready_at["at"], _UTC_FORMAT).replace(tzinfo=timezone.utc)
        - datetime.strptime(notready_at["at"], _UTC_FORMAT).replace(tzinfo=timezone.utc)
    ).total_seconds()
    # THE HOLD, MEASURED out of the drill's own two instants rather than taken
    # from the flag that configured it. One second of slack for the reports'
    # one-second resolution; the point is that the node was down for the window
    # and not merely bounced, which is the condition the sandbox observer needs
    # and the one a zero-length hold would silently fail to provide.
    assert held >= _TEST_HOLD_SECONDS - 1, (
        f"the node was reported NotReady at {notready_at['at']} and Ready again "
        f"at {ready_at['at']} — {held}s apart, under the configured "
        f"{_TEST_HOLD_SECONDS}s hold. A drill that bounced the agent instead of "
        f"holding the node down gives the observer no window:\n{output}"
    )
    assert scratch.agent_state.read_text(encoding="utf-8") == "running", (
        "the drill must leave the agent running; it left "
        f"`{scratch.agent_state.read_text(encoding='utf-8')}`"
    )


def test_the_drill_pauses_the_timers_that_would_restart_the_agent_and_re_arms_them(
    *, scratch: _Scratch
) -> None:
    """The node's OWN timers, paused for the hold and re-armed after it.

    This is the defect the drill's first real run met and the reason this test
    exists (livespec-dev-tooling-6xki5a, gmktec-xubuntu 2026-10-16). The drill
    stopped `k3s-agent` at 22:44:05Z and at 22:44:45Z systemd started it again,
    with no operator session and not by the drill: `agent-rejoin-watchdog.timer`
    fires every minute and its service declares `Wants=k3s-agent.service`, so
    activating it pulled the stopped agent back up before its own body ran. The
    node controller never observed NotReady, and `reapply-node-extended-resource`
    — which `Requires=k3s-agent.service` on a five-minute timer — would have
    done the same thing a moment later. A hold longer than about a minute is
    undone by the node itself.

    So the ordering is asserted in the ONE shared command log, by POSITION, and
    in both directions:

    1. each timer whose service Wants OR Requires the agent is stopped BEFORE
       the agent is — a pause issued afterwards leaves a window in which the
       watchdog can fire;
    2. each of them is started again AFTER the agent is back, and the stand-in's
       per-unit state file is read to prove it ended up armed rather than merely
       asked to start;
    3. a timer whose service pulls NOTHING is neither stopped nor started, so a
       drill cannot pass this by disarming the node's whole timer set;
    4. a timer whose service wants the agent but which was ALREADY inactive is
       neither stopped nor started, so the restore re-arms what it paused and
       never arms what an operator had deliberately left down.

    The play's output must also NAME them, in both senses: an operator reading a
    run has to see which of the node's units were disarmed for the hold and that
    they were put back.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT)

    assert exit_code == 0, f"an idle, confirmed drill must complete:\n{output}"
    statuses = _task_statuses(output=output, host=_AGENT)
    for task in (_DISCOVER_TASK, _PAUSE_TASK, _REARM_TASK, _REARM_REPORT_TASK):
        assert _status_of(statuses=statuses, task=task) in {"ok", "changed"}, (
            f"task `{task}` did not run to a clean status on {_AGENT}: "
            f"{statuses.get(task)}\n{output}"
        )

    commands = _commands(scratch=scratch)
    agent_stop = _first_index(commands=commands, needle=f"systemctl stop {_AGENT_UNIT}")
    agent_start = _first_index(commands=commands, needle=f"systemctl start {_AGENT_UNIT}")
    assert agent_stop >= 0 and agent_start >= 0, (
        f"the drill must stop and then start `{_AGENT_UNIT}`; the log reads " f"{commands}"
    )
    for timer in _PAUSED_TIMERS:
        paused = _first_index(commands=commands, needle=f"systemctl stop {timer}")
        re_armed = _last_index(commands=commands, needle=f"systemctl start {timer}")
        assert 0 <= paused < agent_stop, (
            f"`{timer}` triggers a unit that pulls `{_AGENT_UNIT}` in, so it must "
            f"be stopped at a log position BEFORE the agent's own stop at "
            f"{agent_stop}; it was stopped at {paused}. A timer left armed "
            f"restarts the agent mid-hold and the node never reads NotReady: "
            f"{commands}"
        )
        assert re_armed > agent_start, (
            f"`{timer}` must be started again after the agent is back; the agent "
            f"started at log position {agent_start} and the timer at {re_armed}. "
            f"A drill that left the node's rejoin watchdog disarmed is worse than "
            f"one that failed: {commands}"
        )
        assert (scratch.state_dir / timer).read_text(encoding="utf-8") == "running", (
            f"`{timer}` must be left ARMED, not merely asked to start; it was "
            f"left `{(scratch.state_dir / timer).read_text(encoding='utf-8')}`"
        )
        assert timer in output, (
            f"the run must name `{timer}` — an operator cannot confirm the node's "
            f"timers were put back if the play never says which it took "
            f"down:\n{output}"
        )
    for timer in _UNPAUSED_TIMERS:
        assert _first_index(commands=commands, needle=f"systemctl stop {timer}") == -1, (
            f"`{timer}` must not be stopped by the drill: its unit does not pull "
            f"`{_AGENT_UNIT}` in, or it was already inactive. A drill that "
            f"disarms a node's whole timer set is doing something else: {commands}"
        )
        assert _first_index(commands=commands, needle=f"systemctl start {timer}") == -1, (
            f"`{timer}` must not be started by the drill — the restore re-arms "
            f"what the drill paused and nothing else: {commands}"
        )


def test_the_drill_re_arms_the_paused_timers_when_a_step_after_the_stop_fails(
    *, scratch: _Scratch
) -> None:
    """The re-arm on the failure path, driven by the very failure that was observed.

    The first real run of this drill failed at "Wait until the API first reports
    the node NotReady", because the node's own watchdog had already put the agent
    back. That is the shape the re-arm has to survive: a step AFTER the agent stop
    fails, and the play must still end with the node's timers armed — a failed
    drill that leaves the rejoin watchdog disarmed is worse than no drill, because
    the next real agent stall then has nothing to recover it.

    `NODE_LOSS_DRILL_READY_WHILE_STOPPED` reproduces it exactly: the stand-in
    `kubectl` answers `ready=True` even with the agent stopped, so the NotReady
    wait exhausts its bounded window and the play fails THERE, with the drill's
    own stop already issued. The run must fail, and the timers must still come
    back armed — which is what an `always:` path buys and a later task would not.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, ready_while_stopped=True)

    assert exit_code != 0, (
        f"a drill whose node never reads NotReady must FAIL — that observation is "
        f"the artifact the drill exists to produce:\n{output}"
    )
    statuses = _task_statuses(output=output, host=_AGENT)
    assert _status_of(statuses=statuses, task=_NOTREADY_WAIT_TASK) == "fatal"
    assert _status_of(statuses=statuses, task=_REARM_TASK) in {"ok", "changed"}, (
        f"the re-arm must run on a failed drill; it reported "
        f"{statuses.get(_REARM_TASK)}\n{output}"
    )
    commands = _commands(scratch=scratch)
    agent_start = _first_index(commands=commands, needle=f"systemctl start {_AGENT_UNIT}")
    assert agent_start >= 0, (
        f"a failed drill must still start `{_AGENT_UNIT}` again, or it has taken "
        f"a pool node out: {commands}"
    )
    assert scratch.agent_state.read_text(encoding="utf-8") == "running", (
        "the agent must be left running even when the drill fails; it was left "
        f"`{scratch.agent_state.read_text(encoding='utf-8')}`"
    )
    for timer in _PAUSED_TIMERS:
        paused = _first_index(commands=commands, needle=f"systemctl stop {timer}")
        re_armed = _last_index(commands=commands, needle=f"systemctl start {timer}")
        assert 0 <= paused < re_armed, (
            f"`{timer}` was paused at log position {paused} and re-armed at "
            f"{re_armed} on a run that failed after the agent stop; a failed "
            f"drill must never leave it disarmed: {commands}"
        )
        assert (scratch.state_dir / timer).read_text(encoding="utf-8") == "running", (
            f"`{timer}` must be left ARMED by a failed drill; it was left "
            f"`{(scratch.state_dir / timer).read_text(encoding='utf-8')}`"
        )
        assert timer in output, (
            f"a failed run must still name `{timer}` as paused and re-armed — it "
            f"is the run an operator most needs that from:\n{output}"
        )


@pytest.mark.parametrize(
    "axis",
    sorted(_DRIFTED_NODES),
    ids=sorted(_DRIFTED_NODES),
)
def test_the_drill_fails_when_the_restored_nodes_posture_differs_on_any_axis(
    *, scratch: _Scratch, axis: str
) -> None:
    """The verification half of the third Definition-of-Done assertion, one axis at a time.

    A drill that brought a node back MINUS its factory label, MINUS its
    churn-slot capacity, or carrying a taint it did not have before has not
    restored the node — it has quietly changed the pool. None of those three
    raises an error on its own: a selector that matches one node fewer simply
    schedules less, an admission budget short a slot simply admits less, and an
    extra taint simply repels. So the drill has to CONVICT each of them, and
    each is asserted alone rather than together, because a play that compared
    only two of the three would pass a fixture that moved all three.

    The restore itself succeeds in every case — the agent is started and the
    node reads Ready — so what fails here is the verification and nothing else.
    """
    scratch.node_after.write_text(_DRIFTED_NODES[axis], encoding="utf-8")

    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT)

    assert exit_code != 0, (
        f"a restore that brought the node back with its {axis} changed must FAIL "
        f"the play; nothing else would notice:\n{output}"
    )
    statuses = _task_statuses(output=output, host=_AGENT)
    assert _status_of(statuses=statuses, task=_VERIFY_TASK) == "fatal"
    assert _status_of(statuses=statuses, task=_START_TASK) in {"ok", "changed"}, (
        f"the node must still have been restored before the verification "
        f"failed — a drill that fails its check AND leaves the agent down has "
        f"taken a pool node out:\n{output}"
    )
    assert scratch.agent_state.read_text(encoding="utf-8") == "running", (
        "the agent must be left running even when the verification fails; it "
        f"was left `{scratch.agent_state.read_text(encoding='utf-8')}`"
    )
    notready_at = _NOTREADY_AT.search(output)
    ready_at = _READY_AT.search(output)
    assert notready_at is not None and ready_at is not None, (
        f"the drill must report its two UTC instants even on a run whose "
        f"verification fails — they are what an operator diagnoses from:\n{output}"
    )
