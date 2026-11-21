"""Integration coverage for the committed stuck-object drill.

The test runs the real playbook through pinned ansible-core.  Its kubectl
stand-in is stateful: it serves a node whose Ready and cordon state the test
chooses, remembers created objects, and logs every call so a test can prove a
refusal changed nothing.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_PLAYBOOK = _ROOT / "ansible" / "stuck-object-drill.yml"
_SERVER = "stuck-drill-server"
_NODE = "dead-node"
_RUN = "01KTESTRUNIDENTIFIER0001"
_POD = "petri-01ktestrunidentifier0001-l0"
_JOB = "gate-drill-abc123"

_KUBECTL = r"""#!/bin/sh
printf 'kubectl %s\n' "$*" >> "$DRILL_LOG"
args="$*"
case "$args" in
  'get node '*)
    printf 'ready=%s unschedulable=%s' "$NODE_READY" "$NODE_UNSCHEDULABLE" ;;
  'create --filename -')
    cat >> "$DRILL_STATE/created.json"
    printf '\n' >> "$DRILL_STATE/created.json"
    touch "$DRILL_STATE/exists" ;;
  'get pod --namespace '*'--ignore-not-found --output name'*|'get job --namespace '*'--ignore-not-found --output name'*)
    if test -f "$DRILL_STATE/exists" || test "$OBJECT_EXISTS" = yes; then printf 'object/x\n'; fi ;;
  *'jsonpath={.metadata.labels.livespec'*)
    printf '%s' "$OBJECT_LABEL" ;;
  'get pods --namespace gates --selector batch.kubernetes.io/job-name='*'livespec.dev/drill-fixture=stuck-object'*)
    printf 'pod-of-job\n' ;;
  'get pods --namespace gates --selector batch.kubernetes.io/job-name='*)
    if test -f "$DRILL_STATE/job-deleted"; then
      printf 'pod-of-job dead-node marked:2026-11-21T00:00:00Z finalizers:batch.kubernetes.io/job-tracking\n'
    else
      printf 'pod-of-job dead-node marked: finalizers:batch.kubernetes.io/job-tracking\n'
    fi ;;
  'delete job '*) touch "$DRILL_STATE/job-deleted" ;;
  'delete pod '*) : ;;
  *) printf 'unexpected kubectl invocation: %s\n' "$args" >&2; exit 1 ;;
