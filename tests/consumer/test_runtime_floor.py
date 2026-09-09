"""Consumer-tier: the `SPECIFICATION/constraints.md` §"Runtime" Python floor.

The constraint states the library MUST target Python 3.10 or later and MUST
NOT use any language feature introduced after 3.10 unless the introducing
release is added to the floor through a propose-change. Both halves are read
the way a consumer meets them, because they fail at different moments:

- **The DECLARED floor, read at install time.** `requires-python` is what a
  consumer's resolver reads before it will install the distribution at all.
  It is asserted together with the two tool pins that decide the same
  question for the tools a consumer runs against the shipped source — ruff's
  `target-version` and pyright's `pythonVersion`. A floor declared in one
  place and contradicted in another is a floor nobody enforces: the lint and
  type gates would silently accept syntax the resolver has promised runs on
  3.10, and the consumer meets the contradiction as an ImportError.
- **The ACTUAL floor, read at import time.** Every shipped first-party module
  is re-parsed with `ast.parse(..., feature_version=(3, 10))`, the parser
  mode that refuses grammar introduced after that release. A module carrying
  `except*` (PEP 654, 3.11) or a PEP 695 `type` alias (3.12) does not compile
  on the interpreter the declared floor promises — a break the declaration
  alone cannot catch, since `requires-python` is a claim rather than a check.

The vendored `_vendor/` subtree is excluded: it is upstream code this
repository does not author, and the constraint governs the library's own
modules.

`_post_floor_syntax_error` is exercised in BOTH directions — against every
shipped module, where it must find nothing, and against a fixture carrying a
post-floor feature, where it must convict — so the probe is proven capable of
failing rather than assumed to be.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"

# The floor the constraint names, spelled as `ast.parse`'s `feature_version`
# pair — the (major, minor) release whose grammar the parser will accept.
_FLOOR = (3, 10)

# The three places the floor is declared, each read as the (major, minor)
# release it names. `requires-python` additionally carries the patch component
# this repo pins (`>=3.10.16`); only the release components decide the language
# level, so the patch is deliberately not captured.
_FLOOR_DECLARATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("requires-python", re.compile(r'^requires-python = ">=(\d+)\.(\d+)', re.MULTILINE)),
    ("ruff target-version", re.compile(r'^target-version = "py(\d)(\d+)"', re.MULTILINE)),
    ("pyright pythonVersion", re.compile(r'^pythonVersion = "(\d+)\.(\d+)"', re.MULTILINE)),
)

# A language feature introduced AFTER the floor, used to prove the probe
# convicts: `except*` exception groups are PEP 654, Python 3.11.
_POST_FLOOR_SOURCE = "try:\n    pass\nexcept* ValueError:\n    pass\n"


def _declared_floor(*, text: str, label: str, pattern: re.Pattern[str]) -> tuple[int, int]:
    """The (major, minor) release `label`'s declaration names in `text`."""
    matched = pattern.search(text)
    assert matched is not None, f"pyproject.toml must declare the {label} floor"
    return (int(matched.group(1)), int(matched.group(2)))


def _shipped_modules() -> list[Path]:
    """Every shipped first-party module (the vendored subtree is upstream code)."""
    return sorted(
        path
        for path in _PACKAGE_DIR.rglob("*.py")
        if "_vendor" not in path.relative_to(_REPO_ROOT).parts
    )


def _post_floor_syntax_error(*, source: str) -> str | None:
    """The parse error `source` raises at the floor, or `None` when it compiles."""
    try:
        _ = ast.parse(source, feature_version=_FLOOR)
    except SyntaxError as beyond_floor:
        return str(beyond_floor)
    return None


def test_every_shipped_module_compiles_on_the_declared_python_floor() -> None:
    """The floor is 3.10 in all three declarations, and no shipped module outruns it."""
    text = _PYPROJECT.read_text(encoding="utf-8")
    declared = {
        label: _declared_floor(text=text, label=label, pattern=pattern)
        for label, pattern in _FLOOR_DECLARATIONS
    }
    disagreeing = sorted(label for label, floor in declared.items() if floor != _FLOOR)
    assert not disagreeing, (
        f"the resolver's floor and the lint/type gates' floor must name the same release "
        f'(constraints.md §"Runtime"); disagreeing={disagreeing} declared={declared}'
    )

    modules = _shipped_modules()
    assert modules, "the library must ship at least one first-party module"
    beyond = {
        str(path.relative_to(_REPO_ROOT)): _post_floor_syntax_error(
            source=path.read_text(encoding="utf-8")
        )
        for path in modules
    }
    outrunning = {name: error for name, error in sorted(beyond.items()) if error is not None}
    assert not outrunning, (
        f"a shipped module uses grammar introduced after Python "
        f"{_FLOOR[0]}.{_FLOOR[1]}, so it cannot be imported on the floor the "
        f"distribution promises; adding a release to the floor is a "
        f"propose-change. outrunning={outrunning}"
    )


def test_a_post_floor_language_feature_does_not_compile_at_the_floor() -> None:
    """The floor probe convicts a fixture carrying a 3.11 feature.

    Without this, a probe that silently accepted everything would report the
    invariant above as held for a tree that violates it.
    """
    error = _post_floor_syntax_error(source=_POST_FLOOR_SOURCE)

    assert error is not None, (
        f"the floor probe must refuse `except*` (PEP 654, Python 3.11) when parsing "
        f"at {_FLOOR[0]}.{_FLOOR[1]}; it accepted the fixture instead"
    )
