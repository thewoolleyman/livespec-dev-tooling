"""Lane capacity: a declared gate request no committed gates-cq lane admits is refused (yznwz7).

contracts.md "Delegated pre-push gate", Declared gate resources, Lane
capacity (v192). Every threshold here is DERIVED from the committed
`cluster-queue-gates.yaml`, never stated as a literal, per "Tests never pin
committed configuration values".
"""

from __future__ import annotations

import importlib
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from returns.pipeline import is_successful

from livespec_dev_tooling._gate_remote_assembly import (
    declared_gate_job_resources,
    refuses_declaration,
)

__all__: list[str] = []

_ROOT = Path(__file__).parents[2]
_MODULE_PATH = _ROOT / "livespec_dev_tooling" / "_gate_lane_capacity.py"
_QUEUE = Path("ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml")
_RENDERER = Path("ci-runner/k3s/phase2/gates/render-gate-job.sh")


def _module() -> Any:
    """Import the seam only after the Red assertion has run."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module("livespec_dev_tooling._gate_lane_capacity")


def _committed_lanes() -> list[tuple[str, Fraction, Fraction, str, str]]:
    """(name, cpu, memory, cpu text, memory text) of every committed gates-cq flavor."""
    module = _module()
    return [
        (lane.name, lane.cpu, lane.memory, lane.cpu_text, lane.memory_text)
        for lane in module.committed_lanes(queue=_ROOT / _QUEUE)
    ]


def _consumer(
    tmp_path: Path, *, table: str, in_tree: bool = True, queue_text: str | None = None
) -> Path:
    """A consuming repository with this table and, in-tree, the committed renderer and queue."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    _ = (tmp_path / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\n{table}", encoding="utf-8"
    )
    if in_tree:
        renderer = tmp_path / _RENDERER
        renderer.parent.mkdir(parents=True)
        _ = shutil.copy(_ROOT / _RENDERER, renderer)
        queue = tmp_path / _QUEUE
        queue.parent.mkdir(parents=True)
        text = (_ROOT / _QUEUE).read_text(encoding="utf-8") if queue_text is None else queue_text
        _ = queue.write_text(text, encoding="utf-8")
    return tmp_path


def test_a_declared_cpu_above_every_lane_is_refused_naming_the_key_value_and_largest_lane(
    *, tmp_path: Path
) -> None:
    """One more cpu than the largest committed lane is refused before any Job, as a declaration refusal."""
    lanes = _committed_lanes()
    name, cpu, _memory, cpu_text, memory_text = max(lanes, key=lambda lane: (lane[1], lane[2]))
    declared = int(cpu) + 1
    repo = _consumer(tmp_path, table=f"gate_cpu = {declared}\n")

    refused = declared_gate_job_resources(repo_root=repo)

    assert not is_successful(refused)
    detail = refused.failure().detail
    facts = [
        refuses_declaration(failure=refused.failure()),
        f"gate_cpu = {declared}" in detail,
        name in detail,
        f"{cpu_text} CPU" in detail,
        memory_text in detail,
    ]
    assert facts == [True] * 5


def test_a_declared_request_that_fits_a_lane_is_passed_to_the_renderer(*, tmp_path: Path) -> None:
    """A request inside the largest lane is not refused, and its flags reach the renderer."""
    repo = _consumer(tmp_path, table='gate_cpu = 1\ngate_memory = "1Gi"\n')
    assert declared_gate_job_resources(repo_root=repo).unwrap() == ("--cpu", "1", "--memory", "1Gi")


def test_a_declared_memory_above_every_lane_is_refused(*, tmp_path: Path) -> None:
    """Memory is compared by value: one MiB more than the largest committed memory quota is refused."""
    largest = max(lane[2] for lane in _committed_lanes())
    declared = f"{int(largest) // 2**20 + 1}Mi"
    repo = _consumer(tmp_path, table=f'gate_memory = "{declared}"\n')
    refused = declared_gate_job_resources(repo_root=repo)
    assert not is_successful(refused)
    assert f"gate_memory = {declared}" in refused.failure().detail


