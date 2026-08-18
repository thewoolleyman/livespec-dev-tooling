"""Shared Claude plugin provisioner derived from committed project settings.

The invoking repo's `.claude/settings.json` is the single source of truth: this
module reads its project-scoped marketplaces and enabled plugins at runtime and
executes the matching Claude CLI registration commands.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._ensure_plugin_artifacts import (
    ArtifactReader,
    CacheDirRemover,
    artifact_record_findings,
    artifact_record_repair_paths,
    plugin_artifact_findings,
    remove_plugin_cache_dir,
)
from livespec_dev_tooling.fleet._ensure_plugin_commands import (
    CommandResult,
    CommandRunner,
    enabled_plugin_names,
    planned_commands,
    run_from_settings,
    subprocess_runner,
)

__all__: list[str] = [
    "ArtifactReader",
    "CacheDirRemover",
    "CommandResult",
    "CommandRunner",
    "RegistryReader",
    "ensure",
    "main",
    "planned_commands",
    "plugin_artifact_findings",
    "registry_findings",
    "remove_plugin_cache_dir",
    "run_from_settings",
    "settings_findings",
    "subprocess_runner",
]


class RegistryReader(Protocol):
    """Callable seam reading the installed-plugins registry, or None if absent."""

    def __call__(self) -> str | None: ...


def _marketplace_of(*, plugin: str) -> str:
    """The marketplace half of a `<plugin>@<marketplace>` key."""
    _, _, marketplace = plugin.partition("@")
    return marketplace or plugin


def _split_enablement(*, raw: object) -> tuple[tuple[str, ...], tuple[str, ...], str | None]:
    """(enabled, explicitly-disabled, shape-finding) from an enabledPlugins value."""
    if raw is None:
        return ((), (), None)
    if isinstance(raw, list):
        names = enabled_plugin_names(raw=cast("list[object]", raw))
        if names is None:
            return ((), (), "enabledPlugins list entries must be strings")
        return (names, (), None)
    if not isinstance(raw, dict):
        return ((), (), "enabledPlugins must be a JSON object")
    on: list[str] = []
    off: list[str] = []
    for key, value in cast("dict[str, object]", raw).items():
        if not isinstance(value, bool):
            return ((), (), f"enabledPlugins values must be JSON booleans; {key!r} is not")
        (on if value else off).append(key)
    return (tuple(on), tuple(off), None)


def settings_findings(*, settings_text: str) -> tuple[str, ...]:
    """Findings for the committed settings file alone. Empty means well-formed.

    Rejects all three vacuity levels: an empty enablement set, an all-false one
    (a `false` value is an explicit disable, not an enablement), and a partially
    stripped one where a declared marketplace has no enabled plugin left.
    """
    parsed = json.loads(settings_text)
    if not isinstance(parsed, dict):
        return (".claude/settings.json must contain a JSON object",)
    settings = cast("dict[str, object]", parsed)
    marketplaces = settings.get("extraKnownMarketplaces")
    if marketplaces is not None and not isinstance(marketplaces, dict):
        return ("extraKnownMarketplaces must be a JSON object",)
    enabled, disabled, shape = _split_enablement(raw=settings.get("enabledPlugins"))
    if shape is not None:
        return (shape,)
    declared = tuple(cast("dict[str, object]", marketplaces or {}))
    if declared and not enabled:
        return ("no plugin is enabled; enabledPlugins is empty, absent, or all-false",)
    covered = {_marketplace_of(plugin=name) for name in enabled}
    off_markets = {_marketplace_of(plugin=name) for name in disabled}
    findings: list[str] = []
    for market in declared:
        if market in covered:
            continue
        if market in off_markets:
            findings.append(f"marketplace {market!r} has only explicitly disabled plugins")
        else:
            findings.append(f"marketplace {market!r} declared but nothing enabled from it")
    return tuple(findings)


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


def _project_records(
    *, registry: object, plugin: str, project_root: str
) -> tuple[dict[str, object], ...]:
    """Install records for one plugin in this project."""
    return tuple(
        cast("dict[str, object]", entry)
        for entry in _records_for(registry=registry, plugin=plugin)
        if isinstance(entry, dict)
        and cast("dict[str, object]", entry).get("projectPath") == project_root
    )


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
    enabled, _, shape = _split_enablement(
        raw=cast("dict[str, object]", parsed).get("enabledPlugins")
    )
    if shape is not None:
        return (shape,)
    registry = json.loads(registry_text) if registry_text is not None else None
    findings: list[str] = []
    for plugin in enabled:
        records = _project_records(registry=registry, plugin=plugin, project_root=project_root)
        if not records:
            findings.append(
                f"{plugin} is enabled but has no install record for projectPath {project_root}"
            )
            continue
        findings.extend(
            artifact_record_findings(
                plugin=plugin,
                records=records,
                read_artifact=read_artifact,
            )
        )
    return tuple(findings)


def _registry_repair_paths(
    *,
    settings_text: str,
    project_root: str,
    registry_text: str | None,
    read_artifact: ArtifactReader,
) -> tuple[str, ...]:
    """Failing install paths from enabled plugin records, deduplicated in registry order."""
    parsed = json.loads(settings_text)
    enabled, _, _ = _split_enablement(raw=cast("dict[str, object]", parsed).get("enabledPlugins"))
    registry = json.loads(registry_text) if registry_text is not None else None
    paths: dict[str, None] = {}
    for plugin in enabled:
        records = _project_records(registry=registry, plugin=plugin, project_root=project_root)
        for install_path in artifact_record_repair_paths(
            records=records,
            read_artifact=read_artifact,
        ):
            paths[install_path] = None
    return tuple(paths)


def _run_commands(
    *, commands: tuple[tuple[str, ...], ...], runner: CommandRunner
) -> tuple[str, ...]:
    """Run one provisioning cycle and return the first command failure."""
    for command in commands:
        result = runner(args=command)
        if result.returncode != 0:
            return (f"command failed with exit {result.returncode}: {' '.join(command)}",)
    return ()


def ensure(
    *,
    settings_text: str,
    project_root: str,
    runner: CommandRunner,
    read_registry: RegistryReader,
    read_artifact: ArtifactReader = plugin_artifact_findings,
    remove_cache_dir: CacheDirRemover = remove_plugin_cache_dir,
) -> tuple[str, ...]:
    """Provision from settings, then confirm it landed. Empty means provisioned.

    Gates BEFORE running anything: a vacuous or malformed settings file derives
    zero commands, so running it would exit 0 having done nothing.
    """
    pre = settings_findings(settings_text=settings_text)
    if pre:
        return pre
    commands = planned_commands(settings_text=settings_text)
    command_findings = _run_commands(commands=commands, runner=runner)
    if command_findings:
        return command_findings
    registry_text = read_registry()
    findings = registry_findings(
        settings_text=settings_text,
        project_root=project_root,
        registry_text=registry_text,
        read_artifact=read_artifact,
    )
    if not findings:
        return ()
    for install_path in _registry_repair_paths(
        settings_text=settings_text,
        project_root=project_root,
        registry_text=registry_text,
        read_artifact=read_artifact,
    ):
        removal_findings = remove_cache_dir(install_path=install_path)
        if removal_findings:
            return removal_findings
    command_findings = _run_commands(commands=commands, runner=runner)
    return command_findings or registry_findings(
        settings_text=settings_text,
        project_root=project_root,
        registry_text=read_registry(),
        read_artifact=read_artifact,
    )


def _read_installed_registry() -> str | None:  # pragma: no cover
    """The Claude installed-plugins registry text, or None when absent."""
    path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def main() -> int:  # pragma: no cover
    """CLI entry point for `python -m livespec_dev_tooling.fleet.ensure_plugins`.

    Exit codes follow `SPECIFICATION/contracts.md` section "Exit-code table": `3` when
    the committed settings file cannot support provisioning (a precondition the
    project state does not meet), `4` when provisioning ran but verification
    found the records absent or bound to another project.
    """
    root = Path.cwd()
    settings_text = (root / ".claude" / "settings.json").read_text(encoding="utf-8")
    precondition = settings_findings(settings_text=settings_text)
    for finding in precondition:
        _ = sys.stderr.write(f"ensure_plugins: {finding}\n")
    if precondition:
        return 3
    findings = ensure(
        settings_text=settings_text,
        project_root=str(root),
        runner=subprocess_runner,
        read_registry=_read_installed_registry,
    )
    for finding in findings:
        _ = sys.stderr.write(f"ensure_plugins: {finding}\n")
    return 4 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
