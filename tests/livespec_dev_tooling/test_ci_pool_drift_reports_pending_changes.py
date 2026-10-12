"""`just ansible-drift ansible/ci-pool.yml` must REPORT the pool's real drift, not hide it.

`SPECIFICATION/non-functional-requirements.md`, where this repository's
runner-pool node rebuild recipe is stated, requires that "the drift report
`just ansible-drift ansible/ci-pool.yml` MUST be run and read before that
apply". A report that reads clean over a diverged node satisfies the letter of
that step and defeats its purpose: the operator reads `changed=0`, concludes the
pool is converged, and applies blind.

That is what it did. Measured 2026-10-12 at 04:26Z with gmktec-xubuntu still
tainted `node-role/ci=pending` against an empty `NODE_TAINTS`, and its
node-status credential being refused by the API server, `just ansible-drift
ansible/ci-pool.yml` reported `changed=0` on both nodes. Every task that would
have made either change is an `ansible.builtin.command` or an
`ansible.builtin.shell` — modules ansible SKIPS under `--check`, because it
cannot know whether running them would mutate anything — so each one printed
`skipping` and contributed nothing to the count. The report was not wrong about
any single task; it was silent about the whole change.

THE FIX IS TO SEPARATE THE READ FROM THE WRITE, and these tests assert the read
half. A check-mode-safe probe (`check_mode: false`, so it runs during the drift
report, and `changed_when` computed from the live state against the declared
state) reports the pending change; the mutating command still runs only on an
apply. Both halves are asserted in each test below: the probe reports the host
as CHANGED, and the mutating task it predicts is still SKIPPED — a drift report
that mutated the cluster to find out what it would change would be a far worse
defect than the silence it replaces.

WHY THE ROLES ARE RUN RATHER THAN READ. The sibling
`test_node_status_credential_host_key_trust` reads its role's committed tasks,
because its claims are claims about SHAPE — whose `known_hosts`, under which
name. The claim here is about ansible's own `--check` semantics: which tasks
execute, which skip, and what the host's changed count ends up being. No reading
of a task file establishes that, and a reader that tried would be asserting a
model of check mode rather than check mode itself. So the roles are executed, by
the SAME `ansible-core` pin `just ansible-drift` executes (read out of the
justfile rather than restated, so the two cannot drift), with `--check --diff`,
against a one-host local inventory and a scratch PATH carrying stand-in
`kubectl` and `sudo`. No cluster is reached, no host is mutated, and every path
the roles touch is under `tmp_path`.

THE LIVE STATE IS THE ONE THE BUG WAS MEASURED IN. The stand-in `kubectl`
answers the taint read with a `node-role/ci` key the fixture's profile does not
declare, and answers the node-status probe with the API server's own refusal
wording — gmktec-xubuntu's state at 04:26Z, reproduced. It also appends every
invocation it receives to a log, which is how each test proves the drift report
asked the cluster nothing but questions.

Work-item: livespec-dev-tooling-ewjby3. Plan: livespec `k3s-on-gmktec-for-vps-usage`
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
_ROLES_PATH = _REPO_ROOT / "ansible" / "roles"

# The `ansible-drift` recipe's own tool pin, so these tests exercise the
# interpreter the drift report exercises. Restating the version here would let
# the recipe move to an ansible whose check-mode semantics nothing had tested.
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

# A kubectl invocation that WRITES. The drift report must issue none of them:
# its whole contract is that it reports what an apply would change and changes
# nothing, and a probe that reached for the live state by mutating it would be a
# worse defect than the silence it replaces.
_MUTATING_KUBECTL_VERBS = ("taint", "apply", "patch", "delete", "create")

# The one taint the pool manages. An EMPTY `NODE_TAINTS` is R5's open state, and
# gmktec-xubuntu's committed state, so a node still carrying the key is the
# removal the report has to surface.
_TAINT_KEY = "node-role/ci"

# The API server's refusal, verbatim as kubectl renders it. This is the answer a
# poweredge-xubuntu reboot produces for every agent: its k3s datastore is a
# tmpfs and is empty at boot, so every ServiceAccount token is re-minted and a
# previously-delivered kubeconfig carries one the fresh API server has never
# seen.
_CREDENTIAL_REFUSAL = (
    "error: You must be logged in to the server "
    "(the server has asked for the client to provide credentials)"
)

# The roles' OWN task names, which are the vocabulary a drift report is read in:
# an operator scanning the output matches these strings, so a test that asserts
# a status against them is asserting what the operator sees.
_TAINT_PROBE_TASK = "Probe the live node-role/ci taint against the profile"
_TAINT_REMOVAL_TASK = "Remove the node-role/ci taint the profile no longer declares"
_CREDENTIAL_PROBE_TASK = (
    "Probe whether the API server still accepts the delivered node-status credential"
)
_CREDENTIAL_RENDER_TASK = "Render the node-status kubeconfig"
_CREDENTIAL_DELIVERY_TASK = "Deliver the node-status kubeconfig to the agent"

# A stand-in ed25519 host public key. The `node_status_credential` role refuses a
# host key that does not read back as one, so the fixture has to offer something
# shaped like one; these bytes authenticate nothing and reach no `known_hosts`
# outside `tmp_path`.
_HOST_KEY_LINE = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIStandInHostKeyForThisTestOnly root@stand-in\n"
)

# Set in the stand-in kubectl's environment to make the node-status probe
# SUCCEED — the converged agent, whose credential the API server accepts.
_CREDENTIAL_ACCEPTED_ENV = "KUBECTL_CREDENTIAL_ACCEPTED"

# A stand-in `sudo` that drops its option flags and its `-u <user>` and execs the
# rest. The roles' reads carry `become: true` because the files they read are
# root-owned on a real node; this suite runs as whoever invoked pytest, with no
# sudo guaranteed on the image, and the read targets are all under `tmp_path`.
# So become is SATISFIED rather than switched off, which keeps the executed task
# shape the same as the converge's.
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

# The stand-in `kubectl`, answering as the diverged node did. It logs every
# invocation FIRST, so a test can prove what the report asked for, and it exits
# non-zero on anything it was not written to answer rather than returning a
# plausible empty string — an unexpected invocation must break a test, not
# quietly satisfy a guard.
_KUBECTL_STAND_IN = f"""#!/bin/sh
printf '%s\\n' "$*" >> "${{KUBECTL_ARGV_LOG}}"
case "$*" in
  *'jsonpath={{.spec.taints[*].key}}'*)
    printf '{_TAINT_KEY}'
    exit 0 ;;
  *'get --subresource=status node'*)
    if [ -n "${{{_CREDENTIAL_ACCEPTED_ENV}:-}}" ]; then
      printf 'NAME STATUS\\nstand-in Ready\\n'
      exit 0
    fi
    printf '%s\\n' '{_CREDENTIAL_REFUSAL}' >&2
    exit 1 ;;
  *'jsonpath={{.data.token}}'*)
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""

