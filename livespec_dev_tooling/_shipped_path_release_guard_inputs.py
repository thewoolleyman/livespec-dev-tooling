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
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "Resolved",
    "resolve_releasing_types",
    "resolve_shipped_prefixes",
]


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


def resolve_releasing_types(*, repo_root: Path) -> Resolved:
    """Resolve THIS repository's releasing-type set, and say where it came from."""
    for name in _RELEASE_PLEASE_CONFIG_NAMES:
        path = repo_root / name
        if not path.is_file():
            continue
        parsed = json.loads(path.read_text(encoding="utf-8"))
        document = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
        sections = document.get("changelog-sections")
        if isinstance(sections, list):
            return Resolved(
                values=_visible_types(sections=cast("list[object]", sections)),
                source=f"{name} `changelog-sections` (the entries without `hidden: true`)",
            )
        break
    return Resolved(
        values=_RELEASE_PLEASE_DEFAULT_RELEASING_TYPES,
        source=(
            "release-please's built-in defaults — this repository declares no "
            "`changelog-sections`, so `refactor` is hidden and does not release here"
        ),
    )


def resolve_shipped_prefixes(*, repo_root: Path) -> Resolved:
    """Derive THIS repository's shipped-path prefixes, and say where they came from.

    DERIVED rather than declared, from the artifact that already answers the
    question: a plugin's shipped bytes are the directory carrying its manifest.
    An empty derivation is an ANSWER (this repo ships no plugin bytes), and it
    carries its own source string so an empty set is never reported as if a
    manifest had produced it.
    """
    prefixes: set[str] = set()
    for parent in (repo_root, *sorted(p for p in repo_root.iterdir() if p.is_dir())):
        manifest_dir = parent / _MANIFEST_DIR_NAME
        if any((manifest_dir / name).is_file() for name in _MANIFEST_NAMES):
            prefixes.add(f"{manifest_dir.relative_to(repo_root).as_posix()}/")
    if not prefixes:
        return Resolved(
            values=frozenset(),
            source=(
                f"derived: no `{_MANIFEST_DIR_NAME}/` manifest at the repository root or one "
                "level below it, so this repository ships no plugin bytes"
            ),
        )
    return Resolved(
        values=frozenset(prefixes),
        source=(
            f"derived from the `{_MANIFEST_DIR_NAME}/` manifest directories "
            f"({', '.join(sorted(prefixes))})"
        ),
    )
