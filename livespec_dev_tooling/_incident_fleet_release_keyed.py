"""A self-serving build, keyed to a release rather than to the commit that serves it.

Some consumers serve a capability from their own source: this library's gate readers are
an editable install of its own checkout, and a consumer that runs its own local workflow
templates serves them from its own default branch. If such a serving build were the
serving commit itself, no committed claim could ever name it, because committing the
claim moves that commit. So the serving build is the newest release tag that is an
ancestor of the serving commit, with the tag's commit confirmed on the remote.

It is read per row, never for the whole tree: a row serves that release only while
every file of ITS surface (`_incident_fleet_surface_files`) at the serving commit is
byte-identical to the release's, so commits that touch only files outside the surface
leave it serving. A release name alone is still never evidence: the bytes that serve
are read and bound to the release, and anything else is unverified with a named reason.
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
    "claim_reason",
    "release_keyed_reading",
    "remote_commit",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ri2lwi
_RELEASE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_LS_REMOTE_FIELDS = 2
_UNDEFINED = "no surface file set is defined for this surface"


@dataclass(frozen=True, kw_only=True)
class ServingReading:
    """One capability's serving read, with what it rests on.

    `build` is "" when the read is unverified, and `detail` names the matched release and
    the serving commit `head`, or why nothing matched. A release-keyed read also carries
    `releases`, the release tags that are ancestors of `head` (None on any other read),
    and `surfaces`: each surface of the capability, with "" when its files are
    byte-identical to the release's, else the reason they are not.
    """

    build: str
    detail: str = ""
    head: str = ""
    releases: frozenset[str] | None = None
    surfaces: tuple[tuple[str, str], ...] = ()

    def build_for(self, *, surface: str) -> str:
        """The build this read serves for one row's surface; "" when it serves none."""
        if self.releases is None:
            return self.build
        return self.build if dict(self.surfaces).get(surface, _UNDEFINED) == "" else ""


def remote_commit(*, run: CommandRunner, repo: str, ref: str) -> str | None:
    """The commit `ref` names on the remote; an annotated tag is read through to its commit."""
    url = f"https://github.com/{FLEET_OWNER}/{repo}.git"
    answer = command_answer(outcome=run(args=["git", "ls-remote", url, ref, f"{ref}^{{}}"]))
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    rows = {
        fields[1]: fields[0]
        for line in answer.stdout.splitlines()
        if len(fields := line.split()) == _LS_REMOTE_FIELDS
    }
    commit = rows.get(f"{ref}^{{}}") or rows.get(ref)
    return commit if commit and _COMMIT.fullmatch(commit) else None


def _git(*, run: CommandRunner, clone: Path, args: list[str]) -> str | None:
    answer = command_answer(outcome=run(args=["git", "-C", str(clone), *args]))
    if isinstance(answer, InvocationNotPerformed) or answer.returncode != 0:
        return None
    return answer.stdout


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


def _surface_reasons(
    *, read: _TextAt, changed: frozenset[str], capability: str, release: str
) -> tuple[tuple[str, str], ...]:
    reasons: list[tuple[str, str]] = []
    for surface, roots in SURFACE_ROOTS.items():
        if SURFACE_CAPABILITY.get(surface) != capability:
            continue
        files, absent = surface_files(roots=roots, read=lambda path: read(path=path))
        touched = sorted(files & changed)
        if absent:
            reasons.append(
                (surface, f"surface files absent at the serving commit: {', '.join(absent)}")
            )
        elif touched:
            reasons.append(
                (surface, f"surface files changed since release {release}: {', '.join(touched)}")
            )
        else:
            reasons.append((surface, ""))
    return tuple(reasons)


def _unverified(*, head: str, detail: str, releases: frozenset[str] | None) -> ServingReading:
    return ServingReading(build="", detail=detail, head=head, releases=releases)


def release_keyed_reading(
    *, run: CommandRunner, clone: Path, repo: str, head: str, capability: str
) -> ServingReading:
    """The newest release ancestor of `head`, and which of the capability's surfaces it serves."""
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
    newest = max(versions, key=versions.__getitem__)
    tagged = _git(
        run=run,
        clone=clone,
        args=["rev-parse", "--verify", "--quiet", f"refs/tags/{newest}^{{commit}}"],
    )
    tagged = None if tagged is None else tagged.strip()
    if tagged is None or tagged != remote_commit(run=run, repo=repo, ref=f"refs/tags/{newest}"):
        detail = f"release {newest} is not confirmed on the remote at the commit it names here"
        return _unverified(head=head, detail=detail, releases=releases)
    changed = _git(run=run, clone=clone, args=["diff", "--name-only", "--no-renames", tagged, head])
    if changed is None:
        detail = f"the files changed between release {newest} and {head} cannot be read"
        return _unverified(head=head, detail=detail, releases=releases)
    return ServingReading(
        build=newest,
        detail=f"release {newest} at HEAD {head}",
        head=head,
        releases=releases,
        surfaces=_surface_reasons(
            read=_reader(run=run, clone=clone, head=head),
            changed=frozenset(changed.split("\n")) - {""},
            capability=capability,
            release=newest,
        ),
    )


def claim_reason(*, reading: ServingReading, surface: str, claimed: str) -> str:
    """Why a claim naming `claimed` cannot classify its row against `reading`; "" if it may."""
    if reading.build_for(surface=surface) == claimed != "":
        return ""
    if not reading.build:
        return reading.detail
    if reading.releases is None:
        return ""
    if claimed not in reading.releases:
        return f"claimed release {claimed} is not an ancestor of HEAD {reading.head}"
    if claimed != reading.build:
        return (
            f"claimed release {claimed} is not {reading.build}, "
            f"the newest release ancestor of HEAD {reading.head}"
        )
    return dict(reading.surfaces).get(surface, _UNDEFINED)
