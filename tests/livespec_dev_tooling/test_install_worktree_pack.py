"""Outside-in test for `livespec_dev_tooling/install_worktree_pack.py`.

The installer writes the canonical worktree-discipline pack — the four
executable scripts `worktree-lib.sh`, `branch-protection.sh`, `gate-run.sh`
and `check-no-workflow-edits.sh` (the fleet's one workflow-edit guard,
livespec-dev-tooling-fy02) plus the non-executable justfile fragments
`worktree.just` and `branch-protection.just` — into a governed repo's
`dev-tooling/` directory, resolving the target via `git rev-parse
--show-toplevel` so the pack lands at the work-tree root of wherever the
installer runs (the pack files are UNTRACKED-AND-INSTALLED, gitignored and
materialized by `just install-worktree-pack`). The `.sh` scripts are made
executable (the recipes invoke them directly); the `.just` fragments are
`import`ed by the consumer root justfile, never run directly, so they are
installed non-executable. The canonical bodies ship as wheel-safe
package-data resources read once at import.

The installer is exercised IN-PROCESS (`main()` with `monkeypatch.chdir`) —
no Python subprocess spawn (this test is not on the
`subprocess_spawn_allowlist`); the only subprocesses are `git` for repo
setup.
"""

from __future__ import annotations

import errno
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling import install_worktree_pack
from livespec_dev_tooling.checks._primary_checkout_unreadable import CheckInputUnreadable
from livespec_dev_tooling.checks._primary_checkout_worktree_pack import (
    inspect_worktree_pack,
)
from livespec_dev_tooling.fleet._context import RowFinding, RowPass
from livespec_dev_tooling.fleet._contract_local_rows import (
    LOCAL_OBLIGATION_ROWS,
    LocalObligationRow,
)
from livespec_dev_tooling.fleet._local_context import CommandOutcome, LocalContext
from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_BRANCH_PROTECTION_BODY,
    CANONICAL_BRANCH_PROTECTION_JUST_BODY,
    CANONICAL_GATE_RUN_BODY,
    CANONICAL_WORKTREE_JUST_BODY,
    CANONICAL_WORKTREE_LIB_BODY,
    WORKTREE_PACK_FILES,
    main,
)

__all__: list[str] = []


# The package-data directory the installer reads its canonical bodies from,
# resolved the same `__file__`-relative way the installer resolves it. The
# seventh member is asserted THROUGH THIS PATH rather than through a
# `CANONICAL_*` import so the Red leg fails on the assertion that the member
# is not installed — an import of a not-yet-existing constant would fail at
# collection and prove only that a symbol is unimportable.
_PACK_DATA_DIR = Path(install_worktree_pack.__file__).resolve().parent / "worktree_pack"
_NO_WORKFLOW_EDITS_NAME = "check-no-workflow-edits.sh"

# The pack's executable script basenames paired with their canonical bodies.
_PACK_SCRIPT_EXPECTED: tuple[tuple[str, str], ...] = (
    ("worktree-lib.sh", CANONICAL_WORKTREE_LIB_BODY),
    ("branch-protection.sh", CANONICAL_BRANCH_PROTECTION_BODY),
    ("gate-run.sh", CANONICAL_GATE_RUN_BODY),
)

# Every pack file basename paired with its canonical body.
_PACK_EXPECTED: tuple[tuple[str, str], ...] = (
    *_PACK_SCRIPT_EXPECTED,
    ("worktree.just", CANONICAL_WORKTREE_JUST_BODY),
    ("branch-protection.just", CANONICAL_BRANCH_PROTECTION_JUST_BODY),
)

# git sets these in a hook's environment when it fires inside a worktree;
# when this suite runs under a lefthook pre-commit they also leak in from
# the surrounding repo. Scrubbing them confines every git invocation to the
# tmp_path fixture.
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


def _scrub_git_env(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every GIT_* passthrough var from the process environment."""
    for var in _GIT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _pack_failures(*, repo_root: Path) -> list[tuple[str, str]]:
    """The arm's VIOLATIONS, asserting first that it answered at all.

    Every caller below is asking "what does the arm say about this pack",
    which is a question the arm can only answer when every read succeeded.
    Unwrapping through this helper means a read failure can never be read as
    "no violations" by a test — it fails the assertion here instead, naming
    the path.
    """
    inspected = inspect_worktree_pack(repo_root=repo_root)
    assert isinstance(inspected, IOSuccess), f"arm did not answer: {inspected}"
    return unsafe_perform_io(inspected.unwrap())


def _make_read_fail(*, monkeypatch: pytest.MonkeyPatch, target: Path, detail: str) -> None:
    """Make exactly `target`'s byte read raise `OSError`; leave every other read real.

    ⛔ NOT `chmod 000`. This suite runs as ROOT, where a mode-based fixture is
    a lie — every read still succeeds, the assertion never fires, and the test
    passes proving nothing. Patching the read itself is the only instrument
    here that can actually produce the negative.

    The condition is not hypothetical for real operators even though it is
    unconstructible for this suite: the fleet's checks run as a non-root user
    in CI and in Fabro sandboxes, where `EACCES` is ordinary, and a pack file
    replaced between the `is_file()` probe and the read is reachable whenever
    `just bootstrap` runs concurrently.
    """
    real_read_bytes = Path.read_bytes

    def _read_bytes(self: Path) -> bytes:
        if self == target:
            raise OSError(errno.EIO, detail)
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _read_bytes)


def _run_git(*, args: list[str], cwd: Path) -> None:
    """Run a git command in `cwd`, raising on failure."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _run_git_capture(*, args: list[str], cwd: Path) -> str:
    """Run a git command in `cwd`, returning stdout."""
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_repo(*, repo: Path) -> None:
    """Initialize a git repo at `repo` with a local identity."""
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(args=["init", "--quiet"], cwd=repo)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=repo)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=repo)


