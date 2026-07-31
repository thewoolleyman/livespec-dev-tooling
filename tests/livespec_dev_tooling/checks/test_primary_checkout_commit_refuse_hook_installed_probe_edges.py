"""Green-leg edges for `primary_checkout_commit_refuse_hook_installed` — unanswered inputs.

A `*_edges.py` sibling of `test_primary_checkout_commit_refuse_hook_installed.py`
per the repo's Green-leg convention: the Red-recorded test file of a
Red→Green pair is byte-identity-bound, so tests authored at the Green amend
land here. `check_coverage_incremental` selects `test_<stem>_*.py` siblings
alongside the paired test, so these count toward the parent impl's coverage.

WHAT THESE PIN — livespec-dev-tooling-qndn, epic 8o8e. Every verdict the
parent check reports rests on six git probes. Until the probes went on the
`IOResult` railway, a probe that did not ANSWER was spelled the same as an
answer: `is_git_repo_at_all` returned a bare `False` whether git said "not a
repository" or never ran, and that `False` took the SKIP path — exit 0, a pass
the run never earned. `git_common_dir` and `work_tree_root` raised
`CalledProcessError` instead, which at least did not go green but produced a
traceback rather than a structured finding.

Each arm below drives ONE probe's failure and asserts the CHECK's disposition;
the probe-level success/failure split has its own mirror-paired test in
`test_primary_checkout_git_probes.py`.

The last five arms carry the same question from the git probes to the FILE
reads, where it convicted both remaining arms.

Two are the worktree-pack arm's, which had the defect one layer over: an unread
`.livespec.jsonc` resolved to the `ungoverned` policy, an ungoverned tree needs
no pack, and the check exited 0 having read nothing. Their unit-level split
lives in `tests/livespec_dev_tooling/test_install_worktree_pack.py`; what these
pin is that the parent narrates it as its OWN failure mode, never as pack drift.

Three are the HOOK arm's, and that one matters more — the pack is optional per
repo, these three hooks are the check's reason to exist. `inspect_hook`
compared DECODED text under a docstring promising "STRICT BYTE-IDENTITY", so a
CRLF-converted hook decoded back to canonical and PASSED, and an undecodable
one raised out of `main()` rather than reporting the mismatch that was always
available. The arm was found by the extraction the conversion forced, not by
anything that suspected it.

`main()` is called IN-PROCESS (`monkeypatch.chdir` + `capsys`) rather than
spawned, per `check-tests-no-subprocess-spawn` — the paired file predates that
rule and sits on the migrate-away-from allowlist, which a new file must not
join. The git subprocesses the fixtures and the check itself run are
unaffected: that check governs PYTHON children, which are the ones that
self-instrument under `--cov` and race.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed import main
from livespec_dev_tooling.install_commit_refuse_hooks import CANONICAL_HOOK_BODY
from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_BRANCH_PROTECTION_JUST_BODY,
    CANONICAL_WORKTREE_LIB_BODY,
)

__all__: list[str] = []


# Vars git sets when invoking hooks (lefthook pre-commit / pre-push). Under a
# hook these would redirect the check's probes at the SURROUNDING repo instead
# of the tmp_path fixture.
_GIT_ENV_PASSTHROUGH_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

# The check's fail exit; `0` is pass-or-skip and is what these arms must NOT be.
_FAIL_EXIT = 4

# An exit code no probe treats as an answer (`git config --get` uses 1 for an
# unset key, and that one IS an answer).
_SYNTHETIC_GIT_EXIT = 66


def _git_init(*, cwd: Path) -> None:
    """Initialize a git repo at `cwd` with local user.name/user.email."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    for args in (
        ["init", "--quiet"],
        ["config", "--local", "user.name", "Test User"],
        ["config", "--local", "user.email", "test@example.com"],
    ):
        _ = subprocess.run(["git", *args], cwd=str(cwd), check=True, env=env)


