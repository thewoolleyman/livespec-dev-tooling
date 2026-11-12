"""The admission hold's lift, `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

A newly joined worker carries the admission hold taint "until that hold is lifted by a separate,
explicit operator action". `homelab-worker/lift-admission-hold.sh` is that action. These run it
under the system `/bin/bash` against a stub `kubectl` that answers the Node and its taints from
mocked files and logs every call, and assert:

- the hold is removed, by exactly one taint write, and the permanent class taint is kept;
- a Node without the hold exits 0 with no write;
- an absent Node, a Node without the worker class label, a NotReady Node and a cordoned Node are
  each refused with no write;
- a failed read is named, and a hold still present on the read-back fails the run;
- an undeclared host or a bad argument is refused before any cluster call.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "lift-admission-hold.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"
_HOLD = "homelab-worker.livespec.dev/admission=hold:NoSchedule"
_CLASS = "homelab-worker.livespec.dev/class=worker:NoSchedule"

# The Node is the file $STUB_STATE/node, holding "<class label>|<Ready status>|<unschedulable>";
# its taints are the lines of $STUB_STATE/taints. KUBECTL_FAILS names the read ("node" or
# "taints") that fails. `taint` removes the named taint, unless TAINT_STICKS, and removes the
# class taint as well under TAINT_TAKES_CLASS.
_STUB_KUBECTL = """#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
case "$1 $2" in
  "get node")
    case "$*" in
      *spec.taints*)
        [ "$KUBECTL_FAILS" != taints ] || { echo "Connection closed" >&2; exit 255; }
        cat "$s/taints" ;;
      *)
        [ "$KUBECTL_FAILS" != node ] || { echo "Connection closed" >&2; exit 255; }
        [ ! -f "$s/node" ] || printf '%s|%s' "$3" "$(cat "$s/node")" ;;
    esac ;;
  "taint node")
    [ -n "$TAINT_STICKS" ] || { grep -vxF "${4%-}" "$s/taints" > "$s/taints.new"; mv "$s/taints.new" "$s/taints"; }
    [ -z "$TAINT_TAKES_CLASS" ] || : > "$s/taints" ;;
esac
exit 0
"""


@dataclass(frozen=True, kw_only=True)
class _Env:
    state: Path
    bin_dir: Path


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    """A registered, Ready, uncordoned worker carrying the hold and the class taint."""
    state = tmp_path / "stub"
    (state / "hosts").mkdir(parents=True)
    (state / "hosts" / f"{_HOST}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    (state / "calls.log").write_text("", encoding="utf-8")
    (state / "node").write_text("worker|True|", encoding="utf-8")
    (state / "taints").write_text(f"{_HOLD}\n{_CLASS}\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "kubectl"
    stub.write_text(_STUB_KUBECTL, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return _Env(state=state, bin_dir=bin_dir)


def _run(
    *, env: _Env, args: list[str] | None = None, **stub: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), *([_HOST] if args is None else args)],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{env.bin_dir}:/usr/bin:/bin",
            "HOMELAB_WORKER_HOSTS_DIR": str(env.state / "hosts"),
            "STUB_STATE": str(env.state),
            "KUBECTL_FAILS": stub.get("kubectl_fails", ""),
            "TAINT_STICKS": stub.get("taint_sticks", ""),
            "TAINT_TAKES_CLASS": stub.get("taint_takes_class", ""),
        },
        check=False,
        timeout=60,
    )


def _calls(*, env: _Env) -> list[str]:
    return (env.state / "calls.log").read_text(encoding="utf-8").splitlines()


def _writes(*, env: _Env) -> list[str]:
    return [c for c in _calls(env=env) if not c.startswith("kubectl get ")]


def _taints(*, env: _Env) -> list[str]:
    return (env.state / "taints").read_text(encoding="utf-8").splitlines()


def test_the_hold_is_lifted_by_one_taint_write_and_the_class_taint_is_kept(env: _Env) -> None:
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _writes(env=env) == [f"kubectl taint node {_WORKER} {_HOLD}-"]
    assert _taints(env=env) == [_CLASS]
    assert f"admission hold lifted from Node {_WORKER}" in result.stdout
    assert _calls(env=env)[-1].startswith(f"kubectl get node {_WORKER} ")
    assert "spec.taints" in _calls(env=env)[-1]


def test_a_node_without_the_hold_exits_zero_and_writes_nothing(env: _Env) -> None:
    (env.state / "taints").write_text(f"{_CLASS}\n", encoding="utf-8")
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "does not carry the admission hold" in result.stdout
    assert _writes(env=env) == []
    assert _taints(env=env) == [_CLASS]


@pytest.mark.parametrize(
    ("node", "message"),
    [
        (None, "is not registered"),
        ("|True|", "is not a container worker"),
        ("worker|False|", "is not Ready"),
        ("worker|Unknown|", "is not Ready"),
        ("worker||", "is not Ready"),
        ("worker|True|true", "is cordoned"),
    ],
)
def test_a_node_that_must_not_be_admitted_is_refused_with_no_write(
    env: _Env, node: str | None, message: str
) -> None:
    if node is None:
        (env.state / "node").unlink()
    else:
        (env.state / "node").write_text(node, encoding="utf-8")
    result = _run(env=env)
    assert result.returncode != 0
    assert f"Node {_WORKER} {message}" in result.stderr
    assert "Nothing was changed" in result.stderr
    assert _writes(env=env) == []
    assert _taints(env=env) == [_HOLD, _CLASS]


@pytest.mark.parametrize(
    ("read", "named"),
    [("node", f"could not read Node {_WORKER}"), ("taints", "could not read the taints of Node")],
)
def test_a_failed_kubectl_read_is_named_and_nothing_is_changed(
    env: _Env, read: str, named: str
) -> None:
    result = _run(env=env, kubectl_fails=read)
    assert result.returncode != 0
    assert named in result.stderr
    assert "nothing was changed" in result.stderr
    assert _writes(env=env) == []


def test_a_hold_still_present_on_the_read_back_fails_the_run(env: _Env) -> None:
    result = _run(env=env, taint_sticks="1")
    assert result.returncode != 0
    assert f"Node {_WORKER} still carries {_HOLD}" in result.stderr
    assert "admission hold lifted" not in result.stdout


def test_a_class_taint_missing_on_the_read_back_fails_the_run(env: _Env) -> None:
    result = _run(env=env, taint_takes_class="1")
    assert result.returncode != 0
    assert f"no longer carries its permanent class taint {_CLASS}" in result.stderr
    assert "admission hold lifted" not in result.stdout


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["gamma"], "is not declared"),
        (["Bad_Host"], "is not a valid host name"),
        ([_HOST, "--force"], "usage: lift-admission-hold <host>"),
        ([], "usage: lift-admission-hold <host>"),
    ],
)
def test_bad_arguments_are_refused_before_any_cluster_call(
    env: _Env, args: list[str], message: str
) -> None:
    result = _run(env=env, args=args)
    assert result.returncode != 0
    assert message in result.stderr
    assert _calls(env=env) == []
