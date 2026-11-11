"""The refusals an orchestrator adopt step decides before it moves anything.

A tag adopt names a published release tag of the orchestrator plugin instead of
a full commit id. Before it builds or writes anything it establishes, from the
marketplace's REMOTE and never from the host's shallow marketplace clone, that
the tag names a non-draft GitHub release, which commit the tag and the
marketplace's recorded ref name, and that the forge compares the tag's commit as
identical to or ahead of the recorded ref's commit; every GitHub read goes
through the budgeted client (`budgeted_gh.gh_read`). It also establishes that the
clone's own session reconcile will hold the adopted build: the package the
clone's `just ensure-plugins` runs must pass the hold probe, and the clone's
committed settings must carry a SessionStart hook that runs `just ensure-plugins`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandRunner, command_answer
from livespec_dev_tooling.fleet._orchestrator_hold import ORCHESTRATOR_PLUGIN
from livespec_dev_tooling.fleet._plugin_build_currency_reads import governed_pins
from livespec_dev_tooling.fleet._plugin_settings import marketplace_of

__all__: list[str] = [
    "HOLD_PROBE_MODULE",
    "ORCHESTRATOR_MARKETPLACE",
    "ORCHESTRATOR_REPO",
    "AdoptionOutcome",
    "GhReader",
    "RemoteCommits",
    "ancestry_refusal",
    "enablement_refusal",
    "hold_probe_refusal",
    "is_commit_prefix",
    "is_full_commit",
    "json_object",
    "marketplace_install_source",
    "marketplace_remote",
    "release_refusal",
    "remote_commits",
    "session_hook_refusal",
]

ORCHESTRATOR_REPO = "thewoolleyman/livespec-orchestrator-beads-fabro"
ORCHESTRATOR_MARKETPLACE = marketplace_of(plugin=ORCHESTRATOR_PLUGIN)
HOLD_PROBE_MODULE = "livespec_dev_tooling.fleet.orchestrator_hold_probe"

_FULL_COMMIT = re.compile(r"[0-9a-f]{40}")
_COMMIT_PREFIX = re.compile(r"[0-9a-f]{7,39}")
_TAG_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
_ENSURE_PLUGINS = re.compile(r"\bjust\s+ensure-plugins(?![\w-])")
_ACCEPTED_COMPARISONS = frozenset({"identical", "ahead"})


@dataclass(frozen=True, kw_only=True)
class AdoptionOutcome:
    """The lines an adoption printed and, when it failed, the cause."""

    lines: tuple[str, ...]
    failure: str


class GhReader(Protocol):
    """One GitHub read through the budgeted client; `args` excludes the leading `gh`."""

    def __call__(self, *, args: list[str]) -> GhRead: ...


@dataclass(frozen=True, kw_only=True)
class RemoteCommits:
    """The tag's commit and the recorded ref's commit, or why they were not read."""

    tag_commit: str
    ref_commit: str
    failure: str


def is_full_commit(*, build: str) -> bool:
    """Whether the named build is a full 40-hex commit id."""
    return _FULL_COMMIT.fullmatch(build.strip().lower()) is not None


def is_commit_prefix(*, build: str) -> bool:
    """Whether the named build is a 7-to-39-character hexadecimal commit prefix."""
    return _COMMIT_PREFIX.fullmatch(build.strip().lower()) is not None


def json_object(*, text: str | None) -> dict[str, object]:
    """The JSON object a text holds, or an empty mapping for anything else."""
    try:
        parsed: object = json.loads(text) if text is not None else None
    except json.JSONDecodeError:
        return {}
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}


def enablement_refusal(*, clone: Path) -> str:
    """Why the clone's committed settings cannot take the adopt step, or the empty string."""
    settings = clone / ".claude" / "settings.json"
    if not settings.is_file():
        return f"{clone} has no committed .claude/settings.json"
    pins = governed_pins(settings_text=settings.read_text(encoding="utf-8"))
    if pins.unreadable:
        return f"{settings} is unusable: {pins.unreadable}"
    if all(pin.plugin != ORCHESTRATOR_PLUGIN for pin in pins.sources):
        return f"{settings} does not enable {ORCHESTRATOR_PLUGIN}"
    return ""


def _session_start_commands(*, settings: dict[str, object]) -> tuple[str, ...]:
    """Every command string the settings' SessionStart hooks run."""
    hooks = settings.get("hooks")
    groups = cast("dict[str, object]", hooks).get("SessionStart") if isinstance(hooks, dict) else ()
    commands: list[str] = []
    for group in cast("list[object]", groups) if isinstance(groups, list) else ():
        entries = cast("dict[str, object]", group).get("hooks") if isinstance(group, dict) else ()
        for entry in cast("list[object]", entries) if isinstance(entries, list) else ():
            command = (
                cast("dict[str, object]", entry).get("command") if isinstance(entry, dict) else None
            )
            if isinstance(command, str):
                commands.append(command)
    return tuple(commands)