def _repo_at(*, tmp_path: Path) -> Path:
    """A real git repo, initialized while the REAL git is still on PATH."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    return project_root


def _unexecutable_git_bin(*, tmp_path: Path) -> str:
    """A directory whose `git` passes `shutil.which` but cannot be exec'd.

    `shutil.which` asks only for an existing, executable, non-directory file,
    so a shim whose interpreter does not resolve satisfies the check's ONE git
    guard and then makes `subprocess.run` raise `FileNotFoundError`. That is
    exactly the gap between "git is unavailable" (a documented skip) and "git
    does not answer" (a finding), and it is reachable in the field: a
    truncated install, a wrapper pointing at a removed toolchain.

    ⛔ The caller MUST use this directory as the WHOLE PATH, never as a
    prefix. An unresolvable interpreter makes `execve` fail with `ENOENT`, and
    `subprocess`'s own PATH search reads that as "not here" and CONTINUES to
    the next directory — so a real git further along the path silently
    services the call and the arm never fires. Measured, not assumed: the
    first version of this fixture appended `os.environ["PATH"]` and the check
    ran to completion against the real git.
    """
    bin_dir = tmp_path / "unexecutable-bin"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    _ = shim.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
    shim.chmod(0o755)
    return str(bin_dir)


def _git_bin_failing_on(*, tmp_path: Path, name: str, argv: str) -> str:
    """A directory whose `git` exits non-zero for exactly `argv`, else delegates.

    One shim per scenario rather than one switched by an env var, so each arm
    isolates a single probe. The delegation target is the REAL git resolved
    absolutely, so every OTHER probe in the run answers normally — which is
    what makes the asserted `probe` field meaningful rather than incidental.
    """
    real_git = shutil.which("git")
    assert real_git is not None, "the suite needs a real git to delegate to"
    bin_dir = tmp_path / name
    bin_dir.mkdir()
    shim = bin_dir / "git"
    _ = shim.write_text(
        "#!/bin/sh\n"
        f'if [ "$*" = "{argv}" ]; then\n'
        "  printf 'fatal: synthetic git failure\\n' >&2\n"
        f"  exit {_SYNTHETIC_GIT_EXIT}\n"
        "fi\n"
        f'exec {real_git} "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return str(bin_dir)


def _run_check(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cwd: Path,
    path_override: str,
) -> tuple[int, str]:
    """Call `main()` in-process under `cwd` and `path_override`, returning (rc, stderr)."""
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", path_override)
    rc = main()
    return rc, capsys.readouterr().err


def _assert_probe_failure(*, rc: int, stderr: str, probe: str) -> None:
    """The run FAILED, named `git_probe_failed`, and named WHICH probe.

    All four assertions carry weight. The exit code alone would not
    distinguish this from a hook-drift fail; the failure mode alone would not
    tell the operator which command to rerun; the argv is what makes the
    finding actionable rather than merely correct.
    """
    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}"
    assert '"failure_mode": "git_probe_failed"' in stderr, stderr
    assert f'"probe": "{probe}"' in stderr, stderr
    assert '"argv": "git ' in stderr, stderr


def test_fails_when_git_is_on_path_but_cannot_be_executed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unexecutable `git` is a FINDING, not the `git unavailable` skip.

    The first probe the check runs is `is_git_repo_at_all`, and its bare
    `False` used to route this environment to "cwd is not a git repository;
    skipping check" — exit 0. The two states are now distinct: no git at all
    still skips (`test_skipped_when_git_unavailable` in the paired file), a
    git that does not answer fails.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    rc, stderr = _run_check(
        monkeypatch=monkeypatch,
        capsys=capsys,
        cwd=project_root,
        path_override=_unexecutable_git_bin(tmp_path=tmp_path),
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="is_git_repo_at_all")


def test_fails_when_the_core_bare_probe_cannot_read_config(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`git config --get core.bare` failing is a finding, not git's default `false`.

    Exit 1 means the key is UNSET and stays an answer; this exercises the
    other non-zero codes, which used to reach the caller as the same empty
    stdout and therefore the same `False`.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path, name="shim-core-bare", argv="config --get core.bare"
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="core_bare_is_true")


def test_fails_when_the_inside_work_tree_probe_does_not_answer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-zero `rev-parse --is-inside-work-tree` is a finding, not "not a work tree"."""
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path,
        name="shim-inside-work-tree",
        argv="rev-parse --is-inside-work-tree",
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="is_inside_work_tree")


