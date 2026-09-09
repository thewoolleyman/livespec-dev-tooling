"""Consumer-tier: the `SPECIFICATION/constraints.md` §"Semver discipline" invariant.

The constraint delegates the ENUMERATION of the semver-stable surface to
`contracts.md` §"Semver discipline" and keeps one invariant for itself: NO
breaking change to any enumerated surface element may land outside a MAJOR
version bump.

That invariant is asserted by RESOLVING the enumeration against the tree at
the version the packaging config currently declares. A surface element that
has been removed or renamed no longer resolves, and since the declared version
is right there beside it, a resolution failure IS a break that landed without
the MAJOR bump the rule requires. Reading it this way covers the removals a
diff-based bump classifier cannot: a composite Action deleted in a `chore:`
commit, a reusable workflow renamed in a `refactor:`, a detector dropped from
the registry — none of which announce themselves as breaking.

The enumerated elements resolved here, in the order `contracts.md` lists them:

- The `python -m livespec_dev_tooling.checks.<slug>` invocation set, and
- the `python -m livespec_dev_tooling.workflow_checks.<slug>` invocation set —
  each non-empty, and every member a real module file. A slug a consumer
  wires into its `just check` or its own workflow step must still be there.
- The composite Action paths, each still declaring the `runs:` wire a
  consumer's `uses:` step executes.
- The reusable workflow paths, each still declaring the `workflow_call:`
  trigger that makes it callable at all.

  Those last two are read off the MINIMUM SETS `contracts.md` §"Composite
  Actions wire contract" and §"Reusable workflows wire contract" name, not
  off the tree — the tree cannot convict a removal of itself. Each section
  says the path IS the semver-stable identifier, so a name the specification
  enumerates and the checkout no longer carries is precisely the break this
  test exists to catch, and it is a break a `chore:` or `refactor:` commit
  ships without announcing.
- The importable charter-defect detector API — the ONE element consumers
  reach by IMPORT rather than by invocation — asserted as a non-empty
  detector registry, a non-empty charter-path glob set, and a callable
  scoring entry point. The glob set is asserted non-empty for the reason
  `contracts.md` gives: NARROWING it silently reduces every consumer's
  coverage while the gate still reports green, so emptying it is breaking
  even though nothing raises.

Finally, the bump the rule names has to be DERIVABLE: `release-please` is what
turns a Conventional Commit into the next version, so its config is asserted to
recognize the `feat` and `fix` types the mapping names and to rewrite the
declared version this test read the surface at. A MAJOR-bump rule nothing can
execute is a rule that cannot be honored.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import cast

import pytest
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _REPO_ROOT / "SPECIFICATION" / "contracts.md"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"
_ACTIONS_DIR = _REPO_ROOT / ".github" / "actions"
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_RELEASE_PLEASE_CONFIG = _REPO_ROOT / "release-please-config.json"

# The version the surface below is resolved AT — the component a consumer's
# `tag = "vX.Y.Z"` pin names and the one `release-please` increments.
_VERSION_LINE = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"', re.MULTILINE)

# The importable element of the enumeration, named as a consumer imports it.
_CHARTERS_MODULE = "livespec_dev_tooling.charters"

# The two `contracts.md` sections whose bullet lists name the MINIMUM shipped
# set of each path-identified surface, and the bolded-backtick bullet form they
# are written in.
_WIRE_CONTRACT_SECTIONS = (
    "## Composite Actions wire contract",
    "## Reusable workflows wire contract",
)
_ENUMERATED_NAME = re.compile(r"^- \*\*`(?P<name>[A-Za-z0-9._-]+)`\*\*\.", re.MULTILINE)
_SECTION_BODY = "^{heading}\n(?P<body>.*?)(?=^## )"

# The Conventional Commit types the mapping names explicitly (`feat:` MINOR,
# `fix:` PATCH); `feat!:` MAJOR rides the same `feat` type with a `!` marker.
_MAPPED_COMMIT_TYPES = ("feat", "fix")


def _declared_version() -> str:
    """The version the packaging config declares."""
    matched = _VERSION_LINE.search(_PYPROJECT.read_text(encoding="utf-8"))
    assert matched is not None, 'pyproject.toml must declare a `version = "..."` line'
    return matched.group("version")


def _canonical_module_paths() -> dict[str, Path]:
    """Each canonical check slug mapped to the module file its invocation names."""
    resolved = canonical_check_slugs()
    assert isinstance(
        resolved, IOSuccess
    ), f"the shipped checks package must be readable; got {resolved}"
    slugs = unsafe_perform_io(resolved.unwrap())
    return {
        slug: _PACKAGE_DIR / "checks" / f"{slug.removeprefix('check-').replace('-', '_')}.py"
        for slug in slugs
    }


def _workflow_check_module_paths() -> dict[str, Path]:
    """Each workflow-check slug mapped to its module file."""
    return {
        path.stem: path
        for path in sorted((_PACKAGE_DIR / "workflow_checks").glob("*.py"))
        if not path.stem.startswith("_")
    }


def _enumerated_names(*, heading: str) -> list[str]:
    """The names `contracts.md`'s section `heading` enumerates as its minimum set."""
    section = re.compile(_SECTION_BODY.format(heading=re.escape(heading)), re.MULTILINE | re.DOTALL)
    matched = section.search(_CONTRACTS.read_text(encoding="utf-8"))
    assert matched is not None, f"contracts.md must carry the section {heading!r}"
    names = _ENUMERATED_NAME.findall(matched.group("body"))
    assert names, f"{heading!r} must enumerate at least one shipped element"
    return names


