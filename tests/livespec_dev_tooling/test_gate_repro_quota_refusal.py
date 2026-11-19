"""The reproduction route refuses a Job its node's flavor could never admit.

A repro Job whose CPU request exceeds the committed quota of the repro flavor
for its node would sit Suspended forever, so `run_repro_gate` reads the
committed `cluster-queue-repro-gates.yaml` beside its renderer and refuses at
submit, naming the flavor and its quota, before any command reaches the
cluster (livespec-dev-tooling-z66x7t).
"""

from __future__ import annotations

from pathlib import Path

from returns.result import Success

from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_repro import REPRO_QUEUE, run_repro_gate

_QUEUE = """\
apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: gates-repro-cq
spec:
  resourceGroups:
    - coveredResources: ["cpu", "memory"]
      flavors:
        - name: gates-repro-gamingpc-flavor
          resources:
            - name: "cpu"
              nominalQuota: 0
            - name: "memory"
              nominalQuota: 0Gi
        - name: gates-repro-poweredge-flavor
          resources:
            - name: "cpu"
              nominalQuota: 5
            - name: "memory"
              nominalQuota: 8Gi
        - name: gates-repro-hp-flavor
          resources:
            - name: "cpu"
              nominalQuota: 10
            - name: "memory"
              nominalQuota: 8Gi
"""


def _tooling(*, root: Path) -> Path:
    """A tooling checkout holding a renderer with its defaults line and the repro queue."""
    renderer = root / "ci-runner/k3s/phase2/gates/render-gate-job.sh"
    renderer.parent.mkdir(parents=True)
    _ = renderer.write_text('cpu="5"; memory="8Gi"; parallelism="4"\n', encoding="utf-8")
    queue = root / "ci-runner/k3s/phase2/kueue/cluster-queue-repro-gates.yaml"
    queue.parent.mkdir(parents=True)
    _ = queue.write_text(_QUEUE, encoding="utf-8")
    return renderer


def _repository(*, root: Path, cpu: str) -> Path:
    root.mkdir()
    _ = (root / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\ngate_cpu = {cpu}\n", encoding="utf-8"
    )
    return root


class _Calls:
    """A runner that records every command and answers each with empty success."""

    def __init__(self) -> None:
        self.argvs: list[tuple[str, ...]] = []

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (cwd, stdin, stream)
        self.argvs.append(tuple(argv))
        return Success(GateCommandResult(returncode=0, stdout="", stderr=""))


def _no_sleep(*, seconds: float) -> None:
    _ = seconds


def _repro(*, tmp_path: Path, cpu: str, node: str) -> tuple[str, str, list[tuple[str, ...]]]:
    renderer = _tooling(root=tmp_path / "tooling")
    calls = _Calls()
    outcome = run_repro_gate(
        repo_root=_repository(root=tmp_path / "widget", cpu=cpu),
        renderer=renderer,
        queue=REPRO_QUEUE,
        stack_interval_seconds=300,
        node=node,
        runner=calls,
        sleeper=_no_sleep,
    )
    return outcome.ended, outcome.detail, calls.argvs


def test_a_request_above_the_node_flavor_quota_is_refused_before_any_command(
    *, tmp_path: Path
) -> None:
    """10 cpu on the 5-cpu poweredge flavor is refused, naming the flavor, with no command run."""
    ended, detail, argvs = _repro(tmp_path=tmp_path, cpu="10", node="poweredge-xubuntu")

    facts = [
        ended == "refused",
        "gates-repro-poweredge-flavor" in detail,
        "could never admit" in detail,
        argvs == [],
    ]
    assert all(facts), (facts, ended, detail, argvs)


def test_a_zero_quota_flavor_is_refused(*, tmp_path: Path) -> None:
    """The armed-at-zero gamingpc flavor admits nothing, so its repro is refused at submit."""
    ended, detail, argvs = _repro(tmp_path=tmp_path, cpu="5", node="gamingpc-xubuntu")

    facts = [ended == "refused", "gates-repro-gamingpc-flavor" in detail, argvs == []]
    assert all(facts), (facts, ended, detail, argvs)


def test_a_request_the_node_flavor_holds_is_not_refused(*, tmp_path: Path) -> None:
    """10 cpu on the 10-cpu hp flavor proceeds to the cluster."""
    ended, _detail, argvs = _repro(tmp_path=tmp_path, cpu="10", node="hp-xubuntu")

    facts = [ended != "refused", argvs != []]
    assert all(facts), (facts, ended, argvs)


def test_an_unreadable_declaration_is_not_refused_by_the_quota_check(*, tmp_path: Path) -> None:
    """A gate_cpu the repository cannot read is left to the client's own refusal, not this one."""
    renderer = _tooling(root=tmp_path / "tooling")
    repository = _repository(root=tmp_path / "widget", cpu='"ten"')
    calls = _Calls()
    outcome = run_repro_gate(
        repo_root=repository,
        renderer=renderer,
        queue=REPRO_QUEUE,
        stack_interval_seconds=300,
        node="poweredge-xubuntu",
        runner=calls,
        sleeper=_no_sleep,
    )

    assert outcome.ended != "refused", outcome
