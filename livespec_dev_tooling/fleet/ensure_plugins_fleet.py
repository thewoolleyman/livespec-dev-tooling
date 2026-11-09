"""Fleet-wide Claude plugin adoption command."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._fleet_manifest_read import (
    ManifestUnreadable,
    fetch_master_manifest,
    master_manifest_source,
)
from livespec_dev_tooling.fleet._local_context import CommandResult, default_command_runner
from livespec_dev_tooling.fleet._orchestrator_hold import (
    ADOPT_COMMAND,
    ORCHESTRATOR_PLUGIN,
    installed_build,
)
from livespec_dev_tooling.fleet._plugin_build_currency_core import BuildIdentifier
from livespec_dev_tooling.fleet._plugin_settings import split_enablement
from livespec_dev_tooling.fleet.adopt_orchestrator_build import (
    AdoptionOutcome,
    CloneUnresolved,
    adopt_build,
    clones_root,
    marketplace_tip,
    read_installed_registry,
    read_known_marketplaces,
)
from livespec_dev_tooling.fleet.contract import parse_manifest

__all__: list[str] = [
    "AdoptStep",
    "FleetAdoption",
    "RecipeRunner",
    "adopt",
    "fetch_master_manifest",
    "main",
]

_USAGE_EXIT = 2


class RecipeRunner(Protocol):
    """Run one member recipe in its local clone."""

    def __call__(self, *, args: list[str], cwd: Path | None = None) -> CommandResult: ...


class AdoptStep(Protocol):
    """The orchestrator adopt step, taken for one member clone."""

    def __call__(self, *, clone: Path, build: str) -> AdoptionOutcome: ...


@dataclass(frozen=True, kw_only=True)
class FleetAdoption:
    """A fleet adoption report."""

    lines: tuple[str, ...]
    exit_code: int


def _enabled_plugins(*, settings_path: Path) -> tuple[str, ...]:
    """Read the enabled plugin names from one member's committed settings."""
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    enabled, _disabled, _shape = split_enablement(
        raw=cast("dict[str, object]", settings).get("enabledPlugins")
    )
    return enabled


def _registry_text(*, registry_path: Path) -> str | None:
    """Read the host registry when it exists."""
    return registry_path.read_text(encoding="utf-8") if registry_path.is_file() else None


def _builds(*, registry_path: Path, plugins: tuple[str, ...], member_path: Path) -> dict[str, str]:
    """The build recorded for each plugin at exactly one member's project path."""
    registry_text = _registry_text(registry_path=registry_path)
    return {
        plugin: installed_build(
            registry_text=registry_text, plugin=plugin, project_root=str(member_path)
        )
        for plugin in plugins
    }


def _tip_refusal(*, build: str, tip: BuildIdentifier) -> str:
    """Why no member may run, or the empty string when the named build is the tip."""
    if tip.unresolved:
        return f"the marketplace commit could not be read: {tip.unresolved}; no member was run"
    if tip.sha != build.strip().lower():
        return f"named build {build} is not the marketplace commit {tip.sha}; no member was run"
    return ""


def _adopter_lines(
    *, adopters: tuple[str, ...], clones_root: Path, registry_path: Path
) -> tuple[str, ...]:
    """One line per adopter clone enabling the orchestrator plugin; nothing is adopted."""
    lines: list[str] = []
    for adopter in adopters:
        settings = clones_root / adopter / ".claude" / "settings.json"
        if not settings.is_file():
            continue
        if ORCHESTRATOR_PLUGIN not in _enabled_plugins(settings_path=settings):
            continue
        build = _builds(
            registry_path=registry_path,
            plugins=(ORCHESTRATOR_PLUGIN,),
            member_path=clones_root / adopter,
        )[ORCHESTRATOR_PLUGIN]
        installed = f"{adopter} {ORCHESTRATOR_PLUGIN} installed={build}"
        lines.append(f"{installed}; adopt with: {ADOPT_COMMAND} {adopter} <build>")
    return tuple(lines)


@dataclass(frozen=True, kw_only=True)
class _MemberRun:
    """What one member's recipe and adopt step reported."""

    lines: tuple[str, ...]
    failures: tuple[str, ...]
    after: dict[str, str]


