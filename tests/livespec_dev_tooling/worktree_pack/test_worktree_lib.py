"""Behaviour tests for the pack member `worktree_pack/worktree-lib.sh`.

Two verbs are covered, each because it carried a defect that made it fail in
the direction that looks like nothing being wrong: `create` (the
pack-provisioning leg) and `reap` — twice over, once for the merged-ness
discriminator and once for the safety gates that decide what `reap` must
leave alone whatever that discriminator says.

`reap` — the merged-ness discriminator (livespec-dev-tooling-jtrt.2)
-------------------------------------------------------------------
`reap` judged merged-ness by ANCESTRY alone
(`git merge-base --is-ancestor <wt-head> <base>`). On a rebase-merge-only
fleet that test can only ever answer NO: the merge REWRITES the branch's
commits, so a landed branch's tip is never an ancestor of the base. Every
landed worktree therefore printed `SKIP … branch not merged` and the reaper
reaped nothing — livespec-overseer's AGENTS.md recorded it as "essentially
never firing" — while the worktrees it declined to remove accumulated toward
the 4096-byte stdio boundary that takes `create` and `reap` out together.

The discriminator is now ancestry-then-patch-id (`git cherry`). The landed
case here is built on a REBASED land, never a fast-forward: a fast-forward
leaves ancestry intact, so it would pass against the unfixed code and prove
nothing, and `_assert_land_was_rebased` makes that degradation loud rather
than silent. `test_reap_still_skips_a_genuinely_unmerged_worktree` is the
negative control — a reaper that removes everything is the same defect
inverted, and this one deletes work.

`reap` — the liveness and factory-ownership gates (livespec-dev-tooling-7i2z5j)
-------------------------------------------------------------------------------
The discriminator above decides whether a worktree is FINISHED. It says
nothing about whether anyone is still USING it, and `reap` had no test that
did. A Fabro factory source checkout defeats the merged-ness gate by
construction — the factory creates `fabro-source-<id>` AT master, so ancestry
always reads it as merged and `--force` is never even needed. Measured
2026-10-21 during a dev-host disk sweep, one dry run across the four
repositories carrying this pack listed NINE such worktrees as REMOVE, and
three were the working directory of a live `fabro run` at that moment; an
`--execute` would have deleted a running run's source tree from under it.

The gates are two, and the cases below assert them separately because neither
subsumes the other. LIVENESS fails safe: a holder is named by pid, and a scan
that cannot see the whole process table reports `cannot establish` and SKIPs
rather than guessing idle. FACTORY OWNERSHIP is decided by NAME, because a
run-board lookup needs an authenticated factory client a consuming host may
not hold and a paused run holds its tree with no process at all. Every case
runs `--force`, or asserts that `--execute --force` left the directory on
disk, since `--force` overriding one of these skips is the defect restated.

`create` — pack provisioning
----------------------------
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

The merged-ness `reap` cases run in DRY-RUN, which is the default: the
verdict is the whole assertion, and a test that actually removed worktrees
would be asking a destructive command to prove a read-only claim. The two
safety cases that assert a worktree SURVIVES are the exception and have to
be: "`--execute` would not have deleted it" is a claim only `--execute`
itself can settle, which is why they run it, in a throwaway tree, against a
directory whose continued existence IS the assertion.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from collections.abc import Iterator
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
    "WORKTREE_PROC_ROOT",
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


# ---------------------------------------------------------------------------
# `reap` — the merged-ness discriminator (livespec-dev-tooling-jtrt.2).
# ---------------------------------------------------------------------------

_LANDED_BRANCH = "feature/landed"
_UNMERGED_BRANCH = "feature/pending"
# A Fabro factory source checkout. The DIRECTORY name is what `reap` keys on,
# so it is spelled out rather than derived from the branch like the two above.
_FACTORY_BRANCH = "fabro/run/dcb603b8"
_FACTORY_DIR = "fabro-source-dcb603b8"
# The script's own seam for the process table its liveness probe reads.
_PROC_ROOT_ENV = "WORKTREE_PROC_ROOT"


def _git_succeeds(*, args: list[str], cwd: Path, env: dict[str, str]) -> bool:
    """Run git for its EXIT STATUS only — `_run_git` raises instead of reporting it."""
    completed = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=False, capture_output=True, text=True
    )
    return completed.returncode == 0


def _commit_file(*, repo: Path, env: dict[str, str], name: str, subject: str) -> None:
    _ = (repo / name).write_text(f"{name}\n", encoding="utf-8")
    _run_git(args=["add", name], cwd=repo, env=env)
    _run_git(args=["commit", "--quiet", "-m", subject], cwd=repo, env=env)


def _land_by_rebase(*, primary: Path, env: dict[str, str], branch: str) -> None:
    """Land `branch` onto `master` and push, the way a rebase-merge does.

    The branch's commits are REPLAYED onto master — new SHAs, byte-identical
    patches — while the worktree's own ref stays at its pre-rebase tip. That
    is the state a rebase-merge leaves behind, and the state ancestry
    misreads.
    """
    _run_git(args=["checkout", "--quiet", "-b", "landing", branch], cwd=primary, env=env)
    _run_git(args=["rebase", "--quiet", "master"], cwd=primary, env=env)
    _run_git(args=["checkout", "--quiet", "master"], cwd=primary, env=env)
    _run_git(args=["merge", "--quiet", "--ff-only", "landing"], cwd=primary, env=env)
    _run_git(args=["branch", "--quiet", "-D", "landing"], cwd=primary, env=env)
    _run_git(args=["push", "--quiet", "origin", "master"], cwd=primary, env=env)


def _assert_land_was_rebased(*, primary: Path, env: dict[str, str], branch: str) -> None:
    """Guard: the branch tip is NOT an ancestor of `origin/master`.

    A fixture that degraded into a fast-forward land would leave ancestry
    intact, and the landed-worktree assertion would then pass against the
    very code it exists to indict.
    """
    assert not _git_succeeds(
        args=["merge-base", "--is-ancestor", branch, "origin/master"], cwd=primary, env=env
    ), (
        f"fixture degraded: {branch} is still an ancestor of origin/master, so the "
        f"land was a fast-forward rather than a rebase and would be judged merged "
        f"by ancestry alone"
    )


@pytest.fixture
def reap_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A primary with three clean secondary worktrees, one per `reap` verdict.

    Two feature worktrees, one rebase-landed and one unmerged: both are ahead
    of `origin/master` by ancestry, so the pre-fix reaper skipped both, and
    only the patch-id leg can tell them apart.

    The third is a `fabro-source-<id>` factory source checkout, branched at
    master AFTER the land so its head IS `origin/master`. That is the real
    shape of the defect this fixture exists to pin: the merged-ness gate reads
    it as merged by plain ancestry, so nothing but the factory-ownership gate
    stands between it and removal.
    """
    env = _child_env(home=tmp_path / "home")
    primary = tmp_path / "primary"
    primary.mkdir()
    _run_git(args=["init", "--quiet", "--initial-branch=master"], cwd=primary, env=env)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=primary, env=env)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=primary, env=env)
    _commit_file(repo=primary, env=env, name="README.md", subject="base")

    origin = tmp_path / "origin.git"
    _run_git(args=["init", "--quiet", "--bare", str(origin)], cwd=tmp_path, env=env)
    _run_git(args=["remote", "add", "origin", str(origin)], cwd=primary, env=env)
    _run_git(args=["push", "--quiet", "-u", "origin", "master"], cwd=primary, env=env)
    _run_git(args=["remote", "set-head", "origin", "master"], cwd=primary, env=env)

    worktrees = tmp_path / "worktrees"
    for branch in (_LANDED_BRANCH, _UNMERGED_BRANCH):
        path = worktrees / branch.replace("/", "_")
        _run_git(
            args=["worktree", "add", "--quiet", "-b", branch, str(path), "master"],
            cwd=primary,
            env=env,
        )
        _commit_file(
            repo=path,
            env=env,
            name=f"{branch.replace('/', '_')}.txt",
            subject=f"work on {branch}",
        )

    # An unrelated commit on master FIRST, so the land below must rebase.
    _commit_file(repo=primary, env=env, name="unrelated.txt", subject="unrelated master work")
    _run_git(args=["push", "--quiet", "origin", "master"], cwd=primary, env=env)
    _land_by_rebase(primary=primary, env=env, branch=_LANDED_BRANCH)
    _assert_land_was_rebased(primary=primary, env=env, branch=_LANDED_BRANCH)

    _run_git(
        args=[
            "worktree",
            "add",
            "--quiet",
            "-b",
            _FACTORY_BRANCH,
            str(worktrees / _FACTORY_DIR),
            "master",
        ],
        cwd=primary,
        env=env,
    )
    return primary, env


