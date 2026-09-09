"""_shipped_path_release_guard_inputs — resolve the guard's PER-REPO inputs.

Slice C of the R6 guard (work-item `livespec-dev-tooling-sxdz`), split out of
`shipped_path_release_guard_check` by COHESION when that module crossed the
250-LLOC ceiling. One concern lives here and it is the one the check module's
docstring calls its whole reason for existing: turning a real repository — its
release-please config, its plugin manifests — into the two value sets the pure
core takes as arguments.

NEITHER INPUT IS A FLEET CONSTANT, and each resolution site states where its
value was read from, in the returned `Resolved.source`. That pairing is the
point of the `Resolved` type: the source travels WITH the value, so a value can
never be reported against a source that did not produce it.

Nothing here decides anything. There is no import of the core and no import of
the check module — this module resolves inputs and hands them back, which is
what keeps the guard's one rule at exactly one implementation.

ON THE `IOResult` RAILWAY (`livespec-dev-tooling-qndn.2`, epic `8o8e`). Both
resolvers call `Path.read_text` and `Path.iterdir` DIRECTLY rather than through
an injected seam, so they are the I/O boundary itself and `IOResult` rather than
`Result` is the honest container. What rides the FAILURE track is only a read
that DID NOT HAPPEN; every state this module managed to establish — including
both of its near-empty answers — stays a success. See `InputUnreadable`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

# Carried rather than inherited from an importer: a bare `from returns...`
# import resolves only if some module up the chain happens to have inserted
# `_vendor/` already, which is a property of the caller rather than of this
# module.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.

__all__: list[str] = [
    "InputUnreadable",
    "Resolved",
    "resolve_releasing_types",
    "resolve_shipped_prefixes",
]


@dataclass(frozen=True, kw_only=True)
class InputUnreadable:
    """A per-repo input this run DID NOT READ, and which read did not happen.

    ⛔ UNREAD IS NOT EMPTY, and here that distinction is unusually sharp: BOTH
    resolvers have a legitimate near-empty ANSWER — release-please's own defaults
    for a repository that declares no `changelog-sections`, and "this repository
    ships no plugin bytes" for one deriving no prefixes. Folding an unread input
    onto either would have the guard report a verdict about a repository it never
    managed to look at, and report it as a PASS.

    `source` names WHERE the read was attempted — the config file's name, or the
    repository root — so it reads against the `Resolved.source` a successful read
    would have carried. `detail` is the operator-facing evidence.
    """

    source: str
    detail: str


# Both spellings release-please accepts for its config file, in the order it
# looks for them.
_RELEASE_PLEASE_CONFIG_NAMES = ("release-please-config.json", ".release-please-config.json")
# release-please's OWN defaults — what a repo declaring no `changelog-sections`
# gets. `refactor`, `docs`, `chore`, `ci`, `build`, `style` and `test` are hidden
# by default, which is exactly why this set and livespec's declared set differ
# and why neither may be hardcoded as "the" releasing set.
_RELEASE_PLEASE_DEFAULT_RELEASING_TYPES = frozenset({"feat", "feature", "fix", "perf", "revert"})

# A plugin's shipped bytes are the directory carrying its manifest. Searched at
# the repo root and one level below it — the two layouts the fleet uses.
_MANIFEST_DIR_NAME = ".claude-plugin"
_MANIFEST_NAMES = ("plugin.json", "marketplace.json")


@dataclass(frozen=True, kw_only=True)
class Resolved:
    """A per-repo input together with the SOURCE it was read from.

    The source travels WITH the value rather than being reconstructed at the log
    site, so a value can never be reported against a source that did not produce
    it.
    """

    values: frozenset[str]
    source: str


def _visible_types(*, sections: list[object]) -> frozenset[str]:
    """The `changelog-sections` entries release-please does NOT hide.

    An entry with no `hidden` key is visible, so the test is `is not True`
    rather than a truthiness read of a possibly-absent key. Malformed entries
    are skipped rather than raising: this parses a file the CONSUMER maintains
    for release-please, and a future schema change there must not turn this
    guard into a crash.
    """
    visible: set[str] = set()
    for raw in sections:
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        name = entry.get("type")
        if isinstance(name, str) and entry.get("hidden") is not True:
            visible.add(name)
    return frozenset(visible)


def resolve_releasing_types(*, repo_root: Path) -> IOResult[Resolved, InputUnreadable]:
    """Resolve THIS repository's releasing-type set, and say where it came from.

    An ABSENT config stays on the SUCCESS track: release-please's own defaults
    then genuinely ARE this repository's releasing set, which is an answer. A
    config that is PRESENT but does not yield a value is not — falling back there
    would report a releasing-type set the repository never declared, sourced to a
    file that could not be parsed, which is exactly the value-against-a-wrong-
    source pairing `Resolved` exists to make impossible.
    """
    for name in _RELEASE_PLEASE_CONFIG_NAMES:
        path = repo_root / name
        if not path.is_file():
            continue
        # NARROW and enumerated, at the seam. `is_file` has already answered the
        # presence question, so an unreadable file and an unparseable one are one
        # outcome with two spellings — "this DECLARED config yielded no value" —
        # and no caller would answer them differently.
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as unreadable:
            return IOFailure(InputUnreadable(source=name, detail=str(unreadable)))
        document = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
        sections = document.get("changelog-sections")
        if isinstance(sections, list):
            return IOSuccess(
                Resolved(
                    values=_visible_types(sections=cast("list[object]", sections)),
                    source=f"{name} `changelog-sections` (the entries without `hidden: true`)",
                )
            )
        break
    return IOSuccess(
        Resolved(
            values=_RELEASE_PLEASE_DEFAULT_RELEASING_TYPES,
            source=(
                "release-please's built-in defaults — this repository declares no "
                "`changelog-sections`, so `refactor` is hidden and does not release here"
            ),
        )
    )


def resolve_shipped_prefixes(*, repo_root: Path) -> IOResult[Resolved, InputUnreadable]:
    """Derive THIS repository's shipped-path prefixes, and say where they came from.

    DERIVED rather than declared, from the artifact that already answers the
    question: a plugin's shipped bytes are the directory carrying its manifest.
    An empty derivation is an ANSWER (this repo ships no plugin bytes), and it
    carries its own source string so an empty set is never reported as if a
    manifest had produced it.

    ⛔ WHICH IS EXACTLY WHY A ROOT THAT WILL NOT LIST LEAVES THE SUCCESS TRACK.
    An unreadable root derives nothing, and nothing is already spelled the same
    way as the load-bearing empty answer above — so folding the two together
    would have the guard report itself correctly INERT on a repository it never
    managed to look at.
    """
    try:
        children = sorted(path for path in repo_root.iterdir() if path.is_dir())
    except OSError as unlistable:
        return IOFailure(InputUnreadable(source=str(repo_root), detail=str(unlistable)))
    prefixes: set[str] = set()
    for parent in (repo_root, *children):
        manifest_dir = parent / _MANIFEST_DIR_NAME
        if any((manifest_dir / name).is_file() for name in _MANIFEST_NAMES):
            prefixes.add(f"{manifest_dir.relative_to(repo_root).as_posix()}/")
    if not prefixes:
        return IOSuccess(
            Resolved(
                values=frozenset(),
                source=(
                    f"derived: no `{_MANIFEST_DIR_NAME}/` manifest at the repository root or one "
                    "level below it, so this repository ships no plugin bytes"
                ),
            )
        )
    return IOSuccess(
        Resolved(
            values=frozenset(prefixes),
            source=(
                f"derived from the `{_MANIFEST_DIR_NAME}/` manifest directories "
                f"({', '.join(sorted(prefixes))})"
            ),
        )
    )
