"""Consumer-tier coverage for the declared and replay gate-Job resource scenarios."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from returns.result import Success

from livespec_dev_tooling.gate_remote_delegate import gate_remote_request
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RENDERER = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"
_QUEUE = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "kueue" / "cluster-queue-gates.yaml"
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_ORIGIN = "git@github.com:acme/widget.git"
_CPU_PARALLELISM_HEADING = (
    "## Scenario: a repository that declares gate_cpu 9 and gate_parallelism 8 gets a gate Job "
    "requesting 9 CPUs whose coverage run uses 8 xdist workers"
)


class _World:
    """Canned host commands with the real renderer as the consumer-visible seam."""

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (stdin, stream)
        if argv[0] == str(_RENDERER):
            completed = subprocess.run(
                argv, cwd=str(cwd), capture_output=True, text=True, check=False
            )
            return Success(
                GateCommandResult(
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )
        stdout = (
            f"{_TREE}\n" if "rev-parse" in argv else f"{_ORIGIN}\n" if "get-url" in argv else ""
        )
        return Success(GateCommandResult(returncode=0, stdout=stdout, stderr=""))


def _consumer(*, tmp_path: Path, declaration: str) -> Path:
    """Create a fixture consumer whose own configuration the client reads."""
    root = tmp_path / "widget"
    root.mkdir()
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(
        "jobs:\n  test:\n    runs-on: self-hosted\n    container:\n"
        "      image: ghcr.io/example/sandbox:python-v1.11.1\n",
        encoding="utf-8",
    )
    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n" + declaration,
        encoding="utf-8",
    )
    fixture_renderer = root / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"
    fixture_queue = root / "ci-runner" / "k3s" / "phase2" / "kueue" / "cluster-queue-gates.yaml"
    fixture_renderer.parent.mkdir(parents=True)
    fixture_queue.parent.mkdir(parents=True)
    _ = fixture_renderer.write_text(_RENDERER.read_text(encoding="utf-8"), encoding="utf-8")
    _ = fixture_queue.write_text(_QUEUE.read_text(encoding="utf-8"), encoding="utf-8")
    return root


def _gate_job(*, root: Path) -> dict[object, object]:
    """Render one fixture consumer through the shipped client's request seam."""
    built = gate_remote_request(repo_root=root, renderer=_RENDERER, runner=_World())
    assert isinstance(built, Success)
    return next(document for document in yaml.safe_load_all(built.unwrap().manifest) if document)


def _registered_test(*, heading: str) -> str:
    """Read the scenario registry exactly as its coverage checker does."""
    rows = json.loads((_REPO_ROOT / "tests" / "heading-coverage.json").read_text(encoding="utf-8"))
    return next(row["test"] for row in rows if row["heading"] == heading)


def test_declared_cpu_and_parallelism_render_into_the_gate_job_and_coverage_worker_count(
    *, tmp_path: Path
) -> None:
    """A consumer's declared resources reach its rendered Job and coverage command."""
    root = _consumer(
        tmp_path=tmp_path,
        declaration="delegated_gate = true\ngate_cpu = 9\ngate_parallelism = 8\n",
    )
    job = _gate_job(root=root)
    gate = next(
        container
        for container in job["spec"]["template"]["spec"]["containers"]
        if container["name"] == "gate"
    )
    env = {entry["name"]: entry["value"] for entry in gate["env"] if "value" in entry}

    assert gate["resources"] == {
        "requests": {"cpu": "9", "memory": "6Gi"},
        "limits": {"memory": "6Gi"},
    }
    assert env["LIVESPEC_TEST_PARALLELISM"] == "8"
    assert 'pytest -n "${test_nprocs}"' in (
        _REPO_ROOT / "scripts" / "just" / "check-per-file-coverage.sh"
    ).read_text(encoding="utf-8")
    assert _registered_test(heading=_CPU_PARALLELISM_HEADING) == (
        "tests.consumer.test_gate_job_resource_scenarios."
        "test_declared_cpu_and_parallelism_render_into_the_gate_job_and_coverage_worker_count"
    )
