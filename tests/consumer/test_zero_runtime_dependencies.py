"""Consumer-tier: the dependencies invariant of `SPECIFICATION/constraints.md`.

The library vendors `returns` and `structlog`, but vendored `returns` imports
`typing_extensions` at runtime. A released wheel must therefore declare that
dependency so a clean `uv` git-source installation supplies it. Tool versions
remain pinned by each consuming repo's own `[dependency-groups].dev` table.
The consumer-facing contract is read from these surfaces:

- **The declaration, in the packaging config.** `[project].dependencies`
  declares the dependency a `uv` git-source consumer installs.
- **The declaration, in the INSTALLED distribution.** `Requires-Dist` is what
  the consumer's RESOLVER reads, and it is a separate artifact from the
  config above — a dependency introduced through a build-backend default, a
  plugin, or a dynamic-metadata hook would appear here and nowhere in the
  `[project]` table. Asserting only the config would leave that gap open.
- **The vendored mechanism.** `returns` and `structlog` resolve from
  `livespec_dev_tooling/_vendor/`; `typing_extensions` resolves from the
  package's declared runtime dependency set. This makes the absolute imports
  in the vendored `returns` tree work for consumers that installed no
  unrelated packages.
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
_DEPENDENCIES_KEY = re.compile(
    r"^dependencies\s*=\s*\[\n(?P<body>.*?)^\]", re.MULTILINE | re.DOTALL
)

# The `[dependency-groups].dev` array's body — the sanctioned home for the tool
# pins, one `"<name>==<version>"` entry per line.
_DEV_GROUP = re.compile(r"^dev = \[\n(?P<body>.*?)^\]", re.MULTILINE | re.DOTALL)

# The tools the dependencies constraint of `SPECIFICATION/constraints.md` names as
# the current shelled-out set, each of which must carry an exact pin in the dev
# group rather than a runtime dependency.
_PINNED_TOOLS = ("ruff", "pyright", "pytest")
_RUNTIME_DEPENDENCY = "typing-extensions>=4.0"


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


def test_vendored_returns_runtime_dependency_is_declared() -> None:
    """Clean wheel consumers receive `typing_extensions` with vendored `returns`."""
    declared = _DEPENDENCIES_KEY.search(_project_table_body())
    assert declared is not None, (
        "`[project]` must declare typing-extensions because the vendored returns "
        "runtime imports it in a clean consumer environment"
    )
    declared_dependencies = [
        line.strip().strip(",").strip('"') for line in declared.group("body").splitlines()
    ]
    assert declared_dependencies == [_RUNTIME_DEPENDENCY], (
        "the only declared runtime dependency must be the typing-extensions "
        f"required by vendored returns; declared={declared_dependencies}"
    )

    requires = importlib.metadata.requires(_DISTRIBUTION) or []
    assert requires == [_RUNTIME_DEPENDENCY], (
        f"the INSTALLED distribution's Requires-Dist is what a consumer's resolver "
        f"reads, and it must declare typing-extensions; declared={sorted(requires)}"
    )

    resolved = {"returns": str(returns.__file__), "structlog": str(structlog.__file__)}
    external = sorted(
        name for name, location in resolved.items() if not location.startswith(str(_VENDOR_DIR))
    )
    assert not external, (
        f"the vendored libraries must resolve from `livespec_dev_tooling/_vendor/`; "
        f"resolved elsewhere={external} ({resolved})"
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
