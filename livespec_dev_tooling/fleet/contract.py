"""The parsed fleet-membership manifest (owner + members + adopters).

`parse_manifest` parses livespec core's `.livespec-fleet-manifest.jsonc`
(the committed member list, fetched from livespec master at run time)
into a `Manifest` of `FleetMember` + `Adopter` records. The obligation
tables the two conformance engines walk live in sibling modules:
`_contract_rows.OBLIGATION_ROWS` (the central GitHub-vantage table,
which also HOMES `REPO_CLASSES`) and
`_contract_local_rows.LOCAL_OBLIGATION_ROWS` (the LOCAL-vantage
first-touch table).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._context import Adopter, FleetMember
from livespec_dev_tooling.fleet._contract_rows import REPO_CLASSES

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "ADOPTER_POSTURES",
    "PROFILE_LAYERS",
    "REPO_CLASSES",
    "Adopter",
    "Manifest",
    "parse_manifest",
]


# The ordered profile layers an adopter may declare (the cumulative
# conformance partition: each layer adds obligations atop the prior).
PROFILE_LAYERS = ("baseline", "fleet-infra", "orchestrator-plugin", "app")
# The adoption postures an adopter may hold toward the fleet pins.
ADOPTER_POSTURES = ("released", "pinned", "none")


@dataclass(frozen=True, kw_only=True)
class Manifest:
    """The parsed fleet manifest: owner + the fleet member list + the adopters."""

    owner: str
    members: tuple[FleetMember, ...]
    adopters: tuple[Adopter, ...]

    def member_names(self) -> frozenset[str]:
        """The set of member repo names (for the discovery sweep)."""
        return frozenset(member.repo for member in self.members)


def _parse_member(*, entry: object) -> FleetMember | None:
    """One manifest member entry, or None when malformed."""
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, object]", entry)
    repo = record.get("repo")
    repo_class = record.get("class")
    if not isinstance(repo, str) or repo_class not in REPO_CLASSES:
        return None
    return FleetMember(repo=repo, repo_class=cast("str", repo_class))


def _parse_members(*, raw: object) -> tuple[FleetMember, ...] | None:
    """Parse the fleet member array; None when non-list, malformed, or duplicated."""
    if not isinstance(raw, list):
        return None
    members: list[FleetMember] = []
    for entry in cast("list[object]", raw):
        member = _parse_member(entry=entry)
        if member is None:
            return None
        members.append(member)
    if len({member.repo for member in members}) != len(members):
        return None
    return tuple(members)


def _parse_adopter(*, entry: object) -> Adopter | None:
    """One manifest adopter entry, or None when malformed."""
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, object]", entry)
    repo = record.get("repo")
    profile = record.get("profile")
    posture = record.get("posture")
    if not isinstance(repo, str) or not repo:
        return None
    if not isinstance(profile, list) or not profile:
        return None
    for layer in cast("list[object]", profile):
        if not isinstance(layer, str) or layer not in PROFILE_LAYERS:
            return None
    if not isinstance(posture, str) or posture not in ADOPTER_POSTURES:
        return None
    return Adopter(repo=repo, profile=tuple(cast("list[str]", profile)), posture=posture)


def _parse_adopters(*, raw: object) -> tuple[Adopter, ...] | None:
    """Parse the optional adopters array; () when absent, None when malformed."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return None
    adopters: list[Adopter] = []
    for entry in cast("list[object]", raw):
        adopter = _parse_adopter(entry=entry)
        if adopter is None:
            return None
        adopters.append(adopter)
    return tuple(adopters)


def parse_manifest(*, source: str) -> Manifest | None:
    """Parse `.livespec-fleet-manifest.jsonc` text; None when malformed.

    The fleet member array is read from the `fleet` key, falling back to
    the legacy `members` key when `fleet` is absent (the required-key
    migration seam: this parser accepts both before livespec core renames
    the manifest key). The optional `adopters` array, when present, parses
    into `Adopter` records; an absent `adopters` key yields an empty tuple.

    Malformed means: invalid JSONC, a non-object root, a non-string
    `owner`, a non-list fleet array (under either `fleet` or `members`),
    any malformed member entry (missing `repo`, unknown `class`),
    duplicate member repos, a present-but-non-list `adopters` value, or
    any malformed adopter entry (missing/empty `repo`, a `profile` that
    is not a non-empty list of known layers, or an unknown `posture`).
    """
    parser = jsoncomment.JsonComment()
    try:
        data = cast("object", parser.loads(source))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    mapping = cast("dict[str, object]", data)
    owner = mapping.get("owner")
    members_raw = mapping.get("fleet")
    if members_raw is None:
        members_raw = mapping.get("members")
    members = _parse_members(raw=members_raw)
    adopters = _parse_adopters(raw=mapping.get("adopters"))
    if not isinstance(owner, str) or members is None or adopters is None:
        return None
    return Manifest(owner=owner, members=members, adopters=adopters)
