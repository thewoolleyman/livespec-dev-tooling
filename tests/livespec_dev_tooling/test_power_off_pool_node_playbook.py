"""`ansible/power-off-pool-node.yml` — the one committed way to power off a pool agent node.

WHY THE PLAYBOOK EXISTS. On 2026-11-20 the maintainer asked to power off the
pool agent gamingpc-xubuntu temporarily, to boot it into Windows, while it stays
commissioned. It was already cordoned and evacuated through
`ansible/k3s-window-drain.yml`. The Driver's `fleet_host_guard.py` refuses a hand
`ssh gamingpc-xubuntu sudo poweroff`, and the only committed power path,
`ansible/reboot-ci-server.yml`, reboots the pool's server alone.

WHAT THESE TESTS HOLD IT TO, each by RUNNING the committed playbook through the
`ansible-core` pin `just ansible-apply` executes, against a two-host local
inventory (one server, one agent) and a scratch PATH carrying stand-in `sudo`,
`kubectl` and `systemctl`. No cluster is reached and no host is powered off: the
stand-in `systemctl` only logs that it was asked.

1. A run without a confirmation naming the host reads nothing, changes nothing
   and exits 0, on an apply and under `--check`.
2. A confirmation that names the pool's server is refused with nothing read.
3. A node that is not cordoned, or carries a pod other than a DaemonSet's or a
   finished one, is refused naming each blocker, and nothing is powered off.
4. A failed kubectl read fails the run; it is never taken for an empty node.
5. Under `--check` an eligible node is reported and not powered off.
6. An eligible node is powered off, through `systemctl poweroff`.
7. A pod named in `pool_node_power_off_waive_pods` by its exact namespace/name is
   waived and reported; any other blocker still refuses, and a listed name that
   is not bound to the node is reported.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_PLAYBOOK = _REPO_ROOT / "ansible" / "power-off-pool-node.yml"

_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

_SERVER = "power-off-drill-server"
_AGENT = "power-off-drill-agent"

_UNCONFIRMED_NOTE_TASK = "Report a run that carries no power-off confirmation for this host"
_ROLE_REFUSAL_TASK = "Refuse a power-off of a host that is not one of the pool's agents"
_PRECHECK_TASK = "Read whether the node is cordoned and which pods hold it"
_PRECHECK_REFUSAL_TASK = "Refuse to power off a node that is not cordoned or still carries a pod"
_CHECK_NOTE_TASK = "Note that a check run withholds the power-off"
_POWER_OFF_TASK = "Power off the confirmed node and run nothing afterwards"

_DAEMONSET_POD = "kube-system/svclb-traefik-abcde Running DaemonSet"
_FINISHED_POD = "gates/gate-job-old-xyz Succeeded Job"
_FAILED_POD = "gates/gate-job-older-xyz Failed Job"
_RUNNER_POD = "arc-runners/livespec-dev-tooling-k3s-vwxyz-runner-9bqdn Running EphemeralRunner"
_GATE_POD = "gates/gate-job-live-abc Running Job"
_FACTORY_POD = "factory/sandbox-run-123 Running"

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

# The stand-in `kubectl` answers from two state files the test writes, logs every
# invocation first, and exits non-zero on anything it was not written to answer
# or when the test marks reads as failing.
_KUBECTL_STAND_IN = """#!/bin/sh
printf '%s\\n' "$*" >> "${STAND_IN_DIR}/kubectl-argv.log"
if [ -e "${STAND_IN_DIR}/kubectl-fails" ]; then
  echo 'stand-in kubectl: the server is unreachable' >&2
  exit 1
fi
case "$*" in
  'get node '*'jsonpath={.spec.unschedulable}')
    cat "${STAND_IN_DIR}/unschedulable"
    exit 0 ;;
  'get pods --all-namespaces --field-selector spec.nodeName='*)
    cat "${STAND_IN_DIR}/pods"
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""

