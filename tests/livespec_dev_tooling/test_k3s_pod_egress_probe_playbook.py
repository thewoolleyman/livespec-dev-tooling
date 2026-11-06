"""`ansible/k3s-pod-egress-probe.yml` — a pod measures the path to the incident observer, then vanishes.

Plan expedited-incident-response-flag (epic livespec-dev-tooling-bqnzcm). The
governing clause is the "Consent-gated pool-node disruption" section of
`SPECIFICATION/non-functional-requirements.md`, on the model of the
container-termination drill.

Every property is asserted by RUNNING the committed playbook through the same
`ansible-core` pin `just ansible-apply` executes, against a local `ci_pool`
inventory (a server and an agent) and a scratch PATH carrying stand-in
`kubectl` and `sudo`. No cluster is reached. The stand-in `kubectl` keeps the
namespace set in a file, accepts the probe's `create` / `apply` / `delete`,
answers the pod's phase only once the pod was applied (Pending first, then
Succeeded), and prints a canned log, so a play that skipped a step fails rather
than passing on a canned answer. Every invocation is appended to one ordered log.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

# INTEGRATION TIER, declared statically for `heading_coverage` direction 4: every
# test drives the real committed playbook through the pinned `ansible-core`.
pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_PLAYBOOK = _REPO_ROOT / "ansible" / "k3s-pod-egress-probe.yml"

_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

_SERVER = "egress-probe-server"
_AGENT = "egress-probe-agent"
_NAMESPACE = "probe-under-test"
_POD = "egress-probe"

_PLAYBOOK_TIMEOUT_SECONDS = 600
_UTC = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
_REPORT = re.compile(
    rf"Pod egress probe namespace (?P<namespace>\S+)\s+"
    rf"started at (?P<start>{_UTC})\s+ended at (?P<end>{_UTC})"
)
_RECAP_CHANGED = re.compile(r"changed=(?P<changed>\d+)")

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

# The stand-in `kubectl`. Exits non-zero on anything it was not written to
# answer, so an unexpected invocation breaks a test rather than reading as an
# empty answer.
_KUBECTL_STAND_IN = """#!/bin/sh
printf 'kubectl %s\\n' "$*" >> "${PROBE_COMMAND_LOG}"
namespaces="${PROBE_STATE_DIR}/namespaces"
applied="${PROBE_STATE_DIR}/applied.json"
touch "${namespaces}"
case "$*" in
  'get namespace '*)
    name="$3"
    if grep -qx "${name}" "${namespaces}"; then printf 'namespace/%s\\n' "${name}"; fi
    exit 0 ;;
  'create namespace '*)
    printf '%s\\n' "$3" >> "${namespaces}"
    exit 0 ;;
  'apply '*)
    cat > "${applied}"
    exit 0 ;;
  'get pod egress-probe '*)
    if [ ! -f "${applied}" ]; then exit 1; fi
    reads="$(cat "${PROBE_STATE_DIR}/reads" 2>/dev/null || printf '0')"
    reads=$((reads + 1))
    printf '%s' "${reads}" > "${PROBE_STATE_DIR}/reads"
    if [ "${reads}" -le 1 ]; then printf 'Pending'; else printf 'Succeeded'; fi
    exit 0 ;;
  'logs egress-probe '*)
    if [ ! -f "${applied}" ]; then exit 1; fi
    printf 'Name: observer.example.invalid\\ntailnet-ip 401 ssl=0 t=0.1\\npublic 401 ssl=0 t=0.2\\n'
    exit 0 ;;
  'delete namespace '*)
    grep -vx "$3" "${namespaces}" > "${namespaces}.new" || true
    mv "${namespaces}.new" "${namespaces}"
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    root: Path
    bin_dir: Path
    state_dir: Path
    command_log: Path

    @property
    def namespaces(self) -> list[str]:
        listed = self.state_dir / "namespaces"
        return listed.read_text(encoding="utf-8").split() if listed.exists() else []

    @property
    def commands(self) -> list[str]:
        if not self.command_log.exists():
            return []
        return self.command_log.read_text(encoding="utf-8").splitlines()

    @property
    def applied_manifest(self) -> dict[str, object]:
        document = json.loads((self.state_dir / "applied.json").read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        return document  # pyright: ignore[reportUnknownVariableType]


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


def _plain_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }


