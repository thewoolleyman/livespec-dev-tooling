"""`ansible/container-termination-drill.yml` — the committed way to produce a crash-looping and an OOM-killed container.

Work-item livespec-dev-tooling-2zii7l, positive control for
livespec-dev-tooling-t6om4l's host leg. The governing clause is
the container-termination paragraph of the "Consent-gated pool-node
disruption" section of `SPECIFICATION/non-functional-requirements.md`, and the
acceptance scenario is in `SPECIFICATION/scenarios.md`; `tests/heading-coverage.json` maps both here.

Every property is asserted by RUNNING the committed playbook through the same
`ansible-core` pin `just ansible-apply` executes, against a local `ci_pool`
inventory (a server and an agent) and a scratch PATH carrying stand-in `kubectl`
and `sudo`. No cluster is reached. The stand-in `kubectl` is a small state
machine: it keeps the set of namespaces in a file, accepts the drill's
`create` / `apply` / `delete`, and answers the pod reads only once the pods were
applied, so a play that skipped a step reads as failing rather than passing on a
canned answer. Every invocation is appended to one ordered log.
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
_PLAYBOOK = _REPO_ROOT / "ansible" / "container-termination-drill.yml"

_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

_SERVER = "termination-drill-server"
_AGENT = "termination-drill-agent"
_NAMESPACE = "drill-under-test"
_CRASH_POD = "crash-loop"
_OOM_POD = "oom-kill"

_PLAYBOOK_TIMEOUT_SECONDS = 600
_UTC = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
_REPORT = re.compile(
    rf"Container-termination drill namespace (?P<namespace>\S+)\s+"
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
# empty answer. `DRILL_CRASH=never` keeps the crash pod out of CrashLoopBackOff
# (so its wait exhausts); `DRILL_FAIL_CREATE=yes` refuses the namespace create.
_KUBECTL_STAND_IN = """#!/bin/sh
printf 'kubectl %s\\n' "$*" >> "${DRILL_COMMAND_LOG}"
namespaces="${DRILL_STATE_DIR}/namespaces"
applied="${DRILL_STATE_DIR}/applied.json"
touch "${namespaces}"
case "$*" in
  'get namespace '*)
    name="$3"
    if grep -qx "${name}" "${namespaces}"; then printf 'namespace/%s\\n' "${name}"; fi
    exit 0 ;;
  'create namespace '*)
    if [ "${DRILL_FAIL_CREATE}" = yes ]; then exit 1; fi
    printf '%s\\n' "$3" >> "${namespaces}"
    exit 0 ;;
  'apply '*)
    cat > "${applied}"
    exit 0 ;;
  'get pod crash-loop '*)
    if [ ! -f "${applied}" ]; then exit 1; fi
    reads="$(cat "${DRILL_STATE_DIR}/crash-reads" 2>/dev/null || printf '0')"
    reads=$((reads + 1))
    printf '%s' "${reads}" > "${DRILL_STATE_DIR}/crash-reads"
    if [ "${DRILL_CRASH}" = never ] || [ "${reads}" -le 1 ]; then
      printf 'reason=ContainerCreating;restarts=0'
    else
      printf 'reason=CrashLoopBackOff;restarts=3'
    fi
    exit 0 ;;
  'get pod oom-kill '*)
    if [ ! -f "${applied}" ]; then exit 1; fi
    printf 'reason=OOMKilled'
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


def _run_playbook(
    *,
    scratch: _Scratch,
    confirm: str | None,
    namespace: str = _NAMESPACE,
    check_mode: bool = False,
    crash: str = "loop",
    fail_create: bool = False,
) -> tuple[int, str]:
    """Run the committed playbook; return its exit code and its callback output."""
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} must exist"
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "DRILL_COMMAND_LOG": str(scratch.command_log),
            "DRILL_STATE_DIR": str(scratch.state_dir),
            "DRILL_CRASH": crash,
            "DRILL_FAIL_CREATE": "yes" if fail_create else "no",
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
        "container_termination_drill_wait_interval=0",
        "-e",
        "container_termination_drill_wait_retries=2",
        "-e",
        f"container_termination_drill_namespace={namespace}",
        *(["-e", f"container_termination_drill_confirm={confirm}"] if confirm is not None else []),
        *(["--check"] if check_mode else []),
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


@pytest.mark.parametrize("namespace", ["factory", "factory-mi-homelab"])
def test_a_factory_namespace_is_refused_before_any_cluster_command(
    *, scratch: _Scratch, namespace: str
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_SERVER, namespace=namespace)

    assert code != 0, output
    assert scratch.commands == [], output


def test_an_existing_namespace_is_refused_and_left_untouched(*, scratch: _Scratch) -> None:
    (scratch.state_dir / "namespaces").write_text(f"{_NAMESPACE}\n", encoding="utf-8")

    code, output = _run_playbook(scratch=scratch, confirm=_SERVER)

    assert code != 0, output
    assert _writes(commands=scratch.commands) == [], output
    assert scratch.namespaces == [_NAMESPACE], output


def test_a_confirmed_run_produces_both_containers_reports_its_times_and_deletes_the_namespace(
    *, scratch: _Scratch
) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_SERVER)

    assert code == 0, output
    report = _REPORT.search(output)
    assert report is not None, output
    assert report["namespace"] == _NAMESPACE
    assert report["start"] <= report["end"]
    assert "reason=CrashLoopBackOff;restarts=3" in output
    assert "reason=OOMKilled" in output

    verbs = [line.split()[1] for line in _writes(commands=scratch.commands)]
    assert verbs == ["create", "apply", "delete"], scratch.commands
    assert scratch.namespaces == [], "the drill namespace must be gone once it exits"
    for line in scratch.commands:
        assert f"namespace {_NAMESPACE}" in line or f"--namespace {_NAMESPACE}" in line, line

    manifest = scratch.applied_manifest
    items = manifest["items"]
    assert isinstance(items, list)
    names = {item["metadata"]["name"] for item in items}  # pyright: ignore[reportUnknownVariableType]
    assert names == {_CRASH_POD, _OOM_POD}
    for item in items:  # pyright: ignore[reportUnknownVariableType]
        assert item["metadata"]["namespace"] == _NAMESPACE  # pyright: ignore[reportUnknownVariableType]
    oom = next(i for i in items if i["metadata"]["name"] == _OOM_POD)  # pyright: ignore[reportUnknownVariableType]
    assert "memory" in oom["spec"]["containers"][0]["resources"]["limits"]


def test_the_namespace_is_deleted_when_a_wait_step_times_out(*, scratch: _Scratch) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_SERVER, crash="never")

    assert code != 0, output
    assert any(line.startswith("kubectl delete namespace ") for line in scratch.commands)
    assert scratch.namespaces == [], output
    assert _REPORT.search(output) is not None, "times are printed even when a wait fails"


def test_a_failed_create_deletes_nothing(*, scratch: _Scratch) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_SERVER, fail_create=True)

    assert code != 0, output
    assert [line for line in scratch.commands if line.startswith("kubectl delete ")] == [], output


def test_a_check_mode_run_issues_no_cluster_write(*, scratch: _Scratch) -> None:
    code, output = _run_playbook(scratch=scratch, confirm=_SERVER, check_mode=True)

    assert code == 0, output
    assert _writes(commands=scratch.commands) == [], output