def session_hook_refusal(*, clone: Path) -> str:
    """Why the clone's next session start would not run `just ensure-plugins`, or ''."""
    settings = json_object(text=(clone / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = _session_start_commands(settings=settings)
    if any(_ENSURE_PLUGINS.search(command) for command in commands):
        return ""
    return (
        f"{clone}: its committed .claude/settings.json carries no SessionStart hook "
        "running just ensure-plugins; nothing was moved"
    )


def hold_probe_refusal(*, clone: Path, run: CommandRunner) -> str:
    """Why the package the clone's `just ensure-plugins` runs fails the hold probe, or ''."""
    probe = command_answer(
        outcome=run(args=["uv", "run", "--no-sync", "python", "-m", HOLD_PROBE_MODULE], cwd=clone)
    )
    if isinstance(probe, InvocationNotPerformed):
        detail = f"the hold probe did not run: {probe.reason}"
    elif probe.returncode != 0:
        detail = f"the hold probe exited {probe.returncode}: {probe.stderr.strip()[-300:]}"
    else:
        return ""
    return (
        f"{clone}: the livespec-dev-tooling package its just ensure-plugins runs does not "
        f"provide the orchestrator hold ({detail}); nothing was moved"
    )


def release_refusal(*, tag: str, gh: GhReader, marketplace_commit: str | None = None) -> str:
    """Why the argument is not a published orchestrator release tag, or ''."""
    named_commit = tag.strip().lower()
    if (
        marketplace_commit is not None
        and is_commit_prefix(build=named_commit)
        and marketplace_commit.startswith(named_commit)
    ):
        return (
            f"commit {tag} must be the full 40-character commit id; "
            f"re-run with {marketplace_commit}; nothing was moved"
        )
    named = (
        f"{tag!r} is neither a full commit id nor a published release tag of "
        f"{ORCHESTRATOR_REPO}; nothing was moved"
    )
    if _TAG_SHAPE.fullmatch(tag) is None:
        return named
    read = gh(args=["api", f"repos/{ORCHESTRATOR_REPO}/releases/tags/{tag}"])
    if read.returncode != 0:
        return f"{named} (the release read exited {read.returncode}: {read.stderr.strip()})"
    release = json_object(text=read.stdout)
    if release.get("tag_name") != tag or release.get("draft") is not False:
        return f"{named} (the release read names no published release for that tag)"
    return ""


def marketplace_remote(*, known_marketplaces: str | None) -> tuple[str, str] | None:
    """The `(remote URL, ref)` the host records for the orchestrator marketplace."""
    entry = json_object(text=known_marketplaces).get(ORCHESTRATOR_MARKETPLACE)
    source = cast("dict[str, object]", entry).get("source") if isinstance(entry, dict) else None
    fields = cast("dict[str, object]", source) if isinstance(source, dict) else {}
    ref, repo, url = fields.get("ref"), fields.get("repo"), fields.get("url")
    if not isinstance(ref, str) or not ref:
        return None
    if fields.get("source") == "github" and isinstance(repo, str) and repo:
        return f"https://github.com/{repo}.git", ref
    if isinstance(url, str) and url:
        return url, ref
    return None


def marketplace_install_source(*, known_marketplaces: str | None) -> tuple[str, str] | None:
    """The installed marketplace location and ref the host recorded, when both are usable."""
    entry = json_object(text=known_marketplaces).get(ORCHESTRATOR_MARKETPLACE)
    fields = cast("dict[str, object]", entry) if isinstance(entry, dict) else {}
    source = fields.get("source")
    ref = cast("dict[str, object]", source).get("ref") if isinstance(source, dict) else None
    location = fields.get("installLocation")
    if isinstance(ref, str) and ref and isinstance(location, str) and location:
        return location, ref
    return None


def _peeled(*, refs: dict[str, str], name: str) -> str:
    """The commit a ref names: the peeled object for an annotated tag."""
    return refs.get(f"{name}^{{}}", refs.get(name, ""))


def remote_commits(*, tag: str, url: str, ref: str, run: CommandRunner) -> RemoteCommits:
    """Read the tag's commit and the recorded ref's commit from the marketplace's remote."""
    patterns = [f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}", f"refs/heads/{ref}"]
    patterns += [f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}"]
    listing = command_answer(outcome=run(args=["git", "ls-remote", url, *patterns]))
    if isinstance(listing, InvocationNotPerformed):
        return RemoteCommits(tag_commit="", ref_commit="", failure=listing.reason)
    if listing.returncode != 0:
        failure = f"git ls-remote exited {listing.returncode}: {listing.stderr.strip()}"
        return RemoteCommits(tag_commit="", ref_commit="", failure=failure)
    refs = {
        name: sha.strip().lower()
        for sha, _, name in (line.partition("\t") for line in listing.stdout.splitlines())
        if name
    }
    tag_commit = _peeled(refs=refs, name=f"refs/tags/{tag}")
    ref_commit = refs.get(f"refs/heads/{ref}", "") or _peeled(refs=refs, name=f"refs/tags/{ref}")
    missing = [
        name for name, sha in ((f"tag {tag}", tag_commit), (f"ref {ref}", ref_commit)) if not sha
    ]
    failure = f"{url} names no commit for {' or '.join(missing)}" if missing else ""
    return RemoteCommits(tag_commit=tag_commit, ref_commit=ref_commit, failure=failure)


def ancestry_refusal(*, commits: RemoteCommits, gh: GhReader) -> str:
    """Why the forge does not compare the tag's commit as identical to or ahead of the ref's."""
    both = f"tag commit {commits.tag_commit}, recorded ref commit {commits.ref_commit}"
    compare_path = f"repos/{ORCHESTRATOR_REPO}/compare/{commits.ref_commit}...{commits.tag_commit}"
    compare = gh(args=["api", compare_path, "--jq", ".status"])
    status = compare.stdout.strip()
    if compare.returncode != 0 or status not in _ACCEPTED_COMPARISONS:
        answer = status or f"exit {compare.returncode}: {compare.stderr.strip()}"
        return (
            f"the forge compares the tag's commit as {answer!r}, not identical to or ahead "
            f"of the recorded ref's commit; {both}; nothing was moved"
        )
    return ""