def test_a_declaration_compares_the_renderer_default_for_the_undeclared_key(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A memory-only declaration is compared with the renderer's default cpu, read from the packaged copy.

    The repository carries no ci-runner tree, so the packaged queue file and
    renderer are the ones read; the packaged lane here holds less cpu than the
    renderer's default, so the small memory request is still refused.
    """
    module = _module()
    packaged = tmp_path / "packaged"
    packaged.mkdir()
    queue = packaged / "cluster-queue-gates.yaml"
    _ = queue.write_text(_queue(flavors=[("tiny-flavor", "1", "64Gi")]), encoding="utf-8")
    _ = shutil.copy(_ROOT / _RENDERER, packaged / "render-gate-job.sh")
    monkeypatch.setattr(module, "GATES_QUEUE_PACKAGED", queue)
    monkeypatch.setattr(module, "RENDERER_PACKAGED", packaged / "render-gate-job.sh")
    repo = _consumer(tmp_path / "repo", table='gate_memory = "1Gi"\n', in_tree=False)

    refused = declared_gate_job_resources(repo_root=repo)

    assert not is_successful(refused)
    assert "tiny-flavor with 1 CPU and 64Gi memory" in refused.failure().detail


def test_a_declaring_repository_whose_queue_file_cannot_be_parsed_is_refused_naming_the_file(
    *, tmp_path: Path
) -> None:
    """An unparseable queue file refuses a declaring repository, naming that file."""
    repo = _consumer(tmp_path, table="gate_cpu = 1\n", queue_text="kind: [unclosed\n")
    refused = declared_gate_job_resources(repo_root=repo)
    assert not is_successful(refused)
    assert str(repo / _QUEUE) in refused.failure().detail


def test_a_declaring_repository_whose_queue_file_is_absent_is_refused_naming_the_file(
    *, tmp_path: Path
) -> None:
    """An absent queue file is one the client cannot read, so a declaring repository is refused."""
    repo = _consumer(tmp_path, table="gate_cpu = 1\n")
    (repo / _QUEUE).unlink()
    refused = declared_gate_job_resources(repo_root=repo)
    assert not is_successful(refused)
    assert str(repo / _QUEUE) in refused.failure().detail


@pytest.mark.parametrize(
    "queue_text",
    [
        "--- just a scalar\n",
        "kind: ClusterQueue\nmetadata: {name: gates-cq}\nspec: {resourceGroups: not-a-list}\n",
        "kind: ClusterQueue\nmetadata: {name: gates-cq}\nspec:\n  resourceGroups:\n"
        "  - flavors:\n    - name: odd-flavor\n      resources:\n"
        "      - {name: cpu, nominalQuota: lots}\n      - {name: memory, nominalQuota: 1Gi}\n",
    ],
)
def test_a_queue_file_with_no_readable_gates_cq_lane_refuses_a_declaring_repository(
    *, tmp_path: Path, queue_text: str
) -> None:
    """No gates-cq flavor with two readable quotas is a file the client cannot parse."""
    repo = _consumer(tmp_path, table="gate_cpu = 1\n", queue_text=queue_text)
    refused = declared_gate_job_resources(repo_root=repo)
    assert not is_successful(refused)
    assert "cannot read or parse" in refused.failure().detail


def test_a_repository_declaring_no_cpu_or_memory_is_never_compared(*, tmp_path: Path) -> None:
    """gate_parallelism alone is passed on even when the queue file is absent."""
    repo = _consumer(tmp_path, table="gate_parallelism = 8\n")
    (repo / _QUEUE).unlink()
    assert declared_gate_job_resources(repo_root=repo).unwrap() == ("--parallelism", "8")


def test_an_unreadable_renderer_default_refuses_a_partial_declaration(*, tmp_path: Path) -> None:
    """With no readable default for the undeclared key, nothing can be compared, so it refuses."""
    repo = _consumer(tmp_path, table="gate_cpu = 1\n")
    _ = (repo / _RENDERER).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    refused = declared_gate_job_resources(repo_root=repo)
    assert not is_successful(refused)
    assert str(repo / _RENDERER) in refused.failure().detail


def test_the_largest_lane_breaks_a_cpu_tie_by_memory_and_then_by_file_order(
    *, tmp_path: Path
) -> None:
    """The refusal names the greatest cpu, then the greater memory, then the first in the file."""
    module = _module()
    by_memory = tmp_path / "by-memory.yaml"
    _ = by_memory.write_text(
        _queue(flavors=[("small", "4", "8Gi"), ("big", "4", "16Gi")]), encoding="utf-8"
    )
    by_order = tmp_path / "by-order.yaml"
    _ = by_order.write_text(
        _queue(flavors=[("first", "4", "8Gi"), ("second", "4", "8Gi")]), encoding="utf-8"
    )
    named = [
        module.largest_lane(lanes=module.committed_lanes(queue=queue)).name
        for queue in (by_memory, by_order)
    ]
    assert named == ["big", "first"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (15, Fraction(15)),
        ("14500m", Fraction(29, 2)),
        ("1.5", Fraction(3, 2)),
        ("24Gi", Fraction(24 * 2**30)),
        ("48G", Fraction(48 * 10**9)),
        ("3Xi", None),
        ("lots", None),
    ],
)
def test_a_quantity_is_read_by_value_not_spelling(
    *, value: object, expected: Fraction | None
) -> None:
    """Kubernetes quantities compare by value, so `15`, `14500m` and `24Gi` each mean their number."""
    assert _module().quantity(value=value) == expected


def test_a_declaration_is_refused_when_no_single_lane_admits_both_its_cpu_and_memory(
    *, tmp_path: Path
) -> None:
    """One lane must hold both quotas: a cpu-rich lane and a memory-rich lane together do not admit it.

    Lane A has the cpu but too little memory; lane B has the memory but too
    little cpu. Each dimension fits SOME lane, and no lane fits both, so the
    declaration is refused. The committed lanes grow cpu and memory together,
    so only a constructed file can tell a single-lane rule from two
    independent any-lane checks.
    """
    queue_text = _queue(flavors=[("cpu-rich", "8", "2Gi"), ("memory-rich", "2", "32Gi")])
    repo = _consumer(tmp_path, table='gate_cpu = 4\ngate_memory = "16Gi"\n', queue_text=queue_text)

    refused = declared_gate_job_resources(repo_root=repo)

    assert not is_successful(refused)
    facts = [
        refuses_declaration(failure=refused.failure()),
        "gate_cpu = 4, gate_memory = 16Gi" in refused.failure().detail,
        "cpu-rich with 8 CPU and 2Gi memory" in refused.failure().detail,
    ]
    assert facts == [True] * 3


def test_the_packaged_queue_file_and_renderer_are_the_ones_the_wheel_ships() -> None:
    """The packaged paths are the destinations of the wheel's `force-include` table.

    A consumer carries no `ci-runner/` tree, so the client reads the copies
    under `livespec_dev_tooling/gates/`. The mapping is read off
    `pyproject.toml` rather than restated, so dropping the force-include line
    for the queue file fails here instead of refusing every declaring consumer
    over a file the package does not carry.
    """
    module = _module()
    declaration = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    facts = [
        module.GATES_QUEUE_PACKAGED.as_posix().endswith(
            "livespec_dev_tooling/gates/cluster-queue-gates.yaml"
        ),
        module.RENDERER_PACKAGED.as_posix().endswith(
            "livespec_dev_tooling/gates/render-gate-job.sh"
        ),
        f'"{_QUEUE.as_posix()}" = "livespec_dev_tooling/gates/cluster-queue-gates.yaml"'
        in declaration,
        f'"{_RENDERER.as_posix()}" = "livespec_dev_tooling/gates/render-gate-job.sh"'
        in declaration,
    ]
    assert facts == [True] * 4


def test_a_repository_declaring_no_cpu_or_memory_is_not_refused_over_an_unparseable_queue_file(
    *, tmp_path: Path
) -> None:
    """A present but unparseable queue file is never read for a repository declaring neither key."""
    repo = _consumer(tmp_path, table="gate_parallelism = 8\n", queue_text="kind: [unclosed\n")
    assert declared_gate_job_resources(repo_root=repo).unwrap() == ("--parallelism", "8")


def _queue(*, flavors: list[tuple[str, str, str]]) -> str:
    """A minimal multi-document queue file with a gates-cq ClusterQueue over these flavors."""
    rendered = "".join(
        f"    - name: {name}\n      resources:\n"
        f"      - {{name: cpu, nominalQuota: {cpu}}}\n"
        f"      - {{name: memory, nominalQuota: {memory}}}\n"
        for name, cpu, memory in flavors
    )
    return (
        "apiVersion: kueue.x-k8s.io/v1beta1\nkind: ResourceFlavor\nmetadata: {name: x}\n---\n"
        "apiVersion: kueue.x-k8s.io/v1beta1\nkind: ClusterQueue\nmetadata: {name: gates-cq}\n"
        f"spec:\n  resourceGroups:\n  - coveredResources: [cpu, memory]\n    flavors:\n{rendered}"
    )
