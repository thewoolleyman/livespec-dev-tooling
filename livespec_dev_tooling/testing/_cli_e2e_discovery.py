"""_cli_e2e_discovery — structural skill discovery + per-skill fixtures loader.

Extracted verbatim from `cli_e2e` (two of the harness contract's five
components). Both walk the on-disk tree as the source of truth — there is
no parallel manifest file:

- **Structural skill discovery** (`discover_skills`) — walks
  `<installed-plugin>/skills/*/SKILL.md` in each plugin's installed
  location and reads the slash-command prefix from `plugin.json`'s `name`
  field (contract requirement 3).
- **Per-skill fixtures loader** (`discover_fixtures`) — a fixtures
  directory `<consumer-repo>/tests/e2e-cli/fixtures/<skill>/` holds a
  `prompt.md` and an optional `expected_files.txt` per skill; directory
  present (with a `prompt.md`) == fixture exists (contract requirement 4).

`cli_e2e` re-exports `FixturedSkill`, `discover_skills`, and
`discover_fixtures` so the public surface is unchanged.

## BOTH ARE ON THE `IOResult` RAILWAY — livespec-dev-tooling-8o8e, pair B

They read the filesystem by calling `Path.read_text` / `Path.iterdir`
DIRECTLY rather than through an injected seam, which is the boundary
livespec v179 clause (a) reaches: `IOResult` rather than `Result` is the
honest container here, the same direct-call-versus-injected-seam reading
that puts `_origin_remote` on `IOResult` and leaves `fetch_manifest` on
`Result`.

**THE PRIZE IS `discover_skills`, NOT `discover_fixtures`, and the intuitive
reading has it backwards.** `assert_coverage` computes
`discovered - fixtured - exempt`. An empty `fixtured` alone still FAILS that
gate, correctly. It was `discover_skills`' `if prefix is None: continue` — a
SILENT DROP of a whole plugin — that emptied `discovered`, and
`set() - anything` is empty, so a BROKEN PLUGIN INSTALL made the fail-closed
time-bomb gate report SATISFIED. A vacuous pass, not a crash.

**WHAT IS AN ANSWER AND WHAT IS A FAILURE, decided by reading each site:**

- `fixtures_root` ABSENT is an ANSWER (`{}`) — the pin-walker ruling that an
  absent path is an ordinary answer. The gate still catches the consequence:
  `discovered` is non-empty, so `discovered - fixtured` is non-empty and it
  fails.
- `fixtures_root` PRESENT BUT UNLISTABLE is a FAILURE. `is_dir()` FUSED the
  two; `iterdir()` splits them for free — `FileNotFoundError` is the answer,
  any other `OSError` is the failure. The same split applies to a plugin's
  `skills/` directory.
- `prompt.md` / `expected_files.txt` `read_text` are FAILURES. They were
  UNCAUGHT, so an unreadable fixture raised straight out of a function
  annotated `dict`.
- EVERY `_read_plugin_prefix` outcome short of a usable `name` is a FAILURE.
  `plugin_install_dirs` is a caller-DECLARED tuple of installed plugin roots;
  a directory in it without a readable manifest is a BROKEN INSTALL, not
  "this is not a plugin". Measured before changing it: all four consuming
  siblings pass exactly ONE directory and each is a real plugin root carrying
  a `plugin.json`, so no live caller relied on the skip.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar, cast

# Carried rather than inherited from an importer: a bare `from returns...`
# import resolves only if some module up the chain happens to have inserted
# `_vendor/` already, which is a property of the caller. That state is what
# broke the fleet's release fan-out for seven hours on 2026-07-30.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.

__all__: list[str] = [
    "DiscoveryUnreadable",
    "FixturedSkill",
    "discover_fixtures",
    "discover_skills",
]


_PLUGIN_MANIFEST = "plugin.json"
_SKILLS_DIRNAME = "skills"
_SKILL_FILENAME = "SKILL.md"

_PROMPT_FILENAME = "prompt.md"
_EXPECTED_FILES_FILENAME = "expected_files.txt"

_Collected = TypeVar("_Collected")


@dataclass(frozen=True, kw_only=True)
class FixturedSkill:
    """One discovered fixture directory — `prompt.md` + `expected_files.txt`."""

    skill: str
    prompt: str
    expected_files: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class DiscoveryUnreadable:
    """A read the discovery walk needed did not happen, and WHICH one.

    `reason` is the discriminator a caller branches on; `path` is the exact
    file or directory the read was attempted on (never just the root, since
    "somewhere under this tree" is not actionable); `detail` is the
    operator-facing evidence. Keeping the three apart is the point — a bare
    "discovery failed" would be the same manufactured confidence this
    conversion removes, one layer up.

    ONE TYPE FOR BOTH WALKS, following `OriginRemoteUnresolved`, which covers
    `resolve_owner` and `resolve_repo_name` the same way. The cost is stated
    rather than hidden: the `reason` set is WIDER than either function alone
    can produce — `discover_fixtures` never yields `manifest-absent`. That was
    accepted because what the epic requires is that each failure stay
    DISCRIMINATED, which a closed nine-member literal delivers, and because two
    types would meet at `run_workflow`'s `bind` as two incompatible failure
    tracks, forcing either a widening seam or an `unsafe_perform_io` escape in
    the middle of the composition — both worse than a wide literal.

    The nine want different operator responses. A missing or unreadable
    `plugin.json` is a broken INSTALL; malformed JSON or a missing `name` is a
    broken PLUGIN; an unlistable `skills/` or fixtures root is a broken
    FILESYSTEM; an unreadable `prompt.md` is a broken FIXTURE. Fused into one
    `None` they were all reported as "that plugin ships no skills".
    """

    path: Path
    reason: Literal[
        "manifest-absent",
        "manifest-not-read",
        "manifest-not-json",
        "manifest-not-an-object",
        "manifest-no-name",
        "skills-dir-not-listed",
        "fixtures-root-not-listed",
        "prompt-not-read",
        "expected-files-not-read",
    ]
    detail: str


def _unreadable(
    *,
    path: Path,
    reason: Literal[
        "manifest-absent",
        "manifest-not-read",
        "manifest-not-json",
        "manifest-not-an-object",
        "manifest-no-name",
        "skills-dir-not-listed",
        "fixtures-root-not-listed",
        "prompt-not-read",
        "expected-files-not-read",
    ],
    detail: str,
) -> IOFailure[DiscoveryUnreadable]:
    """One construction site for the failure track, so every arm carries all three fields."""
    return IOFailure(DiscoveryUnreadable(path=path, reason=reason, detail=detail))


def _captured(*, result: IOResult[_Collected, DiscoveryUnreadable]) -> list[_Collected]:
    """The success value as a 0-or-1 list — the shape-agnostic unwrap.

    `.map` runs ONLY on the success track, so an empty list IS the failure
    track, and no `unsafe_perform_io` escape is needed to read the value. This
    is the same idiom all four sibling consumer wirings use against this very
    module, kept in one spelling here. ⛔ `value_or` is the trap it avoids: on
    an `IOResult` it yields an `IO[...]` that compares unequal to every payload.
    """
    out: list[_Collected] = []
    _ = result.map(out.append)
    return out


def _collected(
    *, results: list[IOResult[_Collected, DiscoveryUnreadable]]
) -> IOResult[tuple[_Collected, ...], DiscoveryUnreadable]:
    """The first failure, or every success value in order — `Fold.collect`, written out.

    Spelled here rather than taken from `returns.iterables` because the vendored
    `Fold.collect` returns a `KindN` that pyright strict cannot resolve back to
    `IOResult`, so every downstream `.map` on it types as unknown. The same
    reason keeps `.bind` out of this module — no module in this package uses it.
    """
    captured: list[_Collected] = []
    for result in results:
        if isinstance(result, IOFailure):
            return result
        captured.extend(_captured(result=result))
    return IOSuccess(tuple(captured))


def _read_plugin_prefix(*, plugin_dir: Path) -> IOResult[str, DiscoveryUnreadable]:
    """Read the slash-command prefix from `<plugin_dir>/plugin.json` `name`.

    Returns the `name` field verbatim (the slash prefix, e.g. `livespec`) on the
    success track, or WHICH of five reads failed on the failure track. There
    MUST be no parallel manifest file — `plugin.json` is the canonical source of
    the prefix (contract requirement 3).

    ONE `try` rather than `is_file()` THEN `read_text()`: the pre-check pair is
    a TOCTOU race whose second arm no test can reach, and `FileNotFoundError`
    already splits absent from unreadable for free. Both are failures here, but
    they stay DISCRIMINATED — a plugin root shipping no manifest and one whose
    manifest cannot be read want different operator responses.
    """
    manifest = plugin_dir / _PLUGIN_MANIFEST
    try:
        text = manifest.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _unreadable(path=manifest, reason="manifest-absent", detail=str(plugin_dir))
    except OSError as unreadable:
        return _unreadable(path=manifest, reason="manifest-not-read", detail=str(unreadable))
    try:
        parsed = json.loads(text)
    except ValueError as malformed:
        return _unreadable(path=manifest, reason="manifest-not-json", detail=str(malformed))
    if not isinstance(parsed, dict):
        return _unreadable(
            path=manifest,
            reason="manifest-not-an-object",
            detail=f"top-level JSON is {type(parsed).__name__}, not an object",
        )
    # The `cast` is the single typed parse boundary: `json.loads` yields `Any`;
    # casting to `dict[str, object]` (under the `isinstance` guard above) types
    # `.get("name")` so the result narrows from `object` via the `isinstance`
    # guard below — the same typed-boundary pattern as `pin_autodiscovery`.
    manifest_dict = cast("dict[str, object]", parsed)
    name = manifest_dict.get("name")
    if not isinstance(name, str) or not name:
        return _unreadable(
            path=manifest,
            reason="manifest-no-name",
            detail=f"`name` is {name!r}; a non-empty string is required",
        )
    return IOSuccess(name)


def _walk_skill_dirs(*, plugin_dir: Path) -> IOResult[tuple[str, ...], DiscoveryUnreadable]:
    """Return the skill names under `<plugin_dir>/skills/*/SKILL.md`, sorted.

    A skill is a subdirectory of `skills/` containing a `SKILL.md`; the skill
    name is the subdirectory name (matching the slash sub-command). Walking
    the directory layout — not a manifest — is the contract's source of truth.

    An ABSENT `skills/` is an ANSWER (the plugin ships no skills); a `skills/`
    that exists and cannot be listed is a FAILURE. `is_dir()` reported both as
    "no skills here", which is the fusion this conversion exists to split.
    """
    skills_dir = plugin_dir / _SKILLS_DIRNAME
    try:
        children = sorted(skills_dir.iterdir())
    except FileNotFoundError:
        return IOSuccess(())
    except OSError as unlistable:
        return _unreadable(path=skills_dir, reason="skills-dir-not-listed", detail=str(unlistable))
    return IOSuccess(
        tuple(
            child.name
            for child in children
            if child.is_dir() and (child / _SKILL_FILENAME).is_file()
        )
    )


def _plugin_entry(
    *, plugin_dir: Path
) -> IOResult[tuple[str, tuple[str, ...]], DiscoveryUnreadable]:
    """One installed plugin's `(slash prefix, discovered skills)` pair.

    Both reads must succeed, and the prefix read goes FIRST so a broken install
    is named as such rather than as an empty skill list.
    """
    prefix = _read_plugin_prefix(plugin_dir=plugin_dir)
    if isinstance(prefix, IOFailure):
        return prefix
    # Non-empty by the check above — `_captured` is empty only on the failure track.
    found = _captured(result=prefix)[0]
    return _walk_skill_dirs(plugin_dir=plugin_dir).map(lambda skills: (found, skills))


def discover_skills(
    *, plugin_install_dirs: tuple[Path, ...]
) -> IOResult[dict[str, tuple[str, ...]], DiscoveryUnreadable]:
    """Walk each installed plugin and map its slash prefix → discovered skills.

    For each directory in `plugin_install_dirs`, reads the slash-command prefix
    from `plugin.json` `name` and enumerates `skills/*/SKILL.md`. The returned
    mapping is keyed by slash prefix so a caller can pair the fixed spec-side
    plugin with the parametrized impl-side plugin.

    ⛔ A DECLARED PLUGIN ROOT THAT DOES NOT RESOLVE FAILS THE WHOLE WALK rather
    than being dropped from the mapping. Dropping it emptied `discovered`, and
    the time-bomb coverage gate reads `discovered - fixtured - exempt`, so an
    empty `discovered` made the gate report SATISFIED over a broken install —
    a fail-closed gate turned fail-open by a silent `continue`.
    """
    return _collected(
        results=[_plugin_entry(plugin_dir=plugin_dir) for plugin_dir in plugin_install_dirs]
    ).map(lambda entries: dict(entries))


def _parse_expected_files(*, text: str) -> tuple[str, ...]:
    """Parse `expected_files.txt` — one path per line, blanks/`#` comments out."""
    out: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return tuple(out)


def _load_fixture(*, fixture_dir: Path) -> IOResult[FixturedSkill, DiscoveryUnreadable]:
    """Load one fixture directory's `prompt.md` and optional `expected_files.txt`.

    Both reads are on the failure track. They were UNCAUGHT before this
    conversion, so an unreadable fixture raised an `OSError` straight out of a
    function whose annotation promised a `dict` — livespec v179 clause (a).

    `expected_files.txt` takes the SAME `FileNotFoundError`-versus-other-`OSError`
    split the two directory walks take: absent means no file assertions, and
    anything else that stopped the read is a broken fixture. The `is_file()`
    pre-check it replaces fused those two and left a TOCTOU race behind it.
    """
    prompt_path = fixture_dir / _PROMPT_FILENAME
    try:
        prompt = prompt_path.read_text(encoding="utf-8")
    except OSError as unreadable:
        return _unreadable(path=prompt_path, reason="prompt-not-read", detail=str(unreadable))
    expected_path = fixture_dir / _EXPECTED_FILES_FILENAME
    try:
        listed = expected_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return IOSuccess(FixturedSkill(skill=fixture_dir.name, prompt=prompt, expected_files=()))
    except OSError as unreadable:
        return _unreadable(
            path=expected_path, reason="expected-files-not-read", detail=str(unreadable)
        )
    return IOSuccess(
        FixturedSkill(
            skill=fixture_dir.name,
            prompt=prompt,
            expected_files=_parse_expected_files(text=listed),
        )
    )


def discover_fixtures(
    *, fixtures_root: Path
) -> IOResult[dict[str, FixturedSkill], DiscoveryUnreadable]:
    """Walk `<fixtures_root>/<skill>/` and load each `prompt.md` fixture.

    Directory present (with a `prompt.md`) == fixture exists (contract
    requirement 4). The optional `expected_files.txt` enumerates paths that
    MUST exist after the skill's turn; an absent file means no file assertions.
    Returns a mapping of skill name → its loaded fixture on the success track.

    An ABSENT root is an ANSWER (`{}`), not a failure: a consumer that ships no
    fixtures yet is an ordinary state, and the coverage gate still convicts it
    because `discovered` is non-empty. A root that EXISTS and cannot be listed
    is a FAILURE — `is_dir()` fused those two and this splits them.

    ⚠️ THE `prompt.md` FILTER IS `exists()`, NOT `is_file()`, and the difference
    is deliberate. `exists()` answers the contract's own question — is there a
    `prompt.md` in this directory — while `is_file()` additionally swallowed
    "there is one and it is not a readable file" into "there is none", so a
    `prompt.md` that is a DIRECTORY vanished silently instead of being named.
    """
    try:
        children = sorted(fixtures_root.iterdir())
    except FileNotFoundError:
        return IOSuccess({})
    except OSError as unlistable:
        return _unreadable(
            path=fixtures_root, reason="fixtures-root-not-listed", detail=str(unlistable)
        )
    return _collected(
        results=[
            _load_fixture(fixture_dir=child)
            for child in children
            if child.is_dir() and (child / _PROMPT_FILENAME).exists()
        ]
    ).map(lambda loaded: {fixture.skill: fixture for fixture in loaded})