def _worktree_dir(*, primary: Path, name: str) -> Path:
    """The on-disk path of a `reap_repo` secondary worktree."""
    return primary.parent / "worktrees" / name


def _landed_dir(*, primary: Path) -> Path:
    return _worktree_dir(primary=primary, name=_LANDED_BRANCH.replace("/", "_"))


def _complete_proc_root(*, primary: Path) -> str:
    """A process table the liveness probe can read WHOLE, holding no worktree.

    Real `/proc` answers the completeness question differently depending on
    whether the invoking user may inspect every process on the host: a scan
    denied one `cwd`/`fd` link reports `cannot establish` and SKIPs, by
    design. Pinning the merged-ness and factory-ownership cases to this
    fixture keeps their verdicts about the gate under test instead of about
    who is running the suite. One entry for this very pytest process — a
    readable `cwd` link pointing at the tmp root, which contains the
    worktrees but is not under any of them, and a readable empty `fd`
    directory — is a COMPLETE table with no holders.

    The live-holder cases below deliberately do NOT use it: a holder that is
    FOUND short-circuits completeness, so real `/proc` answers those
    deterministically and proves the probe against the real thing.
    """
    entry = primary.parent / "proc-complete" / str(os.getpid())
    (entry / "fd").mkdir(parents=True)
    (entry / "cwd").symlink_to(primary.parent)
    return str(entry.parent)