_SYSTEMCTL_STAND_IN = """#!/bin/sh
printf '%s\\n' "$*" >> "${STAND_IN_DIR}/systemctl-argv.log"
"""

_PLAYBOOK_TIMEOUT_SECONDS = 600
_POWER_OFF_WAIT_SECONDS = 30

_TASK_HEADER = re.compile(r"^TASK \[(?P<name>.+?)\] \**$")
_HOST_STATUS = re.compile(r"^(?P<status>ok|changed|skipping|failed|fatal|unreachable): \[")


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    """One test's isolated world: stand-in binaries and the cluster state they answer with."""

    root: Path
    bin_dir: Path


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


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("sudo", _SUDO_STAND_IN),
        ("kubectl", _KUBECTL_STAND_IN),
        ("systemctl", _SYSTEMCTL_STAND_IN),
    ):
        stand_in = bin_dir / name
        _ = stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    return _Scratch(root=tmp_path, bin_dir=bin_dir)


def _set_cluster(*, scratch: _Scratch, unschedulable: str, pods: list[str]) -> None:
    _ = (scratch.root / "unschedulable").write_text(unschedulable, encoding="utf-8")
    _ = (scratch.root / "pods").write_text("".join(f"{pod}\n" for pod in pods), encoding="utf-8")


def _write_inventory(*, scratch: _Scratch) -> Path:
    inventory = scratch.root / "inventory.yml"
    lines = [
        "all:",
        "  children:",
        "    ci_pool:",
        "      hosts:",
        f"        {_SERVER}:",
        "          ansible_connection: local",
        "          cluster_role: server",
        f"        {_AGENT}:",
        "          ansible_connection: local",
        "          cluster_role: agent",
    ]
    _ = inventory.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return inventory


def _playbook_environment(*, scratch: _Scratch) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "STAND_IN_DIR": str(scratch.root),
            "ANSIBLE_DISPLAY_SKIPPED_HOSTS": "True",
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
            "ANSIBLE_LOCAL_TEMP": str(scratch.root / "ansible-local"),
            "ANSIBLE_ASYNC_DIR": str(scratch.root / "ansible-async"),
        }
    )
    return env


