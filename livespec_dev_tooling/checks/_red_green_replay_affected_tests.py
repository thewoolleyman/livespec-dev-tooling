"""Factory-sandbox evidence qualification for suite-green replay."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from livespec_dev_tooling.affected_tests_record import AffectedTestsEvidence

__all__: list[str] = ["qualifying_affected_tests_evidence", "sandbox_exempt", "scope_from_evidence"]


def sandbox_exempt(*, cwd: Path, run: Callable[..., subprocess.CompletedProcess[str]]) -> bool:
    """Return whether this checkout explicitly permits factory-only scope reuse."""
    try:
        result = run(
            ["git", "config", "--bool", "--get", "livespec.sandboxExempt"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def qualifying_affected_tests_evidence(
    *,
    cwd: Path,
    index_tree: str | None,
    sandbox: Callable[..., bool],
    read_evidence: Callable[..., AffectedTestsEvidence | None],
) -> AffectedTestsEvidence | None:
    """Return scoped evidence only when every sandbox reuse condition holds."""
    evidence = read_evidence(cwd=cwd)
    if (
        not sandbox(cwd=cwd)
        or index_tree is None
        or evidence is None
        or evidence.outcome != "passed"
        or not evidence.test_paths
        or evidence.tree_hash != index_tree
    ):
        return None
    return evidence


def scope_from_evidence(
    *,
    evidence: AffectedTestsEvidence | None,
    index_tree: str | None,
    fallback: Callable[[], tuple[str, list[str] | None]],
) -> tuple[str, list[str] | None, tuple[tuple[str, str], ...]]:
    """Return the affected scope only for a still-qualifying evidence record."""
    if (
        evidence is not None
        and evidence.outcome == "passed"
        and evidence.test_paths
        and evidence.tree_hash == index_tree
    ):
        return (
            "affected-tests",
            list(evidence.test_paths),
            (("TDD-Suite-Green-Producer", evidence.run_id),),
        )
    scope, selected_tests = fallback()
    return scope, selected_tests, ()
