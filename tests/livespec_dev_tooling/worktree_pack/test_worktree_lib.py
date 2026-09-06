"""Behaviour tests for the pack member `worktree_pack/worktree-lib.sh` — `create`.

Scope is the pack-provisioning leg of `create`, and it exists because that
leg used to make the PRIMARY checkout the authority on a new worktree's pack
bytes (livespec-dev-tooling-ov9o, absorbed by livespec-dev-tooling-os6wd3).
`worktree_provision_pack_from_primary` copied whatever version the primary
last installed and REFUSED — `BLOCKED — missing …` — when the primary was
incomplete. Measured 2026-09-06 in a real clone, the primary was missing
`check-no-workflow-edits.sh` and carried a `worktree-lib.sh` that differed
from the pinned package, so `just worktree-create` refused outright; and
because the `worktree-pack` bootstrap row targets the INVOKED worktree by
design, `just bootstrap` from a linked worktree never repairs the primary.
A worktree created across a pin bump was therefore born failing the pack's
own byte-verification, or not born at all.

The contract asserted here is the inverted one: `create` materializes the
pack from the PACKAGE the new worktree itself resolves, copy-from-primary
survives only as a degraded fallback, and a stale or partial primary never
blocks creation.

Every case builds a throwaway repository with a bare `origin` whose
advertised default branch is `master` (so `refs/remotes/origin/HEAD`
resolves exactly as it does in a real clone), damages the primary's pack in
both ways at once, and runs the canonical body the way the
`just worktree-create` recipe does. The only subprocesses are `git`
(fixture setup), `bash` (the script under test) and the from-package
installer the script invokes through its override hook; nothing touches the
network, the fleet ledger, or the developer's own repositories. `HOME`, the
git env family and `COVERAGE_PROCESS_START` / `COV_CORE_*` are scrubbed so
the children are hermetic and never self-instrument under `pytest --cov`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_WORKTREE_LIB_BODY,
    WORKTREE_PACK_FILES,
)

__all__: list[str] = []

_SCRIPT = "worktree-lib.sh"
_BRANCH = "feature/pack-drift"
# The primary's two injected defects, one of each kind the old refusal
# conflated: PARTIAL (a pack file the primary never installed) and STALE (a
# pack file whose bytes no longer match the pinned package).
_ABSENT_FROM_PRIMARY = "check-no-workflow-edits.sh"
_DRIFTED_IN_PRIMARY = "branch-protection.sh"
_DRIFT_MARKER = "# drift from the pinned package\n"

# The repository root that carries the `livespec_dev_tooling` package, handed
# to the from-package installer child as its `PYTHONPATH`.
_PACKAGE_PARENT = Path(__file__).resolve().parents[3]

# git sets these in a hook's environment when it fires inside a worktree;
# under a lefthook pre-commit they leak in from the surrounding repo.
# Scrubbing them confines every git invocation to the tmp_path fixture.
_GIT_ENV_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)
# The script's own overridable inputs. A developer running the suite with
# either exported would otherwise steer the code under test.
_LIB_ENV_VARS: tuple[str, ...] = (
    "WORKTREE_ROOT",
    "WORKTREE_HYDRATE_HOOK",
    "WORKTREE_PACK_INSTALL_HOOK",
)


def _child_env(*, home: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in (*_GIT_ENV_VARS, *_LIB_ENV_VARS, "COVERAGE_PROCESS_START"):
        _ = env.pop(name, None)
    for name in [key for key in env if key.startswith("COV_CORE_")]:
        _ = env.pop(name, None)
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["XDG_STATE_HOME"] = str(home / "state")
    env["PYTHONPATH"] = str(_PACKAGE_PARENT)
    return env


def _run_git(*, args: list[str], cwd: Path, env: dict[str, str]) -> None:
    _ = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=True, capture_output=True, text=True
    )


def _write_pack(*, root: Path) -> None:
    """Materialize the canonical pack under `<root>/dev-tooling/`.

    Written from `WORKTREE_PACK_FILES` directly rather than by invoking the
    installer: the primary side of this fixture is the thing under suspicion,
    so it must not be produced by the same code path the assertions trust.
    """
    pack_dir = root / "dev-tooling"
    pack_dir.mkdir(parents=True, exist_ok=True)
    for pack_file in WORKTREE_PACK_FILES:
        path = pack_dir / pack_file.name
        _ = path.write_text(pack_file.body, encoding="utf-8")
        path.chmod(0o755 if pack_file.executable else 0o644)


def _damage_primary_pack(*, primary: Path) -> None:
    """Make the primary's pack PARTIAL and STALE at the same time."""
    pack_dir = primary / "dev-tooling"
    (pack_dir / _ABSENT_FROM_PRIMARY).unlink()
    drifted = pack_dir / _DRIFTED_IN_PRIMARY
    _ = drifted.write_text(drifted.read_text(encoding="utf-8") + _DRIFT_MARKER, encoding="utf-8")


