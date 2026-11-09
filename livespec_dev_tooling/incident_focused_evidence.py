"""Collect isolated incident proof without minting normal validation evidence.

The caller supplies the shared resolver's ExecutionContext. This collector
never interprets flags or grants incident authority. Its output is evidence,
not a green token, TDD receipt or lifecycle state.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from livespec_dev_tooling._incident_focused_measurement import measure
from livespec_dev_tooling._incident_focused_scope import (
    changed_paths,
    classify,
    exact_tree,
    preflight,
    scoped_path,
    select_tests,
)
from livespec_dev_tooling._incident_focused_types import (
    FocusedScope,
    Identity,
    ManualReproduction,
    Measurement,
    ResolvedContext,
)
from livespec_dev_tooling.config import ConfigParseError
from livespec_dev_tooling.incident_git import IncidentGitError

__all__: list[str] = ["FocusedScope", "ManualReproduction", "collect_focused_evidence"]

_FULL_COVERAGE = 100


def _evidence(
    *,
    repo_root: Path,
    identity: Identity,
    scope: FocusedScope,
    manual: ManualReproduction,
    measurement: Measurement,
) -> dict[str, object]:
    tests, report, coverage = measurement.tests, measurement.report, measurement.coverage
    dispositions = measurement.dispositions
    risks = [
        f"coverage incomplete: {name}"
        for name, row in coverage.items()
        if row.get("summary", {}).get("percent_covered", 0) < _FULL_COVERAGE
    ]
    if not exact_tree(repo_root=repo_root, identity=identity, tree_hash=scope.tree_hash):
        risks.append("incident tree changed during collection")
    risks.extend(
        f"unsupported executable coverage: {name}"
        for name, disposition in dispositions.items()
        if disposition == "unsupported-executable"
    )
    risks.extend(f"deferred test: {name}: {reason}" for name, reason in scope.deferred_tests)
    if tests["timed_out"] or report["timed_out"] or report["returncode"]:
        risks.append("focused test or coverage collection incomplete")
    if manual.outcome != "passed":
        risks.append("manual reproduction did not pass")
    outcome = (
        "failed"
        if (tests["returncode"] and not tests["timed_out"]) or manual.outcome == "failed"
        else "incomplete"
        if risks
        else "passed"
    )
    evidence: dict[str, object] = {
        "mode": "expedited-repair",
        "scope": "focused-tests-and-touched-files",
        "tree_hash": scope.tree_hash,
        "identity": {
            name: getattr(identity, name)
            for name in (
                "incident_item_id",
                "attempt_id",
                "phase",
                "repository",
                "base_sha",
                "head_sha",
                "operation_id",
            )
        },
        "paths": dispositions,
        "selection": {
            "tests": sorted(measurement.selected),
            "related_test_reason": scope.related_test_reason,
            "deferred_tests": dict(scope.deferred_tests),
        },
        "manual": asdict(manual),
        "tests": tests,
        "coverage_command": report,
        "coverage": coverage,
        "risks": risks,
        "outcome": outcome,
    }
    evidence["evidence_key"] = hashlib.sha256(
        json.dumps(
            {key: evidence[key] for key in ("mode", "scope", "tree_hash", "identity", "selection")},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return evidence


def _collect_focused_evidence(
    *, repo_root: Path, context: ResolvedContext, scope: FocusedScope, manual: ManualReproduction
) -> dict[str, object]:
    """Measure exact staged scope; refusals are explicit, never empty success."""
    identity = context.identity
    if context.mode != "expedited-repair" or identity is None:
        return {"outcome": "refused", "reason": "resolved expedited repair context required"}
    reason = preflight(repo_root=repo_root, identity=identity, scope=scope)
    if reason:
        return {"outcome": "refused", "reason": reason}
    paths = changed_paths(repo_root=repo_root, identity=identity, scope=scope)
    if any(
        scoped_path(root=repo_root, name=name) is None for name in paths | set(scope.related_tests)
    ):
        return {"outcome": "refused", "reason": "scope escapes repository"}
    dispositions = {
        name: classify(path=repo_root / name, name=name, source_prefixes=scope.source_prefixes)
        for name in sorted(paths)
    }
    selected = select_tests(
        repo_root=repo_root, paths=paths, dispositions=dispositions, scope=scope
    )
    if isinstance(selected, str):
        return {"outcome": "refused", "reason": selected}
    if not all((manual.procedure.strip(), manual.expected.strip(), manual.observed.strip())):
        return {"outcome": "refused", "reason": "manual reproduction is incomplete"}
    executable = [name for name, disposition in dispositions.items() if disposition == "executable"]
    tests, report, coverage = measure(
        repo_root=repo_root, selected=selected, executable=executable, timeout=scope.timeout
    )
    return _evidence(
        repo_root=repo_root,
        identity=identity,
        scope=scope,
        manual=manual,
        measurement=Measurement(
            selected=selected,
            dispositions=dispositions,
            tests=tests,
            report=report,
            coverage=coverage,
        ),
    )


def collect_focused_evidence(
    *, repo_root: Path, context: ResolvedContext, scope: FocusedScope, manual: ManualReproduction
) -> dict[str, object]:
    """Return measured proof or a named refusal when collection cannot be established."""
    try:
        return _collect_focused_evidence(
            repo_root=repo_root, context=context, scope=scope, manual=manual
        )
    except (
        OSError,
        ConfigParseError,
        subprocess.SubprocessError,
        IncidentGitError,
        SyntaxError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        return {"outcome": "refused", "reason": f"focused evidence unavailable: {exc}"}
