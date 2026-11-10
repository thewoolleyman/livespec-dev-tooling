"""Build a tagged orchestrator release in a throwaway home, then land it in the host cache.

The tag adopt never runs a `claude plugin` command against the host's home or
the host's Claude Code configuration directory. It builds the release in a
throwaway builder home instead: user settings declaring the marketplace at the
tag, the marketplace registered at the tag, and a project-scope install in a
throwaway clone. It then copies that build into the host's plugin cache, into
the directory named by the commit's 12-character prefix, which is where a
`claude plugin update` to that commit installs. The copy is staged on the same
filesystem as the cache and lands by a rename; `/tmp` is commonly a tmpfs, so
staging is never placed there.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOSuccess  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._ensure_plugin_registry import (  # noqa: E402
    project_install_records,
)
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._local_context import (  # noqa: E402
    CommandOutcome,
    CommandResult,
    command_answer,
)
from livespec_dev_tooling.fleet._orchestrator_hold import ORCHESTRATOR_PLUGIN  # noqa: E402
from livespec_dev_tooling.fleet._plugin_build_currency_reads import (  # noqa: E402
    served_build_identifier,
)
from livespec_dev_tooling.fleet._tag_adopt_checks import (  # noqa: E402
    ORCHESTRATOR_MARKETPLACE,
    ORCHESTRATOR_REPO,
    json_object,
)

__all__: list[str] = [
    "STAGING_DIRNAME",
    "BuiltPlugin",
    "EnvCommandRunner",
    "LandedBuild",
    "build_plugin",
    "builder_env",
    "carries_required",
    "env_command_runner",
    "land_build",
    "plugin_cache_dir",
]

STAGING_DIRNAME = ".livespec-orchestrator-adopt"
_MARKERS = (".in_use", ".orphaned_at")
_SHORT = 12


class EnvCommandRunner(Protocol):
    """Run one command in a working directory under an explicit environment."""

    def __call__(self, *, args: list[str], cwd: Path, env: Mapping[str, str]) -> CommandOutcome: ...


def env_command_runner(  # pragma: no cover
    *, args: list[str], cwd: Path, env: Mapping[str, str]
) -> CommandOutcome:
    """Run `args` as a subprocess under `env`; a program that never ran FAILS."""
    argv = tuple(args)
    if shutil.which(args[0], path=env.get("PATH")) is None:
        detail = f"{args[0]} not on PATH"
        return IOFailure(InvocationNotPerformed(argv=argv, kind=BINARY_ABSENT, detail=detail))
    try:
        completed = subprocess.run(
            args, capture_output=True, text=True, check=False, cwd=str(cwd), env=dict(env)
        )
    except OSError as unspawnable:
        detail = str(unspawnable)
        return IOFailure(InvocationNotPerformed(argv=argv, kind=SPAWN_FAILED, detail=detail))
    return IOSuccess(
        CommandResult(
            returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )
    )


def builder_env(*, base: Mapping[str, str], home: Path) -> dict[str, str]:
    """The environment every builder command runs under: HOME is the builder home."""
    env = {key: value for key, value in base.items() if key != "CLAUDE_CONFIG_DIR"}
    env["HOME"] = str(home)
    return env


@dataclass(frozen=True, kw_only=True)
class BuiltPlugin:
    """The builder's install directory, or why the build was refused."""

    install_path: Path
    failure: str


def _marketplace_at(*, tag: str) -> dict[str, object]:
    return {
        ORCHESTRATOR_MARKETPLACE: {
            "source": {"source": "github", "repo": ORCHESTRATOR_REPO, "ref": tag}
        }
    }


