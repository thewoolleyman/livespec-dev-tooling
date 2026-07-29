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
from typing import Literal, cast

from livespec_dev_tooling.fleet._context import Adopter, FleetMember
from livespec_dev_tooling.fleet._contract_rows import REPO_CLASSES

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "ADOPTER_POSTURES",
    "PROFILE_LAYERS",
    "REPO_CLASSES",
    "Adopter",
    "Manifest",
    "ManifestParseError",
    "ManifestParseReason",
    "parse_manifest",
]


# The ordered profile layers an adopter may declare (the cumulative
# conformance partition: each layer adds obligations atop the prior).
PROFILE_LAYERS = ("baseline", "fleet-infra", "orchestrator-plugin", "app")
# The adoption postures an adopter may hold toward the fleet pins.
ADOPTER_POSTURES = ("released", "pinned", "none")

# The EXHAUSTIVE set of ways `.livespec-fleet-manifest.jsonc` can fail to
# parse — one member per cause `parse_manifest`'s docstring documents.
# Stated as a `Literal` rather than a bare `str` so adding a rejection
# branch without naming it here is a type error rather than a new
# undocumented reason string leaking into an operator's diagnostic.
ManifestParseReason = Literal[
    "invalid-jsonc",
    "root-not-object",
    "owner-not-string",
    "fleet-not-list",
    "malformed-member",
    "duplicate-member",
    "adopters-not-list",
    "malformed-adopter",
]

# The failure subsets the two array parsers can produce. Kept NARROWER
# than `ManifestParseReason` on purpose: the member parser cannot emit an
# adopter reason and vice versa, and pyright enforces that at the widening
# site rather than leaving it to a comment.
_MemberFailure = Literal["fleet-not-list", "malformed-member", "duplicate-member"]
_AdopterFailure = Literal["adopters-not-list", "malformed-adopter"]

# The EXHAUSTIVE set of ways a manifest FETCH can fail to produce one.
# Strictly coarser than `ManifestParseReason`, and deliberately so: this
# names WHICH STAGE failed, and the parse stage's own eight causes are
# already named one level down.
ManifestUnavailableReason = Literal["unreadable", "unparseable"]


@dataclass(frozen=True, kw_only=True)
class ManifestParseError:
    """A fleet-manifest parse FAILED, naming WHICH documented cause it was.

    The failure-track payload for `parse_manifest`. It exists because the
    eight causes that function's docstring enumerates were previously all
    spelled one `None`, so the two engines that fetch the manifest
    (`fleet_conformance.fetch_manifest` and
    `merged_branch_sweep.fetch_manifest`) could record only "manifest
    fetched but did not parse" — a diagnostic that names the file and says
    nothing about what is wrong with it.

    That cost is concrete rather than theoretical. The manifest is fetched
    from ANOTHER repo (`livespec` master) at run time, so the operator
    reading the failure is typically not the person who broke it, and the
    bytes are not in front of them. One bit of output ("malformed") for a
    39-member document means re-parsing it by hand to discover that a
    `posture` was misspelled.

    The reason is a value rather than a rendered sentence so a caller may
    branch on it — the central sweep and the local sweep want different
    words for the same cause — instead of matching on prose.
    """

    reason: ManifestParseReason


@dataclass(frozen=True, kw_only=True)
class ManifestUnavailable:
    """The fleet manifest could not be produced, naming WHICH STAGE failed.

    The failure-track payload for `fleet_conformance.fetch_manifest`. Its
    two inhabitants are real and were previously indistinguishable: the
    fetch did not answer at all (`unreadable`), or it answered and the
    bytes are no manifest (`unparseable`). Both were one `None`, told apart
    only by whether a `malformed_content` entry had appeared on
    `ctx.read_failures` — a SIDE EFFECT the caller had to go looking for,
    and which therefore did not survive into the caller's control flow.

    That collapse is what convicts `fetch_manifest` under livespec v179:
    clause (e) disqualifies an `X | None` return outright, and the failure
    track is genuinely INHABITED. It is NOT convicted by clause (c) — the
    network reach is through the injected `ctx.file_text` seam — and the
    distinction matters, because a clause-(c) reading also convicts
    `holds_app_class_credential`, whose environment read cannot fail and
    which was restructured rather than converted (livespec-dev-tooling-9sl0).

    The reason is a VALUE rather than a rendered sentence, exactly as for
    `ManifestParseError` above, so a caller may branch on it. The detail
    behind each stays where it already was and is not duplicated here: the
    per-read causes on `ctx.read_failures`, which every call site already
    logs, and which carry the 403 / 404 / rate-limit classification this
    value deliberately does not restate.
    """

    reason: ManifestUnavailableReason


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
    """One manifest member entry, or None when malformed.

    Deliberately NOT on the railway: this helper has exactly ONE failure
    meaning ("this entry is malformed"), so `None` carries the whole
    answer and a `Result` would add a failure track with a single
    inhabitant. Its CALLER is the function that must distinguish causes,
    and that is where the conversion went.
    """
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, object]", entry)
    repo = record.get("repo")
    repo_class = record.get("class")
    if not isinstance(repo, str) or repo_class not in REPO_CLASSES:
        return None
    return FleetMember(repo=repo, repo_class=cast("str", repo_class))