def _run_reap(
    *,
    primary: Path,
    env: dict[str, str],
    proc_root: str | None,
    args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Run `worktree-lib.sh reap` as `just worktree-reap` does; DRY-RUN by default.

    `proc_root` is the process table the liveness probe reads. `None` leaves
    the script on the host's real `/proc`.
    """
    _write_pack(root=primary)
    child_env = dict(env)
    if proc_root is None:
        _ = child_env.pop(_PROC_ROOT_ENV, None)
    else:
        child_env[_PROC_ROOT_ENV] = proc_root
    return subprocess.run(
        ["bash", str(Path("dev-tooling") / _SCRIPT), "reap", *args],
        cwd=str(primary),
        env=child_env,
        check=False,
        capture_output=True,
        text=True,
    )


@contextlib.contextmanager
def _live_process(*, cwd: Path, open_file: Path | None = None) -> Iterator[int]:
    """Spawn a real long-lived process, yield its pid, and kill it on the way out.

    Both shapes of hold the contract names, from one helper. `cwd` becomes the
    child's working directory, which is what `/proc/<pid>/cwd` reports and
    what `subprocess` has already applied by the time `Popen` returns (the
    parent reads the exec error pipe to EOF, so a returned handle means chdir
    and exec both happened).

    `open_file`, when given, is opened HERE and inherited as the child's
    stdin, then closed in this process — so the yielded pid is the ONLY holder
    of that descriptor and there is nothing to poll for. A `tail -f` would
    have opened the file asynchronously, after exec, which is a race the
    assertion would then have blamed on the probe.
    """
    handle = open_file.open("rb") if open_file is not None else None
    try:
        process = subprocess.Popen(
            ["sleep", "300"],
            cwd=str(cwd),
            stdin=handle,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        if handle is not None:
            handle.close()
    try:
        yield process.pid
    finally:
        process.kill()
        _ = process.wait()


def _verdict_line(*, output: str, branch: str) -> str:
    lines = [line for line in output.splitlines() if f"[{branch}]" in line]
    assert len(lines) == 1, f"expected exactly one reap verdict for {branch}; got {lines!r}"
    return lines[0]


def test_reap_removes_a_worktree_whose_branch_landed_by_rebase(
    *, reap_repo: tuple[Path, dict[str, str]]
) -> None:
    """A rebase-landed worktree is REMOVE, not SKIP — the defect leg.

    Under ancestry alone this printed `SKIP … branch not merged into
    origin/master` for a branch whose every commit was already on
    origin/master, which is why the reaper never fired.
    """
    primary, env = reap_repo

    completed = _run_reap(primary=primary, env=env, proc_root=_complete_proc_root(primary=primary))

    assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    verdict = _verdict_line(output=completed.stdout, branch=_LANDED_BRANCH)
    assert verdict.strip().startswith("REMOVE"), verdict
    # The verdict names WHICH discriminator answered, so an operator reading
    # a removal knows whether it rests on ancestry or on patch-id.
    assert "patch-id equivalent" in verdict, verdict


def test_reap_still_skips_a_genuinely_unmerged_worktree(
    *, reap_repo: tuple[Path, dict[str, str]]
) -> None:
    """The NEGATIVE CONTROL: unlanded work is still skipped, in the same tree.

    A reaper that removed everything would be the same defect inverted, and
    this one deletes work. Asserting both verdicts against ONE repository is
    what rules out a fix that merely moved the threshold.
    """
    primary, env = reap_repo

    completed = _run_reap(primary=primary, env=env, proc_root=_complete_proc_root(primary=primary))

    assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    verdict = _verdict_line(output=completed.stdout, branch=_UNMERGED_BRANCH)
    assert verdict.strip().startswith("SKIP"), verdict
    assert "not merged into origin/master" in verdict, verdict


def test_canonical_body_judges_merged_ness_by_more_than_ancestry() -> None:
    """The ancestry-only test is gone from the canonical source, not just from a copy.

    The consumer-side `dev-tooling/worktree-lib.sh` is gitignored and
    byte-verified against this package constant, so a fix that did not land
    HERE would be reverted in every consumer.
    """
    assert "git cherry" in CANONICAL_WORKTREE_LIB_BODY


# ---------------------------------------------------------------------------
# `reap` safety — liveness and factory ownership (livespec-dev-tooling-7i2z5j).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_reap_skips_a_merged_worktree_that_is_the_cwd_of_a_live_process(
    *, reap_repo: tuple[Path, dict[str, str]]
) -> None:
    """A holder's PID is the verdict, on the same worktree that is otherwise REMOVE.

    `test_reap_removes_a_worktree_whose_branch_landed_by_rebase` asserts
    REMOVE for this very worktree with nothing holding it, so the only
    difference between the two verdicts is the live process — which is what
    makes this a test of the liveness gate rather than of the merged-ness one.
    """
    primary, env = reap_repo
    landed = _landed_dir(primary=primary)

    with _live_process(cwd=landed) as pid:
        completed = _run_reap(primary=primary, env=env, proc_root=None, args=("--force",))

        assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        verdict = _verdict_line(output=completed.stdout, branch=_LANDED_BRANCH)
        assert verdict.strip().startswith("SKIP"), verdict
        assert str(pid) in verdict, verdict


@pytest.mark.integration
def test_reap_execute_force_leaves_a_worktree_a_live_process_is_running_in(
    *, reap_repo: tuple[Path, dict[str, str]]
) -> None:
    """`--execute --force` and a live holder: the directory survives.

    The dry-run verdict above is only a claim about what `--execute` would do.
    This is the claim itself, and it is asserted with `--force` because
    `--force` overriding the liveness skip is the original defect restated:
    the sweep that found this listed nine factory worktrees as REMOVE, three
    of them the cwd of a live `fabro run`.
    """
    primary, env = reap_repo
    landed = _landed_dir(primary=primary)

    with _live_process(cwd=landed) as _pid:
        completed = _run_reap(
            primary=primary, env=env, proc_root=None, args=("--execute", "--force")
        )

        assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        assert landed.is_dir(), completed.stdout
        assert (landed / ".git").exists(), completed.stdout


@pytest.mark.integration
def test_reap_skips_a_merged_worktree_holding_an_open_file_of_a_live_process(
    *, reap_repo: tuple[Path, dict[str, str]]
) -> None:
    """An open DESCRIPTOR counts as a hold, not only a working directory.

    The holder here runs OUTSIDE the worktree, so a cwd-only probe would read
    the tree as idle while a live process is reading a file out of it. That is
    the case a `git worktree remove --force` would pull out from under a
    build, a test run, or a factory run writing its own source tree.
    """
    primary, env = reap_repo
    landed = _landed_dir(primary=primary)
    held_file = landed / f"{_LANDED_BRANCH.replace('/', '_')}.txt"
    assert held_file.is_file(), "fixture: the landed worktree's committed file is missing"

    with _live_process(cwd=primary.parent, open_file=held_file) as pid:
        completed = _run_reap(primary=primary, env=env, proc_root=None, args=("--force",))

        assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        verdict = _verdict_line(output=completed.stdout, branch=_LANDED_BRANCH)
        assert verdict.strip().startswith("SKIP"), verdict
        assert str(pid) in verdict, verdict


@pytest.mark.integration
def test_reap_skips_a_merged_worktree_whose_liveness_it_cannot_establish(
    *, reap_repo: tuple[Path, dict[str, str]]
) -> None:
    """No readable process table means SKIP — the fail-safe direction.

    An unobservable process table is the common case, not an exotic one: a
    host with no `/proc`, or an unprivileged scan denied another user's
    `cwd`/`fd` links. Reading either as "no holder" would be a reaper
    certifying absence from evidence it was refused, so the clause requires
    SKIP, never REMOVE. `--force` is passed to prove it does not reach here.
    """
    primary, env = reap_repo

    completed = _run_reap(
        primary=primary,
        env=env,
        proc_root=str(primary.parent / "no-process-table"),
        args=("--force",),
    )

    assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    verdict = _verdict_line(output=completed.stdout, branch=_LANDED_BRANCH)
    assert verdict.strip().startswith("SKIP"), verdict
    assert "cannot establish" in verdict, verdict


@pytest.mark.integration
def test_reap_skips_an_unheld_merged_factory_source_worktree(
    *, reap_repo: tuple[Path, dict[str, str]]
) -> None:
    """`fabro-source-<id>` is skipped by NAME, with no live process anywhere.

    The process table here is complete and holder-free, which is the whole
    point: a paused or blocked factory run keeps its source tree with nothing
    running in it, so a liveness test alone would hand it to the reaper. The
    worktree is branched at master, so the merged-ness gate passes it by plain
    ancestry and the name is the only thing left standing in the way.
    """
    primary, env = reap_repo

    completed = _run_reap(
        primary=primary,
        env=env,
        proc_root=_complete_proc_root(primary=primary),
        args=("--force",),
    )

    assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    verdict = _verdict_line(output=completed.stdout, branch=_FACTORY_BRANCH)
    assert verdict.strip().startswith("SKIP"), verdict
    assert "factory-owned" in verdict, verdict


@pytest.mark.integration
def test_reap_execute_force_leaves_an_unheld_factory_source_worktree(
    *, reap_repo: tuple[Path, dict[str, str]]
) -> None:
    """`--execute --force` on a holder-free factory worktree: it stays on disk.

    The negative control rides along in the same run: the unmerged feature
    worktree IS removed under `--force`, so the surviving factory tree is the
    name gate holding rather than the whole command declining to act.
    """
    primary, env = reap_repo
    factory = _worktree_dir(primary=primary, name=_FACTORY_DIR)
    unmerged = _worktree_dir(primary=primary, name=_UNMERGED_BRANCH.replace("/", "_"))

    completed = _run_reap(
        primary=primary,
        env=env,
        proc_root=_complete_proc_root(primary=primary),
        args=("--execute", "--force"),
    )

    assert completed.returncode == 0, f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    assert factory.is_dir(), completed.stdout
    assert (factory / ".git").exists(), completed.stdout
    assert not unmerged.exists(), (
        f"control failed: --force removed nothing at all, so the factory tree's "
        f"survival proves nothing. stdout={completed.stdout!r}"
    )


def test_canonical_body_carries_the_liveness_and_factory_ownership_gates() -> None:
    """Both gates are in the canonical source, not only in an installed copy.

    `dev-tooling/worktree-lib.sh` is gitignored in every consumer and
    byte-verified against this package constant, so a fix that did not land
    HERE is reverted the next time `install-worktree-pack` runs.
    """
    assert "fabro-source-?*" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_reap_holder_pid" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_reap_scan_gap" in CANONICAL_WORKTREE_LIB_BODY