def _write_json(*, path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _failed(*, outcome: CommandOutcome, what: str) -> str:
    """Why one builder command did not succeed, or the empty string."""
    answer = command_answer(outcome=outcome)
    if isinstance(answer, InvocationNotPerformed):
        return f"{what} did not run: {answer.reason}"
    if answer.returncode != 0:
        return f"{what} exited {answer.returncode}: {answer.stderr.strip()}"
    return ""


def build_plugin(
    *, home: Path, tag: str, tag_commit: str, base_env: Mapping[str, str], run: EnvCommandRunner
) -> BuiltPlugin:
    """Install the tagged release at project scope in a throwaway clone of the builder home."""
    env = builder_env(base=base_env, home=home)
    _write_json(
        path=home / ".claude" / "settings.json",
        value={"extraKnownMarketplaces": _marketplace_at(tag=tag)},
    )
    project = home / "project"
    _write_json(
        path=project / ".claude" / "settings.json",
        value={
            "enabledPlugins": {ORCHESTRATOR_PLUGIN: True},
            "extraKnownMarketplaces": _marketplace_at(tag=tag),
        },
    )
    steps = (
        (
            ["claude", "plugin", "marketplace", "add", f"{ORCHESTRATOR_REPO}#{tag}"],
            home,
            "builder marketplace add",
        ),
        (["git", "init", "-q"], project, "builder clone git init"),
        (
            ["claude", "plugin", "install", ORCHESTRATOR_PLUGIN, "-s", "project"],
            project,
            "builder install",
        ),
    )
    for args, cwd, what in steps:
        failure = _failed(outcome=run(args=args, cwd=cwd, env=env), what=what)
        if failure:
            return BuiltPlugin(install_path=home, failure=f"{failure}; nothing was moved")
    registry_path = home / ".claude" / "plugins" / "installed_plugins.json"
    registry_text = registry_path.read_text(encoding="utf-8") if registry_path.is_file() else None
    built = served_build_identifier(
        registry_text=registry_text, plugin=ORCHESTRATOR_PLUGIN, project_root=str(project)
    )
    records = project_install_records(
        registry=json_object(text=registry_text),
        plugin=ORCHESTRATOR_PLUGIN,
        project_root=str(project),
    )
    install_path = records[0].get("installPath") if records else None
    if built.sha != tag_commit or not isinstance(install_path, str):
        found = built.sha or built.unresolved
        failure = (
            f"the builder installed {found}, not the tag's commit {tag_commit}; nothing was moved"
        )
        return BuiltPlugin(install_path=home, failure=failure)
    return BuiltPlugin(install_path=Path(install_path), failure="")


def plugin_cache_dir(*, plugins_root: Path) -> Path:
    """The orchestrator plugin's cache directory, whose children are per-commit builds."""
    plugin_name = ORCHESTRATOR_PLUGIN.partition("@")[0]
    return plugins_root / "cache" / ORCHESTRATOR_MARKETPLACE / plugin_name


def _required_paths(*, build: Path) -> tuple[str, ...] | None:
    """The manifest's required paths, or None when the build carries no usable manifest."""
    manifest = build / "cache-manifest.json"
    raw = json_object(text=manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    raw_paths = raw.get("required_paths")
    if not isinstance(raw_paths, list):
        return None
    paths = cast("list[object]", raw_paths)
    valid = tuple(
        entry
        for entry in paths
        if isinstance(entry, str)
        and entry
        and not Path(entry).is_absolute()
        and ".." not in Path(entry).parts
    )
    return valid if len(valid) == len(paths) else None


def carries_required(*, directory: Path, required: tuple[str, ...]) -> bool:
    """Whether a build directory carries every path its manifest lists as required."""
    return directory.is_dir() and all((directory / entry).exists() for entry in required)


@dataclass(frozen=True, kw_only=True)
class LandedBuild:
    """The cache directory the record will name, its required paths, or the refusal."""

    target: Path
    required: tuple[str, ...]
    failure: str


def land_build(*, source: Path, commit: str, plugins_root: Path) -> LandedBuild:
    """Copy the builder's build into the host cache through a same-filesystem staging rename."""
    target = plugin_cache_dir(plugins_root=plugins_root) / commit[:_SHORT]
    required = _required_paths(build=source)
    if required is None:
        failure = f"the built release at {source} carries no usable cache-manifest.json"
        failure += "; nothing was moved"
        return LandedBuild(target=target, required=(), failure=failure)
    work = plugins_root / STAGING_DIRNAME
    shutil.rmtree(work, ignore_errors=True)
    if carries_required(directory=target, required=required):
        return LandedBuild(target=target, required=required, failure="")
    staged = work / "staging" / commit[:_SHORT]
    _ = shutil.copytree(source, staged, symlinks=True, ignore=shutil.ignore_patterns(*_MARKERS))
    if target.exists():
        aside = work / "aside" / commit[:_SHORT]
        aside.parent.mkdir(parents=True)
        _ = target.rename(aside)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = staged.rename(target)
    if not carries_required(directory=target, required=required):
        failure = (
            f"{target} lacks a required path after the copy; the install record was not written"
        )
        return LandedBuild(target=target, required=required, failure=failure)
    return LandedBuild(target=target, required=required, failure="")