@pytest.fixture(autouse=True, scope="module")
def _warm_pinned_ansible_env(*, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Build the pinned ansible env with one plain, trivial play before this module's tests.

    Measured in the delegated gate Job on 2026-11-06 (four runs, recorded on
    the claim-token race drill's test module): when a Job's first `uvx
    ansible-playbook` call was a stand-in-heavy harness, every controller start
    in that module timed out at ansible-core 2.21's in-process RPC host; one
    plain trivial play run first cleared it. The fixture asserts its own run so
    a venue where even the plain start fails is reported rather than hidden.
    """
    root = tmp_path_factory.mktemp("ansible-env-warm")
    inventory = root / "inventory.yml"
    inventory.write_text(
        "all:\n  hosts:\n    warm:\n      ansible_connection: local\n", encoding="utf-8"
    )
    play = root / "trivial.yml"
    play.write_text(
        "- hosts: all\n  gather_facts: false\n  tasks:\n    - ansible.builtin.debug:\n        msg: warm\n",
        encoding="utf-8",
    )
    env = _plain_env()
    env["ANSIBLE_NOCOWS"] = "1"
    completed = subprocess.run(
        ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", "-i", str(inventory), str(play)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    """A scratch root with the stand-ins on a private bin dir and an empty cluster."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("sudo", _SUDO_STAND_IN), ("kubectl", _KUBECTL_STAND_IN)):
        stand_in = bin_dir / name
        stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return _Scratch(
        root=tmp_path, bin_dir=bin_dir, state_dir=state_dir, command_log=tmp_path / "command.log"
    )


def _write_inventory(*, scratch: _Scratch) -> Path:
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
        "          cluster_role: agent\n",
        encoding="utf-8",
    )
    return inventory


def _run_playbook(*, scratch: _Scratch, confirm: str | None) -> tuple[int, str]:
    """Run the committed playbook; return its exit code and its callback output."""
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} must exist"
    env = _plain_env()
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "PROBE_COMMAND_LOG": str(scratch.command_log),
            "PROBE_STATE_DIR": str(scratch.state_dir),
            "ANSIBLE_DISPLAY_SKIPPED_HOSTS": "True",
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
        }
    )
    argv = [
        "uvx",
        "--from",
        _ansible_core_pin(),
        "ansible-playbook",
        "-i",
        str(_write_inventory(scratch=scratch)),
        "-e",
        "k3s_pod_egress_probe_wait_interval=0",
        "-e",
        "k3s_pod_egress_probe_wait_retries=3",
        "-e",
        f"k3s_pod_egress_probe_namespace={_NAMESPACE}",
        *(["-e", f"k3s_pod_egress_probe_confirm={confirm}"] if confirm is not None else []),
        str(_PLAYBOOK),
    ]
    completed = subprocess.run(
        argv,
        cwd=scratch.root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _writes(*, commands: list[str]) -> list[str]:
    return [line for line in commands if re.match(r"kubectl (create|apply|delete) ", line)]


@pytest.mark.parametrize("confirm", [None, _AGENT, "not-a-host"])
def test_a_run_without_the_confirmation_naming_the_server_reads_nothing_and_changes_nothing(
    *, scratch: _Scratch, confirm: str | None
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=confirm)

    assert code == 0, output
    assert scratch.commands == [], output
    assert {int(m["changed"]) for m in _RECAP_CHANGED.finditer(output)} == {0}, output


def test_a_confirmed_run_measures_from_one_pod_prints_its_log_and_deletes_the_namespace(
    *, scratch: _Scratch
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_SERVER)

    assert code == 0, output
    report = _REPORT.search(output)
    assert report is not None, output
    assert report["namespace"] == _NAMESPACE
    assert report["start"] <= report["end"]
    assert "tailnet-ip 401 ssl=0 t=0.1" in output
    assert "public 401 ssl=0 t=0.2" in output

    verbs = [line.split()[1] for line in _writes(commands=scratch.commands)]
    assert verbs == ["create", "apply", "delete"], scratch.commands
    assert scratch.namespaces == [], "the probe namespace must be gone once it exits"
    for line in scratch.commands:
        assert f"namespace {_NAMESPACE}" in line or f"--namespace {_NAMESPACE}" in line, line

    manifest = scratch.applied_manifest
    assert manifest["kind"] == "Pod"
    assert manifest["metadata"]["name"] == _POD  # pyright: ignore[reportUnknownVariableType]
    assert manifest["metadata"]["namespace"] == _NAMESPACE  # pyright: ignore[reportUnknownVariableType]
    spec = manifest["spec"]
    assert isinstance(spec, dict)
    assert spec["restartPolicy"] == "Never"
    assert spec["automountServiceAccountToken"] is False
    assert spec["securityContext"]["runAsNonRoot"] is True
    (container,) = spec["containers"]
    assert container["image"] == "curlimages/curl:8.11.1"
    script = container["command"][2]
    assert script.index("nslookup") < script.index("--resolve") < script.index('"public ')
    assert "--resolve vps.perch-rudd.ts.net:8765:100.89.189.118" in script
    assert "-X POST https://vps.perch-rudd.ts.net:8765/current" in script
