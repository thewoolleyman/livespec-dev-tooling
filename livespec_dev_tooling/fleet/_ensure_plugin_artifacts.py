"""Artifact validation for Claude plugin install records."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "ArtifactReader",
    "artifact_record_findings",
    "plugin_artifact_findings",
]


class ArtifactReader(Protocol):
    """Callable seam confirming the artifact named by one install record."""

    def __call__(self, *, install_path: str) -> tuple[str, ...]: ...


def plugin_artifact_findings(*, install_path: str) -> tuple[str, ...]:
    """Findings for the plugin build directory named by an install record."""
    path = Path(install_path)
    if not path.is_dir():
        return (f"installPath {install_path} does not exist or is not a directory",)
    manifest = path / "plugin.json"
    if not manifest.is_file() or not os.access(manifest, os.R_OK):
        return (f"installPath {install_path} has no readable plugin.json",)
    return ()


def artifact_record_findings(
    *, plugin: str, records: tuple[dict[str, object], ...], read_artifact: ArtifactReader
) -> tuple[str, ...]:
    """Findings proving that no project record names a usable plugin artifact."""
    findings: list[str] = []
    for record in records:
        install_path = record.get("installPath")
        if not isinstance(install_path, str) or not install_path:
            findings.append(f"{plugin} install record has no installPath")
            continue
        artifact_findings = read_artifact(install_path=install_path)
        if not artifact_findings:
            return ()
        findings.extend(f"{plugin} {finding}" for finding in artifact_findings)
    return tuple(findings)
