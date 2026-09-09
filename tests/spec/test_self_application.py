"""The `SPECIFICATION/constraints.md` §"Self-application" dogfood loop, read off the config.

The constraint states that `just check` in this repo MUST run every shared
check this library ships AGAINST THIS REPO'S OWN SOURCE TREE, and gives the
reason: a check the library cannot apply to itself is a check no consumer can
apply either.

Two halves have to hold, and they fail independently:

- **Every shipped check is a target of the aggregate.** That half is asserted
  by `test_definition_of_done_gates` (the Definition of Done names it as a
  merge condition) and by the shipped `aggregate_completeness` and
  `canonical_recipe_fidelity` checks, so it is deliberately not restated here.
- **What those targets SCAN is this library's own code.** That is this file,
  and it is the half with no other guard. Wiring is not application: a
  repository can carry every canonical slug in its `targets=(...)` array and
  every recipe pointed at the pinned shared module while its
  `[tool.livespec_dev_tooling]` block aims the scan somewhere the shipped
  modules are not. Every one of those checks then passes by inspecting
  nothing, `just check` is green, and self-application is vacuous — the exact
  shape the constraint's "a check that the library cannot apply to itself"
  sentence is guarding against, and one that raises no error because an empty
  universe has no violations in it.

So the configured universe is resolved the way the checks resolve it and then
asked whether the library's own shipped modules are IN it — first by
containment under a declared source tree, then through `iter_py_files`, the
shared walker the shape-checking checks actually use. The second is not
redundant: a tree may contain a path the walker never yields (it skips
`_vendor/` and `__pycache__`), so containment alone would prove the
declaration and not the scan.
"""

from __future__ import annotations

from pathlib import Path

from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs
from livespec_dev_tooling.config import iter_py_files, load_config

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"


def _shipped_check_modules() -> dict[str, Path]:
    """Each canonical slug mapped to the shipped module file it invokes."""
    resolved = canonical_check_slugs()
    assert isinstance(
        resolved, IOSuccess
    ), f"the shipped checks package must be readable; got {resolved}"
    slugs = unsafe_perform_io(resolved.unwrap())
    return {
        slug: _CHECKS_DIR / f"{slug.removeprefix('check-').replace('-', '_')}.py" for slug in slugs
    }


def test_the_configured_universe_contains_this_repositorys_own_shipped_modules() -> None:
    """`just check`'s scan universe is the library's own source tree, not an empty one."""
    config = load_config(repo_root=_REPO_ROOT)
    assert config.source_trees, (
        "self-application requires a declared source tree — an undeclared one leaves "
        'every shape-checking check scanning nothing (constraints.md §"Self-application")'
    )

    declared_trees = [(_REPO_ROOT / tree).resolve() for tree in config.source_trees]
    absent = sorted(str(tree) for tree in declared_trees if not tree.is_dir())
    assert not absent, f"every declared source tree must exist in this checkout; absent={absent}"

    shipped = _shipped_check_modules()
    assert shipped, "the library must ship at least one canonical check"

    outside = sorted(
        slug
        for slug, module_path in shipped.items()
        if not any(module_path.resolve().is_relative_to(tree) for tree in declared_trees)
    )
    assert not outside, (
        f"a shipped check module sits outside every declared source tree, so `just "
        f"check` never applies the suite to it; outside={outside}"
    )

    walked = {path.resolve() for tree in declared_trees for path in iter_py_files(root=tree)}
    unwalked = sorted(
        slug for slug, module_path in shipped.items() if module_path.resolve() not in walked
    )
    assert not unwalked, (
        f"the shared walker the shape checks use must reach every shipped check module "
        f"— a declared tree whose modules it skips is a scan of nothing; "
        f"unwalked={unwalked}"
    )