def _run_playbook(
    *,
    scratch: _Scratch,
    confirm: str | None,
    check_mode: bool,
    waive: str | None = None,
) -> tuple[int, str]:
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} must exist"
    argv = [
        "uvx",
        "--from",
        _ansible_core_pin(),
        "ansible-playbook",
        "-i",
        str(_write_inventory(scratch=scratch)),
        "-e",
        "pool_node_power_off_delay_seconds=0",
        *(["-e", f"pool_node_power_off_confirm={confirm}"] if confirm is not None else []),
        *(["-e", waive] if waive is not None else []),
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


def _task_statuses(*, output: str, host: str) -> dict[str, str]:
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
    assert statuses, f"no per-task status for {host} was parsed out of the run:\n{output}"
    return statuses


def _recap_changed(*, output: str, host: str) -> int:
    recap = re.search(
        rf"^{re.escape(host)}\s+: .*?\bchanged=(?P<changed>\d+)\b", output, re.MULTILINE
    )
    assert recap is not None, f"the run carried no PLAY RECAP for {host}:\n{output}"
    return int(recap["changed"])


def _log(*, scratch: _Scratch, name: str) -> list[str]:
    log = scratch.root / f"{name}-argv.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _assert_not_powered_off(*, scratch: _Scratch, output: str) -> None:
    # The async job is launched with a zero delay in these tests, so a power-off
    # that had been launched would reach the stand-in within this wait.
    time.sleep(2)
    assert (
        _log(scratch=scratch, name="systemctl") == []
    ), f"systemctl was asked to act on a run that must not power anything off:\n{output}"


@pytest.mark.parametrize("check_mode", [False, True], ids=["apply", "check"])
@pytest.mark.parametrize("confirm", [None, "some-other-host"], ids=["absent", "wrong-value"])
def test_an_unconfirmed_run_reads_nothing_and_changes_nothing(
    *, scratch: _Scratch, confirm: str | None, check_mode: bool
) -> None:
    _set_cluster(scratch=scratch, unschedulable="true", pods=[])
    exit_code, output = _run_playbook(scratch=scratch, confirm=confirm, check_mode=check_mode)

    assert exit_code == 0, output
    for host in (_SERVER, _AGENT):
        statuses = _task_statuses(output=output, host=host)
        assert statuses[_UNCONFIRMED_NOTE_TASK] == "ok"
        assert statuses[_PRECHECK_TASK] == "skipping"
        assert statuses[_POWER_OFF_TASK] == "skipping"
        assert _recap_changed(output=output, host=host) == 0
    assert _log(scratch=scratch, name="kubectl") == [], output
    _assert_not_powered_off(scratch=scratch, output=output)


def test_a_confirmation_naming_the_server_is_refused_with_nothing_read(
    *, scratch: _Scratch
) -> None:
    _set_cluster(scratch=scratch, unschedulable="true", pods=[])
    exit_code, output = _run_playbook(scratch=scratch, confirm=_SERVER, check_mode=False)

    assert exit_code != 0, output
    assert _task_statuses(output=output, host=_SERVER)[_ROLE_REFUSAL_TASK] == "fatal"
    assert "reboot-ci-server.yml" in output
    assert _log(scratch=scratch, name="kubectl") == [], output
    _assert_not_powered_off(scratch=scratch, output=output)


@pytest.mark.parametrize("check_mode", [False, True], ids=["apply", "check"])
def test_a_node_that_is_not_cordoned_is_refused(*, scratch: _Scratch, check_mode: bool) -> None:
    _set_cluster(scratch=scratch, unschedulable="", pods=[_DAEMONSET_POD])
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, check_mode=check_mode)

    assert exit_code != 0, output
    statuses = _task_statuses(output=output, host=_AGENT)
    assert statuses[_PRECHECK_REFUSAL_TASK] == "fatal"
    assert _POWER_OFF_TASK not in statuses
    assert f"node {_AGENT} is not cordoned" in output
    _assert_not_powered_off(scratch=scratch, output=output)


@pytest.mark.parametrize("check_mode", [False, True], ids=["apply", "check"])
def test_a_node_carrying_a_live_pod_is_refused_naming_each_blocker(
    *, scratch: _Scratch, check_mode: bool
) -> None:
    _set_cluster(
        scratch=scratch,
        unschedulable="true",
        pods=[_DAEMONSET_POD, _FINISHED_POD, _FAILED_POD, _RUNNER_POD, _GATE_POD, _FACTORY_POD],
    )
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, check_mode=check_mode)

    assert exit_code != 0, output
    statuses = _task_statuses(output=output, host=_AGENT)
    assert statuses[_PRECHECK_REFUSAL_TASK] == "fatal"
    assert _POWER_OFF_TASK not in statuses
    for blocker in (_RUNNER_POD, _GATE_POD, _FACTORY_POD):
        assert f"pod {blocker.split()[0]} is bound" in output, output
    for exempt in (_DAEMONSET_POD, _FINISHED_POD, _FAILED_POD):
        assert f"pod {exempt.split()[0]} is bound" not in output, output
    for invocation in _log(scratch=scratch, name="kubectl"):
        assert invocation.split()[0] == "get", invocation
    _assert_not_powered_off(scratch=scratch, output=output)


def test_a_failed_read_fails_the_run_rather_than_reading_as_an_empty_node(
    *, scratch: _Scratch
) -> None:
    _set_cluster(scratch=scratch, unschedulable="true", pods=[])
    _ = (scratch.root / "kubectl-fails").write_text("", encoding="utf-8")
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, check_mode=False)

    assert exit_code != 0, output
    statuses = _task_statuses(output=output, host=_AGENT)
    assert statuses[_PRECHECK_TASK] == "fatal"
    assert _POWER_OFF_TASK not in statuses
    _assert_not_powered_off(scratch=scratch, output=output)


