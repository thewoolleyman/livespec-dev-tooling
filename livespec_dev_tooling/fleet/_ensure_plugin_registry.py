"""Registry reading half of `ensure_plugins`: install records, findings, repair paths.

Moved out of `ensure_plugins` unchanged so that module stays within the LLOC
ceiling while it grows the orchestrator hold. `project_install_records` is the
one reader of "which install records belong to this project", shared with the
hold decision in `_orchestrator_hold`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

# `returns` is VENDORED, not installed; this module reads the artifact seams'
# railway tracks directly, so it establishes the path itself.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._ensure_plugin_artifacts import (  # noqa: E402
    ArtifactOutcome,
    ArtifactReader,
    artifact_record_findings,
    artifact_record_repair_paths,
    plugin_artifact_findings,
)
from livespec_dev_tooling.fleet._plugin_settings import split_enablement  # noqa: E402

__all__: list[str] = [
    "project_install_records",
    "registry_findings",
    "registry_repair_paths",
]


def _records_for(*, registry: object, plugin: str) -> tuple[object, ...]:
    """Registry entries recorded for one plugin key."""
    if not isinstance(registry, dict):
        return ()
    plugins = cast("dict[str, object]", registry).get("plugins")
    if not isinstance(plugins, dict):
        return ()
    entries = cast("dict[str, object]", plugins).get(plugin)
    if not isinstance(entries, list):
        return ()
    return tuple(cast("list[object]", entries))


def project_install_records(
    *, registry: object, plugin: str, project_root: str
) -> tuple[dict[str, object], ...]:
    """Install records for one plugin in this project."""
    return tuple(
        cast("dict[str, object]", entry)
        for entry in _records_for(registry=registry, plugin=plugin)
        if isinstance(entry, dict)
        and cast("dict[str, object]", entry).get("projectPath") == project_root
    )


def _probe_findings(*, plugin: str, outcome: ArtifactOutcome) -> tuple[str, ...]:
    """Findings from an artifact probe that ANSWERED, or its failure rendered as one.

    A probe that could not decide is reported to the operator here rather than
    dropped: `main` turns any non-empty finding set into exit 4, so the
    unanswered case surfaces as loudly as a broken build while — because the
    failure never reaches `registry_repair_paths` as a path — authorizing no
    deletion of its own.
    """
    if isinstance(outcome, IOFailure):
        return (f"{plugin} {unsafe_perform_io(outcome.failure()).finding}",)
    return unsafe_perform_io(outcome.unwrap())


def registry_findings(
    *,
    settings_text: str,
    project_root: str,
    registry_text: str | None,
    read_artifact: ArtifactReader = plugin_artifact_findings,
) -> tuple[str, ...]:
    """Findings for enabled-vs-installed, keyed on `projectPath` and artifact content.

    A zero exit from a scoped plugin command does not establish which project's
    record it touched, so provisioning is confirmed against the record itself.
    The record is still a proxy for the build it names, so the matching
    `installPath` must also point at plugin content.
    """
    parsed = json.loads(settings_text)
    if not isinstance(parsed, dict):
        return (".claude/settings.json must contain a JSON object",)
    enabled, _, shape = split_enablement(
        raw=cast("dict[str, object]", parsed).get("enabledPlugins")
    )
    if shape is not None:
        return (shape,)
    registry = json.loads(registry_text) if registry_text is not None else None
    findings: list[str] = []
    for plugin in enabled:
        records = project_install_records(
            registry=registry, plugin=plugin, project_root=project_root
        )
        if not records:
            findings.append(
                f"{plugin} is enabled but has no install record for projectPath {project_root}"
            )
            continue
        findings.extend(
            _probe_findings(
                plugin=plugin,
                outcome=artifact_record_findings(
                    plugin=plugin,
                    records=records,
                    read_artifact=read_artifact,
                ),
            )
        )
    return tuple(findings)


def registry_repair_paths(
    *,
    settings_text: str,
    project_root: str,
    registry_text: str | None,
    read_artifact: ArtifactReader,
) -> tuple[str, ...]:
    """Failing install paths from enabled plugin records, deduplicated in registry order.

    A plugin whose probe did not answer contributes NOTHING. That is the whole
    reason the artifact seams carry a failure track: the paths returned here
    are deleted, and an unanswered probe has not established that there is
    anything to delete.
    """
    parsed = json.loads(settings_text)
    enabled, _, _ = split_enablement(raw=cast("dict[str, object]", parsed).get("enabledPlugins"))
    registry = json.loads(registry_text) if registry_text is not None else None
    paths: dict[str, None] = {}
    for plugin in enabled:
        records = project_install_records(
            registry=registry, plugin=plugin, project_root=project_root
        )
        outcome = artifact_record_repair_paths(records=records, read_artifact=read_artifact)
        if isinstance(outcome, IOFailure):
            continue
        for install_path in unsafe_perform_io(outcome.unwrap()):
            paths[install_path] = None
    return tuple(paths)
