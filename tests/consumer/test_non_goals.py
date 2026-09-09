"""Consumer-tier: the `SPECIFICATION/spec.md` §"Non-goals" negatives, asserted as invariants.

A non-goal is a promise about what a consumer will NOT find, so each one is
read the way a consumer meets it — off the installed distribution's metadata
and off the shipped tree — rather than off intent:

- **PyPI publishing.** "The library is consumed exclusively via `uv` git
  source in v1." Asserted as the absence of any publishing MECHANISM in the
  shipped CI surface or the packaging config: a publish step landing by
  accident is exactly how a "future optional flip" becomes v1 behaviour.
- **Runtime dependency on livespec.** "introducing a runtime dependency on
  livespec would create a circular dependency between the two repos."
  Asserted twice, because the two halves fail independently: the INSTALLED
  distribution declares no livespec requirement (what a consumer's resolver
  reads), and no shipped module imports the `livespec` package (what the
  interpreter would need at runtime regardless of metadata).
- **Hosting checks that are intrinsically `livespec`-specific.** Asserted as
  the absence of the two named livespec-private checks from the shipped
  canonical set — the partition's own worked examples, per `contracts.md`
  §"Shared check inventory".
- **A `templates/library/` extraction in v1.** Asserted as the absence of
  that tree.

The remaining non-goal — network I/O from any check — has its own coverage
at `tests.consumer.test_no_network_io` and is deliberately not restated
here.
"""

from __future__ import annotations

import ast
import importlib.metadata
from pathlib import Path

import pytest
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"
_DISTRIBUTION = "livespec-dev-tooling"

# Publishing mechanisms, spelled as they would appear in a workflow step, a
# composite Action, or the packaging config. Substrings rather than parsed
# YAML: a publish step is caught wherever it is expressed.
_PUBLISH_MECHANISMS = (
    "pypa/gh-action-pypi-publish",
    "twine upload",
    "uv publish",
    "hatch publish",
    "flit publish",
    "poetry publish",
    "publish-url",
)

# The two checks `contracts.md` §"Shared check inventory" names as
# livespec-private: each asserts a property of livespec-core's own layout,
# so neither may appear in this library's shipped set.
_LIVESPEC_PRIVATE_CHECKS = ("check-schema-dataclass-pairing", "check-copier-template-smoke")


def _publishing_surface_files() -> list[Path]:
    """The packaging config plus every shipped CI workflow and composite Action."""
    github = _REPO_ROOT / ".github"
    return [
        _REPO_ROOT / "pyproject.toml",
        *sorted(github.glob("workflows/*.yml")),
        *sorted(github.glob("actions/*/action.yml")),
    ]


def _imported_roots(*, source: str) -> set[str]:
    """The set of top-level module roots imported by `source` (via AST)."""
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _shipped_modules() -> list[Path]:
    """Every shipped first-party module (the vendored subtree is upstream code)."""
    return sorted(
        path
        for path in _PACKAGE_DIR.rglob("*.py")
        if "_vendor" not in path.relative_to(_REPO_ROOT).parts
    )


def test_every_tree_decidable_v1_non_goal_holds() -> None:
    """None of the v1 non-goals has crept into the shipped surfaces."""
    publish_hits = {
        path.name: sorted(
            token for token in _PUBLISH_MECHANISMS if token in path.read_text(encoding="utf-8")
        )
        for path in _publishing_surface_files()
    }
    published = sorted(name for name, hits in publish_hits.items() if hits)
    assert not published, (
        f"PyPI publishing is a v1 non-goal — the library is consumed exclusively via "
        f"`uv` git source; publishing mechanisms found in {published} ({publish_hits})"
    )

    declared_requirements = importlib.metadata.requires(_DISTRIBUTION) or []
    livespec_requirements = sorted(
        requirement for requirement in declared_requirements if "livespec" in requirement.lower()
    )
    assert not livespec_requirements, (
        f"a runtime dependency on livespec would close the dependency cycle between the "
        f"two repos; the installed distribution declares {livespec_requirements}"
    )

    livespec_importers = {
        str(path.relative_to(_REPO_ROOT)): "livespec"
        for path in _shipped_modules()
        if "livespec" in _imported_roots(source=path.read_text(encoding="utf-8"))
    }
    assert not livespec_importers, (
        f"no shipped module may import the `livespec` package — the dependency runs "
        f"livespec → this library, never the reverse; importers={sorted(livespec_importers)}"
    )

    resolved = canonical_check_slugs()
    assert isinstance(
        resolved, IOSuccess
    ), f"the shipped checks package must be readable; got {resolved}"
    shipped = set(unsafe_perform_io(resolved.unwrap()))
    hosted_private = sorted(slug for slug in _LIVESPEC_PRIVATE_CHECKS if slug in shipped)
    assert not hosted_private, (
        f"livespec-specific checks stay in livespec-core per contracts.md "
        f'§"Shared check inventory"; hosted={hosted_private}'
    )

    assert not (_REPO_ROOT / "templates" / "library").exists(), (
        "a `templates/library/` extraction is a v1 non-goal (livespec epic li-fgqgnk "
        "Phase G.2's YAGNI); it lands only if a second sibling library appears"
    )