# Generous: a cold `uvx` resolves and caches ansible-core before the first play
# runs. Bounded all the same, so a hung play fails this test rather than the
# suite's whole budget.
_DRIFT_TIMEOUT_SECONDS = 600

_TASK_HEADER = re.compile(r"^TASK \[(?P<name>.+?)\] \**$")
_HOST_STATUS = re.compile(r"^(?P<status>ok|changed|skipping|failed|fatal|unreachable): \[")


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    """One test's isolated world: its stand-in binaries, its kubectl log, its play."""

    root: Path
    bin_dir: Path
    kubectl_log: Path


def _ansible_core_pin() -> str:
    """The `ansible-core==<version>` pin the `ansible-drift` recipe resolves."""
    recipe = re.search(
        r"^ansible-drift \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, (
        f"{_JUSTFILE} must carry an `ansible-drift *args:` recipe — it is the "
        f"drift report these tests hold to its contract, and a test that cannot "
        f"find it is testing some other ansible"
    )
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, (
        "the `ansible-drift` recipe must pin ansible-core exactly, so the "
        "check-mode behaviour these tests assert is the behaviour the operator "
        "gets"
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


def _write_play(*, scratch: _Scratch, role: str, host: str, host_vars: dict[str, str]) -> Path:
    """A one-host local inventory and a one-role play; returns the inventory path.

    The role overrides ride as INVENTORY HOST VARS rather than `--extra-vars`,
    because that is the precedence an operator's own inventory uses: host vars
    beat role defaults and nothing else in this play competes with them. An
    extra-var would also win, and would win over anything a role itself sets,
    which is a stronger instrument than a fixture needs.
    """
    declared = "".join(f"      {key}: {value}\n" for key, value in host_vars.items())
    inventory = scratch.root / "inventory.yml"
    inventory.write_text(
        f"all:\n  hosts:\n    {host}:\n      ansible_connection: local\n{declared}",
        encoding="utf-8",
    )
    play = scratch.root / "play.yml"
    play.write_text(
        f"- name: {role} drift report\n"
        f"  hosts: all\n"
        f"  gather_facts: false\n"
        f"  roles:\n"
        f"    - role: {role}\n",
        encoding="utf-8",
    )
    return inventory


def _drift_environment(*, scratch: _Scratch, credential_accepted: bool) -> dict[str, str]:
    """The child's environment, built rather than inherited wholesale.

    `COVERAGE_PROCESS_START` and `COV_CORE_*` are scrubbed so the ansible
    interpreter does not self-instrument and race the suite's own coverage data.
    The ansible settings the drift report relies on are passed as `ANSIBLE_*`
    rather than through a config file, because `ansible/ansible.cfg` is not on
    ansible's search path from the repository root either — which is where
    `just ansible-drift` runs from.
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
            "ANSIBLE_ROLES_PATH": str(_ROLES_PATH),
            # Skipped tasks are SHOWN, as `ansible/ansible.cfg` shows them: a
            # task that vanishes from the output cannot be read as "this was not
            # evaluated", and these tests assert on exactly those lines.
            "ANSIBLE_DISPLAY_SKIPPED_HOSTS": "True",
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
        }
    )
    if credential_accepted:
        env[_CREDENTIAL_ACCEPTED_ENV] = "1"
    return env


def _run_drift(
    *,
    scratch: _Scratch,
    role: str,
    host: str,
    host_vars: dict[str, str],
    credential_accepted: bool = False,
) -> str:
    """Run `--check --diff` over one role and return the callback output."""
    inventory = _write_play(scratch=scratch, role=role, host=host, host_vars=host_vars)
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "--check",
            "--diff",
            "-i",
            str(inventory),
            str(scratch.root / "play.yml"),
        ],
        cwd=scratch.root,
        env=_drift_environment(scratch=scratch, credential_accepted=credential_accepted),
        capture_output=True,
        text=True,
        timeout=_DRIFT_TIMEOUT_SECONDS,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, (
        f"the drift report over `{role}` must complete — a report that aborts "
        f"tells an operator nothing about the rest of the play:\n{output}"
    )
    return output


def _task_statuses(*, output: str, host: str) -> dict[str, str]:
    """Each task's reported status for `host`, keyed on the task name after its role."""
    statuses: dict[str, str] = {}
    task = ""
    for line in output.splitlines():
        header = _TASK_HEADER.match(line)
        if header is not None:
            task = header["name"].split(" : ", 1)[-1]
            continue
        status = _HOST_STATUS.match(line)
        if status is not None and f"[{host}" in line and task not in statuses:
            statuses[task] = status["status"]
    assert statuses, (
        f"no per-task status for {host} was parsed out of the drift report; this "
        f"reader cannot assert anything about a report it cannot read:\n{output}"
    )
    return statuses


def _status_of(*, statuses: dict[str, str], task: str) -> str:
    """One task's reported status, refusing a task the report never carried.

    Asked through a helper rather than by subscript so the absence of the task
    is an ASSERTION about the report — "nothing in this play reports that
    change" — rather than a `KeyError` whose message names only the key.
    """
    assert task in statuses, (
        f"the drift report carried no task named `{task}`, so nothing in it "
        f"reports that pending change; it carried: {sorted(statuses)}"
    )
    return statuses[task]


def _recap_changed(*, output: str, host: str) -> int:
    """The host's `changed=` count in the PLAY RECAP — the line an operator reads."""
    recap = re.search(
        rf"^{re.escape(host)}\s+: .*?\bchanged=(?P<changed>\d+)\b", output, re.MULTILINE
    )
    assert recap is not None, f"the drift report carried no PLAY RECAP for {host}:\n{output}"
    return int(recap["changed"])


def _assert_only_read(*, scratch: _Scratch) -> None:
    """The report asked the cluster questions only — no kubectl write verb."""
    log = scratch.kubectl_log
    invocations = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    assert invocations, (
        "the drift report asked the cluster nothing at all, so it cannot have "
        "compared the live state against the declared one"
    )
    for invocation in invocations:
        verbs = invocation.split()
        for mutating in _MUTATING_KUBECTL_VERBS:
            assert mutating not in verbs, (
                f"the drift report issued a MUTATING kubectl invocation "
                f"`kubectl {invocation}` — it must report what an apply would "
                f"change and change nothing"
            )


def test_drift_reports_a_node_whose_live_taint_its_profile_no_longer_declares(
    *, scratch: _Scratch
) -> None:
    """The first Definition-of-Done assertion, run rather than modelled.

    The fixture's profile declares no `node-role/ci` taint — R5's open state,
    and gmktec-xubuntu's committed state — while the stand-in `kubectl` answers
    the taint read with that key still live on the node. An apply would remove
    it, so the drift report must report the node as changed.

    The removal task itself stays SKIPPED, and that is asserted rather than
    merely tolerated: the pending change is reported by the READ, the only half
    of the reconcile that can safely run under `--check`. `changed=1` is exact
    because every other task in this role is a fact derivation or a read.
    """
    host = "drift-probe-node"
    profile = scratch.root / f"{host}.env"
    profile.write_text(f"NODE_NAME={host}\nCLUSTER_ROLE=agent\nNODE_TAINTS=\n", encoding="utf-8")

    output = _run_drift(
        scratch=scratch,
        role="node_taints",
        host=host,
        host_vars={
            "node_taints_profile": str(profile),
            # The reconcile is delegated to the pool's server; here that is this
            # same local host, so the delegation runs without reaching a node.
            "node_taints_server_host": host,
        },
    )
    statuses = _task_statuses(output=output, host=host)

    assert _status_of(statuses=statuses, task=_TAINT_PROBE_TASK) == "changed"
    assert _status_of(statuses=statuses, task=_TAINT_REMOVAL_TASK) == "skipping"
    assert _recap_changed(output=output, host=host) == 1
    _assert_only_read(scratch=scratch)


def _agent_host_vars(*, scratch: _Scratch, host: str) -> dict[str, str]:
    """An agent-shaped `node_status_credential` fixture, entirely under the scratch root.

    Every path the role would reach on a real agent — the delivered credential,
    the runtime refresh tool and its env-file, the server's host key, the ssh
    user's `known_hosts` — is redirected into `tmp_path`, and the directories the
    role expects to find rather than create are created here. What is NOT
    redirected is the role's logic: the profile is a real profile, the mint is
    the real `ansible.builtin.shell`, and the guards are the committed ones.
    """
    delivered = scratch.root / "etc" / "rancher" / "k3s" / "node-status-kubeconfig"
    delivered.parent.mkdir(parents=True)
    tooling = scratch.root / "etc" / "ci-runner"
    tooling.mkdir(parents=True)
    ssh_dir = scratch.root / "home" / ".ssh"
    ssh_dir.mkdir(parents=True)
    host_key = scratch.root / "ssh_host_ed25519_key.pub"
    host_key.write_text(_HOST_KEY_LINE, encoding="utf-8")
    profile = scratch.root / f"{host}.env"
    profile.write_text(
        f"NODE_NAME={host}\n"
        f"CLUSTER_ROLE=agent\n"
        f"CLUSTER_JOIN_ADDRESS=https://198.51.100.1:6443\n"
        f"CHURN_KUBECONFIG_FILE={delivered}\n",
        encoding="utf-8",
    )
    return {
        "cluster_role": "agent",
        "node_status_credential_profile": str(profile),
        "node_status_credential_server_host": host,
        # One attempt, no delay: the token Secret's absence is this fixture's
        # live state, not a cold API server to wait out.
        "node_status_credential_token_retries": "1",
        "node_status_credential_token_delay": "0",
        "node_status_credential_refresh_bin": str(scratch.bin_dir / "refresh-node-status"),
        "node_status_credential_refresh_env": str(tooling / "node-status-refresh.env"),
        "node_status_credential_server_host_key": str(host_key),
        "node_status_credential_known_hosts": str(ssh_dir / "known_hosts"),
        # The stand-in `sudo` ignores `-u`, so this names the account the
        # role's become_user and its env-file record, not a real login.
        "node_status_credential_ssh_user": "root",
    }


def test_drift_reports_an_agent_whose_delivered_node_status_credential_is_refused(
    *, scratch: _Scratch
) -> None:
    """The second Definition-of-Done assertion, and the one `--check` could see least.

    The stand-in `kubectl` refuses the agent's delivered credential with the API
    server's own wording, and answers the ServiceAccount token read as a
    reboot-emptied datastore does: with nothing. So the mint is skipped (it is an
    `ansible.builtin.shell`), the token read comes back empty, and the render and
    the delivery skip on their non-empty-token guard — the exact state in which
    the report said `changed=0` over an agent whose credential nothing accepted.

    The render and the delivery are asserted SKIPPED on purpose. The Definition
    of Done asks for the agent to be reported as changed *rather than* for those
    two to stop skipping, and they cannot stop: the credential they would write
    does not exist until the cluster-side mint the drift report must not perform.
    So the report has to come from the probe or from nowhere.
    """
    host = "drift-probe-agent"
    output = _run_drift(
        scratch=scratch,
        role="node_status_credential",
        host=host,
        host_vars=_agent_host_vars(scratch=scratch, host=host),
    )
    statuses = _task_statuses(output=output, host=host)

    assert _status_of(statuses=statuses, task=_CREDENTIAL_PROBE_TASK) == "changed"
    assert _status_of(statuses=statuses, task=_CREDENTIAL_RENDER_TASK) == "skipping"
    assert _status_of(statuses=statuses, task=_CREDENTIAL_DELIVERY_TASK) == "skipping"
    _assert_only_read(scratch=scratch)


def test_drift_reports_no_change_for_an_agent_whose_credential_the_api_server_accepts(
    *, scratch: _Scratch
) -> None:
    """The other half of the same probe: a clean run must keep meaning something.

    A probe that reported a change on every non-zero exit — or on every run —
    would replace a report that was silent about real drift with one that is
    noisy about none, and an operator cannot read either. So the probe is keyed
    on the API server's REFUSAL wording, exactly as the runtime
    `patch-node-churn-capacity.sh` keys its own retry: a credential the server
    accepts is the converged state, and the converged state reports `ok`.
    """
    host = "drift-probe-agent"
    output = _run_drift(
        scratch=scratch,
        role="node_status_credential",
        host=host,
        host_vars=_agent_host_vars(scratch=scratch, host=host),
        credential_accepted=True,
    )
    statuses = _task_statuses(output=output, host=host)

    assert _status_of(statuses=statuses, task=_CREDENTIAL_PROBE_TASK) == "ok"
    _assert_only_read(scratch=scratch)
