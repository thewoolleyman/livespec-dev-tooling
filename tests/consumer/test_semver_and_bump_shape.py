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

The check is invoked IN-PROCESS. `_run_no_inheritance` resolves it by
module name (`importlib.import_module`), chdirs into the fixture with
`monkeypatch.chdir`, calls `main()`, and reads the output off `capsys`.
A consumer reaches the SAME `main()` whether it names the module via
`python -m` or imports it, so the consumer-observable contract is
unchanged. That matters most here, because the argv surface is the thing
under test: the documented contract is that the check takes no required
positional, and calling `main()` with no arguments is exactly that
contract expressed in-process — a newly-required positional (the
backwards-incompatible change that would ship as a MAJOR bump) breaks
this call just as it would break the `python -m` invocation. The
assertion target is untouched: the same int exit code, still `0` on a
clean tree. Running in-process also removes the
`COVERAGE_PROCESS_START`-instrumented child, so there is no `.coverage.*`
write race under the parallel dispatcher, and the test is faster.

The `git` spawn in `_git` STAYS, which is why this file keeps its
`subprocess_spawn_allowlist` entry in `pyproject.toml`. The rerouted
checks derive their file universe from the git index
(`config.resolve_check_universe`), so the fixture must be a real git
working tree — that spawn is the behaviour being produced, not an
implementation detail to be replaced. Its hardcoded 3-key env (`HOME`,
`GIT_CONFIG_GLOBAL`, `PATH`) keeps `COVERAGE_PROCESS_START` and
`COV_CORE_*` out of that child, so the surviving spawn starts no
coverage writer.
"""

from __future__ import annotations

import importlib
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# The shared check whose argv surface this file pins, named exactly as a
# consumer names it in `python -m livespec_dev_tooling.checks.no_inheritance`.
_CHECK_MODULE = "livespec_dev_tooling.checks.no_inheritance"


class _CheckRun(NamedTuple):
    """The three `CompletedProcess` fields the assertions read, in-process."""

    returncode: int
    stdout: str
    stderr: str


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


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    The rerouted checks derive their file universe from the git index
    (`config.resolve_check_universe`), so the consumer fixture must be a
    real git working tree. `git` is not a Python spawn, so it is allowed;
    the hardcoded env keeps `COVERAGE_PROCESS_START` out of this child.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


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


def _run_no_inheritance(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _CheckRun:
    """Invoke the shared check under its documented no-argument contract.

    A consumer names the check by MODULE NAME, so this resolves it by
    module name too: `importlib.import_module` reaches the same
    package-provided module `python -m
    livespec_dev_tooling.checks.no_inheritance` would, and calls the same
    `main()`. Calling `main()` with no arguments is the in-process
    expression of the argv contract this test pins — a required
    positional would make this call fail exactly as it would break the
    `python -m` invocation.
    """
    module = importlib.import_module(_CHECK_MODULE)
    monkeypatch.chdir(cwd)

    returncode = module.main()

    captured = capsys.readouterr()
    return _CheckRun(returncode=returncode, stdout=captured.out, stderr=captured.err)


def test_existing_check_argv_and_exit_code_contract_is_stable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])

    result = _run_no_inheritance(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"the documented argv contract (no required positional) must exit 0 on a "
        f"clean tree; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