def test_a_check_run_reports_an_eligible_node_and_powers_nothing_off(*, scratch: _Scratch) -> None:
    _set_cluster(scratch=scratch, unschedulable="true", pods=[_DAEMONSET_POD, _FINISHED_POD])
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, check_mode=True)

    assert exit_code == 0, output
    statuses = _task_statuses(output=output, host=_AGENT)
    assert statuses[_PRECHECK_REFUSAL_TASK] == "skipping"
    assert statuses[_CHECK_NOTE_TASK] == "ok"
    assert statuses[_POWER_OFF_TASK] == "skipping"
    assert "the power-off would go through" in output
    _assert_not_powered_off(scratch=scratch, output=output)


def test_an_eligible_node_is_powered_off(*, scratch: _Scratch) -> None:
    _set_cluster(scratch=scratch, unschedulable="true", pods=[_DAEMONSET_POD, _FINISHED_POD])
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, check_mode=False)

    assert exit_code == 0, output
    assert _task_statuses(output=output, host=_AGENT)[_POWER_OFF_TASK] == "changed"
    deadline = time.monotonic() + _POWER_OFF_WAIT_SECONDS
    while not _log(scratch=scratch, name="systemctl") and time.monotonic() < deadline:
        time.sleep(0.5)
    assert _log(scratch=scratch, name="systemctl") == ["poweroff"], output


_LEFTOVER_SANDBOX = "factory/petri-leftover-l0 Running"


@pytest.mark.parametrize(
    "waive",
    [
        '{"pool_node_power_off_waive_pods": ["factory/petri-leftover-l0", "factory/not-on-node"]}',
        "pool_node_power_off_waive_pods=factory/petri-leftover-l0",
    ],
    ids=["list", "bare-string"],
)
def test_an_operator_named_pod_is_waived_and_reported(*, scratch: _Scratch, waive: str) -> None:
    _set_cluster(scratch=scratch, unschedulable="true", pods=[_DAEMONSET_POD, _LEFTOVER_SANDBOX])
    exit_code, output = _run_playbook(scratch=scratch, confirm=_AGENT, check_mode=True, waive=waive)

    assert exit_code == 0, output
    statuses = _task_statuses(output=output, host=_AGENT)
    assert statuses[_PRECHECK_REFUSAL_TASK] == "skipping"
    assert statuses[_CHECK_NOTE_TASK] == "ok"
    assert "waived (operator-named): pod factory/petri-leftover-l0 is bound" in output, output
    if "not-on-node" in waive:
        assert "waiver not used: factory/not-on-node is not bound" in output, output
    _assert_not_powered_off(scratch=scratch, output=output)


def test_a_waiver_covers_only_the_exact_pods_it_names(*, scratch: _Scratch) -> None:
    _set_cluster(
        scratch=scratch,
        unschedulable="true",
        pods=[_LEFTOVER_SANDBOX, _GATE_POD],
    )
    exit_code, output = _run_playbook(
        scratch=scratch,
        confirm=_AGENT,
        check_mode=False,
        waive='{"pool_node_power_off_waive_pods": ["factory/petri-leftover", "gates/gate-job-live-abc"]}',
    )

    assert exit_code != 0, output
    statuses = _task_statuses(output=output, host=_AGENT)
    assert statuses[_PRECHECK_REFUSAL_TASK] == "fatal"
    assert _POWER_OFF_TASK not in statuses
    assert "blocker: pod factory/petri-leftover-l0 is bound" in output, output
    assert "waived (operator-named): pod gates/gate-job-live-abc is bound" in output, output
    _assert_not_powered_off(scratch=scratch, output=output)