def _parse_members(*, raw: object) -> Result[tuple[FleetMember, ...], _MemberFailure]:
    """Parse the fleet member array, or name which of its three failures occurred.

    Converted alongside its caller because it is where two of the eight
    causes are DECIDED: a duplicate repo and a malformed entry are
    different operator actions (deduplicate the list vs. fix one record),
    and returning `None` for both meant `parse_manifest` could not tell
    them apart to report them.
    """
    if not isinstance(raw, list):
        return Failure("fleet-not-list")
    members: list[FleetMember] = []
    for entry in cast("list[object]", raw):
        member = _parse_member(entry=entry)
        if member is None:
            return Failure("malformed-member")
        members.append(member)
    if len({member.repo for member in members}) != len(members):
        return Failure("duplicate-member")
    return Success(tuple(members))


def _parse_adopter(*, entry: object) -> Adopter | None:
    """One manifest adopter entry, or None when malformed.

    Left on `None` for the same reason as `_parse_member`: one failure
    meaning, so the failure track would have a single inhabitant.
    """
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


def _parse_adopters(*, raw: object) -> Result[tuple[Adopter, ...], _AdopterFailure]:
    """Parse the optional adopters array; `Success(())` when absent.

    `adopters` is OPTIONAL, so an ABSENT key is a success carrying the
    empty tuple — not a failure. That distinction was already correct
    before the conversion (`()` vs `None`) and is preserved exactly: the
    railway must not turn "you did not declare adopters" into an error.
    """
    if raw is None:
        return Success(())
    if not isinstance(raw, list):
        return Failure("adopters-not-list")
    adopters: list[Adopter] = []
    for entry in cast("list[object]", raw):
        adopter = _parse_adopter(entry=entry)
        if adopter is None:
            return Failure("malformed-adopter")
        adopters.append(adopter)
    return Success(tuple(adopters))


def parse_manifest(*, source: str) -> Result[Manifest, ManifestParseError]:
    """Parse `.livespec-fleet-manifest.jsonc` text, or name why it would not.

    The fleet member array is read from the `fleet` key, falling back to
    the legacy `members` key when `fleet` is absent (the required-key
    migration seam: this parser accepts both before livespec core renames
    the manifest key). The optional `adopters` array, when present, parses
    into `Adopter` records; an absent `adopters` key yields an empty tuple.

    The EIGHT rejection causes each arrive as a distinct
    `ManifestParseError.reason` rather than as one shared `None`:
    `invalid-jsonc`, `root-not-object`, `owner-not-string`,
    `fleet-not-list` (under either `fleet` or `members`),
    `malformed-member` (missing `repo`, unknown `class`),
    `duplicate-member`, `adopters-not-list`, and `malformed-adopter`
    (missing/empty `repo`, a `profile` that is not a non-empty list of
    known layers, or an unknown `posture`).

    CHECK ORDER IS PART OF THE CONTRACT NOW, because it decides which
    reason a doubly-malformed manifest reports, and that was previously
    unobservable — every order produced the same `None`. It runs
    OUTERMOST-FIRST — JSONC, root, owner, fleet, adopters — so the
    reported cause is always the outermost thing wrong: complaining about
    a member entry inside a document whose root is not an object would
    send the reader to the wrong line. One consequence is deliberate: a
    manifest with BOTH a bad owner and a bad member reports
    `owner-not-string`, and fixing it surfaces the next cause. This is
    also a behavior change from the pre-conversion code, which parsed the
    arrays BEFORE testing `owner` — invisible then, observable now.
    """
    parser = jsoncomment.JsonComment()
    try:
        data = cast("object", parser.loads(source))
    except ValueError:
        return Failure(ManifestParseError(reason="invalid-jsonc"))
    if not isinstance(data, dict):
        return Failure(ManifestParseError(reason="root-not-object"))
    mapping = cast("dict[str, object]", data)
    owner = mapping.get("owner")
    if not isinstance(owner, str):
        return Failure(ManifestParseError(reason="owner-not-string"))
    members_raw = mapping.get("fleet")
    if members_raw is None:
        members_raw = mapping.get("members")
    members = _parse_members(raw=members_raw)
    if isinstance(members, Failure):
        return Failure(ManifestParseError(reason=members.failure()))
    adopters = _parse_adopters(raw=mapping.get("adopters"))
    if isinstance(adopters, Failure):
        return Failure(ManifestParseError(reason=adopters.failure()))
    return Success(Manifest(owner=owner, members=members.unwrap(), adopters=adopters.unwrap()))