def _init_bare_remote(*, remote: Path) -> None:
    """Initialize a bare remote with `master` as its advertised default."""
    _run_git(args=["init", "--bare", "--quiet", str(remote)], cwd=remote.parent)
    _run_git(args=["symbolic-ref", "HEAD", "refs/heads/master"], cwd=remote)


def _init_primary_with_worktree(*, tmp_path: Path) -> tuple[Path, Path]:
    """Create a primary checkout plus one linked worktree; return both paths."""
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    seed = primary / "seed.md"
    _ = seed.write_text("# seed\n", encoding="utf-8")
    _run_git(args=["add", "seed.md"], cwd=primary)
    _run_git(args=["commit", "--quiet", "-m", "fixture commit"], cwd=primary)
    _run_git(args=["branch", "feature/wip"], cwd=primary)
    worktree = tmp_path / "wt-feature"
    _run_git(args=["worktree", "add", str(worktree), "feature/wip"], cwd=primary)
    return primary, worktree


def _init_primary_with_remote(*, tmp_path: Path) -> Path:
    """Create a primary checkout whose origin has an advertised default branch.

    The fixture carries a root justfile with the pack's two `import?` lines
    because that is what a WIRED governed repo looks like. Since A2 the
    verifier asserts discoverability as well as byte-identity: a pack whose
    fragments nothing imports is invisible to `just --list` and is its own
    failure mode, so a fixture without them would be asserting that an
    operator-broken repo is clean.
    """
    primary = tmp_path / "project"
    remote = tmp_path / "origin.git"
    _init_bare_remote(remote=remote)
    _init_repo(repo=primary)
    _ = (primary / "justfile").write_text(
        "import? 'dev-tooling/worktree.just'\nimport? 'dev-tooling/branch-protection.just'\n",
        encoding="utf-8",
    )
    seed = primary / "seed.md"
    _ = seed.write_text("# seed\n", encoding="utf-8")
    # The justfile is COMMITTED, not merely written: `worktree_create` checks
    # out a fresh branch, so an untracked justfile would not reach the created
    # worktree and the discoverability arm would fire there.
    _run_git(args=["add", "seed.md", "justfile"], cwd=primary)
    _run_git(args=["commit", "--quiet", "-m", "fixture commit"], cwd=primary)
    _run_git(args=["remote", "add", "origin", str(remote)], cwd=primary)
    _run_git(args=["push", "--quiet", "-u", "origin", "master"], cwd=primary)
    _run_git(args=["remote", "set-head", "origin", "--auto"], cwd=primary)
    return primary


def _run_worktree_create(
    *,
    primary: Path,
    branch: str,
    worktree_root: Path,
) -> None:
    """Invoke the canonical shell `worktree_create` function in `primary`."""
    script = primary / "dev-tooling" / "worktree-lib.sh"
    _ = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" && worktree_create "$2"',
            "bash",
            str(script),
            branch,
        ],
        cwd=str(primary),
        env={**os.environ, "WORKTREE_ROOT": str(worktree_root)},
        check=True,
        capture_output=True,
        text=True,
    )


