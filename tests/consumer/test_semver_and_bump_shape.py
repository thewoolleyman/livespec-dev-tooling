"""Consumer-tier: additive surface bumps (MINOR) and breaking CLI bumps (MAJOR).

Covers two `SPECIFICATION/scenarios.md` scenarios:

- "a livespec contract change ships an additive surface bump" — an
  additive new shared check ships as a MINOR version bump.
- "a breaking change to an existing check's CLI ships as a MAJOR bump" —
  a backwards-incompatible argv change ships as a MAJOR version bump.

A consumer pins `livespec-dev-tooling` at `tag = "vX.Y.Z"` and bumps the
pin when a new release ships; `release-please` derives the MINOR-vs-MAJOR
increment from the Conventional Commit type. The consumer-observable
contracts this test pins are:

- the package's declared version is a well-formed 3-part semver
  (`MAJOR.MINOR.PATCH`), so the MAJOR / MINOR / PATCH components a consumer's
  pin tag and `release-please` operate on are unambiguous; and
- a shared check's argv / exit-code contract is consumer-observable and
  stable — a check accepts its documented invocation and emits exit `0` on
  a clean tree (the contract a MAJOR bump is what would change). A consumer
  bumps its pin against this surface, so the test pins the surface itself.

Read through `pyproject.toml` (the consumer-facing pin source) and the
`python -m` entrypoint — no internal package state.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# A 3-part semver `MAJOR.MINOR.PATCH` of non-negative integers — the shape
# `release-please` cuts and a consumer pins as `tag = "vX.Y.Z"`. The
# `version = "..."` line under `[project]` is the consumer-facing source.
_SEMVER_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
_VERSION_LINE_RE = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"', re.MULTILINE)


def _declared_version() -> str:
    text = _PYPROJECT.read_text(encoding="utf-8")
    match = _VERSION_LINE_RE.search(text)
    assert match is not None, 'pyproject.toml must declare a `version = "..."` line'
    return match.group("version")


def test_declared_version_is_a_wellformed_three_part_semver() -> None:
    """The package version is `MAJOR.MINOR.PATCH` of non-negative integers.

    A MINOR bump (additive surface) and a MAJOR bump (breaking CLI change)
    both operate on these components; a malformed version would make the
    consumer's pin tag and `release-please`'s increment ambiguous.
    """
    version = _declared_version()
    match = _SEMVER_RE.match(version)

    assert (
        match is not None
    ), f"declared version {version!r} must be a 3-part semver MAJOR.MINOR.PATCH"
    # All three components parse as non-negative integers — the increment
    # axes `release-please` chooses between (MINOR vs MAJOR).
    assert int(match.group("major")) >= 0
    assert int(match.group("minor")) >= 0
    assert int(match.group("patch")) >= 0


def test_existing_check_argv_and_exit_code_contract_is_stable(*, tmp_path: Path) -> None:
    """A shared check honors its documented argv + exit-code contract.

    This is the consumer-observable CLI surface a MAJOR bump would change: the
    check accepts `python -m livespec_dev_tooling.checks.<slug>` (no required
    positional argument) and exits `0` against a clean consumer tree. A
    backwards-incompatible argv change (e.g. a new required positional) would
    break this invocation and is what ships as a MAJOR bump.
    """
    (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\nsource_trees = []\n", encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, "-m", "livespec_dev_tooling.checks.no_inheritance"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"the documented argv contract (no required positional) must exit 0 on a "
        f"clean tree; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