def test_every_enumerated_semver_stable_surface_element_still_resolves() -> None:
    """Each element `contracts.md` enumerates resolves at the declared version."""
    version = _declared_version()

    invocation_sets = {
        "checks": _canonical_module_paths(),
        "workflow_checks": _workflow_check_module_paths(),
    }
    empty_sets = sorted(name for name, members in invocation_sets.items() if not members)
    assert not empty_sets, f"each enumerated invocation set must be non-empty; empty={empty_sets}"
    missing_modules = sorted(
        f"{namespace}.{slug}"
        for namespace, members in invocation_sets.items()
        for slug, path in members.items()
        if not path.is_file()
    )
    assert not missing_modules, (
        f"an enumerated `python -m` invocation no longer resolves to a module, so a "
        f"consumer wiring it breaks; version={version} missing={missing_modules}"
    )

    actions = {
        name: _ACTIONS_DIR / name / "action.yml"
        for name in _enumerated_names(heading=_WIRE_CONTRACT_SECTIONS[0])
    }
    unwired_actions = sorted(
        name
        for name, path in actions.items()
        if not (path.is_file() and "runs:" in path.read_text(encoding="utf-8"))
    )
    assert not unwired_actions, (
        f"each composite Action the specification enumerates must still ship at its "
        f"path — the path IS the semver-stable identifier — and still declare the "
        f"`runs:` wire a consumer's `uses:` step executes; version={version} "
        f"unwired={unwired_actions}"
    )

    reusables = {
        name: _WORKFLOWS_DIR / name
        for name in _enumerated_names(heading=_WIRE_CONTRACT_SECTIONS[1])
    }
    uncallable = sorted(
        name
        for name, path in reusables.items()
        if not (path.is_file() and "workflow_call:" in path.read_text(encoding="utf-8"))
    )
    assert not uncallable, (
        f"each reusable workflow the specification enumerates must still ship at its "
        f"path and declare `workflow_call:`, or a consumer's `uses:` reference cannot "
        f"resolve; version={version} uncallable={uncallable}"
    )

    charters = importlib.import_module(_CHARTERS_MODULE)
    assert charters.DETECTORS, (
        f"the enumerated detector registry must be non-empty — removing a detector is "
        f"a MAJOR-bump change; version={version}"
    )
    assert charters.CHARTER_GLOBS, (
        f"narrowing the enumerated charter-path glob set silently reduces every "
        f"consumer's coverage while its gate still reports green, so an empty set is "
        f"breaking even though nothing raises; version={version}"
    )
    assert callable(charters.defects_in), (
        "the enumerated per-document scoring entry point must stay callable — its "
        "signature and return shape are the surface consumers import"
    )


def test_the_conventional_commit_to_semver_mapping_is_executable() -> None:
    """`release-please` recognizes the mapped commit types and rewrites the version.

    The MAJOR-bump rule the constraint states is only enforceable if some
    mechanism derives the bump; this asserts the mechanism is wired to the
    same version string the surface above is resolved at.
    """
    config = cast(
        "dict[str, object]", json.loads(_RELEASE_PLEASE_CONFIG.read_text(encoding="utf-8"))
    )

    sections = cast("list[dict[str, object]]", config["changelog-sections"])
    assert sections, "release-please must declare a non-empty `changelog-sections` list"
    declared_types = {
        name for entry in sections for name in [entry.get("type")] if isinstance(name, str)
    }
    unmapped = sorted(name for name in _MAPPED_COMMIT_TYPES if name not in declared_types)
    assert not unmapped, (
        f"the Conventional Commits → semver mapping names these types, so "
        f"`release-please` must recognize each; unmapped={unmapped} "
        f"declared={sorted(declared_types)}"
    )

    packages = cast("dict[str, object]", config["packages"])
    assert packages, "release-please must declare a non-empty `packages` table"
    extra_files = json.dumps(packages)
    assert "$.project.version" in extra_files, (
        "a derived bump must rewrite `pyproject.toml`'s `[project].version` — the "
        "component a consumer's pin tag names and the MAJOR/MINOR/PATCH rules operate on"
    )
