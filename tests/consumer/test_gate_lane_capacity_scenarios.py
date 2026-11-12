"""Consumer-tier scenarios for delegated-gate lane capacity.

The gate client sees a consumer repository through its ``GateCommandRunner``
seam.  These fixtures therefore create a consumer tree and a canned gate
cluster, while still driving ``run_delegated_gate``: the same client entry point
that a consumer's pre-push recipe invokes.  No cluster, mirror, or credential
is contacted.
"""

from __future__ import annotations

import json
import re
import shutil
from fractions import Fraction
from pathlib import Path
from typing import cast

import pytest
from returns.result import Success

from livespec_dev_tooling._gate_lane_capacity import committed_lanes, largest_lane
from livespec_dev_tooling.gate_credential import GATES_WRAPPER
from livespec_dev_tooling.gate_remote_delegate import run_delegated_gate
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_verdict import GATE_NO_VERDICT

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_ROOT = Path(__file__).resolve().parents[2]
_QUEUE = Path("ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml")
_RENDERER = Path("ci-runner/k3s/phase2/gates/render-gate-job.sh")
_COVERAGE = _ROOT / "tests" / "heading-coverage.json"
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_JOB = "gate-widget-7f2qd"
_CREATED = json.dumps({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB}})
_COMPLETE = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})
_DEFAULTS = re.compile(r'^cpu="([^"]*)"; memory="([^"]*)";', re.MULTILINE)
_OVERSIZED_HEADING = (
    "## Scenario: a declared gate resource that no single gate lane can admit is refused "
    "naming the largest lane's quotas"
)
_OVERSIZED_TEST = (
    "tests.consumer.test_gate_lane_capacity_scenarios."
    "test_a_declared_cpu_above_every_committed_lane_is_refused_before_any_gate_job"
)
_UNREADABLE_HEADING = (
    "## Scenario: a repository that declares no gate cpu or memory is not refused over an "
    "unreadable gates queue file"
)
_UNREADABLE_TEST = (
    "tests.consumer.test_gate_lane_capacity_scenarios."
    "test_a_consumer_without_cpu_or_memory_submits_at_default_size_despite_an_unreadable_queue"
)


class _GateCluster:
    """Canned commands for one push, recording render and submit boundaries."""

    def __init__(self) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self.stdins: list[str | None] = []

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (cwd, stream)
        self.argvs.append(tuple(argv))
        self.stdins.append(stdin)
        if "rev-parse" in argv:
            return self._success(stdout=f"{_TREE}\n")
        if argv[0].endswith("render-gate-job.sh"):
            return self._success(stdout=self._rendered_manifest(argv=argv))
        if argv[0] == GATES_WRAPPER:
            if "create" in argv:
                return self._success(stdout=_CREATED)
            if "get" in argv and "job" in argv:
                return self._success(stdout=_COMPLETE)
        return self._success(stdout="")

    def issued(self, *, needle: str) -> list[tuple[str, ...]]:
        """Return each command containing ``needle``."""
        return [argv for argv in self.argvs if needle in argv]

    def submitted_manifests(self) -> list[str]:
        """The manifest text handed to kubectl create for every submitted Job."""
        return [
            stdin
            for argv, stdin in zip(self.argvs, self.stdins, strict=True)
            if argv[0] == GATES_WRAPPER and "create" in argv and stdin is not None
        ]

    def _rendered_manifest(self, *, argv: list[str]) -> str:
        """Render the source renderer's defaults unless the client supplied flags."""
        renderer = Path(argv[0])
        defaults = _DEFAULTS.search(renderer.read_text(encoding="utf-8"))
        assert defaults is not None
        cpu = self._argument(argv=argv, flag="--cpu") or defaults.group(1)
        memory = self._argument(argv=argv, flag="--memory") or defaults.group(2)
        return (
            "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n"
            "spec:\n  template:\n    spec:\n      containers:\n        - resources:\n"
            f"            requests: {{cpu: {cpu}, memory: {memory}}}\n"
        )

    @staticmethod
    def _argument(*, argv: list[str], flag: str) -> str | None:
        return argv[argv.index(flag) + 1] if flag in argv else None

    @staticmethod
    def _success(*, stdout: str) -> GateCommandOutcome:
        return Success(GateCommandResult(returncode=0, stdout=stdout, stderr=""))


def _consumer(*, tmp_path: Path, table: str) -> Path:
    """A fixture consumer carrying the in-tree renderer and committed queue file."""
    repo = tmp_path / "consumer"
    repo.mkdir(parents=True)
    _ = (repo / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\n{table}", encoding="utf-8"
    )
    for source in (_QUEUE, _RENDERER):
        destination = repo / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy(_ROOT / source, destination)
    return repo


def _coverage_test(*, heading: str) -> str:
    """Read the scenario's registered consumer node from the heading registry."""
    rows = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    return next(row["test"] for row in rows if row["heading"] == heading)


def _no_sleep(*, seconds: float) -> None:
    """The canned cluster does not consume real time while it reports completion."""
    _ = seconds


def test_a_declared_cpu_above_every_committed_lane_is_refused_before_any_gate_job(
    *, tmp_path: Path
) -> None:
    """A consumer request one CPU above the file's largest lane is a pre-submit refusal."""
    lanes = committed_lanes(queue=_ROOT / _QUEUE)
    largest = largest_lane(lanes=lanes)
    declared = int(cast(Fraction, largest.cpu)) + 1
    repo = _consumer(tmp_path=tmp_path, table=f"gate_cpu = {declared}\n")
    cluster = _GateCluster()

    verdict = run_delegated_gate(
        repo_root=repo, renderer=repo / _RENDERER, runner=cluster, sleeper=_no_sleep
    )

    facts = [
        verdict.state == GATE_NO_VERDICT,
        verdict.refuses_push,
        f"gate_cpu = {declared}" in verdict.detail,
        largest.name in verdict.detail,
        f"{largest.cpu_text} CPU" in verdict.detail,
        f"{largest.memory_text} memory" in verdict.detail,
        not cluster.issued(needle="create"),
        _coverage_test(heading=_OVERSIZED_HEADING) == _OVERSIZED_TEST,
    ]
    assert facts == [True] * len(facts)


def test_a_consumer_without_cpu_or_memory_submits_at_default_size_despite_an_unreadable_queue(
    *, tmp_path: Path
) -> None:
    """Neither a missing nor an invalid queue file blocks a default-sized consumer Job."""
    defaults = _DEFAULTS.search((_ROOT / _RENDERER).read_text(encoding="utf-8"))
    assert defaults is not None
    expected_request = f"requests: {{cpu: {defaults.group(1)}, memory: {defaults.group(2)}}}"
    submitted: list[str] = []
    for name, queue_text in (("absent", None), ("unparseable", "kind: [unclosed\n")):
        repo = _consumer(tmp_path=tmp_path / name, table="")
        queue = repo / _QUEUE
        if queue_text is None:
            queue.unlink()
        else:
            _ = queue.write_text(queue_text, encoding="utf-8")
        cluster = _GateCluster()

        verdict = run_delegated_gate(
            repo_root=repo, renderer=repo / _RENDERER, runner=cluster, sleeper=_no_sleep
        )

        assert verdict.refuses_push is False
        assert not [argv for argv in cluster.issued(needle="--cpu")]
        assert not [argv for argv in cluster.issued(needle="--memory")]
        submitted.extend(cluster.submitted_manifests())
    assert [expected_request in manifest for manifest in submitted] == [True, True]
    assert _coverage_test(heading=_UNREADABLE_HEADING) == _UNREADABLE_TEST