def test_fails_when_the_common_dir_probe_does_not_answer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The converted `check=True` raise: a structured finding, not a traceback."""
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path, name="shim-common-dir", argv="rev-parse --git-common-dir"
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="git_common_dir")


def test_fails_when_the_work_tree_root_probe_does_not_answer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The work-tree root anchors the no-vendored-copy scan.

    An unresolved root must not reach that scan as any path at all: `rglob`
    over the wrong tree finds no vendored copy and the arm passes silently.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path, name="shim-toplevel", argv="rev-parse --show-toplevel"
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="work_tree_root")


def test_fails_when_the_sandbox_exempt_probe_cannot_read_config(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unreadable exemption marker fails rather than silently NOT exempting.

    A failed read collapsing onto `False` is the SAFE direction here — the
    pack arm just stays armed — which is exactly why it survived: a fail-safe
    that is indistinguishable from an answer still hides a broken environment.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path,
        name="shim-sandbox-exempt",
        argv="config --get livespec.sandboxExempt",
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="sandbox_exempt_is_true")


def _make_read_fail(*, monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    """Make exactly `target`'s byte read raise `OSError`; leave every other read real.

    ⛔ NOT `chmod 000`: this suite runs as root, where a mode-based fixture is
    a lie — the read succeeds anyway and the assertion never fires. Scoped to
    ONE path so every other read in the run, including the hook byte-identity
    arm's, still answers normally; that is what makes the asserted failure mode
    attributable to this file rather than incidental.
    """
    real_read_bytes = Path.read_bytes

    def _read_bytes(self: Path) -> bytes:
        if self == target:
            raise OSError(5, "synthetic read failure")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _read_bytes)


def _assert_pack_read_failure(*, rc: int, stderr: str, path: Path) -> None:
    """The run FAILED, named the file, and did NOT call it pack drift.

    The negative assertion is the load-bearing one. Reporting an unread file as
    `worktree_pack_body_mismatch` would hand the operator `just bootstrap` — a
    remedy for a fault this run never observed — which is the articulate wrong
    answer this epic exists to remove.
    """
    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}"
    assert '"failure_mode": "worktree_pack_unreadable"' in stderr, stderr
    assert f'"path": "{path}"' in stderr, stderr
    assert "synthetic read failure" in stderr, stderr
    assert "worktree_pack_body_mismatch" not in stderr, stderr
    assert "worktree_pack_not_imported" not in stderr, stderr


def test_fails_when_the_livespec_config_cannot_be_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 The fail-open this arm closes: an unread config used to mean "ungoverned".

    `_read_pack_policy` resolved an unreadable `.livespec.jsonc` to
    `ungoverned`, an ungoverned tree needs no pack, and the check returned
    exit 0 — a governed repo told its pack requirement did not apply, on the
    evidence of a file nothing read. Exit 0 here would be the whole defect.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    config = project_root / ".livespec.jsonc"
    _ = config.write_text('{"template": "livespec"}\n', encoding="utf-8")
    _make_read_fail(monkeypatch=monkeypatch, target=config)

    rc, stderr = _run_check(
        monkeypatch=monkeypatch,
        capsys=capsys,
        cwd=project_root,
        path_override=os.environ["PATH"],
    )
    _assert_pack_read_failure(rc=rc, stderr=stderr, path=config)


def test_fails_when_an_installed_pack_file_cannot_be_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unread pack file is not a DRIFTED pack file, and it VOIDS the partial verdict.

    The byte-identity arm decides drift from the bytes it reads. With no bytes
    there is no verdict to report, and the one it used to reach — raising
    `UnicodeDecodeError`, or for an I/O error propagating out of `main()` —
    was a traceback rather than a finding.

    ⛔ The fixture is ordered deliberately. `branch-protection.just` is
    installed canonical and IS read successfully, `branch-protection.sh` is
    absent and so is collected as `worktree_pack_file_missing`, and only then
    does `worktree-lib.sh` fail to read. The check must report NEITHER
    collected finding: an arm that could not finish its scan has no partial
    answer to publish, and a `worktree_pack_file_missing` emitted here would
    be a real-looking finding from an incomplete pass. The successful read
    also exercises the fixture's passthrough, so the patch is proven to be
    scoped to one path rather than failing everything.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    pack_dir = project_root / "dev-tooling"
    pack_dir.mkdir()
    _ = (pack_dir / "branch-protection.just").write_text(
        CANONICAL_BRANCH_PROTECTION_JUST_BODY, encoding="utf-8"
    )
    installed = pack_dir / "worktree-lib.sh"
    _ = installed.write_text(CANONICAL_WORKTREE_LIB_BODY, encoding="utf-8")
    _make_read_fail(monkeypatch=monkeypatch, target=installed)

    rc, stderr = _run_check(
        monkeypatch=monkeypatch,
        capsys=capsys,
        cwd=project_root,
        path_override=os.environ["PATH"],
    )
    _assert_pack_read_failure(rc=rc, stderr=stderr, path=installed)
    assert "worktree_pack_file_missing" not in stderr, stderr


def _install_hooks(*, repo_root: Path, bodies: dict[str, bytes]) -> Path:
    """Write the three commit-refuse hooks, overriding named ones with raw bytes."""
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook_name in ("pre-commit", "pre-push", "commit-msg"):
        hook = hooks_dir / hook_name
        _ = hook.write_bytes(bodies.get(hook_name, CANONICAL_HOOK_BODY.encode("utf-8")))
        hook.chmod(0o755)
    return hooks_dir


def test_fails_when_a_hook_is_crlf_converted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 The MANDATORY arm's own fail-open: bytes differ and the check passed.

    The parent's docstring states the contract as "STRICT BYTE-IDENTITY
    (zs22.7.9.5)" and "Any deviation — a hook that is missing, non-executable,
    or whose bytes differ from the canonical body ... — is a FAIL".
    `inspect_hook` compared DECODED TEXT, and `Path.read_text` performs
    universal-newline translation, so a CRLF-converted hook decoded back to
    the canonical string and the arm returned `(True, "")` — exit 0 on a hook
    whose bytes on disk are not the ones the installer wrote.

    This is the same defect as the worktree-pack arm's, on the arm that
    matters more: the pack is optional per repo, these three hooks are the
    check's reason to exist.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    _ = _install_hooks(
        repo_root=project_root,
        bodies={"pre-push": CANONICAL_HOOK_BODY.replace("\n", "\r\n").encode("utf-8")},
    )

    rc, stderr = _run_check(
        monkeypatch=monkeypatch,
        capsys=capsys,
        cwd=project_root,
        path_override=os.environ["PATH"],
    )

    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}"
    assert '"failure_mode": "body_mismatch"' in stderr, stderr
    assert '"hook": "pre-push"' in stderr, stderr


def test_fails_when_a_hook_is_not_valid_utf8(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bytes that do not decode are DEFINITIVELY not the canonical body.

    `CANONICAL_HOOK_BODY` is UTF-8 by construction, so an undecodable hook
    cannot equal it — there was never anything indeterminate here. Decoding
    first meant `UnicodeDecodeError` propagated out of `main()` as a traceback
    instead of the `body_mismatch` that was always available.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    _ = _install_hooks(
        repo_root=project_root, bodies={"commit-msg": b"#!/bin/sh\n\xff\xfe\x00 not utf-8\n"}
    )

    rc, stderr = _run_check(
        monkeypatch=monkeypatch,
        capsys=capsys,
        cwd=project_root,
        path_override=os.environ["PATH"],
    )

    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}"
    assert '"failure_mode": "body_mismatch"' in stderr, stderr
    assert '"hook": "commit-msg"' in stderr, stderr


def test_fails_when_a_hook_cannot_be_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unread hook is not a MISSING hook and not a drifted one.

    The two remaining hooks are canonical, so a partial verdict would report
    the check clean on them and say nothing about the third. `hook_unreadable`
    is a distinct mode precisely so the operator is not told to reinstall a
    hook whose bytes this run never saw.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    hooks_dir = _install_hooks(repo_root=project_root, bodies={})
    _make_read_fail(monkeypatch=monkeypatch, target=hooks_dir / "pre-commit")

    rc, stderr = _run_check(
        monkeypatch=monkeypatch,
        capsys=capsys,
        cwd=project_root,
        path_override=os.environ["PATH"],
    )

    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}"
    assert '"failure_mode": "hook_unreadable"' in stderr, stderr
    assert f'"path": "{hooks_dir / "pre-commit"}"' in stderr, stderr
    assert '"failure_mode": "missing"' not in stderr, stderr
    assert '"failure_mode": "body_mismatch"' not in stderr, stderr
