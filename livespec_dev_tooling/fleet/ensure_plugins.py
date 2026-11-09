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

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# `returns` is VENDORED, not installed; this module reads both artifact seams'
# railway tracks directly, so it establishes the path itself rather than
# relying on whichever sibling import happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._ensure_plugin_artifacts import (  # noqa: E402
    ArtifactReader,
    CacheDirRemover,
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
from livespec_dev_tooling.fleet._ensure_plugin_registry import (  # noqa: E402
    registry_findings,
    registry_repair_paths,
)
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed  # noqa: E402
from livespec_dev_tooling.fleet._orchestrator_hold import (  # noqa: E402
    ORCHESTRATOR_PLUGIN,
    STATE_HELD,
    hold_notice,
    orchestrator_state,
    repair_notice,
    without_plugin_commands,
)
from livespec_dev_tooling.fleet._plugin_settings import vacuity_findings  # noqa: E402
from livespec_dev_tooling.fleet._plugin_startup import (  # noqa: E402
    _logged_runner,
    _startup_currency,
)

__all__: list[str] = [
    "ArtifactReader",
    "CacheDirRemover",
    "EnsureReport",
    "PluginCommandOutcome",
    "PluginCommandResult",
    "PluginCommandRunner",
    "RegistryReader",
    "ensure",
    "ensure_report",
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


@dataclass(frozen=True, kw_only=True)
class EnsureReport:
    """What one reconcile found (`findings`) and what it tells the operator (`notices`)."""

    findings: tuple[str, ...]
    notices: tuple[str, ...]


def ensure_report(  # noqa: PLR0913 — preserve existing I/O seams while adding proven skip sets.
    *,
    settings_text: str,
    project_root: str,
    runner: PluginCommandRunner,
    read_registry: RegistryReader,
    read_artifact: ArtifactReader = plugin_artifact_findings,
    remove_cache_dir: CacheDirRemover = remove_plugin_cache_dir,
    current_plugins: frozenset[str] = frozenset(),
    registered_marketplaces: frozenset[str] = frozenset(),
) -> EnsureReport:
    """Provision from settings, then confirm it landed.

    Gates BEFORE running anything: a vacuous or malformed settings file derives
    zero commands, so running it would exit 0 having done nothing.

    A HELD ORCHESTRATOR BUILD IS DROPPED FROM BOTH COMMAND PASSES. The repair
    pass re-runs every planned command, so another plugin's finding would
    otherwise update the held build; repair paths still come only from a
    plugin whose probe answered with a failure.
    """
    pre = settings_findings(settings_text=settings_text)
    if pre:
        return EnsureReport(findings=pre, notices=())
    state = orchestrator_state(
        settings_text=settings_text,
        project_root=project_root,
        read_registry=read_registry,
        read_artifact=read_artifact,
    )
    notices = hold_notice(state=state, project_root=project_root)
    commands = planned_commands(settings_text=settings_text)
    if state.kind == STATE_HELD:
        commands = without_plugin_commands(commands=commands, plugin=ORCHESTRATOR_PLUGIN)
    needed = tuple(
        command
        for command in commands
        if (
            command[4] not in registered_marketplaces
            if command[2] == "marketplace"
            else command[3] not in current_plugins
        )
    )
    command_findings = _run_commands(commands=needed, runner=runner)
    if command_findings:
        return EnsureReport(findings=command_findings, notices=notices)
    registry_text = read_registry()
    findings = registry_findings(
        settings_text=settings_text,
        project_root=project_root,
        registry_text=registry_text,
        read_artifact=read_artifact,
    )
    if findings:
        for install_path in registry_repair_paths(
            settings_text=settings_text,
            project_root=project_root,
            registry_text=registry_text,
            read_artifact=read_artifact,
        ):
            removal = remove_cache_dir(install_path=install_path)
            if isinstance(removal, IOFailure):
                return EnsureReport(
                    findings=(unsafe_perform_io(removal.failure()).finding,), notices=notices
                )
        command_findings = _run_commands(commands=commands, runner=runner)
        registry_text = read_registry()
        findings = command_findings or registry_findings(
            settings_text=settings_text,
            project_root=project_root,
            registry_text=registry_text,
            read_artifact=read_artifact,
        )
    repaired = repair_notice(state=state, project_root=project_root, registry_text=registry_text)
    return EnsureReport(findings=findings, notices=(*notices, *repaired))


def ensure(  # noqa: PLR0913 — preserve existing I/O seams while adding proven skip sets.
    *,
    settings_text: str,
    project_root: str,
    runner: PluginCommandRunner,
    read_registry: RegistryReader,
    read_artifact: ArtifactReader = plugin_artifact_findings,
    remove_cache_dir: CacheDirRemover = remove_plugin_cache_dir,
    current_plugins: frozenset[str] = frozenset(),
    registered_marketplaces: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Provision from settings, then confirm it landed. Empty means provisioned."""
    return ensure_report(
        settings_text=settings_text,
        project_root=project_root,
        runner=runner,
        read_registry=read_registry,
        read_artifact=read_artifact,
        remove_cache_dir=remove_cache_dir,
        current_plugins=current_plugins,
        registered_marketplaces=registered_marketplaces,
    ).findings


def _read_installed_registry() -> str | None:  # pragma: no cover
    """The Claude installed-plugins registry text, or None when absent."""
    path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _read_marketplace_registry() -> str | None:  # pragma: no cover
    path = Path.home() / ".claude/plugins/known_marketplaces.json"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


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
    current, registered = _startup_currency(
        settings_text=settings_text,
        project_root=str(root),
        registry_text=_read_installed_registry(),
        marketplaces_text=_read_marketplace_registry(),
    )
    report = ensure_report(
        settings_text=settings_text,
        project_root=str(root),
        runner=_logged_runner,
        read_registry=_read_installed_registry,
        current_plugins=current,
        registered_marketplaces=registered,
    )
    for notice in report.notices:
        _ = sys.stdout.write(f"ensure_plugins: {notice}\n")
    for finding in report.findings:
        _ = sys.stderr.write(f"ensure_plugins: {finding}\n")
    return 4 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
