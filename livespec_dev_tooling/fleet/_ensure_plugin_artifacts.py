"""Artifact validation for Claude plugin install records.

EVERY PUBLIC ANSWER HERE RIDES THE `IOResult` RAILWAY —
livespec-dev-tooling-qndn, the fleet-wide ROP conversion — and the reason is
not uniformity. What this module answers authorizes a DESTRUCTIVE repair:
`ensure_plugins` reads a non-empty finding set as "this cached build is
broken", deletes the directory it names under `~/.claude/plugins/cache`, and
re-installs. Three distinct facts used to share one `tuple[str, ...]`
spelling:

- "the artifact is usable" — the EMPTY tuple;
- "the artifact is broken" — a non-empty tuple, which authorizes the delete;
- "I refused to delete that path" — also a non-empty tuple, from the OTHER
  seam, meaning something the first two do not.

And a fourth fact had no spelling at all: "I could not decide", which used to
leave this module as an uncaught `json.JSONDecodeError` out of
`_cache_manifest_findings` and abort the whole provisioning run with a
traceback. It is now the FAILURE track, and keeping it off the success track
is the load-bearing half: a probe that could not read the cache manifest has
not established that the build is broken, so it must NOT authorize deleting a
directory under the operator's home. `artifact_record_findings` and
`artifact_record_repair_paths` FORWARD that failure unchanged rather than
re-wrapping it — neither adds a failure mode of its own, and a second error
type for one condition would make a caller distinguish two things that are one
thing.

WHAT IS DELIBERATELY *NOT* ON THE FAILURE TRACK: an `OSError` reaching any of
the `Path` probes. A cache directory the owning user cannot stat or open is a
broken host rather than a broken plugin, and this repo's rule is that expected
errors ride the rails while bugs raise.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

# `returns` is VENDORED, not installed, so a bare import resolves only if some
# EARLIER import in the same process already put `_vendor/` on `sys.path`. This
# module is the FIRST import of `fleet/ensure_plugins`, so nothing runs before
# it in the `python -m livespec_dev_tooling.fleet.ensure_plugins` entry point;
# it establishes the path itself exactly as `_ensure_plugin_commands` does.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "MANIFEST_UNDECODABLE",
    "MANIFEST_UNPARSEABLE",
    "ArtifactOutcome",
    "ArtifactReader",
    "ArtifactUnreadable",
    "CacheDirRemover",
    "CacheRemovalRefused",
    "RemovalOutcome",
    "artifact_record_findings",
    "artifact_record_repair_paths",
    "plugin_artifact_findings",
    "remove_plugin_cache_dir",
]

# The two ways a cache manifest that IS present refuses to yield its declared
# content. They stay apart because they name different halves of a half-written
# cache entry: undecodable bytes say the file was truncated or is not text at
# all, while text that is not JSON says a writer got as far as producing
# characters. Both leave the required-path set unknown.
MANIFEST_UNDECODABLE = "cache-manifest-undecodable"
MANIFEST_UNPARSEABLE = "cache-manifest-unparseable"


@dataclass(frozen=True, kw_only=True)
class ArtifactUnreadable:
    """The artifact probe could not reach a verdict, and why.

    Deliberately NOT inhabited by "the artifact is broken": that is a FINDING
    on the success track. The two must never share a spelling, because the
    responses they authorize are opposite — a finding sends `ensure` to
    `remove_plugin_cache_dir`, which DELETES the named directory, while a probe
    that did not answer must delete nothing at all.
    """

    install_path: str
    reason: str
    detail: str

    @property
    def finding(self) -> str:
        """One line naming the artifact whose usability could not be decided."""
        return (
            f"installPath {self.install_path} could not be inspected "
            f"({self.reason}: {self.detail})"
        )


# The railway alias for the artifact probe: findings are the ANSWER and travel
# the success track however they read, including the empty tuple that means the
# build is usable.
#
# ⚠️ THE FOUR PUBLIC FUNCTIONS BELOW SPELL THEIR RETURNS OUT RATHER THAN USING
# THIS ALIAS, and that is not an oversight. `checks/public_api_result_typed`
# decides railway-typedness from the SOURCE annotation's terminal name via
# `ast`, so a function annotated `ArtifactOutcome` reads to it as a bare name
# and stays convicted however the alias is defined. The alias is for the seam
# Protocols and the private helpers, which the check does not judge.
ArtifactOutcome = IOResult[tuple[str, ...], ArtifactUnreadable]


@dataclass(frozen=True, kw_only=True)
class CacheRemovalRefused:
    """A deletion this module declined, naming the boundary that stopped it.

    A refusal is this seam's own expected error, not a finding about the
    plugin: nothing was learned about the build, and the operator's repair is
    to look at why a registry record points outside the plugin cache at all.
    """

    install_path: str
    cache_root: str

    @property
    def finding(self) -> str:
        """The refusal line an operator reads, naming both path and boundary."""
        return f"refusing to delete installPath {self.install_path} outside {self.cache_root}"


# The railway alias for the removal seam: the success value is the path that
# was actually removed, so "I deleted nothing" can no longer be spelled the
# same way as "I deleted it and have nothing to report".
RemovalOutcome = IOResult[str, CacheRemovalRefused]


class ArtifactReader(Protocol):
    """Callable seam confirming the artifact named by one install record.

    The success track carries FINDINGS, an empty tuple meaning the artifact is
    usable. The failure track carries "the probe could not decide", which is
    never a spelling of either.
    """

    def __call__(self, *, install_path: str) -> ArtifactOutcome: ...


class CacheDirRemover(Protocol):
    """Callable seam removing one invalid plugin cache directory."""

    def __call__(self, *, install_path: str) -> RemovalOutcome: ...


def plugin_artifact_findings(*, install_path: str) -> IOResult[tuple[str, ...], ArtifactUnreadable]:
    """Findings for the plugin build directory named by an install record."""
    path = Path(install_path)
    if not path.is_dir():
        return IOSuccess((f"installPath {install_path} does not exist or is not a directory",))
    manifest = path / "plugin.json"
    if not manifest.is_file() or not os.access(manifest, os.R_OK):
        return IOSuccess((f"installPath {install_path} has no readable plugin.json",))
    return _cache_manifest_findings(install_path=install_path, path=path)


def _unreadable(*, install_path: str, reason: str, detail: str) -> ArtifactOutcome:
    """The failure track, naming the artifact whose manifest did not yield content."""
    return IOFailure(ArtifactUnreadable(install_path=install_path, reason=reason, detail=detail))


def _cache_manifest_findings(*, install_path: str, path: Path) -> ArtifactOutcome:
    """Findings for required cache content declared by `cache-manifest.json`.

    A manifest that is PRESENT but yields no content rides the failure track
    rather than raising. Before this conversion the `json.JSONDecodeError`
    escaped as far as `main` and killed the provisioning run, and the tempting
    alternative — reading it as an ordinary finding — would silently authorize
    deleting the directory on the strength of a required-path set nobody read.
    """
    manifest = path / "cache-manifest.json"
    if not manifest.is_file():
        return IOSuccess(())
    try:
        parsed = json.loads(manifest.read_text(encoding="utf-8"))
    except UnicodeDecodeError as undecodable:
        return _unreadable(
            install_path=install_path, reason=MANIFEST_UNDECODABLE, detail=str(undecodable)
        )
    except json.JSONDecodeError as unparseable:
        return _unreadable(
            install_path=install_path, reason=MANIFEST_UNPARSEABLE, detail=str(unparseable)
        )
    return IOSuccess(_required_path_findings(install_path=install_path, path=path, parsed=parsed))


def _required_path_findings(*, install_path: str, path: Path, parsed: object) -> tuple[str, ...]:
    """Findings for each `required_paths` entry the parsed manifest declares."""
    raw_paths = (
        cast("dict[str, object]", parsed).get("required_paths", ())
        if isinstance(parsed, dict)
        else ()
    )
    findings: list[str] = []
    for raw_path in cast("tuple[object, ...] | list[object]", raw_paths):
        if not isinstance(raw_path, str) or not _is_relative_manifest_path(raw_path=raw_path):
            findings.append(f"installPath {install_path} cache-manifest.json has invalid path")
            continue
        if not (path / raw_path).exists():
            findings.append(f"installPath {install_path} is missing required path {raw_path}")
    return tuple(findings)


def _is_relative_manifest_path(*, raw_path: str) -> bool:
    """Whether a cache-manifest path names non-empty content below the cache root."""
    candidate = Path(raw_path)
    return raw_path != "" and not candidate.is_absolute() and ".." not in candidate.parts


def remove_plugin_cache_dir(*, install_path: str) -> IOResult[str, CacheRemovalRefused]:
    """Delete one invalid Claude plugin cache dir, refusing paths outside cache."""
    path = Path(install_path).resolve()
    cache_root = (Path.home() / ".claude" / "plugins" / "cache").resolve()
    if path == cache_root or os.path.commonpath((str(cache_root), str(path))) != str(cache_root):
        return IOFailure(CacheRemovalRefused(install_path=install_path, cache_root=str(cache_root)))
    shutil.rmtree(path, ignore_errors=True)
    return IOSuccess(str(path))


def artifact_record_findings(
    *, plugin: str, records: tuple[dict[str, object], ...], read_artifact: ArtifactReader
) -> IOResult[tuple[str, ...], ArtifactUnreadable]:
    """Findings proving that no project record names a usable plugin artifact.

    A probe that did not answer STOPS the scan and is forwarded: a record whose
    artifact could not be inspected proves neither that the plugin is usable
    nor that it is broken, and continuing would let the surviving records
    decide a question this one left open.
    """
    findings: list[str] = []
    for record in records:
        install_path = record.get("installPath")
        if not isinstance(install_path, str) or not install_path:
            findings.append(f"{plugin} install record has no installPath")
            continue
        probe = read_artifact(install_path=install_path)
        if isinstance(probe, IOFailure):
            return probe
        artifact_findings = unsafe_perform_io(probe.unwrap())
        if not artifact_findings:
            return IOSuccess(())
        findings.extend(f"{plugin} {finding}" for finding in artifact_findings)
    return IOSuccess(tuple(findings))


def artifact_record_repair_paths(
    *, records: tuple[dict[str, object], ...], read_artifact: ArtifactReader
) -> IOResult[tuple[str, ...], ArtifactUnreadable]:
    """Install paths to remove when every project record names a broken artifact.

    THE FAILURE TRACK IS WHAT KEEPS THE DESTRUCTIVE HALF HONEST. Whatever this
    returns is handed to `remove_plugin_cache_dir` and deleted, so a record
    whose artifact could not be inspected withholds the WHOLE set rather than
    contributing a path — the empty tuple this already returns for "some record
    is fine" says do not repair, and an unanswered probe says the same thing for
    a different reason.
    """
    repair_paths: list[str] = []
    for record in records:
        install_path = cast("str", record.get("installPath"))
        probe = read_artifact(install_path=install_path)
        if isinstance(probe, IOFailure):
            return probe
        if not unsafe_perform_io(probe.unwrap()):
            return IOSuccess(())
        repair_paths.append(install_path)
    return IOSuccess(tuple(repair_paths))
