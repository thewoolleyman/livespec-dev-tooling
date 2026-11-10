"""The operator step that moves the orchestrator plugin to a named build.

A session reconcile never moves an installed orchestrator build. This is the
named operator step that does. Given a full commit id it refreshes the host's
marketplace, refuses any commit other than the one the marketplace names at its
recorded ref, runs `claude plugin update` at project scope in the chosen clone,
and confirms the install record afterwards. `claude plugin update` can report
"already at the latest version" after a failed fetch, which is why the record
is read back. Given a published release tag it takes the tag adopt instead
(`_tag_adopt`), which moves only that clone's record and never touches the
host's marketplace. Run on its own, the step holds the host-wide adoption lock
for its whole run.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._adoption_lock import adoption_lock_path, holding_adoption_lock
from livespec_dev_tooling.fleet._fleet_manifest_read import (
    ManifestUnreadable,
    manifest_names,
    master_manifest_source,
)
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import (
    CommandRunner,
    command_answer,
    default_command_runner,
)
from livespec_dev_tooling.fleet._orchestrator_hold import (
    ORCHESTRATOR_PLUGIN,
    installed_build,
)
from livespec_dev_tooling.fleet._plugin_build_currency_core import (
    BuildIdentifier,
    resolved_build,
    unresolved_build,
)
from livespec_dev_tooling.fleet._plugin_settings import marketplace_of
from livespec_dev_tooling.fleet._tag_adopt import TagAdoptHost, host_seams, tag_adopt
from livespec_dev_tooling.fleet._tag_adopt_checks import (
    AdoptionOutcome,
    enablement_refusal,
    is_full_commit,
)

__all__: list[str] = [
    "AdoptionOutcome",
    "CloneUnresolved",
    "adopt_build",
    "adopt_named_build",
    "clones_root",
    "main",
    "marketplace_tip",
    "read_installed_registry",
    "read_known_marketplaces",
    "resolve_clone",
]

_MARKETPLACE = marketplace_of(plugin=ORCHESTRATOR_PLUGIN)
_USAGE_EXIT = 2


@dataclass(frozen=True, kw_only=True)
class CloneUnresolved:
    """A clone or clones root that could not be resolved, and why."""

    cause: str


def read_installed_registry() -> str | None:  # pragma: no cover
    """The Claude installed-plugins registry text, or None when absent."""
    path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def read_known_marketplaces() -> str | None:  # pragma: no cover
    """The host's `known_marketplaces.json` text, or None when absent."""
    path = Path.home() / ".claude" / "plugins" / "known_marketplaces.json"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _recorded_source(*, text: str | None) -> tuple[str, str] | None:
    """The `(installLocation, ref)` the host records for the orchestrator marketplace."""
    parsed: object = json.loads(text) if text is not None else None
    entry = (
        cast("dict[str, object]", parsed).get(_MARKETPLACE) if isinstance(parsed, dict) else None
    )
    if not isinstance(entry, dict):
        return None
    fields = cast("dict[str, object]", entry)
    source = fields.get("source")
    ref = cast("dict[str, object]", source).get("ref") if isinstance(source, dict) else None
    location = fields.get("installLocation")
    if isinstance(ref, str) and ref and isinstance(location, str) and location:
        return location, ref
    return None


def marketplace_tip(
    *, run: CommandRunner, read_known_marketplaces: Callable[[], str | None]
) -> BuildIdentifier:
    """Refresh the orchestrator marketplace, then read the commit at its recorded `origin/<ref>`."""
    refresh = command_answer(
        outcome=run(args=["claude", "plugin", "marketplace", "update", _MARKETPLACE])
    )
    if isinstance(refresh, InvocationNotPerformed):
        return unresolved_build(detail=f"marketplace refresh did not run: {refresh.reason}")
    if refresh.returncode != 0:
        return unresolved_build(
            detail=f"marketplace refresh exited {refresh.returncode}: {refresh.stderr.strip()}"
        )
    recorded = _recorded_source(text=read_known_marketplaces())
    if recorded is None:
        return unresolved_build(
            detail=f"known_marketplaces.json records no source and location for {_MARKETPLACE}"
        )
    location, ref = recorded
    read = command_answer(
        outcome=run(args=["git", "-C", location, "rev-parse", "--verify", f"origin/{ref}"])
    )
    if isinstance(read, InvocationNotPerformed):
        return unresolved_build(detail=f"git rev-parse did not run: {read.reason}")
    if read.returncode != 0:
        return unresolved_build(
            detail=f"git rev-parse origin/{ref} exited {read.returncode}: {read.stderr.strip()}"
        )
    return resolved_build(sha=read.stdout)


def resolve_clone(
    *, clone: str, clones_root: Path, names: frozenset[str]
) -> Path | CloneUnresolved:
    """An absolute path as given, or a manifest repository name under the clones root."""
    if Path(clone).is_absolute():
        return Path(clone)
    if clone in names:
        return clones_root / clone
    return CloneUnresolved(
        cause=f"{clone!r} is neither an absolute path nor a name in the fleet manifest"
    )