@pytest.fixture
def damaged_primary(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A clone with a bare `origin` whose installed pack is partial AND stale."""
    env = _child_env(home=tmp_path / "home")
    primary = tmp_path / "primary"
    primary.mkdir()
    _run_git(args=["init", "--quiet", "--initial-branch=master"], cwd=primary, env=env)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=primary, env=env)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=primary, env=env)
    _ = (primary / "README.md").write_text("# fixture\n", encoding="utf-8")
    _run_git(args=["add", "--all"], cwd=primary, env=env)
    _run_git(args=["commit", "--quiet", "-m", "base"], cwd=primary, env=env)

    origin = tmp_path / "origin.git"
    _run_git(args=["init", "--quiet", "--bare", str(origin)], cwd=tmp_path, env=env)
    _run_git(args=["remote", "add", "origin", str(origin)], cwd=primary, env=env)
    _run_git(args=["push", "--quiet", "-u", "origin", "master"], cwd=primary, env=env)
    _run_git(args=["remote", "set-head", "origin", "master"], cwd=primary, env=env)

    _write_pack(root=primary)
    _damage_primary_pack(primary=primary)

    env["WORKTREE_ROOT"] = str(tmp_path / "worktrees")
    return primary, env


def _run_create(*, primary: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run `worktree-lib.sh create <branch>` exactly as the recipe does."""
    return subprocess.run(
        ["bash", str(Path("dev-tooling") / _SCRIPT), "create", _BRANCH],
        cwd=str(primary),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _created_pack_dir(*, env: dict[str, str]) -> Path:
    return Path(env["WORKTREE_ROOT"]) / _BRANCH / "dev-tooling"


def test_create_installs_the_package_pack_over_a_partial_and_stale_primary(
    *, damaged_primary: tuple[Path, dict[str, str]]
) -> None:
    """The new worktree's pack is the PACKAGE's bytes, not the primary's.

    This is the whole defect in one assertion: the primary is missing one
    pack file and carries a drifted copy of another, and the worktree
    `create` produces must still be byte-identical to the pinned package —
    otherwise a worktree branched across a pin bump is born failing the pack
    arm of `check-primary-checkout-commit-refuse-hook-installed`.
    """
    primary, env = damaged_primary
    env["WORKTREE_PACK_INSTALL_HOOK"] = (
        f"{sys.executable} -m livespec_dev_tooling.install_worktree_pack"
    )

    completed = _run_create(primary=primary, env=env)

    assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    pack_dir = _created_pack_dir(env=env)
    for pack_file in WORKTREE_PACK_FILES:
        path = pack_dir / pack_file.name
        assert path.read_text(encoding="utf-8") == pack_file.body, pack_file.name
        assert os.access(path, os.X_OK) is pack_file.executable, pack_file.name


def test_create_does_not_block_on_a_partial_primary_when_the_package_is_unreachable(
    *, damaged_primary: tuple[Path, dict[str, str]]
) -> None:
    """With no from-package installer, `create` degrades — it never refuses.

    The old leg treated a primary missing one pack file as a hard `BLOCKED`,
    which is how a stale primary became a wall in front of every new
    worktree. The absent file is now reported as an informational note beside
    a best-effort copy, and creation still succeeds.
    """
    primary, env = damaged_primary
    env["WORKTREE_PACK_INSTALL_HOOK"] = "false"

    completed = _run_create(primary=primary, env=env)

    assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    output = completed.stdout + completed.stderr
    assert "BLOCKED" not in output, output
    assert _ABSENT_FROM_PRIMARY in output, output
    pack_dir = _created_pack_dir(env=env)
    assert not (pack_dir / _ABSENT_FROM_PRIMARY).exists()
    for pack_file in WORKTREE_PACK_FILES:
        if pack_file.name == _ABSENT_FROM_PRIMARY:
            continue
        assert (pack_dir / pack_file.name).is_file(), pack_file.name


def test_canonical_body_no_longer_refuses_on_a_partial_primary() -> None:
    """The refusal the defect was made of is gone from the canonical source."""
    assert "BLOCKED — missing" not in CANONICAL_WORKTREE_LIB_BODY
