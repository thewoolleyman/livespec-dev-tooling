"""The exact files each release-keyed incident surface is served from.

A release-keyed row (a gate-reader or template row of a consumer that serves from its
own checkout) classifies only while ITS surface is unchanged since the release its claim
names. A surface is never the whole tree: this repository's master moves many times an
hour, so a tree-wide identity check would leave every row unclassifiable by another route.

Each surface starts from its roots, the seams `research/002-override-surface-inventory.md`
of plan expedited-incident-response-flag names for it in this repository (the gate's
module and declared inputs, or the template's workflow files). The surface is the roots
plus everything they reach inside this package:

- a Python module's `livespec_dev_tooling` imports, each with its parent packages;
- a script's, recipe's or workflow's `-m livespec_dev_tooling...` invocations;
- a workflow's local `uses: ./.github/...` workflows and composite actions.

Where the inventory names a seam owned by another repository, the root is the file of
this package that the surface's incident behaviour passes through here. The table is
pinned by a test, so a change to any surface's roots is a reviewed change.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping
from types import MappingProxyType

__all__: list[str] = ["SURFACE_ROOTS", "surface_files"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ri2lwi
_PACKAGE = "livespec_dev_tooling"
_P = f"{_PACKAGE}/"
_MODULE_RUN = re.compile(rf"-m\s+({_PACKAGE}(?:\.\w+)+)")
_LOCAL_USES = re.compile(r"uses:\s*[\"']?\./(\.github/[^\s\"'#@]+)")
_WORKFLOW_SUFFIXES = (".yml", ".yaml")

SURFACE_ROOTS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        # gate readers: this package as the consumer's gates run it
        "Pre-commit before mode selection": (
            "scripts/just/check-pre-commit.sh",
            "scripts/just/lint-autofix-staged.sh",
            f"{_P}workflow_checks/staged_precheck.py",
        ),
        "Commit-msg and TDD": (
            f"{_P}checks/red_green_replay.py",
            f"{_P}commit_replay_delegate.py",
            f"{_P}shipped_path_release_guard_check.py",
        ),
        "Pre-push": ("scripts/just/check-pre-push.sh", f"{_P}green_token.py"),
        "Explicit commands and parallel aggregation": (
            "scripts/just/check.sh",
            "scripts/just/check-changed.sh",
            "scripts/just/check-scoped.sh",
            f"{_P}parallel_check_dispatcher.py",
        ),
        "Fast-gate timing": (f"{_P}incident_gate_inventory.py", f"{_P}incident_local_gates.py"),
        "Focused test selection": (
            f"{_P}incident_focused_admission.py",
            f"{_P}_incident_focused_scope.py",
        ),
        "Touched-file coverage": (
            f"{_P}checks/check_coverage_incremental.py",
            f"{_P}checks/per_file_coverage.py",
        ),
        "Full coverage producers/consumers": (
            "scripts/just/check-per-file-coverage.sh",
            "scripts/just/check-coverage.sh",
            f"{_P}checks/pbt_coverage_pure_modules.py",
        ),
        "Normal evidence caches": (
            "scripts/just/coverage-reuse-id.sh",
            f"{_P}green_token.py",
            f"{_P}_green_token_evidence.py",
        ),
        "Delegated pre-commit": (f"{_P}pre_commit_delegate.py", f"{_P}_gate_host_authority.py"),
        "Delegated push/replay/explicit gates": (
            f"{_P}gate_remote_delegate.py",
            f"{_P}gate_runner_delegate.py",
            f"{_P}commit_replay_delegate.py",
        ),
        "Parity/completeness enforcement": (
            f"{_P}checks/ci_gate_parity.py",
            f"{_P}checks/aggregate_completeness.py",
            f"{_P}checks/ci_matrix_completeness.py",
            f"{_P}checks/canonical_recipe_fidelity.py",
        ),
        "Spec enforcement and debt": (
            f"{_P}checks/heading_coverage.py",
            f"{_P}checks/heading_coverage_debt_register.py",
            f"{_P}checks/no_todo_registry.py",
        ),
        "PR factory provenance": (f"{_P}factory_provenance_gate.py",),
        "Retrospective bypass audit": (
            f"{_P}_incident_provenance_protocol.py",
            f"{_P}checks/_red_green_replay_incident.py",
        ),
        "Branch/PR resolution": (f"{_P}incident_execution.py",),
        "Acceptance and completion": (f"{_P}incident_run_evidence.py",),
        "Normal master context": (f"{_P}incident_execution.py", f"{_P}incident_trusted_origin.py"),
        "Closure/proof/archive": (f"{_P}incident_run_evidence.py", f"{_P}incident_hook_receipt.py"),
        # templates: the workflow files the consumer's CI runs
        "Gate renderer and pod": (
            "ci-runner/k3s/phase2/gates/render-gate-job.sh",
            "ci-runner/k3s/phase2/gates/gate-job-template.yaml",
        ),
        "PR mode transport": (".github/workflows/incident-label-ci.yml",),
        "CI matrix/batch/direct action": (
            ".github/workflows/ci.yml",
            ".github/workflows/reusable-check-matrix.yml",
            ".github/actions/run-check/action.yml",
        ),
        "CI dependency/aggregate/merge context": (".github/workflows/ci.yml",),
        "Release and distribution": (
            ".github/workflows/release-please.yml",
            ".github/workflows/release-dispatch.yml",
            ".github/workflows/reusable-release-dispatch.yml",
        ),
        "Generated projects": (".github/workflows/fleet-conformance.yml",),
    }
)


def _module_file(*, name: str, read: Callable[[str], str | None]) -> str | None:
    base = name.replace(".", "/")
    return next((p for p in (f"{base}.py", f"{base}/__init__.py") if read(p) is not None), None)


def _python_names(*, text: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names |= {node.module, *(f"{node.module}.{alias.name}" for alias in node.names)}
    return {name for name in names if name.split(".")[0] == _PACKAGE}


def _reached(*, path: str, text: str, read: Callable[[str], str | None]) -> list[str]:
    if path.endswith(".py"):
        names = _python_names(text=text)
        uses: list[str] = []
    else:
        names = set(_MODULE_RUN.findall(text))
        uses = [
            use if use.endswith(_WORKFLOW_SUFFIXES) else f"{use.rstrip('/')}/action.yml"
            for use in _LOCAL_USES.findall(text)
        ]
    modules = {
        found
        for name in names
        for depth in range(1, name.count(".") + 2)
        if (found := _module_file(name=".".join(name.split(".")[:depth]), read=read))
    }
    return [*uses, *sorted(modules)]


def surface_files(
    *, roots: tuple[str, ...], read: Callable[[str], str | None]
) -> tuple[frozenset[str], tuple[str, ...]]:
    """The surface's files, and every root or local workflow reference that is absent."""
    seen: set[str] = set()
    absent: list[str] = []
    pending = list(roots)
    while pending:
        path = pending.pop()
        if path in seen or path in absent:
            continue
        text = read(path)
        if text is None:
            absent.append(path)
            continue
        seen.add(path)
        pending.extend(_reached(path=path, text=text, read=read))
    return frozenset(seen), tuple(sorted(absent))
