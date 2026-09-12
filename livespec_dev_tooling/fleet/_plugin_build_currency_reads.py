"""Readers for governed marketplace pins and Claude install records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from livespec_dev_tooling.fleet._plugin_build_currency_core import (
    BuildIdentifier,
    resolved_build,
    unresolved_build,
)
from livespec_dev_tooling.fleet._plugin_settings import (
    marketplace_of,
    split_enablement,
    vacuity_findings,
)

__all__: list[str] = [
    "GovernedPins",
    "PinnedSource",
    "governed_pins",
    "served_build_identifier",
]


@dataclass(frozen=True, kw_only=True)
class PinnedSource:
    """One enabled plugin paired with its marketplace repository and ref."""

    plugin: str
    marketplace: str
    repo: str
    ref: str
    unresolved: str


@dataclass(frozen=True, kw_only=True)
class GovernedPins:
    """The readable enabled pins, or one settings-level precondition finding."""

    sources: tuple[PinnedSource, ...]
    unreadable: str


def governed_pins(*, settings_text: str) -> GovernedPins:
    """Read enabled plugins and their locally resolvable marketplace pins."""
    try:
        parsed = json.loads(settings_text)
    except json.JSONDecodeError as unparseable:
        return GovernedPins(
            sources=(), unreadable=f".claude/settings.json is not JSON: {unparseable}"
        )
    if not isinstance(parsed, dict):
        return GovernedPins(
            sources=(), unreadable=".claude/settings.json must contain a JSON object"
        )
    settings = cast("dict[str, object]", parsed)
    findings = vacuity_findings(settings_text=settings_text, settings_label=".claude/settings.json")
    if findings:
        return GovernedPins(sources=(), unreadable="; ".join(findings))
    enabled, _disabled, _shape = split_enablement(raw=settings.get("enabledPlugins"))
    raw_marketplaces = settings.get("extraKnownMarketplaces")
    marketplaces = (
        cast("dict[str, object]", raw_marketplaces) if isinstance(raw_marketplaces, dict) else {}
    )
    return GovernedPins(
        sources=tuple(
            _pinned_source(plugin=plugin, marketplaces=marketplaces) for plugin in enabled
        ),
        unreadable="",
    )


def _pinned_source(*, plugin: str, marketplaces: dict[str, object]) -> PinnedSource:
    """Pair one enablement with its marketplace source, preserving bad pins."""
    marketplace = marketplace_of(plugin=plugin)
    entry = marketplaces.get(marketplace)
    source = cast("dict[str, object]", entry).get("source") if isinstance(entry, dict) else None
    if not isinstance(source, dict):
        return PinnedSource(
            plugin=plugin,
            marketplace=marketplace,
            repo="",
            ref="",
            unresolved=f"marketplace {marketplace!r} declares no source for marketplace",
        )
    source_fields = cast("dict[str, object]", source)
    raw_repo = source_fields.get("repo")
    raw_ref = source_fields.get("ref")
    repo = raw_repo.strip() if isinstance(raw_repo, str) else ""
    ref = raw_ref.strip() if isinstance(raw_ref, str) else ""
    if repo == "" or ref == "":
        return PinnedSource(
            plugin=plugin,
            marketplace=marketplace,
            repo=repo,
            ref=ref,
            unresolved=f"marketplace {marketplace!r} declares no repo and ref pair",
        )
    return PinnedSource(
        plugin=plugin,
        marketplace=marketplace,
        repo=repo,
        ref=ref,
        unresolved="",
    )


def served_build_identifier(
    *, registry_text: str | None, plugin: str, project_root: str
) -> BuildIdentifier:
    """Read the served SHA for this exact governed root, never list position."""
    if registry_text is None:
        return unresolved_build(detail="no installed-plugins registry to read")
    try:
        parsed = json.loads(registry_text)
    except json.JSONDecodeError as unparseable:
        return unresolved_build(detail=f"installed-plugins registry is not JSON: {unparseable}")
    records = _matching_records(registry=parsed, plugin=plugin, project_root=project_root)
    if not records:
        return unresolved_build(detail=f"no install record has projectPath {project_root}")
    shas = {
        raw_sha.strip().lower()
        for record in records
        if isinstance((raw_sha := record.get("gitCommitSha")), str) and raw_sha.strip()
    }
    if not shas:
        return unresolved_build(
            detail=f"the install record for projectPath {project_root} has no gitCommitSha"
        )
    if len(shas) != 1:
        return unresolved_build(
            detail=f"install records for projectPath {project_root} disagree on gitCommitSha"
        )
    return resolved_build(sha=next(iter(shas)))


def _matching_records(
    *, registry: object, plugin: str, project_root: str
) -> tuple[dict[str, object], ...]:
    """Select records for one plugin and project from the sparse v2 registry."""
    if not isinstance(registry, dict):
        return ()
    plugins = cast("dict[str, object]", registry).get("plugins")
    if not isinstance(plugins, dict):
        return ()
    entries = cast("dict[str, object]", plugins).get(plugin)
    if not isinstance(entries, list):
        return ()
    return tuple(
        cast("dict[str, object]", entry)
        for entry in cast("list[object]", entries)
        if isinstance(entry, dict)
        and cast("dict[str, object]", entry).get("projectPath") == project_root
    )