def test_worktree_create_provisions_pack_from_primary(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh `worktree_create` worktrees receive the canonical pack before hydration."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = _init_primary_with_remote(tmp_path=tmp_path)
    monkeypatch.chdir(primary)
    assert main() == 0

    branch = "feature/pack-provisioned"
    worktree_root = tmp_path / "worktrees"
    _run_worktree_create(primary=primary, branch=branch, worktree_root=worktree_root)

    worktree = worktree_root / branch
    assert _run_git_capture(args=["rev-parse", "--show-toplevel"], cwd=worktree) == str(worktree)
    for name, body in _PACK_EXPECTED:
        installed = worktree / "dev-tooling" / name
        assert installed.is_file(), f"{name} not provisioned into created worktree"
        assert installed.read_text(encoding="utf-8") == body

    assert _pack_failures(repo_root=worktree) == []
    branch_check = subprocess.run(
        ["./dev-tooling/branch-protection.sh", "check"],
        cwd=str(worktree),
        check=False,
        capture_output=True,
        text=True,
    )
    assert branch_check.returncode == 0


def test_main_installs_both_pack_scripts(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` writes both canonical scripts to `dev-tooling/`, executable and byte-identical."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    rc = main()

    assert rc == 0
    pack_dir = primary / "dev-tooling"
    for name, body in _PACK_SCRIPT_EXPECTED:
        script = pack_dir / name
        assert script.is_file(), f"{name} not installed"
        assert os.access(script, os.X_OK), f"{name} not executable"
        assert script.read_text(encoding="utf-8") == body


def test_main_installs_check_no_workflow_edits_guard(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` installs the seventh member — the fleet's ONE workflow-edit guard.

    livespec-dev-tooling-fy02: one shared hard-block body with a
    ledger-verified human-authorization override, carried exactly like the
    other pack scripts — installed executable into `dev-tooling/`,
    byte-identical to the package-data source, and gitignored by the
    generated ignore file (which derives from the payload tuple, so the
    ignore rule follows the member automatically). The body markers lock
    the design's load-bearing surfaces: the CI-venue skip, the tracked
    declaration, the human-set approval label, the `bd` resolution — and
    the ABSENCE of every retired environment escape.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    assert main() == 0

    installed = primary / "dev-tooling" / _NO_WORKFLOW_EDITS_NAME
    assert installed.is_file(), f"{_NO_WORKFLOW_EDITS_NAME} not installed"
    assert os.access(installed, os.X_OK), f"{_NO_WORKFLOW_EDITS_NAME} not executable"
    canonical = _PACK_DATA_DIR / _NO_WORKFLOW_EDITS_NAME
    assert installed.read_bytes() == canonical.read_bytes()
    _run_git(
        args=["check-ignore", "--quiet", f"dev-tooling/{_NO_WORKFLOW_EDITS_NAME}"], cwd=primary
    )

    body = installed.read_text(encoding="utf-8")
    for marker in (
        "GITHUB_ACTIONS",
        ".livespec-workflow-edit-exemption",
        "approval:workflow-edit",
        ".beads/config.yaml",
        "LIVESPEC_BD_PATH",
        "BEADS_DOLT_PASSWORD",
    ):
        assert marker in body, f"{marker} missing from {_NO_WORKFLOW_EDITS_NAME}"
    for retired_escape in ("LIVESPEC_WORKFLOW_EDIT_BASE", "LIVESPEC_FACTORY_BASE_REF"):
        assert retired_escape not in body, f"{retired_escape} is a retired escape"
    assert body.endswith("\n")


def test_main_installs_worktree_just_fragment(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` writes `dev-tooling/worktree.just` NON-executable, carrying the four recipes.

    Unlike the two `.sh` scripts, the `worktree.just` recipe fragment is
    `import`ed by the consumer root justfile — never run directly — so it is
    installed without the executable bit. Its body carries the four canonical
    `worktree-*` lifecycle recipe stanzas, each a one-line pass-through onto
    `./dev-tooling/worktree-lib.sh`.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    rc = main()

    assert rc == 0
    fragment = primary / "dev-tooling" / "worktree.just"
    assert fragment.is_file(), "worktree.just not installed"
    assert not os.access(fragment, os.X_OK), "worktree.just must not be executable"
    content = fragment.read_text(encoding="utf-8")
    for recipe in ("worktree-create", "worktree-hydrate", "worktree-land", "worktree-reap"):
        assert recipe in content, f"{recipe} recipe stanza missing from worktree.just"
    assert "./dev-tooling/worktree-lib.sh create" in content


def test_main_installs_branch_protection_just_fragment(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` writes `dev-tooling/branch-protection.just` NON-executable, carrying the recipes.

    Like `worktree.just`, the `branch-protection.just` recipe fragment is
    `import`ed by the consumer root justfile — never run directly — so it is
    installed without the executable bit. Its body carries the two canonical
    branch-protection recipe stanzas (`protect-default-branch` /
    `check-branch-protection`), each a one-line pass-through onto
    `./dev-tooling/branch-protection.sh`.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    rc = main()

    assert rc == 0
    fragment = primary / "dev-tooling" / "branch-protection.just"
    assert fragment.is_file(), "branch-protection.just not installed"
    assert not os.access(fragment, os.X_OK), "branch-protection.just must not be executable"
    content = fragment.read_text(encoding="utf-8")
    for recipe in ("protect-default-branch", "check-branch-protection"):
        assert recipe in content, f"{recipe} recipe stanza missing from branch-protection.just"
    assert "./dev-tooling/branch-protection.sh apply" in content
    assert "./dev-tooling/branch-protection.sh check" in content


def test_main_from_worktree_installs_into_that_worktree_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invoked from a linked worktree, the pack lands at THAT worktree's `dev-tooling/`.

    Unlike the commit-refuse hooks (which target the shared common dir), the
    pack scripts are tracked files, so `git rev-parse --show-toplevel`
    resolves to the current worktree's own root — the install lands there,
    not in the primary checkout.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary, worktree = _init_primary_with_worktree(tmp_path=tmp_path)
    monkeypatch.chdir(worktree)

    rc = main()

    assert rc == 0
    for name, body in _PACK_SCRIPT_EXPECTED:
        installed = worktree / "dev-tooling" / name
        assert installed.is_file(), f"{name} not installed into worktree root"
        assert installed.read_text(encoding="utf-8") == body
        # The primary checkout is untouched (the pack is per-checkout tracked state).
        assert not (primary / "dev-tooling" / name).exists()


def test_main_is_idempotent(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running the installer overwrites with the identical canonical bodies."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    assert main() == 0
    first = (primary / "dev-tooling" / "worktree-lib.sh").read_text(encoding="utf-8")
    assert main() == 0
    second = (primary / "dev-tooling" / "worktree-lib.sh").read_text(encoding="utf-8")

    assert first == second == CANONICAL_WORKTREE_LIB_BODY


def test_main_gitignores_every_installed_pack_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh install into a clean clone leaves no untracked pack dirt."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    assert main() == 0

    installed = sorted(path.name for path in (primary / "dev-tooling").iterdir())
    assert installed, "installer wrote no pack files"
    for name in installed:
        _run_git(args=["check-ignore", "--quiet", f"dev-tooling/{name}"], cwd=primary)
    assert _run_git_capture(args=["status", "--short"], cwd=primary) == ""


def test_canonical_worktree_lib_body_carries_distinctive_markers() -> None:
    """Lock distinctive structural markers of the worktree-lib body.

    Guards against silent corruption or truncation of the embedded
    constant: the header, the load-bearing primary-vs-linked detection, and
    each of the four lifecycle verbs MUST be present.
    """
    assert "worktree-lib.sh — portable, ecosystem-neutral" in CANONICAL_WORKTREE_LIB_BODY
    assert "git rev-parse --git-common-dir" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_is_primary()" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_create()" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_hydrate()" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_land()" in CANONICAL_WORKTREE_LIB_BODY
    assert CANONICAL_WORKTREE_LIB_BODY.endswith("\n")


def test_canonical_worktree_lib_uses_from_package_hook_phrasing() -> None:
    """The canonical worktree-lib body carries the POST-CONVERGENCE from-package phrasing.

    The fleet's two pre-existing copies had drifted: core's template
    (blob cd21441) still describes the commit-refuse hook as the vendored
    `git-hook-wrapper.sh`, while `livespec-orchestrator-git-jsonl`'s copy
    (blob 94b8034) describes it as "installed from the shared
    livespec_dev_tooling package" — the correct phrasing now that the hook
    installs from-package and the vendored wrapper is retired. The canonical
    package-data body MUST be the from-package one, so it never references a
    file the convergence deletes. This locks that choice against a future
    re-sync from the (still-lagging) core template.
    """
    assert "installed from the shared" in CANONICAL_WORKTREE_LIB_BODY
    assert "livespec_dev_tooling package" in CANONICAL_WORKTREE_LIB_BODY
    assert "git-hook-wrapper.sh" not in CANONICAL_WORKTREE_LIB_BODY


def test_canonical_branch_protection_body_carries_distinctive_markers() -> None:
    """Lock distinctive structural markers of the branch-protection body."""
    assert "branch-protection.sh — the SERVER-SIDE mirror" in CANONICAL_BRANCH_PROTECTION_BODY
    assert "LIVESPEC_BRANCH_PROTECTION_CHECK" in CANONICAL_BRANCH_PROTECTION_BODY
    assert CANONICAL_BRANCH_PROTECTION_BODY.endswith("\n")


def test_main_leaves_unparseable_livespec_jsonc_untouched(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garbled JSONC is the config-integrity tooling's problem, not the installer's.

    The installer must neither crash nor diagnose a file it cannot parse — a
    document whose contents are unknown cannot be missing a declaration, and
    the config-integrity check already owns that diagnosis.

    ⛔ RENAMED from `..._unreadable_...`. The fixture below writes INVALID
    JSON, which is a file this run read perfectly and could not PARSE — a
    definitive fact about the document. It never made a file unreadable, so
    the old name described a condition no test here exercised.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    config = primary / ".livespec.jsonc"
    garbled = "{ this is not json at all ["
    _ = config.write_text(garbled, encoding="utf-8")
    monkeypatch.chdir(primary)

    assert main() == 0
    assert config.read_text(encoding="utf-8") == garbled


def _commit_governed_config_without_the_declaration(*, repo: Path) -> str:
    """Commit a governed `.livespec.jsonc` that carries no `worktree_discipline`.

    The fixture the two tests below share: the state 7 of 10 fleet repos were
    measured in on 2026-08-04 — a TRACKED, committed, splice-anchored config
    (its `{` alone on the first line) with the key absent. Returns the exact
    committed text so a caller can assert byte-identity after the install.
    """
    config = repo / ".livespec.jsonc"
    governed = '{\n  "template": "livespec"\n}\n'
    _ = config.write_text(governed, encoding="utf-8")
    _run_git(args=["add", ".livespec.jsonc"], cwd=repo)
    _run_git(args=["commit", "--quiet", "-m", "fixture: governed config"], cwd=repo)
    return governed


def test_main_leaves_no_tracked_modification_in_a_repo_lacking_the_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installer NEVER dirties a tracked file (livespec-dev-tooling-7ix8).

    🔴 The defect this closes. The installer used to SPLICE a
    `worktree_discipline` default into the governed, TRACKED `.livespec.jsonc`
    of every repo whose committed config lacked the key. Nothing commits that
    write, so `just bootstrap` — the prescribed first-touch setup step, which
    reaches the installer through the local reconcile's `worktree-pack` row —
    left the checkout dirty BY CONSTRUCTION and re-created the modification on
    every subsequent run. Measured across the fleet on 2026-08-04 it reproduced
    in 6 of 6 fresh worktrees, each with exactly one tracked modification:
    `.livespec.jsonc`.

    Why that consequence is worth a fix rather than a tolerance: a dirty SOURCE
    checkout makes the dispatcher's pre-clone push be refused and fall back to
    a snapshot base that exists nowhere on origin, after which publish dies
    with a MISLEADING GitHub rejection about creating `.github/workflows/*`
    without `workflows` permission. The sanctioned setup command was
    manufacturing the precondition the sanctioned dispatch preflight exists to
    clear, and the resulting failure presented as a permissions problem.

    It was also NON-CONFORMANT, not merely inconvenient:
    `SPECIFICATION/non-functional-requirements.md` already requires this
    installer to "write only files the repository ignores", and
    `.livespec.jsonc` is tracked.

    Runs the installer TWICE, as the acceptance criterion specifies, so a write
    that merely converged on a second pass could not pass this test either.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    governed = _commit_governed_config_without_the_declaration(repo=primary)
    monkeypatch.chdir(primary)

    assert main() == 0
    assert main() == 0

    dirty = _run_git_capture(args=["status", "--porcelain", "--untracked-files=no"], cwd=primary)
    assert dirty == "", f"install dirtied tracked files: {dirty}"
    assert (primary / ".livespec.jsonc").read_text(encoding="utf-8") == governed


def test_main_reports_an_absent_declaration_as_guidance(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dropping the WRITE must not drop the OBLIGATION — it becomes guidance.

    The spliced block existed to make the pack policy readable in config rather
    than folklore a new adopter discovers by tripping the verifier, and that
    goal is worth keeping: what was wrong is the CARRIER, not the intent. So
    the installer now DETECTS-AND-GUIDES the absence — the shape the
    beads-runtime prerequisite rows already use — carrying the EXACT
    copy-pasteable declaration line and the path to add it to, and touching
    nothing.

    Asserts the structured field rather than a substring of the rendered line:
    the log is JSON, so the declaration arrives escaped and a naive `in` check
    on the raw text would be looking for bytes the renderer never emits.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    _ = _commit_governed_config_without_the_declaration(repo=primary)
    monkeypatch.chdir(primary)

    assert main() == 0

    emitted = [
        json.loads(line)
        for line in capsys.readouterr().err.splitlines()
        if line.strip().startswith("{")
    ]
    guidance = [
        event
        for event in emitted
        if event.get("add") == '"worktree_discipline": { "pack": "required" }'
    ]
    assert len(guidance) == 1, f"expected exactly one guidance line, got: {emitted}"
    assert guidance[0]["path"] == str(primary / ".livespec.jsonc")


def test_inspect_treats_unparseable_config_as_ungoverned(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unparseable `.livespec.jsonc` must not turn the pack arm into a FAIL.

    Failing here would double-report one broken file: the config-integrity
    check already owns that diagnosis, and a second voice adds noise, not
    signal.

    ⛔ RENAMED from `..._unreadable_...` for the same reason as the installer
    test above: the fixture writes INVALID JSON. A document this run read and
    could not parse is a definitive fact and correctly stays on the success
    track; a document this run could not READ is not. Genuine unreadability is
    covered by `test_inspect_reports_an_unreadable_config_as_a_failure`, the
    only test here whose fixture makes a read fail.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    _ = (primary / ".livespec.jsonc").write_text("{ broken [", encoding="utf-8")

    assert _pack_failures(repo_root=primary) == []


def test_inspect_rejects_an_unknown_pack_policy_value(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unrecognized `pack` value is MALFORMED, never a silent opt-out.

    Fail-closed: a typo such as `"optionl"` must not read as "optional" and
    quietly disable the gate.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    _ = (primary / ".livespec.jsonc").write_text(
        '{\n  "worktree_discipline": {"pack": "optionl"}\n}\n', encoding="utf-8"
    )

    failures = _pack_failures(repo_root=primary)
    assert [mode for _name, mode in failures] == ["worktree_discipline_malformed"]


def _install_governed_pack(*, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give `repo_root` a governed config, a canonical pack and both imports.

    The baseline every byte-identity test below perturbs by exactly one file,
    so a reported failure can only be the perturbation.

    The pack is materialized by the REAL installer rather than by a
    hand-written member list: the verifier requires every member the
    installer ships, so a fixture that enumerated members by hand would fall
    out of step the moment the pack grew and report `worktree_pack_file_missing`
    for a baseline nobody perturbed. The config declares no
    `worktree_discipline`, which the installer REPORTS as guidance and never
    writes, so the fixture's config is exactly the text written here.
    """
    _ = (repo_root / ".livespec.jsonc").write_text('{"template": "livespec"}\n', encoding="utf-8")
    _ = (repo_root / "justfile").write_text(
        "import? 'dev-tooling/branch-protection.just'\nimport? 'dev-tooling/worktree.just'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo_root)
    assert main() == 0
    return repo_root / "dev-tooling"


def test_inspect_reports_no_failure_for_a_canonical_governed_pack(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The baseline the three perturbation tests below are measured against.

    Without it a perturbation test proves nothing: an assertion that some
    failure is reported would also pass if the fixture were broken in an
    unrelated way. This pins that the unperturbed fixture is CLEAN, so each
    perturbation below is the only thing that can have caused its finding.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    _ = _install_governed_pack(repo_root=primary, monkeypatch=monkeypatch)

    assert _pack_failures(repo_root=primary) == []


def test_inspect_reports_body_mismatch_for_a_crlf_converted_pack_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pack file whose BYTES differ only in line endings is still drift.

    🔴 The fail-open this test exists to close. The arm's contract is stated as
    "a present file whose bytes differ", but it compared DECODED TEXT via
    `Path.read_text`, which performs universal-newline translation — so a
    CRLF-converted pack file decoded back to the canonical string and the
    check reported the pack CLEAN. The bytes on disk are not the bytes the
    installer wrote, and the operator was told they were.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    pack_dir = _install_governed_pack(repo_root=primary, monkeypatch=monkeypatch)
    _ = (pack_dir / "worktree-lib.sh").write_bytes(
        CANONICAL_WORKTREE_LIB_BODY.replace("\n", "\r\n").encode("utf-8")
    )

    failures = _pack_failures(repo_root=primary)
    assert failures == [("worktree-lib.sh", "worktree_pack_body_mismatch")]


def test_inspect_reports_body_mismatch_for_a_pack_file_that_is_not_utf8(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pack file that is not valid UTF-8 is DEFINITIVELY not the canonical body.

    The canonical bodies are UTF-8 by construction, so bytes that do not
    decode cannot equal them — there is nothing indeterminate here. The arm
    nonetheless decoded before comparing, so this raised `UnicodeDecodeError`
    straight out of the check: a crash where a definitive finding was
    available. Invalid UTF-8 is used rather than `chmod 000` because this
    suite runs as root, where a mode-based fixture cannot fail.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    pack_dir = _install_governed_pack(repo_root=primary, monkeypatch=monkeypatch)
    _ = (pack_dir / "branch-protection.sh").write_bytes(b"#!/usr/bin/env bash\n\xff\xfe\x00drift\n")

    failures = _pack_failures(repo_root=primary)
    assert failures == [("branch-protection.sh", "worktree_pack_body_mismatch")]


def test_inspect_reports_not_imported_for_a_justfile_that_is_not_utf8(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An undecodable justfile is still ANSWERABLE, one import line at a time.

    The import lines are pure ASCII, so whether a byte sequence contains them
    is answerable without decoding the whole file. The arm decoded first and
    raised `UnicodeDecodeError` out of the check instead.

    ⛔ The fixture is deliberately not merely undecodable: it still CARRIES
    the `worktree.just` import and omits the `branch-protection.just` one, so
    the arm must report exactly ONE fragment. That is what makes this a real
    instrument — the cheap fix (catch the decode error and treat the justfile
    as empty) would report BOTH and fail here, while the honest fix searches
    the bytes and discriminates.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    _ = _install_governed_pack(repo_root=primary, monkeypatch=monkeypatch)
    _ = (primary / "justfile").write_bytes(b"\xff\xfeimport? 'dev-tooling/worktree.just'\n")

    failures = _pack_failures(repo_root=primary)
    assert failures == [("branch-protection.just", "worktree_pack_not_imported")]


def test_inspect_reports_an_unreadable_pack_file_as_a_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pack file this run could not READ is not a pack file that DRIFTED.

    The distinction PR #988 drew for the Driver profiles, in the one place
    here where it genuinely applies. Every other condition this arm meets is
    definitive — absent, present-and-different, present-and-undecodable — and
    stays on the success track as a violation. Only a read that did not happen
    leaves it, because only that says nothing about the pack.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    pack_dir = _install_governed_pack(repo_root=primary, monkeypatch=monkeypatch)
    _make_read_fail(
        monkeypatch=monkeypatch, target=pack_dir / "worktree.just", detail="pack read refused"
    )

    inspected = inspect_worktree_pack(repo_root=primary)

    assert isinstance(inspected, IOFailure)
    failed = unsafe_perform_io(inspected.failure())
    assert failed == CheckInputUnreadable(
        path=str(pack_dir / "worktree.just"),
        detail=f"[Errno {errno.EIO}] pack read refused",
    )


def test_inspect_reports_an_unreadable_config_as_a_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 The fail-open: an unread `.livespec.jsonc` used to mean "UNGOVERNED".

    `_read_pack_policy` fused three conditions into that one word — the config
    ABSENT (definitive: not a governed repo), present-and-unparseable
    (definitive: the document is broken, and deliberately deferred to the
    config-integrity check), and the read never happening (definitive about
    nothing). The third rode the first two onto the success track, and since
    an ungoverned tree needs no pack, the arm returned NO violations: a repo
    whose config could not be read was told its pack requirement did not
    apply. That is precisely the fail-open zs22 A2 exists to close, re-entered
    through the config read.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    _ = (primary / ".livespec.jsonc").write_text('{"template": "livespec"}\n', encoding="utf-8")
    _make_read_fail(
        monkeypatch=monkeypatch, target=primary / ".livespec.jsonc", detail="config read refused"
    )

    inspected = inspect_worktree_pack(repo_root=primary)

    assert isinstance(inspected, IOFailure)
    failed = unsafe_perform_io(inspected.failure())
    assert failed == CheckInputUnreadable(
        path=str(primary / ".livespec.jsonc"),
        detail=f"[Errno {errno.EIO}] config read refused",
    )


def test_inspect_reports_an_unreadable_justfile_as_a_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unread justfile is not a justfile missing its `import?` lines.

    The discoverability arm's own fail-open twin: reporting
    `worktree_pack_not_imported` here would tell the operator to add import
    lines that may already be present, on the evidence of a read that never
    happened.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    _ = _install_governed_pack(repo_root=primary, monkeypatch=monkeypatch)
    _make_read_fail(
        monkeypatch=monkeypatch, target=primary / "justfile", detail="justfile read refused"
    )

    inspected = inspect_worktree_pack(repo_root=primary)

    assert isinstance(inspected, IOFailure)
    failed = unsafe_perform_io(inspected.failure())
    assert failed == CheckInputUnreadable(
        path=str(primary / "justfile"),
        detail=f"[Errno {errno.EIO}] justfile read refused",
    )


# A `git` stand-in whose `worktree list --porcelain` output is far larger than
# one pipe buffer, so a reader that quits after the first line CANNOT have been
# handed the whole stream already.
#
# `exec` is load-bearing. It makes awk REPLACE this shell, so the stub's exit
# status IS awk's — which is how the real `git` reports its own SIGPIPE death.
# A stub that printed from the shell and then `exit 0`ed would swallow the very
# signal under test and the test would pass against the defect.
_FAKE_GIT_LARGE_WORKTREE_LISTING = """#!/usr/bin/env bash
if [ "${1:-}" != "worktree" ] || [ "${2:-}" != "list" ]; then
    echo "unexpected git invocation: $*" >&2
    exit 2
fi
exec awk 'BEGIN {
    printf "worktree /primary/checkout\\nHEAD 0\\nbranch refs/heads/master\\n\\n"
    for (i = 1; i <= 4000; i++) {
        printf "worktree /w/b-%d\\nHEAD 0\\nbranch refs/heads/b-%d\\n\\n", i, i
    }
}'
"""


def test_worktree_primary_path_survives_a_listing_larger_than_one_pipe_buffer(
    tmp_path: Path,
) -> None:
    """`worktree_primary_path` must not die of SIGPIPE on a long worktree list.

    It read the primary checkout as `git worktree list --porcelain | awk
    '/^worktree /{print $2; exit}'`. The `exit` closes the pipe after the FIRST
    line; while git's whole output fits one stdio block it has already finished
    writing and nothing notices, but past one block git is still writing when
    the reader goes away, takes SIGPIPE and exits 141 — and the pack runs under
    `set -euo pipefail`, so `pipefail` promotes that to the pipeline's status
    and `set -e` aborts. Exit 141, stdout empty, stderr empty.

    THE SIZE IS THE WHOLE POINT, which is why this stub emits ~4000 entries
    rather than a handful. The defect is a RACE at small sizes: measured
    2026-08-03, a repo with 8-13 worktrees never reproduced it, one with 24
    (4181 bytes) failed 2 times in 20, and one with 106 (18480 bytes) failed 18
    in 20. A fixture sized near the boundary would be a flaky test of a real
    defect — the worst of both. Far past one buffer it is deterministic: the
    writer physically cannot have finished.

    Guards the fix rather than the spelling: any implementation that reads the
    listing without abandoning the writer mid-stream passes.
    """
    lib = tmp_path / "worktree-lib.sh"
    _ = lib.write_text(CANONICAL_WORKTREE_LIB_BODY, encoding="utf-8")
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    _ = fake_git.write_text(_FAKE_GIT_LARGE_WORKTREE_LISTING, encoding="utf-8")
    fake_git.chmod(0o755)

    completed = subprocess.run(
        ["bash", "-c", f'set -euo pipefail; . "{lib}"; worktree_primary_path'],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert completed.returncode == 0, (
        f"worktree_primary_path exited {completed.returncode} "
        f"(141 = SIGPIPE, the defect); stderr={completed.stderr!r}"
    )
    assert completed.stdout.strip() == "/primary/checkout"


# ---------------------------------------------------------------------------
# ONE enumeration of the pack file set (livespec-dev-tooling-l5gypl).
#
# The installer, the `just check` verifier arm, the `worktree-pack` bootstrap
# obligation row and `worktree-lib.sh`'s shell copy each used to write the set
# down themselves, and measured 2026-09-06 the copies DISAGREED: the verifier
# asserted six files, the bootstrap row four. `just bootstrap` therefore passed
# a pack `just check` rejected, and its reconcile never fired. The three Python
# consumers now derive from `WORKTREE_PACK_FILES`; the shell copy cannot import
# Python, so the lockstep is asserted here instead.
#
# `_EXPECTED_PACK` states the set INDEPENDENTLY of the installer on purpose. A
# lockstep test that read the constant on both sides of every assertion would
# compare the constant with itself and pass no matter what the set became.
# ---------------------------------------------------------------------------

_EXPECTED_PACK: tuple[tuple[str, bool], ...] = (
    ("worktree-lib.sh", True),
    ("branch-protection.sh", True),
    ("gate-run.sh", True),
    ("check-no-workflow-edits.sh", True),
    ("worktree.just", False),
    ("branch-protection.just", False),
    (".gitignore", False),
)

_WORKTREE_LIB_PATH = _PACK_DATA_DIR / "worktree-lib.sh"
_PACK_FILES_ASSIGNMENT = re.compile(r'^\s*pack_files="([^"]*)"\s*$', re.MULTILINE)
_CHMOD_INVOCATION = re.compile(r"^\s*chmod (\+x|a-x) (.*)$", re.MULTILINE)
_DEST_DIR_ENTRY = re.compile(r'"\$dest_dir/([^"]+)"')


def _installed_names() -> tuple[str, ...]:
    """Every basename the installer's single constant enumerates."""
    return tuple(pack_file.name for pack_file in WORKTREE_PACK_FILES)


def _shell_pack_file_names() -> tuple[str, ...]:
    """The `pack_files` string inside `worktree-lib.sh`, as a name tuple."""
    body = _WORKTREE_LIB_PATH.read_text(encoding="utf-8")
    assignments = _PACK_FILES_ASSIGNMENT.findall(body)
    assert len(assignments) == 1, (
        f"expected exactly one `pack_files=` assignment in worktree-lib.sh, "
        f"found {len(assignments)}"
    )
    return tuple(assignments[0].split())


def _shell_chmod_names(*, flag: str) -> tuple[str, ...]:
    """The `$dest_dir/` basenames the pack's single `chmod <flag>` line names."""
    body = _WORKTREE_LIB_PATH.read_text(encoding="utf-8")
    lines = [argv for found_flag, argv in _CHMOD_INVOCATION.findall(body) if found_flag == flag]
    assert (
        len(lines) == 1
    ), f"expected exactly one `chmod {flag}` line in worktree-lib.sh, found {len(lines)}"
    return tuple(_DEST_DIR_ENTRY.findall(lines[0]))


def _install_pack_into_wired_repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A governed, WIRED repo carrying a freshly installed canonical pack.

    The root justfile carries both `import?` lines because that is what a wired
    governed repo looks like: since A2 the verifier asserts discoverability as
    well as byte-identity, so a fixture without them would start from a repo
    the arm already fails for an unrelated reason.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    repo = tmp_path / "project"
    _init_repo(repo=repo)
    _ = (repo / "justfile").write_text(
        "import? 'dev-tooling/worktree.just'\nimport? 'dev-tooling/branch-protection.just'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo)
    assert main() == 0
    return repo


def _worktree_pack_obligation_row() -> LocalObligationRow:
    """The `worktree-pack` row, taken from the table rather than imported."""
    rows = [row for row in LOCAL_OBLIGATION_ROWS if row.row_id == "worktree-pack"]
    assert rows, "LOCAL_OBLIGATION_ROWS carries no `worktree-pack` row"
    return rows[0]


def _refuse_to_run(*, args: list[str], cwd: Path | None = None) -> CommandOutcome:
    """A command seam that REFUSES rather than reporting a fabricated success.

    `assert_worktree_pack` answers from files alone. A seam returning a canned
    exit-0 would let a future row start shelling out and still pass these
    tests against whatever the fake claimed; refusing makes that a failure at
    the moment it happens, and names it.
    """
    raise AssertionError(f"the worktree-pack assert must not spawn: {args} (cwd={cwd})")


def _row_context(*, checkout: Path) -> LocalContext:
    """A `LocalContext` over `checkout` whose command seam refuses to run."""
    return LocalContext(checkout=checkout, home=checkout / "home", run=_refuse_to_run)


def test_the_row_context_command_seam_refuses_to_run(*, tmp_path: Path) -> None:
    """The seam is a GUARD, so it is dead unless something calls it deliberately.

    Asserted here for the same reason the local-context Red file asserts its
    own `_never_run`: the tests below pass precisely by never reaching it, so
    without this the guard would be an untested claim.
    """
    with pytest.raises(AssertionError, match="must not spawn"):
        _ = _row_context(checkout=tmp_path).exec(args=["git", "status"])


def test_installer_carries_one_enumeration_of_the_pack_file_set() -> None:
    """`WORKTREE_PACK_FILES` is the exported single source of the pack's shape."""
    assert "WORKTREE_PACK_FILES" in install_worktree_pack.__all__
    assert (
        tuple((pack_file.name, pack_file.executable) for pack_file in WORKTREE_PACK_FILES)
        == _EXPECTED_PACK
    )


def test_installer_installs_exactly_the_enumerated_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The constant is not decorative: it is what lands in `dev-tooling/`."""
    repo = _install_pack_into_wired_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    pack_dir = repo / "dev-tooling"
    installed = {entry.name for entry in pack_dir.iterdir()}
    assert installed == {name for name, _executable in _EXPECTED_PACK}
    for name, executable in _EXPECTED_PACK:
        assert os.access(pack_dir / name, os.X_OK) is executable, name


def test_verifier_arm_asserts_every_file_the_installer_installs(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drifting ANY installed file must red the `just check` pack arm.

    Proves the arm's set is not a subset of the installer's — a subset is
    exactly the shape that lets a drifted pack pass the gate.
    """
    repo = _install_pack_into_wired_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    pack_dir = repo / "dev-tooling"
    assert _pack_failures(repo_root=repo) == []
    for name, _executable in _EXPECTED_PACK:
        target = pack_dir / name
        canonical = target.read_bytes()
        _ = target.write_bytes(canonical + b"# drift\n")
        assert (name, "worktree_pack_body_mismatch") in _pack_failures(
            repo_root=repo
        ), f"the verifier arm does not assert {name}, which the installer installs"
        _ = target.write_bytes(canonical)
    assert _pack_failures(repo_root=repo) == []


def test_bootstrap_row_asserts_every_file_the_installer_installs(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `worktree-pack` row passes ONLY on a complete, byte-identical pack.

    The row's assert leg is what decides whether `just bootstrap` reconciles.
    When it asserted a strict subset of the installed set — four files against
    the gate's six — bootstrap reported the pack satisfied while `just check`
    rejected it, and no amount of re-running bootstrap could clear the gate.
    """
    repo = _install_pack_into_wired_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    pack_dir = repo / "dev-tooling"
    row = _worktree_pack_obligation_row()
    assert row.assert_local is not None
    ctx = _row_context(checkout=repo)
    assert isinstance(row.assert_local(ctx=ctx), RowPass)
    for name, _executable in _EXPECTED_PACK:
        target = pack_dir / name
        canonical = target.read_bytes()
        target.unlink()
        outcome = row.assert_local(ctx=ctx)
        assert isinstance(
            outcome, RowFinding
        ), f"the bootstrap row does not assert {name}, which the installer installs"
        assert name in outcome.message
        _ = target.write_bytes(canonical)
    assert isinstance(row.assert_local(ctx=ctx), RowPass)


def test_worktree_lib_pack_files_string_matches_the_installer_constant() -> None:
    """The shell copy of the set is held in lockstep with the constant.

    `worktree_provision_pack_from_primary` copies the pack into a freshly added
    linked worktree, and shell cannot import the constant — so this is the one
    consumer whose agreement has to be asserted rather than derived. All three
    lines are checked: the file list, and both `chmod` lines, since a file
    copied with the wrong mode is drift the byte-identity arms cannot see.
    """
    assert _shell_pack_file_names() == _installed_names()
    assert set(_shell_pack_file_names()) == {name for name, _executable in _EXPECTED_PACK}
    assert set(_shell_chmod_names(flag="+x")) == {
        name for name, executable in _EXPECTED_PACK if executable
    }
    assert set(_shell_chmod_names(flag="a-x")) == {
        name for name, executable in _EXPECTED_PACK if not executable
    }
