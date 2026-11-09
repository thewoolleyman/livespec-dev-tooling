"""The orchestrator build hold: decide it, strip its commands, and word its notices.

The orchestrator plugin moves only through a named operator step. A session
reconcile that finds an install record for the working directory therefore
holds that build, whichever build the marketplace offers, and says so in one
line. A clone with no record gets the offered build, and a clone whose
installed build fails verification is repaired. A probe that did not answer is
HELD, never repaired: it has not established that anything is broken.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._ensure_plugin_artifacts import (  # noqa: E402
    ArtifactReader,
    artifact_record_findings,
)
from livespec_dev_tooling.fleet._ensure_plugin_registry import (  # noqa: E402
    project_install_records,
)
from livespec_dev_tooling.fleet._plugin_build_currency_reads import (  # noqa: E402
    served_build_identifier,
)
from livespec_dev_tooling.fleet._plugin_settings import split_enablement  # noqa: E402

__all__: list[str] = [
    "ADOPT_COMMAND",
    "ORCHESTRATOR_PLUGIN",
    "STATE_ABSENT",
    "STATE_BROKEN",
    "STATE_HELD",
    "STATE_NOT_ENABLED",
    "OrchestratorState",
    "hold_notice",
    "installed_build",
    "orchestrator_state",
    "repair_notice",
    "without_plugin_commands",
]

ORCHESTRATOR_PLUGIN = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
ADOPT_COMMAND = "just adopt-orchestrator-build"

STATE_NOT_ENABLED = "not-enabled"
STATE_ABSENT = "absent"
STATE_BROKEN = "broken"
STATE_HELD = "held"


@dataclass(frozen=True, kw_only=True)
class OrchestratorState:
    """What a session reconcile found about the orchestrator install for one project."""

    kind: str
    build: str
    last_updated: str


def installed_build(*, registry_text: str | None, plugin: str, project_root: str) -> str:
    """The build recorded for exactly one project path, or the reason it is unresolved."""
    identifier = served_build_identifier(
        registry_text=registry_text, plugin=plugin, project_root=project_root
    )
    return identifier.sha or f"<unresolved: {identifier.unresolved}>"


def _last_updated(*, records: tuple[dict[str, object], ...]) -> str:
    """The first `lastUpdated` value a project record carries."""
    values = [
        value for record in records if isinstance(value := record.get("lastUpdated"), str) and value
    ]
    return values[0] if values else "<unrecorded>"


def orchestrator_state(
    *,
    settings_text: str,
    project_root: str,
    read_registry: Callable[[], str | None],
    read_artifact: ArtifactReader,
) -> OrchestratorState:
    """Classify the orchestrator install: not enabled, absent, broken or held.

    The registry is read only when the orchestrator plugin is enabled, so a
    clone that does not enable it pays no extra read.
    """
    settings = cast("dict[str, object]", json.loads(settings_text))
    enabled, _disabled, _shape = split_enablement(raw=settings.get("enabledPlugins"))
    if ORCHESTRATOR_PLUGIN not in enabled:
        return OrchestratorState(kind=STATE_NOT_ENABLED, build="", last_updated="")
    registry_text = read_registry()
    registry = json.loads(registry_text) if registry_text is not None else None
    records = project_install_records(
        registry=registry, plugin=ORCHESTRATOR_PLUGIN, project_root=project_root
    )
    if not records:
        return OrchestratorState(kind=STATE_ABSENT, build="", last_updated="")
    build = installed_build(
        registry_text=registry_text, plugin=ORCHESTRATOR_PLUGIN, project_root=project_root
    )
    probe = artifact_record_findings(
        plugin=ORCHESTRATOR_PLUGIN, records=records, read_artifact=read_artifact
    )
    answered_broken = not isinstance(probe, IOFailure) and bool(unsafe_perform_io(probe.unwrap()))
    return OrchestratorState(
        kind=STATE_BROKEN if answered_broken else STATE_HELD,
        build=build,
        last_updated=_last_updated(records=records),
    )


def without_plugin_commands(
    *, commands: tuple[tuple[str, ...], ...], plugin: str
) -> tuple[tuple[str, ...], ...]:
    """The planned commands minus every install or update of one plugin."""
    return tuple(
        command
        for command in commands
        if not (command[2] in {"install", "update"} and command[3] == plugin)
    )


def hold_notice(*, state: OrchestratorState, project_root: str) -> tuple[str, ...]:
    """The one line naming a held build, or nothing when no build is held."""
    if state.kind != STATE_HELD:
        return ()
    holding = f"holding {ORCHESTRATOR_PLUGIN} at {state.build} (lastUpdated {state.last_updated})"
    adopt = f"adopt a build with: {ADOPT_COMMAND} {project_root} <build>"
    return (f"{holding}; {adopt}",)


def repair_notice(
    *, state: OrchestratorState, project_root: str, registry_text: str | None
) -> tuple[str, ...]:
    """The one line naming a repaired build before and after, or nothing."""
    if state.kind != STATE_BROKEN:
        return ()
    after = installed_build(
        registry_text=registry_text, plugin=ORCHESTRATOR_PLUGIN, project_root=project_root
    )
    return (f"repaired {ORCHESTRATOR_PLUGIN} before={state.build} after={after}",)