esac
"""


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    root: Path
    bin_dir: Path
    state: Path
    log: Path

    @property
    def commands(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    @property
    def writes(self) -> list[str]:
        return [
            line for line in self.commands if line.startswith(("kubectl create", "kubectl delete"))
        ]

    @property
    def created(self) -> str:
        path = self.state / "created.json"
        return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stand_in = bin_dir / "kubectl"
    _ = stand_in.write_text(_KUBECTL, encoding="utf-8")
    stand_in.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    return _Scratch(root=tmp_path, bin_dir=bin_dir, state=state, log=tmp_path / "log")


def _inventory(*, scratch: _Scratch) -> Path:
    path = scratch.root / "inventory.yml"
    _ = path.write_text(
        "all:\n  children:\n    ci_pool:\n      hosts:\n"
        f"        {_SERVER}:\n          ansible_connection: local\n          cluster_role: server\n",
        encoding="utf-8",
    )
    return path


def _run(
    *,
    scratch: _Scratch,
    action: str = "create-factory-pod",
    confirm: str | None = "same",
    object_name: str | None = f"factory/{_POD}",
    object_confirm: str | None = None,
    node: str | None = _NODE,
    node_confirm: str | None = "same",
    ready: str = "False",
    unschedulable: str = "true",
    exists: bool = False,
    label: str = "stuck-object",
    check: bool = False,
) -> tuple[int, str]:
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} must exist"
    env = {key: value for key, value in os.environ.items() if not key.startswith("COV_CORE_")}
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "DRILL_LOG": str(scratch.log),
            "DRILL_STATE": str(scratch.state),
            "NODE_READY": ready,
            "NODE_UNSCHEDULABLE": unschedulable,
            "OBJECT_EXISTS": "yes" if exists else "no",
            "OBJECT_LABEL": label,
        }
    )
    variables = [
        # The play escalates with `become` for the root-owned kubeconfig; sudo would reset
        # PATH and hide the kubectl stand-in, so the test runs unescalated.
        "ansible_become=false",
        f"stuck_object_drill_action={action}",
        "stuck_object_drill_wait_interval=0",
        "stuck_object_drill_wait_retries=2",
        f"stuck_object_drill_run_id={_RUN}",
    ]
    if confirm is not None:
        variables.append(f"stuck_object_drill_confirm={action if confirm == 'same' else confirm}")
    if object_name is not None:
        variables.append(f"stuck_object_drill_object={object_name}")
    if object_confirm is not None:
        variables.append(f"stuck_object_drill_object_confirm={object_confirm}")
    if node is not None:
        variables.append(f"stuck_object_drill_node={node}")
    if node_confirm is not None:
        variables.append(
            f"stuck_object_drill_node_confirm={node if node_confirm == 'same' else node_confirm}"
        )
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            "ansible-core==2.18.9",
            "ansible-playbook",
            "-i",
            str(_inventory(scratch=scratch)),
            *(["--check"] if check else []),
            *[argument for variable in variables for argument in ("-e", variable)],
            str(_PLAYBOOK),
        ],
        cwd=scratch.root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    return completed.returncode, completed.stdout + completed.stderr


@pytest.mark.parametrize(
    "overrides",
    [
        {"confirm": None},
        {"confirm": "create-stuck-gate-job"},
        {"node_confirm": None},
        {"node_confirm": "other-node"},
        {"object_name": None},
    ],
)
def test_absent_or_mismatched_confirmation_reads_and_changes_nothing(
    *, scratch: _Scratch, overrides: dict[str, str | None]
) -> None:
    code, output = _run(scratch=scratch, **overrides)  # type: ignore[arg-type]
    assert code == 0, output
    assert scratch.commands == [], output


def test_remove_without_a_matching_object_confirmation_changes_nothing(
    *, scratch: _Scratch
) -> None:
    code, output = _run(
        scratch=scratch,
        action="remove-drill-fixtures",
        node=None,
        node_confirm=None,
        exists=True,
        object_confirm="factory/another",
    )
    assert code == 0, output
    assert scratch.commands == [], output


@pytest.mark.parametrize(
    ("ready", "unschedulable"), [("True", "true"), ("False", ""), ("True", "")]
)
@pytest.mark.parametrize(
    ("action", "object_name"),
    [("create-factory-pod", f"factory/{_POD}"), ("create-stuck-gate-job", f"gates/{_JOB}")],
)
def test_a_ready_or_uncordoned_node_is_refused_before_any_write(
    *, scratch: _Scratch, action: str, object_name: str, ready: str, unschedulable: str
) -> None:
    code, output = _run(
        scratch=scratch,
        action=action,
        object_name=object_name,
        ready=ready,
        unschedulable=unschedulable,
    )
    assert code != 0, output
    assert scratch.writes == [], output


@pytest.mark.parametrize(
    ("action", "object_name"),
    [("create-factory-pod", f"factory/{_POD}"), ("create-stuck-gate-job", f"gates/{_JOB}")],
)
def test_an_existing_object_is_never_overwritten(
    *, scratch: _Scratch, action: str, object_name: str
) -> None:
    code, output = _run(scratch=scratch, action=action, object_name=object_name, exists=True)
    assert code != 0, output
    assert "already exists" in output
    assert scratch.writes == [], output


@pytest.mark.parametrize(
    ("action", "object_name"),
    [
        ("create-factory-pod", f"gates/{_POD}"),
        ("create-factory-pod", "factory/not-a-petri-pod"),
        ("create-factory-pod", "factory/*"),
        ("create-stuck-gate-job", f"factory/{_JOB}"),
    ],
)
def test_a_target_outside_the_drill_scope_is_refused(
    *, scratch: _Scratch, action: str, object_name: str
) -> None:
    code, output = _run(scratch=scratch, action=action, object_name=object_name)
    assert code != 0, output
    assert scratch.writes == [], output


def test_create_factory_pod_creates_one_labelled_pod_bound_to_the_node(
    *, scratch: _Scratch
) -> None:
    code, output = _run(scratch=scratch)
    assert code == 0, output
    assert f"created pod factory/{_POD} on not-Ready cordoned node {_NODE}" in output
    assert len(scratch.writes) == 1, scratch.commands
    assert f'"nodeName":"{_NODE}"' in scratch.created
    assert '"livespec.dev/drill-fixture":"stuck-object"' in scratch.created
    assert f'"petri.run":"{_RUN}"' in scratch.created
    assert "busybox:1.37.0" in scratch.created


def test_create_stuck_gate_job_creates_then_deletes_the_job_in_the_background(
    *, scratch: _Scratch
) -> None:
    code, output = _run(
        scratch=scratch, action="create-stuck-gate-job", object_name=f"gates/{_JOB}"
    )
    assert code == 0, output
    assert f"created stuck job gates/{_JOB}" in output
    assert "batch.kubernetes.io/job-tracking" in output
    assert '"backoffLimit":0' in scratch.created
    assert f'"nodeName":"{_NODE}"' in scratch.created
    assert [line for line in scratch.writes if line.startswith("kubectl delete job")] == [
        f"kubectl delete job --namespace gates {_JOB} --cascade=background --wait=false"
    ]


def test_check_mode_reports_and_changes_nothing(*, scratch: _Scratch) -> None:
    code, output = _run(scratch=scratch, check=True)
    assert code == 0, output
    assert f"would create pod factory/{_POD}" in output
    assert scratch.writes == [], output


@pytest.mark.parametrize("object_name", [f"factory/{_POD}", f"gates/{_JOB}"])
def test_remove_refuses_an_object_without_the_fixture_label(
    *, scratch: _Scratch, object_name: str
) -> None:
    code, output = _run(
        scratch=scratch,
        action="remove-drill-fixtures",
        object_name=object_name,
        object_confirm=object_name,
        node=None,
        node_confirm=None,
        exists=True,
        label="",
    )
    assert code != 0, output
    assert "does not carry label livespec.dev/drill-fixture=stuck-object" in output
    assert scratch.writes == [], output


@pytest.mark.parametrize(
    "object_name", ["factory/*", "factory", "kube-system/coredns", "gates/a/b"]
)
def test_remove_refuses_an_unnamed_or_out_of_scope_object(
    *, scratch: _Scratch, object_name: str
) -> None:
    code, output = _run(
        scratch=scratch,
        action="remove-drill-fixtures",
        object_name=object_name,
        object_confirm=object_name,
        node=None,
        node_confirm=None,
        exists=True,
    )
    assert code != 0, output
    assert scratch.writes == [], output


def test_remove_deletes_a_labelled_pod_by_name(*, scratch: _Scratch) -> None:
    code, output = _run(
        scratch=scratch,
        action="remove-drill-fixtures",
        object_name=f"factory/{_POD}",
        object_confirm=f"factory/{_POD}",
        node=None,
        node_confirm=None,
        exists=True,
    )
    assert code == 0, output
    assert f"removed pod factory/{_POD}" in output
    assert scratch.writes == [
        f"kubectl delete pod --namespace factory {_POD} --wait=false --grace-period=0 --force"
    ]


def test_remove_deletes_a_labelled_job_and_its_labelled_pod_by_name(*, scratch: _Scratch) -> None:
    code, output = _run(
        scratch=scratch,
        action="remove-drill-fixtures",
        object_name=f"gates/{_JOB}",
        object_confirm=f"gates/{_JOB}",
        node=None,
        node_confirm=None,
        exists=True,
    )
    assert code == 0, output
    assert f"removed job gates/{_JOB}" in output
    assert "removed pod gates/pod-of-job" in output
    assert len(scratch.writes) == 2, scratch.commands
