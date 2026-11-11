"""A self-serving build, keyed to a release rather than to the commit that serves it.

Some consumers serve a capability from their own source: this library's gate readers are
an editable install of its own checkout, and a consumer that runs its own local workflow
templates serves them from its own default branch. If such a serving build were the
serving commit itself, no committed claim could ever name it, because committing the
claim moves that commit. So the serving build is a release tag that is an ancestor of the
serving commit, with the tag's commit confirmed on the remote.

It is read per row, never for the whole tree: a claim naming release R classifies its row
only while every file of THAT row's surface (`_incident_fleet_surface_files`) at the
serving commit is byte-identical to the release's, so commits that touch only files
outside the surface leave it serving, and so does a later release that touches none of
them. The `serving` line names the newest release ancestor. A release name alone is still
never evidence: the bytes that serve are read and bound to the release, and anything else
is unverified with a named reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling._incident_fleet_surface_files import SURFACE_ROOTS, surface_files
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import CommandRunner, command_answer
from livespec_dev_tooling.incident_fleet_host import FLEET_OWNER

__all__: list[str] = [
    "ServingReading",
    "SurfaceReading",
    "claim_reason",
    "release_keyed_reading",
    "remote_commit",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ri2lwi
_RELEASE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_LS_REMOTE_FIELDS = 2
_TAG_FIELDS = 3
_UNDEFINED = "no surface file set is defined for this surface"


@dataclass(frozen=True, kw_only=True)
class SurfaceReading:
    """One surface's files at the serving commit, compared against the confirmed releases.

    `serving` holds the confirmed releases whose bytes for this surface are the serving
    commit's. `changed` names the surface files found changed at the newest release that
    does not serve it; every older release is judged changed since it too, without
    another comparison. `absent` names surface files the serving commit lacks.
    """

    surface: str
    serving: frozenset[str] = frozenset()
    changed: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ServingReading:
    """One capability's serving read, with what it rests on.

    `build` is "" when the read is unverified, and `detail` names the newest release
    ancestor and the serving commit `head`, or why nothing matched. A release-keyed read
    also carries `releases`, the release tags that are ancestors of `head` (None on any
    other read); `confirmed`, those the remote confirms at the commit they name here,
    newest first; `unread`, the confirmed release at which comparing stopped unread (it
    and every older one are unread); and `surfaces`, one reading per surface.
    """

    build: str
    detail: str = ""
    head: str = ""
    releases: frozenset[str] | None = None
    confirmed: tuple[str, ...] = ()
    unread: str = ""
    surfaces: tuple[SurfaceReading, ...] = ()

    def build_for(self, *, surface: str, claimed: str) -> str:
        """The build this read serves for a row claiming `claimed`; "" when it serves none."""
        if self.releases is None:
            return self.build
        reason = claim_reason(reading=self, surface=surface, claimed=claimed)
        return claimed if claimed != "" and reason == "" else ""


def remote_commit(*, run: CommandRunner, repo: str, ref: str) -> str | None:
    """The commit `ref` names on the remote; an annotated tag is read through to its commit."""
    rows = _remote_rows(run=run, repo=repo, refs=[ref, f"{ref}^{{}}"])
    commit = None if rows is None else rows.get(f"{ref}^{{}}") or rows.get(ref)
    return commit if commit and _COMMIT.fullmatch(commit) else None


def _remote_rows(*, run: CommandRunner, repo: str, refs: list[str]) -> dict[str, str] | None:
    url = f"https://github.com/{FLEET_OWNER}/{repo}.git"
    answer = command_answer(outcome=run(args=["git", "ls-remote", url, *refs]))
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    return {
        fields[1]: fields[0]
        for line in answer.stdout.splitlines()
        if len(fields := line.split()) == _LS_REMOTE_FIELDS
    }


def _remote_releases(*, run: CommandRunner, repo: str) -> dict[str, str]:
    """Each `vX.Y.Z` tag on the remote and its commit (an annotated tag read through)."""
    rows = _remote_rows(run=run, repo=repo, refs=["refs/tags/v*"]) or {}
    plain = {ref.removeprefix("refs/tags/"): sha for ref, sha in rows.items() if "^{}" not in ref}
    peeled = {
        ref.removeprefix("refs/tags/").removesuffix("^{}"): sha
        for ref, sha in rows.items()
        if ref.endswith("^{}")
    }
    return {tag: peeled.get(tag, sha) for tag, sha in plain.items()}


def _git(*, run: CommandRunner, clone: Path, args: list[str]) -> str | None:
    answer = command_answer(outcome=run(args=["git", "-C", str(clone), *args]))
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    return answer.stdout


def _local_releases(*, run: CommandRunner, clone: Path) -> dict[str, str]:
    """Each local `vX.Y.Z` tag and the commit it names (an annotated tag read through)."""
    form = "%(refname:strip=2)%09%(objectname)%09%(*objectname)"
    listed = _git(run=run, clone=clone, args=["for-each-ref", f"--format={form}", "refs/tags/v*"])
    rows = [line.split("\t") for line in (listed or "").splitlines()]
    return {row[0]: row[2] or row[1] for row in rows if len(row) == _TAG_FIELDS}


class _TextAt(Protocol):
    def __call__(self, *, path: str) -> str | None: ...


def _reader(*, run: CommandRunner, clone: Path, head: str) -> _TextAt:
    """Each file's text at `head`, read once; None when `head` has no such file."""
    texts: dict[str, str | None] = {}

    def read(*, path: str) -> str | None:
        if path not in texts:
            texts[path] = _git(run=run, clone=clone, args=["show", f"{head}:{path}"])
        return texts[path]

    return read