def _run_member(
    *,
    repo: str,
    member_path: Path,
    build: str,
    registry_path: Path,
    run: RecipeRunner,
    adopt_step: AdoptStep,
) -> _MemberRun:
    """Run one member's own recipe, then the adopt step when it enables the orchestrator."""
    plugins = _enabled_plugins(settings_path=member_path / ".claude" / "settings.json")
    before = _builds(registry_path=registry_path, plugins=plugins, member_path=member_path)
    failures: list[str] = []
    result = run(args=["just", "ensure-plugins"], cwd=member_path)
    if result.returncode != 0:
        cause = f"ensure-plugins exited {result.returncode}: {result.stderr.strip()}"
        failures.append(f"{repo} failed: {cause}")
    if ORCHESTRATOR_PLUGIN in plugins:
        outcome = adopt_step(clone=member_path, build=build)
        if outcome.failure:
            failures.append(f"{repo} failed: {outcome.failure}")
    after = _builds(registry_path=registry_path, plugins=plugins, member_path=member_path)
    lines = tuple(
        f"{repo} {plugin} before={before[plugin]} after={after[plugin]}" for plugin in plugins
    )
    return _MemberRun(lines=lines, failures=tuple(failures), after={} if failures else after)


def adopt(  # noqa: PLR0913 — the recipe's seams: manifest, clones, registry, runner, adopt step.
    *,
    manifest_source: str,
    clones_root: Path,
    registry_path: Path,
    run: RecipeRunner,
    build: str,
    tip: BuildIdentifier,
    adopt_step: AdoptStep,
) -> FleetAdoption:
    """Adopt plugins for every member declared by the fleet manifest."""
    refusal = _tip_refusal(build=build, tip=tip)
    if refusal:
        return FleetAdoption(lines=(refusal,), exit_code=1)
    parsed = parse_manifest(source=manifest_source).unwrap()
    lines: list[str] = []
    failures: list[str] = []
    builds: dict[str, dict[str, list[str]]] = {}
    for member in parsed.members:
        member_path = clones_root / member.repo
        if not member_path.is_dir():
            failures.append(f"{member.repo} failed: local clone missing at {member_path}")
            continue
        report = _run_member(
            repo=member.repo,
            member_path=member_path,
            build=build,
            registry_path=registry_path,
            run=run,
            adopt_step=adopt_step,
        )
        lines.extend(report.lines)
        failures.extend(report.failures)
        for plugin, installed in report.after.items():
            builds.setdefault(plugin, {}).setdefault(installed, []).append(member.repo)
    for plugin, by_build in sorted(builds.items()):
        if len(by_build) > 1:
            details = "; ".join(
                f"{installed}: {', '.join(members)}" for installed, members in by_build.items()
            )
            failures.append(f"{plugin} has split installed builds: {details}")
    lines.extend(
        _adopter_lines(
            adopters=tuple(adopter.repo for adopter in parsed.adopters),
            clones_root=clones_root,
            registry_path=registry_path,
        )
    )
    return FleetAdoption(lines=tuple([*lines, *failures]), exit_code=1 if failures else 0)


def _run_recipe(*, args: list[str], cwd: Path | None = None) -> CommandResult:  # pragma: no cover
    """Run a member recipe in its checkout."""
    import subprocess

    completed = subprocess.run(args, capture_output=True, check=False, cwd=cwd, text=True)
    return CommandResult(
        returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )


def main() -> int:  # pragma: no cover
    """Run fleet adoption against sibling clones on the current host."""
    if len(sys.argv) != 2:  # noqa: PLR2004 — program name and the named build.
        _ = sys.stderr.write("usage: just ensure-plugins-fleet <build>\n")
        return _USAGE_EXIT
    build = sys.argv[1]
    manifest = master_manifest_source()
    if isinstance(manifest, ManifestUnreadable):
        _ = sys.stderr.write(f"ensure-plugins-fleet: {manifest.cause}\n")
        return 1
    root = clones_root(
        env_root=os.environ.get("LIVESPEC_FLEET_CLONES_ROOT"),
        cwd=Path.cwd(),
        run=default_command_runner,
    )
    if isinstance(root, CloneUnresolved):
        _ = sys.stderr.write(f"ensure-plugins-fleet: {root.cause}\n")
        return 1

    def step(*, clone: Path, build: str) -> AdoptionOutcome:
        return adopt_build(
            clone=clone,
            build=build,
            run=default_command_runner,
            read_registry=read_installed_registry,
            read_known_marketplaces=read_known_marketplaces,
        )

    report = adopt(
        manifest_source=manifest,
        clones_root=root,
        registry_path=Path.home() / ".claude" / "plugins" / "installed_plugins.json",
        run=_run_recipe,
        build=build,
        tip=marketplace_tip(
            run=default_command_runner, read_known_marketplaces=read_known_marketplaces
        ),
        adopt_step=step,
    )
    for line in report.lines:
        _ = sys.stdout.write(f"ensure-plugins-fleet: {line}\n")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
