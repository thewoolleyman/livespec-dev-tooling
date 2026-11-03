"""Adopt the enabled Claude plugin builds in every local fleet clone."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from returns.result import Failure

from livespec_dev_tooling.fleet._local_context import (
    CommandResult,
    command_answer,
    default_command_runner,
)
from livespec_dev_tooling.fleet._plugin_build_currency_reads import served_build_identifier
from livespec_dev_tooling.fleet._plugin_settings import split_enablement
from livespec_dev_tooling.fleet.contract import parse_manifest

__all__: list[str] = ["FleetAdoption", "RecipeRunner", "adopt", "main"]


class RecipeRunner(Protocol):
    """Run one member recipe and return its completed process result."""

    def __call__(self, *, args: list[str], cwd: Path | None = None) -> CommandResult: ...


@dataclass(frozen=True, kw_only=True)
class FleetAdoption:
    """The printable adoption report and its process exit status."""

    lines: tuple[str, ...]
    exit_code: int


@dataclass(frozen=True, kw_only=True)
class EnabledPlugins:
    """The enabled names from one member settings file, or its read failure."""

    names: tuple[str, ...]
    failure: str


@dataclass(frozen=True, kw_only=True)
class MemberAdoption:
    """One member's printed build pairs, failures, and converged-build candidates."""

    lines: tuple[str, ...]
    failures: tuple[str, ...]
    builds: tuple[tuple[str, str, str], ...]


def _enabled_plugins(*, settings_path: Path) -> EnabledPlugins:
    """Read enabled names without depending on marketplace pin validity."""
    try:
        text = settings_path.read_text(encoding="utf-8")
    except OSError as error:
        return EnabledPlugins(names=(), failure=f"cannot read {settings_path}: {error}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        return EnabledPlugins(names=(), failure=f"{settings_path} is not JSON: {error}")
    if not isinstance(parsed, dict):
        return EnabledPlugins(names=(), failure=f"{settings_path} must contain a JSON object")
    names, _disabled, shape = split_enablement(
        raw=cast("dict[str, object]", parsed).get("enabledPlugins")
    )
    if shape is not None:
        return EnabledPlugins(names=(), failure=f"{settings_path}: {shape}")
    return EnabledPlugins(names=names, failure="")


def _registry_text(*, registry_path: Path) -> str | None:
    """Return the registry text when the host has recorded one."""
    try:
        return registry_path.read_text(encoding="utf-8") if registry_path.is_file() else None
    except OSError:
        return None


def _build(*, registry_text: str | None, plugin: str, member_path: Path) -> str:
    """Render the installed project-scoped build without guessing from another record."""
    identifier = served_build_identifier(
        registry_text=registry_text,
        plugin=plugin,
        project_root=str(member_path),
    )
    return identifier.sha or f"<unresolved: {identifier.unresolved}>"


def _failure(*, member: str, cause: str) -> str:
    """One complete, member-attributed failure line."""
    return f"{member} failed: {cause}"


def _adopt_member(
    *,
    member: str,
    clones_root: Path,
    registry_path: Path,
    before_registry: str | None,
    run: RecipeRunner,
) -> MemberAdoption:
    """Run one member recipe while retaining the exact project-scoped read-backs."""
    member_path = clones_root / member
    if not member_path.is_dir():
        return MemberAdoption(
            lines=(),
            failures=(_failure(member=member, cause=f"local clone missing at {member_path}"),),
            builds=(),
        )
    enabled = _enabled_plugins(settings_path=member_path / ".claude" / "settings.json")
    if enabled.failure:
        return MemberAdoption(
            lines=(),
            failures=(_failure(member=member, cause=enabled.failure),),
            builds=(),
        )
    before = {
        plugin: _build(registry_text=before_registry, plugin=plugin, member_path=member_path)
        for plugin in enabled.names
    }
    result = run(args=["just", "ensure-plugins"], cwd=member_path)
    after = {
        plugin: _build(
            registry_text=_registry_text(registry_path=registry_path),
            plugin=plugin,
            member_path=member_path,
        )
        for plugin in enabled.names
    }
    lines = tuple(
        f"{member} {plugin} before={before[plugin]} after={after[plugin]}"
        for plugin in enabled.names
    )
    if result.returncode != 0:
        cause = f"ensure-plugins exited {result.returncode}"
        if result.stderr.strip():
            cause = f"{cause}: {result.stderr.strip()}"
        return MemberAdoption(
            lines=lines,
            failures=(_failure(member=member, cause=cause),),
            builds=(),
        )
    unresolved = tuple(
        _failure(member=member, cause=f"{plugin} after build {build}")
        for plugin, build in after.items()
        if build.startswith("<unresolved:")
    )
    builds = tuple(
        (plugin, build, member)
        for plugin, build in after.items()
        if not build.startswith("<unresolved:")
    )
    return MemberAdoption(lines=lines, failures=unresolved, builds=builds)


def adopt(
    *, manifest_path: Path, clones_root: Path, registry_path: Path, run: RecipeRunner
) -> FleetAdoption:
    """Run every manifest member's own recipe, reporting its before and after builds."""
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
    except OSError as error:
        return FleetAdoption(
            lines=(f"fleet manifest unavailable: {manifest_path}: {error}",), exit_code=1
        )
    parsed = parse_manifest(source=manifest_text)
    if isinstance(parsed, Failure):
        return FleetAdoption(
            lines=(f"fleet manifest is invalid: {parsed.failure().reason}",), exit_code=1
        )
    before_registry = _registry_text(registry_path=registry_path)
    lines: list[str] = []
    failures: list[str] = []
    builds: dict[str, dict[str, list[str]]] = {}
    for member in parsed.unwrap().members:
        member_adoption = _adopt_member(
            member=member.repo,
            clones_root=clones_root,
            registry_path=registry_path,
            before_registry=before_registry,
            run=run,
        )
        lines.extend(member_adoption.lines)
        failures.extend(member_adoption.failures)
        for plugin, build, member_name in member_adoption.builds:
            builds.setdefault(plugin, {}).setdefault(build, []).append(member_name)
    for plugin, by_build in sorted(builds.items()):
        if len(by_build) > 1:
            fragments = "; ".join(
                f"{build}: {', '.join(members)}" for build, members in sorted(by_build.items())
            )
            failures.append(f"{plugin} has split installed builds: {fragments}")
    return FleetAdoption(lines=tuple([*lines, *failures]), exit_code=1 if failures else 0)


def _run_recipe(*, args: list[str], cwd: Path | None = None) -> CommandResult:
    """Adapt the shared local-command railway to the adoption runner seam."""
    answer = command_answer(outcome=default_command_runner(args=args, cwd=cwd))
    if isinstance(answer, CommandResult):
        return answer
    return CommandResult(returncode=127, stdout="", stderr=answer.reason)


def main() -> int:
    """Adopt plugins from the core manifest in the local sibling-clone root."""
    fleet_root = Path(os.environ.get("LIVESPEC_FLEET_CLONES_ROOT", Path.cwd().parent))
    report = adopt(
        manifest_path=fleet_root / "livespec" / ".livespec-fleet-manifest.jsonc",
        clones_root=fleet_root,
        registry_path=Path.home() / ".claude" / "plugins" / "installed_plugins.json",
        run=_run_recipe,
    )
    for line in report.lines:
        _ = sys.stdout.write(f"ensure-plugins-fleet: {line}\n")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
