"""Fleet-wide Claude plugin adoption command."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.fleet._local_context import CommandResult
from livespec_dev_tooling.fleet._plugin_build_currency_reads import served_build_identifier
from livespec_dev_tooling.fleet._plugin_settings import split_enablement
from livespec_dev_tooling.fleet.contract import parse_manifest

# `returns` is vendored. This command is a process entry point, so it cannot
# rely on an earlier sibling import having placed the dependency on sys.path.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

__all__: list[str] = ["FleetAdoption", "RecipeRunner", "adopt", "main"]


class RecipeRunner(Protocol):
    """Run one member recipe in its local clone."""

    def __call__(self, *, args: list[str], cwd: Path | None = None) -> CommandResult: ...


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


def _build(*, registry_text: str | None, plugin: str, member_path: Path) -> str:
    """Render the build recorded for precisely one member's project path."""
    identifier = served_build_identifier(
        registry_text=registry_text,
        plugin=plugin,
        project_root=str(member_path),
    )
    return identifier.sha or f"<unresolved: {identifier.unresolved}>"


def adopt(
    *, manifest_path: Path, clones_root: Path, registry_path: Path, run: RecipeRunner
) -> FleetAdoption:
    """Adopt plugins for every member declared by the fleet manifest."""
    parsed = parse_manifest(source=manifest_path.read_text(encoding="utf-8"))
    lines: list[str] = []
    failures: list[str] = []
    builds: dict[str, dict[str, list[str]]] = {}
    for member in parsed.unwrap().members:
        member_path = clones_root / member.repo
        if not member_path.is_dir():
            failures.append(f"{member.repo} failed: local clone missing at {member_path}")
            continue
        plugins = _enabled_plugins(settings_path=member_path / ".claude" / "settings.json")
        before_registry = _registry_text(registry_path=registry_path)
        before = {
            plugin: _build(
                registry_text=before_registry,
                plugin=plugin,
                member_path=member_path,
            )
            for plugin in plugins
        }
        result = run(args=["just", "ensure-plugins"], cwd=member_path)
        after_registry = _registry_text(registry_path=registry_path)
        for plugin in plugins:
            after = _build(
                registry_text=after_registry,
                plugin=plugin,
                member_path=member_path,
            )
            lines.append(f"{member.repo} {plugin} before={before[plugin]} after={after}")
            if result.returncode == 0:
                builds.setdefault(plugin, {}).setdefault(after, []).append(member.repo)
        if result.returncode != 0:
            cause = f"ensure-plugins exited {result.returncode}: {result.stderr.strip()}"
            failures.append(f"{member.repo} failed: {cause}")
    for plugin, by_build in sorted(builds.items()):
        if len(by_build) > 1:
            details = "; ".join(
                f"{build}: {', '.join(members)}" for build, members in by_build.items()
            )
            failures.append(f"{plugin} has split installed builds: {details}")
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
    root = Path(os.environ.get("LIVESPEC_FLEET_CLONES_ROOT", Path.cwd().parent))
    report = adopt(
        manifest_path=root / "livespec" / ".livespec-fleet-manifest.jsonc",
        clones_root=root,
        registry_path=Path.home() / ".claude" / "plugins" / "installed_plugins.json",
        run=_run_recipe,
    )
    for line in report.lines:
        _ = sys.stdout.write(f"ensure-plugins-fleet: {line}\n")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
