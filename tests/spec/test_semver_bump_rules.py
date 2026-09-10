"""The `SPECIFICATION/contracts.md` §"Semver discipline" bump rules, made enforceable.

That the enumerated surface still RESOLVES is asserted at
`tests.consumer.test_semver_stable_surface` (the `constraints.md` §"Semver
discipline" invariant). What that leaves uncovered is whether the BUMP RULES can
be applied to the surface at all, and the two ways they silently cannot:

- **A MAJOR-class key change has to be observable.** The enumeration makes "the
  `[tool.livespec_dev_tooling]` consumer-configuration key set" a semver-stable
  element, and the MAJOR rule names "removing or incompatibly reinterpreting a
  recognized key". "Recognized" is a property of the LOADER, so the rule is only
  applicable while the loader's key set and the specification's role-key
  inventory describe the same set. Asserted in both directions, with the two
  carve-outs the specification itself states: `REQUIRED_ROLE_KEYS` is the
  normative set and every member must appear in the inventory, and every
  documented role key must be a loader field EXCEPT `repo` — which the inventory
  marks "DOCUMENTED BUT NOT LOADER-IMPLEMENTED", so its presence as a field would
  contradict its own bullet.

- **A MAJOR-class removal from either enumerated INVOCATION SET has to be
  observable.** The enumeration names two invocation sets — `checks` and
  `workflow_checks` — and §"`release_bump_classification` check" records, as
  limit one, that a consumer which has not declared `invocation_set_trees` moves
  its inventory by nothing when a slug is added, deleted, or renamed, so "the
  check will pass a PATCH release over a MAJOR change". This repository's public
  surface IS predominantly an invocation set (its slug modules export nothing),
  so a declaration missing either tree disarms the release gate for exactly the
  change class the MAJOR rule exists to catch — and it disarms it SILENTLY, by
  passing.

Both are read off the tree and the specification rather than off a release run,
because a release is the one moment at which discovering either would be too
late.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from livespec_dev_tooling.config import REQUIRED_ROLE_KEYS, Config, load_config

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _REPO_ROOT / "SPECIFICATION" / "contracts.md"

# The role-key inventory: the bolded-backtick bullets of §"Role keys".
_ROLE_KEYS_SECTION = re.compile(r"^### Role keys\n(?P<body>.*?)(?=^### )", re.MULTILINE | re.DOTALL)
_ROLE_KEY_BULLET = re.compile(r"^- \*\*`(?P<name>[a-z_]+)`\*\*", re.MULTILINE)

# The one documented key the inventory itself says the loader never parses.
_NOT_LOADER_IMPLEMENTED = "repo"

# The two invocation sets the enumeration names, spelled as declared paths.
_ENUMERATED_INVOCATION_SETS = (
    "livespec_dev_tooling/checks",
    "livespec_dev_tooling/workflow_checks",
)


def _documented_role_keys() -> set[str]:
    """Every role key the §"Role keys" inventory declares."""
    matched = _ROLE_KEYS_SECTION.search(_CONTRACTS.read_text(encoding="utf-8"))
    assert matched is not None, 'contracts.md must carry the "### Role keys" inventory'
    documented = set(_ROLE_KEY_BULLET.findall(matched.group("body")))
    assert documented, "the role-key inventory must declare at least one key"
    return documented


def _loader_fields() -> set[str]:
    """Every key the loader recognizes, read off the typed `Config` it returns."""
    return {field.name for field in dataclasses.fields(Config)}


def test_the_recognized_configuration_key_set_matches_its_semver_stable_declaration() -> None:
    """The loader's key set and the documented inventory describe the same keys."""
    documented = _documented_role_keys()
    fields = _loader_fields()

    assert REQUIRED_ROLE_KEYS, "the loader must export a non-empty normative role-key set"
    undocumented = sorted(REQUIRED_ROLE_KEYS - documented)
    assert not undocumented, (
        f"`REQUIRED_ROLE_KEYS` is the normative set, so a member the inventory does not "
        f"describe is a recognized key with no semver-stable declaration — and its removal "
        f"would be a MAJOR nobody could classify; undocumented={undocumented}"
    )

    unrecognized = sorted(documented - fields - {_NOT_LOADER_IMPLEMENTED})
    assert not unrecognized, (
        f"a documented role key the loader does not recognize is a key consumers declare "
        f"and no check reads — the inventory would promise stability for nothing; "
        f"unrecognized={unrecognized}"
    )
    assert _NOT_LOADER_IMPLEMENTED not in fields, (
        f"`{_NOT_LOADER_IMPLEMENTED}` is documented as NOT loader-implemented — the loader "
        f"has no such field and never parses the key — so a field of that name would "
        f"contradict its own bullet and silently start honouring a declared override"
    )


def test_both_enumerated_invocation_sets_are_declared_to_the_release_gate() -> None:
    """A slug removed from either set is visible to the check that enforces the bump rules."""
    declared = {str(tree) for tree in load_config(repo_root=_REPO_ROOT).invocation_set_trees}
    missing = sorted(tree for tree in _ENUMERATED_INVOCATION_SETS if tree not in declared)
    assert not missing, (
        f"this repository's public surface is predominantly an INVOCATION set — its slug "
        f"modules export nothing — so an enumerated set left out of `invocation_set_trees` "
        f"moves the release gate's inventory by zero names when a slug is deleted or "
        f"renamed, and it passes a PATCH release over a MAJOR change; missing={missing} "
        f"declared={sorted(declared)}"
    )
