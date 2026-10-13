"""`ansible/reboot-ci-server.yml` — the one committed way to reboot the k3s CI server.

WHY THE PLAYBOOK EXISTS. The livespec plan `livespec-sab5gn` proves its recovery
assertions by an unattended reboot of the k3s server, and its replays need
further reboots (maintainer approval 2026-10-12). The Driver's
`fleet_host_guard.py` correctly refuses `ssh poweredge-xubuntu 'sudo -n
systemctl reboot'` as a hand change to a fleet host — an independent verifier
session was blocked at exactly that step on 2026-10-12T23:11Z — and the guard's
own direction is that a need the committed automation cannot meet is a gap in
the playbooks to fix. There was no committed way to reboot a CI-pool node, so an
approved drill could only be done by hand (`livespec-dev-tooling-a3uvyu`).

WHAT THESE TESTS HOLD IT TO. A playbook that reboots the pool's control plane is
the single most destructive artifact in this tree: it takes every runner the
fleet's gating CI has with it. So the two properties asserted here are both
REFUSALS, and each is asserted by RUNNING the committed playbook rather than by
reading it — a reading would assert a model of ansible's `when`, `until` and
check-mode semantics, and it is exactly those semantics that decide whether a
host reboots:

1. A run that IS confirmed but finds the runner pool busy fails, with a message
   naming the busy pool, and never reaches the reboot task.
2. A run that carries no confirmation — or a confirmation that is not this
   host's inventory name — ends before any idle check and reports zero changes,
   on an apply and under `--check` alike. This is what keeps the playbook out of
   a fleet-wide apply or a drift sweep's side effects: the fence is the
   confirmation variable, not omission from a list.

HOW THEY RUN IT. By the same `ansible-core` pin `just ansible-apply` executes
(read out of the justfile rather than restated, so the two cannot drift),
against a one-host local inventory and a scratch PATH carrying stand-in
`kubectl` and `sudo`. No cluster is reached and no host is mutated: the
stand-in `kubectl` answers the pool read with a Running runner pod — the busy
state the refusal exists for — and logs every invocation it receives, which is
how each test below proves what the play asked the cluster.

A LOCAL CONNECTION IS ALSO THE SECOND BELT. `ansible.builtin.reboot` refuses a
local connection before it does anything else, with `Running
ansible.builtin.reboot with local connection would reboot the control node.`
That string is this suite's mechanical evidence that the reboot action never
ran: if a future edit let either case reach the reboot task, the message would
appear in the output and these tests would fail on it, rather than the suite
rebooting whatever host ran pytest.

Work-item: livespec-dev-tooling-a3uvyu. Plan: livespec `k3s-on-gmktec-for-vps-usage`
(epic livespec-sab5gn).
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
_PLAYBOOK = _REPO_ROOT / "ansible" / "reboot-ci-server.yml"

# The `ansible-apply` recipe's own tool pin, so these tests exercise the
# interpreter the sanctioned invocation exercises. Restating the version here
# would let the recipe move to an ansible whose `when` / `until` / check-mode
# semantics nothing had tested.
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

# The runner pool's namespace — the pool the refusal has to name, and the only
# namespace the playbook reads.
_RUNNER_NAMESPACE = "arc-runners"

# The busy state, as the diverged-from-idle pool presents it: one Running runner
# pod beside one that has already completed. The completed one is not decoration
# — it is the half of the read that must NOT be counted as busy, so a pool whose
# only pods are finished runners still reads idle.
_BUSY_POD = "livespec-dev-tooling-k3s-vwxyz-runner-9bqdn"
_COMPLETED_POD = "livespec-dev-tooling-k3s-vwxyz-runner-2fkpt"

# The playbook's OWN task names, which are the vocabulary a run is read in: an
# operator scanning the output matches these strings, so a test that asserts a
# status against them is asserting what the operator sees.
_UNCONFIRMED_NOTE_TASK = "Report a run that carries no reboot confirmation for this host"
_IDLE_WAIT_TASK = "Wait for two consecutive idle reads of the runner pool"
_REFUSAL_TASK = "Refuse to reboot a host whose runner pool never went idle"
_REBOOT_TASK = "Reboot the confirmed host and run nothing afterwards"

# `ansible.builtin.reboot`'s own refusal of a local connection, verbatim. Its
# ABSENCE from a run's output is what proves the reboot action was never
# entered; its presence would mean a case below reached the reboot task.
_LOCAL_CONNECTION_REFUSAL = "with local connection would reboot the control node"

# The host these tests reboot nothing on. Named for the drill rather than for a
# real pool node so no output of this suite can be mistaken for a record of
# poweredge-xubuntu having been touched.
_HOST = "reboot-drill-server"

# The fixture's wait window: no sleep between the pair of reads, and ONE retry
# (ansible's `retries` is additional attempts, so this is two attempts). Two
# attempts rather than one on purpose — it exercises the retry loop, which is
# the half of the bounded wait that decides whether a pool that stays busy ends
# in a refusal or in a reboot.
_TEST_IDLE_INTERVAL = 0
_TEST_IDLE_RETRIES = 1

# Two reads per attempt, two attempts: the four cluster reads a busy run makes.
# Exact rather than a lower bound, because "two consecutive reads" IS the
# idleness claim — a run that read the pool once and rebooted would satisfy a
# `>= 2` and defeat the whole gate.
_EXPECTED_BUSY_READS = 4

# A stand-in `sudo` that drops its option flags and its `-u <user>` and execs
# the rest. The pool read carries `become: true` because the admin kubeconfig it
# reads is root-owned on a real node; this suite runs as whoever invoked pytest,
# with no sudo guaranteed on the image. So become is SATISFIED rather than
# switched off, which keeps the executed task shape the same as the operator's.
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

# The stand-in `kubectl`, answering as a busy pool does. It logs every
# invocation FIRST, so a test can prove what the run asked for, and it exits
# non-zero on anything it was not written to answer rather than returning a
# plausible empty string — an unexpected invocation must break a test, not
# quietly read as an idle pool and let a reboot through.
_KUBECTL_STAND_IN = f"""#!/bin/sh
printf '%s\\n' "$*" >> "${{KUBECTL_ARGV_LOG}}"
case "$*" in
  *'get pods'*'{_RUNNER_NAMESPACE}'*)
    printf '{_BUSY_POD}=Running\\n{_COMPLETED_POD}=Succeeded\\n'
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""

