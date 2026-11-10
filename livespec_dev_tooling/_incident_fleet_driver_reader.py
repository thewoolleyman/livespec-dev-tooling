"""The driver hooks' serving build: the plugin builds the harness has installed for a consumer.

A consumer's driver hooks are the plugins its committed `.claude/settings.json` enables,
as the harness installed them for that project: the install record whose `projectPath` is
the consumer's clone, its recorded commit, and a plugin cache directory that still exists.
Nothing here reads a repository's own version label, and a plugin that is enabled but not
installed for this project (or installed without its cache) leaves the consumer unverified.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_fleet_clones import consumer_clone
from livespec_dev_tooling.fleet._plugin_build_currency_reads import (
    governed_pins,
    served_build_identifier,
)
from livespec_dev_tooling.incident_fleet_host import HostProbe
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["read_driver_hooks"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
_COMMIT = re.compile(r"[0-9a-f]{40}")
_REGISTRY = Path(".claude") / "plugins" / "installed_plugins.json"


def _cache_present(*, registry_text: str, plugin: str, clone: Path) -> bool:
    try:
        document = cast("object", strict_json(text=registry_text, limit=None))
    except (ValueError, IncidentJsonRefusalError):
        return False
    plugins = (
        cast("dict[str, object]", document).get("plugins") if isinstance(document, dict) else None
    )
    records = cast("dict[str, object]", plugins).get(plugin) if isinstance(plugins, dict) else None
    return isinstance(records, list) and any(
        isinstance(record, dict)
        and cast("dict[str, object]", record).get("projectPath") == str(clone)
        and isinstance(cache := cast("dict[str, object]", record).get("installPath"), str)
        and Path(cache).is_dir()
        for record in cast("list[object]", records)
    )


def read_driver_hooks(*, probe: HostProbe, repository: str) -> str | None:
    """`plugin=<commit>` for every enabled plugin, joined in name order, else None."""
    clone = consumer_clone(probe=probe, repository=repository)
    if clone is None:
        return None
    try:
        settings = (clone / ".claude" / "settings.json").read_text("utf-8")
        registry = (probe.home / _REGISTRY).read_text("utf-8")
    except OSError:
        return None
    pins = governed_pins(settings_text=settings)
    if pins.unreadable or not pins.sources:
        return None
    served: list[str] = []
    for pin in pins.sources:
        build = served_build_identifier(
            registry_text=registry, plugin=pin.plugin, project_root=str(clone)
        )
        if build.unresolved or not _COMMIT.fullmatch(build.sha):
            return None
        if not _cache_present(registry_text=registry, plugin=pin.plugin, clone=clone):
            return None
        served.append(f"{pin.plugin}={build.sha}")
    return ",".join(sorted(served))
