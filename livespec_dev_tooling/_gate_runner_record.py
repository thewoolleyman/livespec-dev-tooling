"""Persist cluster-gate evidence in the detached shell runner's record."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

__all__: list[str] = ["run_cluster_gate_cli"]


class _ClusterGateResult(Protocol):
    """The evidence the delegated client returns to the detached shell runner."""

    @property
    def exit_status(self) -> int: ...

    @property
    def tree_hash(self) -> str: ...

    @property
    def job_name(self) -> str: ...

    @property
    def namespace(self) -> str: ...

    @property
    def detail(self) -> str: ...


class _ClusterGateRunner(Protocol):
    """Run a cluster gate while accepting durable-record callbacks."""

    def __call__(
        self,
        *,
        repo_root: Path,
        command: tuple[str, ...],
        record_job: Callable[..., None],
        record_namespace: Callable[..., None],
    ) -> _ClusterGateResult: ...


def run_cluster_gate_cli(*, argv: list[str], repo_root: Path, runner: _ClusterGateRunner) -> int:
    """Persist remote evidence beside the shell runner's durable run record."""
    parser = argparse.ArgumentParser(prog="gate-runner-venue run")
    _ = parser.add_argument("--run-dir", type=Path, required=True)
    _ = parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args(argv[2:])
    command = tuple(arguments.command[1:]) if arguments.command[:1] == ["--"] else ()

    def record_job(*, name: str) -> None:
        _ = (arguments.run_dir / "job_name").write_text(f"{name}\n", encoding="utf-8")

    def record_namespace(*, name: str) -> None:
        _ = (arguments.run_dir / "namespace").write_text(f"{name}\n", encoding="utf-8")

    result = runner(
        repo_root=repo_root,
        command=command,
        record_job=record_job,
        record_namespace=record_namespace,
    )
    if result.tree_hash:
        _ = (arguments.run_dir / "tree_hash").write_text(f"{result.tree_hash}\n", encoding="utf-8")
    if result.job_name:
        record_job(name=result.job_name)
    if result.namespace:
        record_namespace(name=result.namespace)
    if result.detail:
        _ = sys.stderr.write(f"{result.detail}\n")
    return result.exit_status
