"""The tag adopt: move one clone's orchestrator build to a published release tag.

A canary adopts a release ahead of the release branch, so the tag adopt never
refreshes the host's marketplace, never runs `claude plugin update`, and never
changes the host's user-scope settings, marketplace registration or marketplace
clone. It refuses, moving nothing, until every check holds; then it builds the
release in a throwaway builder home, lands the build in the host cache, and
rewrites only the clone's install record.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from livespec_dev_tooling.budgeted_gh import gh_read
from livespec_dev_tooling.fleet._local_context import CommandRunner, default_command_runner
from livespec_dev_tooling.fleet._orchestrator_hold import ORCHESTRATOR_PLUGIN, installed_build
from livespec_dev_tooling.fleet._tag_adopt_build import (
    STAGING_DIRNAME,
    EnvCommandRunner,
    LandedBuild,
    build_plugin,
    env_command_runner,
    land_build,
)
from livespec_dev_tooling.fleet._tag_adopt_checks import (
    AdoptionOutcome,
    GhReader,
    ancestry_refusal,
    enablement_refusal,
    hold_probe_refusal,
    json_object,
    marketplace_remote,
    release_refusal,
    remote_commits,
    session_hook_refusal,
)
from livespec_dev_tooling.fleet._tag_adopt_record import (
    SETTLE_SECONDS,
    RecordCheck,
    clone_record_refusal,
    verify_record,
    write_record,
)

__all__: list[str] = ["TagAdoptHost", "host_seams", "tag_adopt"]

_SHORT = 12
# The builder home must be disk-backed: `/tmp` is commonly a tmpfs.
_SCRATCH_ROOT = Path("/var/tmp")  # noqa: S108 — a disk-backed scratch root, not a tmpfs.


@dataclass(frozen=True, kw_only=True)
class TagAdoptHost:
    """The tag adopt's seams onto the host: commands, paths, clock and settle wait."""

    run: CommandRunner
    gh: GhReader
    run_env: EnvCommandRunner
    base_env: Mapping[str, str]
    plugins_root: Path
    scratch_root: Path
    read_text: Callable[[Path], str]
    sleep: Callable[[float], None]
    settle_seconds: float
    now: Callable[[], str]


def _registry_text(*, host: TagAdoptHost) -> str | None:
    path = host.plugins_root / "installed_plugins.json"
    return host.read_text(path) if path.is_file() else None


def _known_marketplaces(*, host: TagAdoptHost) -> str | None:
    path = host.plugins_root / "known_marketplaces.json"
    return host.read_text(path) if path.is_file() else None


def _clone_refusal(*, clone: Path, tag: str, host: TagAdoptHost) -> str:
    """Why the clone or the argument cannot take a tag adopt, or ''."""
    if not clone.is_dir():
        return f"local clone missing at {clone}"
    refusal = release_refusal(tag=tag, gh=host.gh) or enablement_refusal(clone=clone)
    refusal = refusal or session_hook_refusal(clone=clone)
    refusal = refusal or hold_probe_refusal(clone=clone, run=host.run)
    registry = json_object(text=_registry_text(host=host))
    return refusal or clone_record_refusal(registry=registry, clone=str(clone))


def _land(*, tag: str, commit: str, host: TagAdoptHost) -> LandedBuild:
    """Build the release in a throwaway builder home, deleted on every exit, and land it."""
    host.scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="livespec-orchestrator-builder-", dir=host.scratch_root
    ) as raw_home:
        built = build_plugin(
            home=Path(raw_home),
            tag=tag,
            tag_commit=commit,
            base_env=host.base_env,
            run=host.run_env,
        )
        if built.failure:
            return LandedBuild(target=built.install_path, required=(), failure=built.failure)
        return land_build(source=built.install_path, commit=commit, plugins_root=host.plugins_root)


def _moved(*, clone: Path, tag: str, host: TagAdoptHost) -> str:
    """Resolve, build, land, record and verify; the cause when any step refuses."""
    remote = marketplace_remote(known_marketplaces=_known_marketplaces(host=host))
    if remote is None:
        return "known_marketplaces.json records no remote and ref for the orchestrator marketplace"
    url, ref = remote
    commits = remote_commits(tag=tag, url=url, ref=ref, run=host.run)
    if commits.failure:
        return f"the marketplace remote could not be read: {commits.failure}; nothing was moved"
    refusal = ancestry_refusal(commits=commits, gh=host.gh)
    if refusal:
        return refusal
    landed = _land(tag=tag, commit=commits.tag_commit, host=host)
    if landed.failure:
        return landed.failure
    registry_path = host.plugins_root / "installed_plugins.json"
    fields = {
        "installPath": str(landed.target),
        "version": commits.tag_commit[:_SHORT],
        "gitCommitSha": commits.tag_commit,
        "lastUpdated": host.now(),
    }
    failure = write_record(
        registry_path=registry_path, clone=str(clone), fields=fields, read_text=host.read_text
    )
    if failure:
        return failure
    (landed.target / ".orphaned_at").unlink(missing_ok=True)
    shutil.rmtree(host.plugins_root / STAGING_DIRNAME, ignore_errors=True)
    check = RecordCheck(clone=str(clone), commit=commits.tag_commit, required=landed.required)
    return verify_record(
        registry_path=registry_path,
        check=check,
        read_text=host.read_text,
        sleep=host.sleep,
        settle_seconds=host.settle_seconds,
    )


def tag_adopt(*, clone: Path, tag: str, host: TagAdoptHost) -> AdoptionOutcome:
    """Move only the named clone's install record to the published release tag's commit."""
    refusal = _clone_refusal(clone=clone, tag=tag, host=host)
    if refusal:
        return AdoptionOutcome(lines=(), failure=refusal)
    before = installed_build(
        registry_text=_registry_text(host=host), plugin=ORCHESTRATOR_PLUGIN, project_root=str(clone)
    )
    failure = _moved(clone=clone, tag=tag, host=host)
    after = installed_build(
        registry_text=_registry_text(host=host), plugin=ORCHESTRATOR_PLUGIN, project_root=str(clone)
    )
    lines = (f"{clone} {ORCHESTRATOR_PLUGIN} before={before} after={after} (tag {tag})",)
    return AdoptionOutcome(lines=lines, failure=failure)


def _now() -> str:  # pragma: no cover
    """The current UTC time in the install registry's millisecond ISO form."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def host_seams(*, home: Path) -> TagAdoptHost:  # pragma: no cover
    """The real host's seams, with `home` the invoking user's home."""
    return TagAdoptHost(
        run=default_command_runner,
        gh=gh_read,
        run_env=env_command_runner,
        base_env=dict(os.environ),
        plugins_root=home / ".claude" / "plugins",
        scratch_root=_SCRATCH_ROOT,
        read_text=lambda path: path.read_text(encoding="utf-8"),
        sleep=time.sleep,
        settle_seconds=SETTLE_SECONDS,
        now=_now,
    )
