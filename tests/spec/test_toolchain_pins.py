"""§"Toolchain pins" — the file/pin PARTITION, and the exactness that makes drift visible.

The section is two clauses, and the second one depends entirely on the first:

- Non-Python binaries (uv, just, lefthook) pin via `.mise.toml`; Python and
  Python packages pin via `pyproject.toml`'s `[project.requires-python]` and
  `[dependency-groups].dev`.
- "Pinned versions MUST match livespec's `.mise.toml` and `pyproject.toml`
  exactly; drift surfaces as a propose-change-worthy event."

Both halves fail SILENTLY, which is why they are asserted here rather than left
to the reader:

- **A pin in the wrong file still resolves.** Adding `python` or `ruff` to
  `.mise.toml`'s `[tools]` gives this repo a working interpreter and a working
  linter — and an ACTIVATED mise shim then shadows the uv-resolved `.venv`
  the `[dependency-groups].dev` table pins. Two pins now exist for one tool,
  the `just check` aggregate runs against whichever one `PATH` reached first,
  and nothing errors. The partition is the thing that keeps one pin per tool.
- **A RANGE pin makes the match clause unfalsifiable.** "MUST match livespec's
  pins exactly" is a statement about a VERSION. Written as `uv = "latest"` or
  `ruff>=0.8.6`, a pin no longer names a version — it names a set, and two
  repositories carrying the same range can and do resolve to different builds
  on different days. Drift then cannot surface as a propose-change-worthy
  event because there is nothing to diff. So the assertion the section needs
  from this tree is that every pin here is an EQUALITY on a concrete version.

The sibling repository's files are not readable from this tree, so the
cross-repo equality itself is not asserted here; what is asserted is the
property that makes that comparison MEANINGFUL when a maintainer or the fleet
conformance sweep makes it.

Both files are read as TEXT rather than parsed: stdlib `tomllib` lands in 3.11
and `[project.requires-python]` here is `>=3.10.16`, so the sibling spec tests
in this directory read their TOML the same way.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MISE = _REPO_ROOT / ".mise.toml"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# The three non-Python binaries the section names by name.
_NAMED_BINARIES = ("uv", "just", "lefthook")

# A concrete version: digits and dots, nothing else. `latest`, `1.36`-with-a
# `-prefix`, `^1`, `>=1.36`, `1.36.x` and every other set-valued form fails it.
_EXACT_VERSION = re.compile(r"^\d+(\.\d+)*$")

# The Python-package pin form `[dependency-groups].dev` must use. A `>=`, a
# `~=` or a bare name names a set rather than a version.
_EQUALITY_PIN = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>[^;\s]+)$")

_TOOL_ENTRY = re.compile(r'^(?P<name>[A-Za-z0-9._-]+)\s*=\s*"(?P<pin>[^"]*)"', re.MULTILINE)
_QUOTED = re.compile(r'"([^"]+)"')


def _table_body(*, source: Path, table: str) -> str:
    """The lines of one top-level TOML table, up to the next table header."""
    text = source.read_text(encoding="utf-8")
    start = text.index(f"\n[{table}]\n") + len(f"\n[{table}]\n")
    tail = text[start:]
    end = tail.find("\n[")
    return tail if end == -1 else tail[:end]


def _mise_tools() -> dict[str, str]:
    """`.mise.toml`'s `[tools]` table, tool name to declared pin."""
    body = _table_body(source=_MISE, table="tools")
    return {matched.group("name"): matched.group("pin") for matched in _TOOL_ENTRY.finditer(body)}


def _dev_group_pins() -> list[str]:
    """Every requirement string in `pyproject.toml`'s `[dependency-groups].dev`."""
    body = _table_body(source=_PYPROJECT, table="dependency-groups")
    dev = body[body.index("dev = [") :]
    return _QUOTED.findall(dev[: dev.index("]")])


def test_no_python_pin_hides_in_the_binary_pin_file() -> None:
    """One tool, one pin, one file — the partition the section draws."""
    tools = _mise_tools()
    for binary in _NAMED_BINARIES:
        assert binary in tools, (
            f"the section names `{binary}` as a non-Python binary that pins via "
            f"`.mise.toml`; declared tools={sorted(tools)}"
        )

    package_names = {
        matched.group("name").lower()
        for matched in (_EQUALITY_PIN.match(entry) for entry in _dev_group_pins())
        if matched is not None
    }
    trespassing = sorted(name for name in tools if name.lower() in package_names)
    assert not trespassing, (
        f"these are pinned in BOTH `.mise.toml` and `[dependency-groups].dev`, so the "
        f"repository carries two pins for one tool and an ACTIVATED mise shim shadows "
        f"the uv-resolved `.venv` the dev group installs. Whichever one `PATH` reaches "
        f"first is the version `just check` actually ran, and neither file errors; "
        f"trespassing={trespassing}"
    )
    assert "python" not in tools, (
        "the section pins the Python interpreter via `[project.requires-python]`, not "
        "via `.mise.toml`; a mise `python` entry gives the repo a second interpreter "
        "that no `uv sync` resolved against"
    )


def test_every_binary_pin_names_a_concrete_version() -> None:
    """A range pin cannot drift, because it never named a version to drift from."""
    inexact = sorted(
        (name, pin) for name, pin in _mise_tools().items() if not _EXACT_VERSION.match(pin)
    )
    assert not inexact, (
        f"every `.mise.toml` pin must name a CONCRETE version. The section requires these "
        f"to match livespec's pins EXACTLY and for drift to surface as a propose-change-"
        f"worthy event; a set-valued pin (`latest`, `^1.2`, `>=1.2`) has no version to "
        f"diff, so two repositories carrying the identical string resolve to different "
        f"builds on different days and the drift is undetectable rather than absent; "
        f"inexact={inexact}"
    )


def test_every_python_package_pin_is_an_equality_and_python_itself_has_a_floor() -> None:
    """The `pyproject.toml` half of the same exactness property."""
    entries = _dev_group_pins()
    assert entries, "`[dependency-groups].dev` must pin this repository's Python dev tools"

    not_equality = sorted(entry for entry in entries if not _EQUALITY_PIN.match(entry))
    assert not not_equality, (
        f"every `[dependency-groups].dev` entry must be an `==` pin, for the same reason "
        f"the binary pins must be concrete: a `>=` or `~=` entry resolves differently on "
        f"different days, so `uv.lock` and not the spec becomes the only record of what "
        f"ran, and a livespec-versus-here comparison has nothing to compare; "
        f"not_equality={not_equality}"
    )

    project = _table_body(source=_PYPROJECT, table="project")
    declared = re.search(r'^requires-python\s*=\s*"(?P<floor>[^"]+)"', project, re.MULTILINE)
    assert declared is not None, (
        f"the section pins the interpreter through `[project.requires-python]`, so the "
        f"key must be present in the `[project]` table; body={project!r}"
    )
    requires_python = declared.group("floor")
    assert re.search(r"\d+\.\d+", requires_python), (
        f"the section pins the interpreter through `[project.requires-python]`, so it "
        f"must name a concrete version floor; requires-python={requires_python!r}"
    )