def clones_root(*, env_root: str | None, cwd: Path, run: CommandRunner) -> Path | CloneUnresolved:
    """The env root when set, else the parent of this repository's primary checkout."""
    if env_root:
        return Path(env_root)
    answer = command_answer(
        outcome=run(
            args=["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd
        )
    )
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return CloneUnresolved(
            cause=f"the primary checkout of the repository at {cwd} could not be located"
        )
    return Path(answer.stdout.strip()).parent.parent


def _refused(*, cause: str) -> AdoptionOutcome:
    return AdoptionOutcome(lines=(), failure=cause)


def _refusal_before_update(
    *,
    clone: Path,
    named: str,
    run: CommandRunner,
    read_known_marketplaces: Callable[[], str | None],
) -> str:
    """Why nothing may be moved yet, or the empty string when the update may run."""
    if not clone.is_dir():
        return f"local clone missing at {clone}"
    refusal = enablement_refusal(clone=clone)
    if refusal:
        return refusal
    tip = marketplace_tip(run=run, read_known_marketplaces=read_known_marketplaces)
    if tip.unresolved:
        return f"the marketplace commit could not be read: {tip.unresolved}"
    if tip.sha != named:
        return f"named build {named} is not the marketplace commit {tip.sha}; nothing was moved"
    return ""


def adopt_build(
    *,
    clone: Path,
    build: str,
    run: CommandRunner,
    read_registry: Callable[[], str | None],
    read_known_marketplaces: Callable[[], str | None],
) -> AdoptionOutcome:
    """Update the orchestrator plugin in one clone to the named marketplace commit."""
    if not is_full_commit(build=build):
        return _refused(cause=f"{build!r} is not a full commit id; nothing was moved")
    named = build.strip().lower()
    refusal = _refusal_before_update(
        clone=clone, named=named, run=run, read_known_marketplaces=read_known_marketplaces
    )
    if refusal:
        return _refused(cause=refusal)
    before = installed_build(
        registry_text=read_registry(), plugin=ORCHESTRATOR_PLUGIN, project_root=str(clone)
    )
    update = command_answer(
        outcome=run(
            args=["claude", "plugin", "update", ORCHESTRATOR_PLUGIN, "-s", "project"], cwd=clone
        )
    )
    if isinstance(update, InvocationNotPerformed):
        return _refused(cause=f"claude plugin update did not run: {update.reason}")
    if update.returncode != 0:
        return _refused(cause=f"claude plugin update exited {update.returncode}")
    after = installed_build(
        registry_text=read_registry(), plugin=ORCHESTRATOR_PLUGIN, project_root=str(clone)
    )
    lines = (f"{clone} {ORCHESTRATOR_PLUGIN} before={before} after={after}",)
    if after != named:
        cause = f"install record holds {after} after the update, not {named}"
        return AdoptionOutcome(lines=lines, failure=cause)
    return AdoptionOutcome(lines=lines, failure="")


def adopt_named_build(
    *,
    clone: Path,
    build: str,
    run: CommandRunner,
    read_registry: Callable[[], str | None],
    read_known_marketplaces: Callable[[], str | None],
    tag_host: TagAdoptHost,
) -> AdoptionOutcome:
    """Take the full-commit adopt step for a full commit id, and the tag adopt otherwise."""
    if is_full_commit(build=build):
        return adopt_build(
            clone=clone,
            build=build,
            run=run,
            read_registry=read_registry,
            read_known_marketplaces=read_known_marketplaces,
        )
    return tag_adopt(clone=clone, tag=build.strip(), host=tag_host)


def _resolved_clone(*, clone_arg: str) -> Path | CloneUnresolved:  # pragma: no cover
    """The clone a CLI argument names, resolved against the manifest when it is a name."""
    names: frozenset[str] = frozenset()
    root = clones_root(
        env_root=os.environ.get("LIVESPEC_FLEET_CLONES_ROOT"),
        cwd=Path.cwd(),
        run=default_command_runner,
    )
    if not Path(clone_arg).is_absolute():
        source = master_manifest_source()
        if isinstance(source, ManifestUnreadable):
            return CloneUnresolved(cause=source.cause)
        names = manifest_names(manifest_source=source)
    if isinstance(root, CloneUnresolved):
        return root
    return resolve_clone(clone=clone_arg, clones_root=root, names=names)


def _adopt_from_cli(*, clone_arg: str, build: str, home: Path) -> int:  # pragma: no cover
    """Resolve the clone, take the step and print its lines; the exit code."""
    clone = _resolved_clone(clone_arg=clone_arg)
    if isinstance(clone, CloneUnresolved):
        _ = sys.stderr.write(f"adopt-orchestrator-build: {clone.cause}\n")
        return 1
    outcome = adopt_named_build(
        clone=clone,
        build=build,
        run=default_command_runner,
        read_registry=read_installed_registry,
        read_known_marketplaces=read_known_marketplaces,
        tag_host=host_seams(home=home),
    )
    for line in outcome.lines:
        _ = sys.stdout.write(f"adopt-orchestrator-build: {line}\n")
    if outcome.failure:
        _ = sys.stderr.write(f"adopt-orchestrator-build: {outcome.failure}\n")
        return 1
    return 0


def _report_wait() -> None:  # pragma: no cover
    _ = sys.stderr.write("adopt-orchestrator-build: waiting for the host-wide adoption lock\n")


def main() -> int:  # pragma: no cover
    """CLI entry point: `adopt_orchestrator_build <clone> <build>`, under the adoption lock."""
    home = Path.home()
    if len(sys.argv) != 3:  # noqa: PLR2004 — program name, clone and build.
        _ = sys.stderr.write("usage: just adopt-orchestrator-build <clone> <build>\n")
        return _USAGE_EXIT
    clone_arg, build = sys.argv[1], sys.argv[2]
    return holding_adoption_lock(
        path=adoption_lock_path(home=home),
        body=lambda: _adopt_from_cli(clone_arg=clone_arg, build=build, home=home),
        on_wait=_report_wait,
    )


if __name__ == "__main__":
    raise SystemExit(main())