# Generous: a cold `uvx` resolves and caches ansible-core before the first play
# runs. Bounded all the same, so a hung play fails this test rather than the
# suite's whole budget.
_PLAYBOOK_TIMEOUT_SECONDS = 600

_TASK_HEADER = re.compile(r"^TASK \[(?P<name>.+?)\] \**$")
_HOST_STATUS = re.compile(r"^(?P<status>ok|changed|skipping|failed|fatal|unreachable): \[")


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    """One test's isolated world: its stand-in binaries, its kubectl log, its inventory."""

    root: Path
    bin_dir: Path
    kubectl_log: Path


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
    """A scratch root with the stand-in `kubectl` and `sudo` on a private bin dir."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("sudo", _SUDO_STAND_IN), ("kubectl", _KUBECTL_STAND_IN)):
        stand_in = bin_dir / name
        stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    return _Scratch(root=tmp_path, bin_dir=bin_dir, kubectl_log=tmp_path / "kubectl-argv.log")


def _write_inventory(*, scratch: _Scratch) -> Path:
    """A one-host `ci_pool` inventory, local-connected and declared as the server.

    The group and the `cluster_role` are the two inventory facts the playbook
    selects on, so they ride as INVENTORY vars — the precedence an operator's
    own inventory uses. Everything the fixture needs to BOUND (the read interval,
    the retry count, the confirmation) rides as `--extra-vars` instead, because
    the playbook declares those as play vars and play vars beat inventory.
    """
    inventory = scratch.root / "inventory.yml"
    inventory.write_text(
        "all:\n"
        "  children:\n"
        "    ci_pool:\n"
        "      hosts:\n"
        f"        {_HOST}:\n"
        "          ansible_connection: local\n"
        "          cluster_role: server\n",
        encoding="utf-8",
    )
    return inventory


def _playbook_environment(*, scratch: _Scratch) -> dict[str, str]:
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
            "KUBECTL_ARGV_LOG": str(scratch.kubectl_log),
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


def _run_playbook(*, scratch: _Scratch, confirm: str | None, check_mode: bool) -> tuple[int, str]:
    """Run the committed playbook; return its exit code and its callback output."""
    assert _PLAYBOOK.is_file(), (
        f"{_PLAYBOOK} must exist — it is the only committed way to reboot the "
        f"k3s CI server, and without it an approved reboot drill can only be "
        f"done by hand against the Driver's fleet-host guard"
    )
    inventory = _write_inventory(scratch=scratch)
    argv = [
        "uvx",
        "--from",
        _ansible_core_pin(),
        "ansible-playbook",
        "-i",
        str(inventory),
        "-e",
        f"ci_server_reboot_idle_interval={_TEST_IDLE_INTERVAL}",
        "-e",
        f"ci_server_reboot_idle_retries={_TEST_IDLE_RETRIES}",
        *(["-e", f"ci_server_reboot_confirm={confirm}"] if confirm is not None else []),
        *(["--check"] if check_mode else []),
        str(_PLAYBOOK),
    ]
    completed = subprocess.run(
        argv,
        cwd=scratch.root,
        env=_playbook_environment(scratch=scratch),
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _task_statuses(*, output: str) -> dict[str, str]:
    """Each task's reported status for the drill host, keyed on the task name."""
    statuses: dict[str, str] = {}
    task = ""
    for line in output.splitlines():
        header = _TASK_HEADER.match(line)
        if header is not None:
            task = header["name"]
            continue
        status = _HOST_STATUS.match(line)
        if status is not None and f"[{_HOST}" in line and task not in statuses:
            statuses[task] = status["status"]
    assert statuses, (
        f"no per-task status for {_HOST} was parsed out of the run; this reader "
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


def _recap_changed(*, output: str) -> int:
    """The host's `changed=` count in the PLAY RECAP — the line an operator reads."""
    recap = re.search(
        rf"^{re.escape(_HOST)}\s+: .*?\bchanged=(?P<changed>\d+)\b", output, re.MULTILINE
    )
    assert recap is not None, f"the run carried no PLAY RECAP for {_HOST}:\n{output}"
    return int(recap["changed"])


def _kubectl_invocations(*, scratch: _Scratch) -> list[str]:
    """Every argv the stand-in `kubectl` was called with, in order."""
    log = scratch.kubectl_log
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _assert_no_reboot_action_entered(*, output: str) -> None:
    """`ansible.builtin.reboot` was never entered, by its own local-connection refusal."""
    assert _LOCAL_CONNECTION_REFUSAL not in output, (
        f"the reboot action RAN: ansible refused it only because this test's "
        f"connection is local. A run that must not reboot has to stop before "
        f"the reboot task, not be caught by it:\n{output}"
    )


def test_a_confirmed_run_refuses_to_reboot_a_host_whose_runner_pool_is_busy(
    *, scratch: _Scratch
) -> None:
    """The first Definition-of-Done assertion, run rather than modelled.

    The run carries this host's own inventory name as its confirmation, so the
    idle gate is reached; the stand-in `kubectl` answers with a Running runner
    pod, so the gate never opens. The play must FAIL, naming the pool it refused
    for, and must never reach the reboot task — a reboot that took the fleet's
    gating runners down mid-job is the harm this gate exists for, and it is not
    undoable by a later task.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=_HOST, check_mode=False)

    assert exit_code != 0, (
        f"a confirmed run against a BUSY pool must fail — an operator who reads "
        f"a zero exit concludes the drill is under way:\n{output}"
    )
    assert _status_of(statuses=_task_statuses(output=output), task=_REFUSAL_TASK) == "fatal"
    assert _REBOOT_TASK not in _task_statuses(
        output=output
    ), f"the reboot task was reached on a busy pool; it must never be:\n{output}"
    _assert_no_reboot_action_entered(output=output)
    # The refusal has to be READABLE as a busy pool: the namespace that was
    # busy, and the runner pod that made it busy.
    assert _RUNNER_NAMESPACE in output and _BUSY_POD in output, (
        f"the refusal must name the busy runner pool and the pod that made it "
        f"busy, so an operator knows what to wait for:\n{output}"
    )
    invocations = _kubectl_invocations(scratch=scratch)
    assert len(invocations) == _EXPECTED_BUSY_READS, (
        f"a busy run must read the pool twice per attempt over two attempts; it "
        f"read it {len(invocations)} times: {invocations}"
    )
    for invocation in invocations:
        assert invocation.split()[:2] == ["get", "pods"], (
            f"the idle gate must only ASK the cluster about pods; it issued "
            f"`kubectl {invocation}`"
        )


@pytest.mark.parametrize("check_mode", [False, True], ids=["apply", "check"])
@pytest.mark.parametrize("confirm", [None, "some-other-host"], ids=["absent", "wrong-value"])
def test_an_unconfirmed_run_ends_before_the_idle_check_and_changes_nothing(
    *, scratch: _Scratch, confirm: str | None, check_mode: bool
) -> None:
    """The second Definition-of-Done assertion, over both ways to be unconfirmed.

    This is what keeps a reboot playbook safe to leave in the tree: a bare
    apply, a drift sweep, or a typo'd confirmation reaches NOTHING. Asserted on
    four axes, because any one of them passing alone would still leave a way to
    reboot a host by accident — the play reports zero changes, the idle gate and
    the reboot task both report `skipping` rather than running, the cluster is
    not even asked whether the pool is idle, and the reboot action is never
    entered. `--check` is asserted beside the apply because a drift sweep runs
    in check mode, and check mode is NOT what makes this safe: the confirmation
    gate is.
    """
    exit_code, output = _run_playbook(scratch=scratch, confirm=confirm, check_mode=check_mode)

    assert exit_code == 0, (
        f"an unconfirmed run must END, not fail — a refusal that errors would "
        f"redden every sweep that includes this playbook:\n{output}"
    )
    statuses = _task_statuses(output=output)
    assert _status_of(statuses=statuses, task=_UNCONFIRMED_NOTE_TASK) == "ok"
    assert _status_of(statuses=statuses, task=_IDLE_WAIT_TASK) == "skipping"
    assert _status_of(statuses=statuses, task=_REBOOT_TASK) == "skipping"
    assert (
        _recap_changed(output=output) == 0
    ), f"an unconfirmed run must report zero changes:\n{output}"
    assert _kubectl_invocations(scratch=scratch) == [], (
        f"an unconfirmed run must end BEFORE any idle check; it asked the "
        f"cluster: {_kubectl_invocations(scratch=scratch)}"
    )
    _assert_no_reboot_action_entered(output=output)
