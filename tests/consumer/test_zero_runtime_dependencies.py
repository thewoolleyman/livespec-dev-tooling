"""Consumer-tier: the `SPECIFICATION/constraints.md` §"Dependencies" invariant.

The constraint states the library MUST declare NO runtime dependencies, and
that tool versions are pinned by each consuming repo's own `[dependency-
groups].dev` rather than by this library. The point of the invariant is stated
in the packaging config itself: a consumer adding this library to its dev group
pays ZERO transitive-pin cost. So each half is read where a consumer meets it:

- **The declaration, in the packaging config.** `[project]` carries no
  `dependencies` key at all. This is the source a `uv` git-source consumer
  builds from, so it is where the promise is authored.
- **The declaration, in the INSTALLED distribution.** `Requires-Dist` is what
  the consumer's RESOLVER reads, and it is a separate artifact from the
  config above — a dependency introduced through a build-backend default, a
  plugin, or a dynamic-metadata hook would appear here and nowhere in the
  `[project]` table. Asserting only the config would leave that gap open.
- **The mechanism that makes zero declared dependencies HONEST.** Every check
  imports `returns` (the ROP railway) and `structlog` (its diagnostics) at
  module import, so a library declaring no dependency on either is only
  truthful because both are VENDORED under `livespec_dev_tooling/_vendor/`.
  Each is asserted to resolve from that subtree rather than from site-
  packages: were the vendor path to stop governing, the imports would silently
  start resolving against whatever the developer's environment happened to
  carry, and the zero-dependency claim would hold on paper while every
  consumer without those packages met an ImportError.
- **Where tool versions ARE pinned.** The three tools the constraint names —
  `ruff`, `pyright`, `pytest` — each carry an EXACT `==` pin under
  `[dependency-groups].dev`. That table is the sanctioned home for them, so a
  tool migrating into `[project].dependencies` (which would push the pin onto
  every consumer) fails the first assertion, and a tool losing its exact pin
  fails this one.

The cross-repo half of the constraint — dev pins mirroring livespec's exactly —
is not decidable from this tree alone and is carried by the fleet pin-currency
surface rather than restated here.
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import pytest
import returns
import structlog

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_VENDOR_DIR = _REPO_ROOT / "livespec_dev_tooling" / "_vendor"
_DISTRIBUTION = "livespec-dev-tooling"

# The `[project]` table's body — everything up to the next top-level table
# header. A `dependencies` key anywhere in it is a declared runtime dependency.
_PROJECT_TABLE = re.compile(r"^\[project\]\n(?P<body>.*?)(?=^\[)", re.MULTILINE | re.DOTALL)
_DEPENDENCIES_KEY = re.compile(r"^dependencies\s*=", re.MULTILINE)

# The `[dependency-groups].dev` array's body — the sanctioned home for the tool
# pins, one `"<name>==<version>"` entry per line.
_DEV_GROUP = re.compile(r"^dev = \[\n(?P<body>.*?)^\]", re.MULTILINE | re.DOTALL)

# The tools §"Dependencies" names as the current shelled-out set, each of which
# must carry an exact pin in the dev group rather than a runtime dependency.
_PINNED_TOOLS = ("ruff", "pyright", "pytest")


def _project_table_body() -> str:
    """The `[project]` table's body text."""
    matched = _PROJECT_TABLE.search(_PYPROJECT.read_text(encoding="utf-8"))
    assert matched is not None, "pyproject.toml must declare a `[project]` table"
    return matched.group("body")


def _dev_pin_entries() -> list[str]:
    """Each `<name>==<version>` entry of `[dependency-groups].dev`."""
    matched = _DEV_GROUP.search(_PYPROJECT.read_text(encoding="utf-8"))
    assert matched is not None, "pyproject.toml must declare a `[dependency-groups].dev` array"
    return [line.strip().strip(",").strip('"') for line in matched.group("body").splitlines()]


def test_the_library_declares_no_runtime_dependencies() -> None:
    """No runtime dependency is declared, vendored imports resolve, tools are dev-pinned."""
    declared = _DEPENDENCIES_KEY.search(_project_table_body())
    assert declared is None, (
        "`[project]` must declare no `dependencies` key — a runtime dependency here "
        "becomes a transitive pin for every consumer that adds this library to its "
        'dev group (constraints.md §"Dependencies")'
    )

    requires = importlib.metadata.requires(_DISTRIBUTION) or []
    assert not requires, (
        f"the INSTALLED distribution's Requires-Dist is what a consumer's resolver "
        f"reads, and it must be empty; declared={sorted(requires)}"
    )

    resolved = {"returns": str(returns.__file__), "structlog": str(structlog.__file__)}
    external = sorted(
        name for name, location in resolved.items() if not location.startswith(str(_VENDOR_DIR))
    )
    assert not external, (
        f"every third-party package the shipped modules import at module scope must "
        f"resolve from `livespec_dev_tooling/_vendor/`, which is what makes the "
        f"zero-runtime-dependency declaration honest; resolved elsewhere={external} "
        f"({resolved})"
    )

    entries = _dev_pin_entries()
    unpinned = sorted(
        tool
        for tool in _PINNED_TOOLS
        if not any(entry.startswith(f"{tool}==") for entry in entries)
    )
    assert not unpinned, (
        f"the tools each check shells out to are pinned exactly by the consuming "
        f"repo's `[dependency-groups].dev`, not by this library's runtime metadata; "
        f"unpinned={unpinned} entries={entries}"
    )
