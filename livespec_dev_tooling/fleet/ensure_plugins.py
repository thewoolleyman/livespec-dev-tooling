"""Shared Claude plugin provisioner derived from committed project settings.

The invoking repo's `.claude/settings.json` is the single source of truth: this
module reads its project-scoped marketplaces and enabled plugins at runtime and
executes the matching Claude CLI registration commands.

`ensure_codex_plugins` is the Codex twin, reading a DIFFERENT committed file for
a measured reason its docstring records. The half the two share — the two keys
and the three vacuity levels — lives in `_plugin_settings`, so the mirror is
structural rather than a copied body.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Protocol, cast

# `returns` is VENDORED, not installed; this module reads both artifact seams'
# railway tracks directly, so it establishes the path itself rather than
# relying on whichever sibling import happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._ensure_plugin_artifacts import (  # noqa: E402
    ArtifactOutcome,
    ArtifactReader,
    CacheDirRemover,
    artifact_record_findings,
    artifact_record_repair_paths,
    plugin_artifact_findings,
    remove_plugin_cache_dir,
)
from livespec_dev_tooling.fleet._ensure_plugin_commands import (  # noqa: E402
    PluginCommandOutcome,
    PluginCommandResult,
    PluginCommandRunner,
    planned_commands,
    plugin_command_answer,
    run_from_settings,
    subprocess_runner,
)
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed  # noqa: E402
from livespec_dev_tooling.fleet._plugin_settings import (  # noqa: E402
    split_enablement,
    vacuity_findings,
)

__all__: list[str] = [
    "ArtifactReader",
    "CacheDirRemover",
    "PluginCommandOutcome",
    "PluginCommandResult",
    "PluginCommandRunner",
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


def settings_findings(*, settings_text: str) -> tuple[str, ...]:
    """Findings for the committed settings file alone. Empty means well-formed.

    Rejects all three vacuity levels: an empty enablement set, an all-false one
    (a `false` value is an explicit disable, not an enablement), and a partially
    stripped one where a declared marketplace has no enabled plugin left. The
    reading itself lives in `_plugin_settings` because the Codex twin
    (`ensure_codex_plugins`) rejects the SAME three levels over the SAME two
    keys; only the file the finding names differs.
    """
    return vacuity_findings(settings_text=settings_text, settings_label=".claude/settings.json")


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


def _probe_findings(*, plugin: str, outcome: ArtifactOutcome) -> tuple[str, ...]:
    """Findings from an artifact probe that ANSWERED, or its failure rendered as one.

    A probe that could not decide is reported to the operator here rather than
    dropped: `main` turns any non-empty finding set into exit 4, so the
    unanswered case surfaces as loudly as a broken build while — because the
    failure never reaches `_registry_repair_paths` as a path — authorizing no
    deletion of its own.
    """
    if isinstance(outcome, IOFailure):
        return (f"{plugin} {unsafe_perform_io(outcome.failure()).finding}",)
    return unsafe_perform_io(outcome.unwrap())


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
    enabled, _, shape = split_enablement(
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
            _probe_findings(
                plugin=plugin,
                outcome=artifact_record_findings(
                    plugin=plugin,
                    records=records,
                    read_artifact=read_artifact,
                ),
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
    """Failing install paths from enabled plugin records, deduplicated in registry order.

    A plugin whose probe did not answer contributes NOTHING. That is the whole
    reason the artifact seams carry a failure track: the paths returned here
    are deleted, and an unanswered probe has not established that there is
    anything to delete.
    """
    parsed = json.loads(settings_text)
    enabled, _, _ = split_enablement(raw=cast("dict[str, object]", parsed).get("enabledPlugins"))
    registry = json.loads(registry_text) if registry_text is not None else None
    paths: dict[str, None] = {}
    for plugin in enabled:
        records = _project_records(registry=registry, plugin=plugin, project_root=project_root)
        outcome = artifact_record_repair_paths(records=records, read_artifact=read_artifact)
        if isinstance(outcome, IOFailure):
            continue
        for install_path in unsafe_perform_io(outcome.unwrap()):
            paths[install_path] = None
    return tuple(paths)


def _run_commands(
    *, commands: tuple[tuple[str, ...], ...], runner: PluginCommandRunner
) -> tuple[str, ...]:
    """Run one provisioning cycle and return EVERY command failure it saw.

    A REFUSAL NO LONGER SUPPRESSES THE COMMANDS BEHIND IT. `planned_commands`
    emits every `marketplace add` before any `install`, and `marketplace add` is
    a network operation against GitHub — a rate limit, a transient fault, or a
    momentarily unavailable repo each exits non-zero. Returning at the first of
    them installed NOTHING while `main` still exited 4, which is the incident
    symptom: plugins enabled by committed settings with no install record, a
    state Claude Code resolves to no operations and no error
    (`livespec-dev-tooling-357j2y`). Continuing is not tolerance — every refusal
    is still reported, one finding per failing command.

    AN INVOCATION THAT NEVER HAPPENED STILL STOPS THE CYCLE, and the two
    failures stay APART because they call for opposite operator responses: a
    command that RAN and refused is the plugin CLI's own verdict, while a
    command that never ran at all is an install or permissions problem on the
    host and says nothing about the plugin. That fact is about `argv[0]`, which
    every planned command shares, so running the remainder would restate one
    host problem as a dozen findings. The stop RETURNS the refusals already
    collected alongside it rather than discarding them — dropping them would
    reintroduce the reporting half of the defect at a different door.
    """
    findings: list[str] = []
    for command in commands:
        answer = plugin_command_answer(outcome=runner(args=command))
        if isinstance(answer, InvocationNotPerformed):
            findings.append(f"command did not run: {answer.reason}")
            return tuple(findings)
        if answer.returncode != 0:
            findings.append(f"command failed with exit {answer.returncode}: {' '.join(command)}")
    return tuple(findings)


def ensure(
    *,
    settings_text: str,
    project_root: str,
    runner: PluginCommandRunner,
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
        removal = remove_cache_dir(install_path=install_path)
        if isinstance(removal, IOFailure):
            return (unsafe_perform_io(removal.failure()).finding,)
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
