"""Artifact validation for Claude plugin install records."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Protocol, cast

__all__: list[str] = [
    "ArtifactReader",
    "CacheDirRemover",
    "artifact_record_findings",
    "artifact_record_repair_paths",
    "plugin_artifact_findings",
    "remove_plugin_cache_dir",
]


class ArtifactReader(Protocol):
    """Callable seam confirming the artifact named by one install record."""

    def __call__(self, *, install_path: str) -> tuple[str, ...]: ...


class CacheDirRemover(Protocol):
    """Callable seam removing one invalid plugin cache directory."""

    def __call__(self, *, install_path: str) -> tuple[str, ...]: ...


def plugin_artifact_findings(*, install_path: str) -> tuple[str, ...]:
    """Findings for the plugin build directory named by an install record."""
    path = Path(install_path)
    if not path.is_dir():
        return (f"installPath {install_path} does not exist or is not a directory",)
    manifest = path / "plugin.json"
    if not manifest.is_file() or not os.access(manifest, os.R_OK):
        return (f"installPath {install_path} has no readable plugin.json",)
    return _cache_manifest_findings(install_path=install_path, path=path)


def _cache_manifest_findings(*, install_path: str, path: Path) -> tuple[str, ...]:
    """Findings for required cache content declared by `cache-manifest.json`."""
    manifest = path / "cache-manifest.json"
    if not manifest.is_file():
        return ()
    parsed = json.loads(manifest.read_text(encoding="utf-8"))
    raw_paths = (
        cast("dict[str, object]", parsed).get("required_paths", ())
        if isinstance(parsed, dict)
        else ()
    )
    findings: list[str] = []
    for raw_path in cast("tuple[object, ...] | list[object]", raw_paths):
        if not isinstance(raw_path, str) or not _is_relative_manifest_path(raw_path=raw_path):
            findings.append(f"installPath {install_path} cache-manifest.json has invalid path")
            continue
        if not (path / raw_path).exists():
            findings.append(f"installPath {install_path} is missing required path {raw_path}")
    return tuple(findings)


def _is_relative_manifest_path(*, raw_path: str) -> bool:
    """Whether a cache-manifest path names non-empty content below the cache root."""
    candidate = Path(raw_path)
    return raw_path != "" and not candidate.is_absolute() and ".." not in candidate.parts


def remove_plugin_cache_dir(*, install_path: str) -> tuple[str, ...]:
    """Delete one invalid Claude plugin cache dir, refusing paths outside cache."""
    path = Path(install_path).resolve()
    cache_root = (Path.home() / ".claude" / "plugins" / "cache").resolve()
    if path == cache_root or os.path.commonpath((str(cache_root), str(path))) != str(cache_root):
        return (f"refusing to delete installPath {install_path} outside {cache_root}",)
    shutil.rmtree(path, ignore_errors=True)
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


def artifact_record_repair_paths(
    *, records: tuple[dict[str, object], ...], read_artifact: ArtifactReader
) -> tuple[str, ...]:
    """Install paths to remove when every project record names a broken artifact."""
    repair_paths: list[str] = []
    for record in records:
        install_path = cast("str", record.get("installPath"))
        if not read_artifact(install_path=install_path):
            return ()
        repair_paths.append(install_path)
    return tuple(repair_paths)