def _unverified(*, head: str, detail: str, releases: frozenset[str] | None) -> ServingReading:
    return ServingReading(build="", detail=detail, head=head, releases=releases)


def _compared(
    *,
    run: CommandRunner,
    clone: Path,
    head: str,
    capability: str,
    confirmed: tuple[str, ...],
    commits: dict[str, str],
) -> tuple[tuple[SurfaceReading, ...], str] | None:
    """Each surface against the confirmed releases, newest first, and where reading stopped.

    One release's changed files are read once and judged against every surface still
    serving; a surface stops serving at the first release that changed one of its files,
    and reading stops once no surface still serves, or at a release whose changed files
    cannot be read. None when the newest release's cannot: nothing serves then.
    """
    read = _reader(run=run, clone=clone, head=head)
    files: dict[str, frozenset[str]] = {}
    readings: dict[str, SurfaceReading] = {}
    for surface, roots in SURFACE_ROOTS.items():
        if SURFACE_CAPABILITY.get(surface) != capability:
            continue
        files[surface], absent = surface_files(roots=roots, read=lambda path: read(path=path))
        readings[surface] = SurfaceReading(surface=surface, absent=absent)
    alive = {surface for surface, reading in readings.items() if not reading.absent}
    serving: dict[str, set[str]] = {surface: set() for surface in alive}
    for release in confirmed:
        if not alive:
            break
        diff = _git(
            run=run,
            clone=clone,
            args=["diff", "--name-only", "--no-renames", commits[release], head],
        )
        if diff is None:
            if release == confirmed[0]:
                return None
            return _readings(readings=readings, serving=serving), release
        touched = frozenset(diff.split("\n")) - {""}
        for surface in sorted(alive):
            changed = sorted(files[surface] & touched)
            if changed:
                readings[surface] = SurfaceReading(surface=surface, changed=tuple(changed))
                alive.discard(surface)
            else:
                serving[surface].add(release)
    return _readings(readings=readings, serving=serving), ""


def _readings(
    *, readings: dict[str, SurfaceReading], serving: dict[str, set[str]]
) -> tuple[SurfaceReading, ...]:
    return tuple(
        SurfaceReading(
            surface=surface,
            serving=frozenset(serving.get(surface, ())),
            changed=reading.changed,
            absent=reading.absent,
        )
        for surface, reading in readings.items()
    )


def release_keyed_reading(
    *, run: CommandRunner, clone: Path, repo: str, head: str, capability: str
) -> ServingReading:
    """The release ancestors of `head`, and which of them each capability surface serves."""
    listed = _git(run=run, clone=clone, args=["tag", "--merged", head, "--list", "v*"])
    if listed is None:
        detail = f"the release tags that are ancestors of {head} cannot be read in {clone}"
        return _unverified(head=head, detail=detail, releases=None)
    versions = {
        tag: tuple(int(part) for part in match.groups())
        for tag in listed.split()
        if (match := _RELEASE.fullmatch(tag))
    }
    releases = frozenset(versions)
    if not releases:
        detail = f"no release tag is an ancestor of {head}"
        return _unverified(head=head, detail=detail, releases=releases)
    ordered = sorted(versions, key=versions.__getitem__, reverse=True)
    newest = ordered[0]
    local = _local_releases(run=run, clone=clone)
    remote = _remote_releases(run=run, repo=repo)
    confirmed = tuple(tag for tag in ordered if tag in local and local[tag] == remote.get(tag))
    if newest not in confirmed:
        detail = f"release {newest} is not confirmed on the remote at the commit it names here"
        return _unverified(head=head, detail=detail, releases=releases)
    compared = _compared(
        run=run, clone=clone, head=head, capability=capability, confirmed=confirmed, commits=local
    )
    if compared is None:
        detail = f"the files changed between release {newest} and {head} cannot be read"
        return _unverified(head=head, detail=detail, releases=releases)
    surfaces, unread = compared
    return ServingReading(
        build=newest,
        detail=f"release {newest} at HEAD {head}",
        head=head,
        releases=releases,
        confirmed=confirmed,
        unread=unread,
        surfaces=surfaces,
    )


def claim_reason(*, reading: ServingReading, surface: str, claimed: str) -> str:
    """Why a claim naming `claimed` cannot classify its row against `reading`; "" if it may."""
    if not reading.build:
        return reading.detail
    if reading.releases is None:
        return ""
    if claimed not in reading.releases:
        return f"claimed release {claimed} is not an ancestor of HEAD {reading.head}"
    if claimed not in reading.confirmed:
        return f"release {claimed} is not confirmed on the remote at the commit it names here"
    ranked = reading.confirmed.index
    if reading.unread and ranked(claimed) >= ranked(reading.unread):
        return f"the files changed between release {claimed} and {reading.head} cannot be read"
    return _surface_reason(reading=reading, surface=surface, claimed=claimed)


def _surface_reason(*, reading: ServingReading, surface: str, claimed: str) -> str:
    read = {each.surface: each for each in reading.surfaces}.get(surface)
    if read is None:
        return _UNDEFINED
    if read.absent:
        return f"surface files absent at the serving commit: {', '.join(read.absent)}"
    if claimed in read.serving:
        return ""
    return f"surface files changed since release {claimed}: {', '.join(read.changed)}"
