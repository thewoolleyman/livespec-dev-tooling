"""The `SPECIFICATION/contracts.md` §"Versioning" lockstep, read off the checkout.

The section makes two claims, and each fails in a way nothing else here would
catch.

**Three version records stay in lockstep.** The `pyproject.toml` `version`
field, the `.release-please-manifest.json` entry, and the git tag. The first two
are always readable and are asserted as equal outright: they are the pair a
consumer's `tag = "vX.Y.Z"` pin and the packaging metadata are resolved from, and
they drift the moment anything but the release tool touches either. The tag is
asserted CONDITIONALLY — `v<version>` must be among the tags when the checkout
carries any at all. That is not a softening: a clone made without tags has not
told us the tag is absent, and a can't-read is not a violation
(`livespec-dev-tooling-6ge`), so a bare `git tag` list of length zero is treated
as the absence of evidence it is.

**`release-please` is the only tool that writes to these.** A second writer is
what makes lockstep unmaintainable, and it announces itself long before it
misfires: to write the manifest a tool must first NAME it. Asserted as the
absence of that name from every shipped module and from the `justfile` — the two
places a second writer would live — with the release-please workflow the single
sanctioned namer. This is a necessary-condition test and says so: it convicts a
would-be writer at the point it acquires the path, which is the only point at
which the convicting is cheap.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import cast

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_MANIFEST = _REPO_ROOT / ".release-please-manifest.json"
_JUSTFILE = _REPO_ROOT / "justfile"
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"

_VERSION_LINE = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"', re.MULTILINE)

# The manifest's root-package key — this repository releases one package.
_ROOT_PACKAGE = "."

# The manifest path a second writer would have to name before writing it, and
# the one workflow sanctioned to.
_MANIFEST_NAME = ".release-please-manifest.json"
_SANCTIONED_NAMER = _REPO_ROOT / ".github" / "workflows" / "release-please.yml"


def _declared_version() -> str:
    """The version `pyproject.toml` declares."""
    matched = _VERSION_LINE.search(_PYPROJECT.read_text(encoding="utf-8"))
    assert matched is not None, 'pyproject.toml must declare a `version = "..."` line'
    return matched.group("version")


def _manifest_version() -> str:
    """The version the release manifest records for the root package."""
    parsed = cast("dict[str, str]", json.loads(_MANIFEST.read_text(encoding="utf-8")))
    assert _ROOT_PACKAGE in parsed, (
        f"the release manifest must carry a `{_ROOT_PACKAGE}` entry for the root package; "
        f"keys={sorted(parsed)}"
    )
    return parsed[_ROOT_PACKAGE]


def _release_tags() -> list[str]:
    """Every `v*` tag this checkout carries — possibly none, on a tagless clone."""
    # S603/S607: a literal `git` plus a fixed argument list, never a shell string.
    completed = subprocess.run(
        ["git", "tag", "--list", "v*"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _manifest_namers() -> list[str]:
    """Every shipped module or justfile recipe naming the release manifest."""
    candidates = [_JUSTFILE, *sorted(_PACKAGE_DIR.rglob("*.py"))]
    return sorted(
        str(path.relative_to(_REPO_ROOT))
        for path in candidates
        if "_vendor" not in path.relative_to(_REPO_ROOT).parts
        and _MANIFEST_NAME in path.read_text(encoding="utf-8")
    )


def test_the_version_records_stay_in_lockstep() -> None:
    """The packaging version, the manifest entry, and (where readable) the tag agree."""
    declared = _declared_version()
    recorded = _manifest_version()
    assert declared == recorded, (
        f"the `pyproject.toml` version and the release manifest entry MUST stay in "
        f"lockstep — a consumer's pin tag names one and its resolver reads the other; "
        f"pyproject={declared!r} manifest={recorded!r}"
    )

    tags = _release_tags()
    assert not tags or f"v{declared}" in tags, (
        f"the git tag is the third record of the lockstep, so the declared version must "
        f"be tagged wherever the tags are readable at all; declared={declared!r} "
        f"tags={tags[-5:]}"
    )


def test_release_please_is_the_only_tool_positioned_to_write_the_manifest() -> None:
    """No shipped module or justfile recipe so much as names the release manifest."""
    assert (
        _SANCTIONED_NAMER.is_file()
    ), "releases are managed by `release-please`, so the workflow that runs it must ship"
    assert _MANIFEST_NAME in _SANCTIONED_NAMER.read_text(encoding="utf-8"), (
        f"the release workflow must name `{_MANIFEST_NAME}` as the manifest it maintains — "
        f"it is the ONE sanctioned writer, and a run pointed at a different file would "
        f"leave the recorded version behind the tag it cut"
    )

    namers = _manifest_namers()
    assert not namers, (
        f"`release-please` is the only tool that writes the version records, and a second "
        f"writer must first NAME the manifest — convicting it here is the cheapest point "
        f"at which lockstep can still be defended; namers={namers}"
    )
