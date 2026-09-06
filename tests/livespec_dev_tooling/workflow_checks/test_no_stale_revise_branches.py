"""Outside-in test for `livespec_dev_tooling/workflow_checks/no_stale_revise_branches.py`.

Per `SPECIFICATION/contracts.md` section "`no_stale_revise_branches` check"
(a revise-workflow check, per section "Shared check inventory"), the check
enumerates local `refs/heads/spec/*` branches and fails when any such
branch carries commits that have NOT landed on the canonical branch. It is
invoked by the `/livespec:revise` pre-step and always fails hard (exit 4) on
any stale branch — there is no downgrade flag.

The two load-bearing scenarios are the LANDED and UNLANDED legs, which
together are the whole of livespec-dev-tooling-jtrt.2. The check used to
judge landed-ness by ANCESTRY (`git rev-list --left-right --count`); on a
rebase-merge-only fleet a landed branch's tip is never an ancestor of the
canonical branch, so every landed-but-undeleted branch was reported and the
precondition could only ever be skipped. `test_landed_branch_after_rebase_
merge_is_not_reported` builds a REBASED land (never a fast-forward, which
would leave ancestry intact and pass against the unfixed code, and which the
test guards against explicitly) and
`test_unlanded_branch_is_still_reported` is the negative control that keeps
the fix from being the same defect inverted.

Test scenarios:

- No `spec/*` branches in the repo → exit 0.
- One `spec/*` branch even with origin/master (nothing unlanded) → exit 0.
- One `spec/*` branch with one unlanded commit → exit 4 with finding.
- A `spec/*` branch landed by REBASE-merge → exit 0 (the defect leg).
- A landed branch and an unlanded branch together → exit 4 naming only the
  unlanded one (the discrimination, asserted in one repository).
- Multiple stale branches → exit 4 with one finding per stale branch.
- `refs/heads/abandoned/spec/*` does NOT match the canonical pattern → exit 0.
- `--help` / `-h` exits 0 with usage on stdout.
- `.livespec.jsonc`'s `livespec-orchestrator-git-jsonl.canonical_branch` resolves
  a non-master canonical branch.
- Fallback to `origin/HEAD` when `.livespec.jsonc` is absent / silent.
- Hard-coded fallback to `master` when neither config nor `origin/HEAD`
  is available.

Tests construct real git repos under `tmp_path` (a "remote" bare repo
and one or more clones) so the check exercises real git plumbing
end-to-end, matching the patterns in `test_commit_pairs_source_and_test.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "workflow_checks" / "no_stale_revise_branches.py"


# Vars git sets when invoking hooks (lefthook pre-commit / pre-push /
# commit-msg). Inherited by subprocess children unless scrubbed, which
# would otherwise redirect the check script's internal `git` calls to
# the SURROUNDING repo (e.g., `git for-each-ref refs/heads/spec/*`
# enumerating the maintainer's actual `spec/*` branches) instead of
# the tmp_path mini-repo the test constructs. Mirrors the discipline
# already established in `test_primary_checkout_commit_refuse_hook_installed.py`.
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


def _scrubbed_environ() -> dict[str, str]:
    """Return a copy of `os.environ` with GIT_* hook vars removed."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}


def _git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke git with a hermetic env so tmp_path tests stay isolated."""
    # S603/S607: argv is a fixed list (literal git binary + repo-controlled
    # args); bare `git` is the canonical invocation per system PATH;
    # no untrusted shell input.
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


def _git_succeeds(*, cwd: Path, args: list[str]) -> bool:
    """Run git for its EXIT STATUS only, under the same hermetic env as `_git`.

    Used by the fixture guards that assert a land really did rewrite
    history, where a non-zero exit is the expected answer and `_git`'s
    `check=True` would raise instead of reporting it.
    """
    # S603/S607: same fixed-argv, repo-controlled invocation as `_git`.
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env={
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )
    return completed.returncode == 0


def _run_check(
    *,
    cwd: Path,
    extra_argv: list[str] | None = None,
    env_path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(_CHECK)]
    if extra_argv is not None:
        argv.extend(extra_argv)
    env = _scrubbed_environ()
    if env_path is not None:
        env["PATH"] = env_path
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _install_fake_git(
    *,
    tmp_path: Path,
    symbolic_ref_stdout: str = "",
    symbolic_ref_returncode: int = 0,
    for_each_ref_stdout: str = "",
    for_each_ref_returncode: int = 0,
    cherry_stdout: str = "",
    cherry_returncode: int = 0,
) -> str:
    """Install a fake `git` shell stub at tmp_path/bin/git; return PATH including it.

    Dispatches on argv[1] (`symbolic-ref`, `for-each-ref`, `cherry`)
    and emits the configured stdout/returncode. Falls through to a
    real `/usr/bin/git` for everything else (`rev-parse`, `log`, etc.)
    so subordinate helpers still produce sensible output.

    `cherry` is the landed-ness discriminator's plumbing — the stub
    arm was `rev-list` while the check judged by ancestry.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    git_stub = bin_dir / "git"
    script = (
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  symbolic-ref)\n"
        f"    cat <<'STUB_EOF'\n{symbolic_ref_stdout}\nSTUB_EOF\n"
        f"    exit {symbolic_ref_returncode}\n"
        "    ;;\n"
        "  for-each-ref)\n"
        f"    cat <<'STUB_EOF'\n{for_each_ref_stdout}\nSTUB_EOF\n"
        f"    exit {for_each_ref_returncode}\n"
        "    ;;\n"
        "  cherry)\n"
        f"    cat <<'STUB_EOF'\n{cherry_stdout}\nSTUB_EOF\n"
        f"    exit {cherry_returncode}\n"
        "    ;;\n"
        "  *)\n"
        '    exec /usr/bin/git "$@"\n'
        "    ;;\n"
        "esac\n"
    )
    _ = git_stub.write_text(script, encoding="utf-8")
    git_stub.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def _make_remote_and_clone(*, tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare `remote.git` + a clone with one baseline commit on `master`.

    Returns `(remote_path, clone_path)`. The clone has `origin/master`
    populated so `git rev-list origin/master...<branch>` succeeds.
    """
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _ = _git(cwd=remote, args=["init", "--bare", "-q", "--initial-branch=master"])
    seed = tmp_path / "seed"
    seed.mkdir()
    _ = _git(cwd=seed, args=["init", "-q", "--initial-branch=master"])
    _ = _git(cwd=seed, args=["config", "user.email", "test@example.com"])
    _ = _git(cwd=seed, args=["config", "user.name", "Test"])
    (seed / "README.md").write_text("baseline\n", encoding="utf-8")
    _ = _git(cwd=seed, args=["add", "README.md"])
    _ = _git(cwd=seed, args=["commit", "-m", "baseline"])
    _ = _git(cwd=seed, args=["remote", "add", "origin", str(remote)])
    _ = _git(cwd=seed, args=["push", "-u", "origin", "master"])
    clone = tmp_path / "clone"
    _ = _git(cwd=tmp_path, args=["clone", "-q", str(remote), str(clone)])
    _ = _git(cwd=clone, args=["config", "user.email", "test@example.com"])
    _ = _git(cwd=clone, args=["config", "user.name", "Test"])
    return remote, clone


def _make_branch_ahead(*, repo: Path, branch: str, commits: int) -> None:
    """Create `branch` from `master` and add `commits` extra commits on top."""
    _ = _git(cwd=repo, args=["checkout", "-q", "-b", branch, "master"])
    for i in range(commits):
        file_path = repo / f"{branch.replace('/', '_')}_change_{i}.txt"
        file_path.write_text(f"change {i}\n", encoding="utf-8")
        _ = _git(cwd=repo, args=["add", str(file_path)])
        _ = _git(cwd=repo, args=["commit", "-m", f"work on {branch} #{i}"])
    _ = _git(cwd=repo, args=["checkout", "-q", "master"])


def _advance_canonical(*, repo: Path, canonical: str, marker: str) -> None:
    """Put one unrelated commit on `canonical` and push it, so a land must REBASE.

    Without a divergent commit here a land is a fast-forward, which leaves
    the branch tip an ancestor of the canonical branch — the one shape that
    passes against the ancestry-based code and would therefore make the
    landed-branch test prove nothing (acceptance criterion 3).
    """
    _ = _git(cwd=repo, args=["checkout", "-q", canonical])
    (repo / marker).write_text("unrelated\n", encoding="utf-8")
    _ = _git(cwd=repo, args=["add", marker])
    _ = _git(cwd=repo, args=["commit", "-m", f"unrelated {marker}"])
    _ = _git(cwd=repo, args=["push", "-q", "origin", canonical])


def _land_by_rebase(*, repo: Path, branch: str, canonical: str) -> None:
    """Land `branch`'s content onto `origin/<canonical>` the way a rebase-merge does.

    The branch's commits are REPLAYED onto the canonical branch — new SHAs,
    byte-identical patches — and pushed, while the local `branch` ref is left
    at its original pre-rebase tip. That is exactly the state a
    rebase-merge leaves behind and exactly the state the check misread: the
    content IS on the canonical branch and the local tip is NOT an ancestor
    of it.
    """
    _ = _git(cwd=repo, args=["checkout", "-q", "-B", "landing", branch])
    _ = _git(cwd=repo, args=["rebase", "-q", canonical])
    _ = _git(cwd=repo, args=["checkout", "-q", canonical])
    _ = _git(cwd=repo, args=["merge", "-q", "--ff-only", "landing"])
    _ = _git(cwd=repo, args=["branch", "-q", "-D", "landing"])
    _ = _git(cwd=repo, args=["push", "-q", "origin", canonical])


def _assert_land_was_rebased(*, repo: Path, branch: str, canonical: str) -> None:
    """Guard: the local tip is NOT an ancestor of the canonical branch.

    A fixture that silently degraded into a fast-forward land would leave
    ancestry intact, so the landed-branch assertion below would pass against
    the very code it exists to indict. This makes that degradation loud.
    """
    assert not _git_succeeds(
        cwd=repo,
        args=["merge-base", "--is-ancestor", branch, f"origin/{canonical}"],
    ), (
        f"fixture degraded: {branch} is still an ancestor of origin/{canonical}, "
        f"so the land was a fast-forward rather than a rebase and would pass "
        f"against the ancestry-based code this test exists to indict"
    )


def test_no_spec_branches_passes(*, tmp_path: Path) -> None:
    """A clone with only `master` and no `spec/*` branches → exit 0."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    result = _run_check(cwd=clone)
    assert result.returncode == 0, (
        f"expected exit 0 when no spec/* branches exist; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_even_spec_branch_passes(*, tmp_path: Path) -> None:
    """A `spec/*` branch even with `master` (nothing unlanded) → exit 0, no findings."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _ = _git(cwd=clone, args=["checkout", "-q", "-b", "spec/in-sync", "master"])
    _ = _git(cwd=clone, args=["checkout", "-q", "master"])
    result = _run_check(cwd=clone)
    assert result.returncode == 0, (
        f"expected exit 0 when spec/* branch is even with master; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "unlanded" not in result.stderr


def test_single_stale_branch_fails(*, tmp_path: Path) -> None:
    """One `spec/*` branch with one unlanded commit → exit 4, finding lists branch."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone)
    assert result.returncode == 4, (
        f"expected exit 4 with one stale branch; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "spec/v003" in result.stderr
    assert "1 unlanded commit" in result.stderr


def test_landed_branch_after_rebase_merge_is_not_reported(*, tmp_path: Path) -> None:
    """A branch whose content landed by REBASE-merge → exit 0 (acceptance criteria 1 and 3).

    This is the defect leg. The branch's patch is on `origin/master` under a
    rewritten SHA, so the ancestry test the check used to run reports it as
    stale forever: nothing an operator can do — merge, abandon — applies to
    a branch that is already merged, so the only remedy left is the skip
    flag, and a precondition that is always skipped protects nothing.
    """
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="spec/landed", commits=1)
    _advance_canonical(repo=clone, canonical="master", marker="unrelated.txt")
    _land_by_rebase(repo=clone, branch="spec/landed", canonical="master")
    _assert_land_was_rebased(repo=clone, branch="spec/landed", canonical="master")

    result = _run_check(cwd=clone)

    assert result.returncode == 0, (
        f"expected exit 0 for a branch already landed by rebase-merge; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "spec/landed" not in result.stderr


def test_unlanded_branch_is_still_reported(*, tmp_path: Path) -> None:
    """The NEGATIVE CONTROL (acceptance criterion 2): unlanded work still fails.

    Built on the same rebase-landed history as the leg above, then given one
    further commit that never landed. A check that stopped reporting
    everything would be the same defect inverted — it would let a revise pass
    clobber a genuinely unlanded spec branch — so this leg is required, not
    optional.
    """
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="spec/landed", commits=1)
    _advance_canonical(repo=clone, canonical="master", marker="unrelated.txt")
    _land_by_rebase(repo=clone, branch="spec/landed", canonical="master")
    _assert_land_was_rebased(repo=clone, branch="spec/landed", canonical="master")
    _ = _git(cwd=clone, args=["checkout", "-q", "spec/landed"])
    (clone / "never-landed.txt").write_text("never landed\n", encoding="utf-8")
    _ = _git(cwd=clone, args=["add", "never-landed.txt"])
    _ = _git(cwd=clone, args=["commit", "-m", "genuinely unlanded work"])
    _ = _git(cwd=clone, args=["checkout", "-q", "master"])

    result = _run_check(cwd=clone)

    assert result.returncode == 4, (
        f"expected exit 4 for a branch carrying genuinely unlanded work; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "spec/landed" in result.stderr
    # Exactly the ONE unlanded commit is counted — the landed one is
    # discriminated away rather than the whole branch being waved through.
    assert "1 unlanded commit" in result.stderr


def test_landed_and_unlanded_branches_are_discriminated(*, tmp_path: Path) -> None:
    """Both legs in ONE repository: only the unlanded branch surfaces a finding.

    Asserting the discrimination in a single tree is what rules out a fix
    that merely moved the always-report / never-report threshold.
    """
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="spec/landed", commits=1)
    _make_branch_ahead(repo=clone, branch="spec/pending", commits=1)
    _advance_canonical(repo=clone, canonical="master", marker="unrelated.txt")
    _land_by_rebase(repo=clone, branch="spec/landed", canonical="master")
    _assert_land_was_rebased(repo=clone, branch="spec/landed", canonical="master")

    result = _run_check(cwd=clone)

    assert result.returncode == 4
    findings = [
        json.loads(line) for line in result.stderr.splitlines() if line.strip().startswith("{")
    ]
    fail_branches = {f.get("branch") for f in findings if f.get("status") == "fail"}
    assert fail_branches == {
        "spec/pending"
    }, f"expected only the unlanded spec/pending to be reported; got {fail_branches!r}"


def test_finding_names_its_discriminator(*, tmp_path: Path) -> None:
    """Acceptance criterion 4: a finding says WHAT it rests on, so its limits are readable."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)

    result = _run_check(cwd=clone)

    assert result.returncode == 4
    findings = [
        json.loads(line) for line in result.stderr.splitlines() if line.strip().startswith("{")
    ]
    fail_findings = [f for f in findings if f.get("status") == "fail"]
    assert fail_findings, f"expected a fail finding; stderr={result.stderr!r}"
    discriminators = {f.get("discriminator") for f in fail_findings}
    assert discriminators == {
        "patch-id equivalence (`git cherry`)"
    }, f"expected every finding to name the patch-id discriminator; got {discriminators!r}"
    assert "patch-id" in fail_findings[0].get("event", "")


def test_multiple_stale_branches_all_emit_findings(*, tmp_path: Path) -> None:
    """Two stale `spec/*` branches → exit 4, both surface in stderr findings."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    _make_branch_ahead(repo=clone, branch="spec/v004", commits=2)
    result = _run_check(cwd=clone)
    assert result.returncode == 4
    assert "spec/v003" in result.stderr
    assert "spec/v004" in result.stderr
    findings = [
        json.loads(line) for line in result.stderr.splitlines() if line.strip().startswith("{")
    ]
    fail_findings = [f for f in findings if f.get("status") == "fail"]
    branch_names = {f.get("branch") for f in fail_findings}
    assert branch_names == {
        "spec/v003",
        "spec/v004",
    }, f"expected fail findings for spec/v003 and spec/v004; got {branch_names!r}"


def test_abandoned_prefix_is_not_enumerated(*, tmp_path: Path) -> None:
    """`refs/heads/abandoned/spec/*` does NOT match `refs/heads/spec/*` → exit 0."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="abandoned/spec/old", commits=1)
    result = _run_check(cwd=clone)
    assert result.returncode == 0, (
        f"expected exit 0 when only abandoned/spec/* branches are present; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "abandoned/spec/old" not in result.stderr


def test_help_flag_exits_zero(*, tmp_path: Path) -> None:
    """`--help` exits 0 with usage text on stdout (per contracts.md section "CLI surface")."""
    result = _run_check(cwd=tmp_path, extra_argv=["--help"])
    assert result.returncode == 0
    assert "no-stale-revise-branches" in result.stdout or "usage" in result.stdout.lower()


def test_canonical_branch_from_livespec_jsonc(*, tmp_path: Path) -> None:
    """`.livespec.jsonc`'s `livespec-orchestrator-git-jsonl.canonical_branch` overrides default.

    The fixture also carries a DECOY impl-plugin block (listed first,
    pointing at a nonexistent branch) so the assertion discriminates the
    preferred-key lookup from the any-other-block fallback scan: only an
    implementation that PREFERS the `livespec-orchestrator-git-jsonl` block
    resolves canonical=main here.
    """
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _ = _git(cwd=remote, args=["init", "--bare", "-q", "--initial-branch=main"])
    seed = tmp_path / "seed"
    seed.mkdir()
    _ = _git(cwd=seed, args=["init", "-q", "--initial-branch=main"])
    _ = _git(cwd=seed, args=["config", "user.email", "test@example.com"])
    _ = _git(cwd=seed, args=["config", "user.name", "Test"])
    (seed / "README.md").write_text("baseline\n", encoding="utf-8")
    _ = _git(cwd=seed, args=["add", "README.md"])
    _ = _git(cwd=seed, args=["commit", "-m", "baseline"])
    _ = _git(cwd=seed, args=["remote", "add", "origin", str(remote)])
    _ = _git(cwd=seed, args=["push", "-u", "origin", "main"])
    clone = tmp_path / "clone"
    _ = _git(cwd=tmp_path, args=["clone", "-q", str(remote), str(clone)])
    _ = _git(cwd=clone, args=["config", "user.email", "test@example.com"])
    _ = _git(cwd=clone, args=["config", "user.name", "Test"])
    # Stale branch ahead of main, not master.
    _ = _git(cwd=clone, args=["checkout", "-q", "-b", "spec/v003", "main"])
    (clone / "change.txt").write_text("change\n", encoding="utf-8")
    _ = _git(cwd=clone, args=["add", "change.txt"])
    _ = _git(cwd=clone, args=["commit", "-m", "work"])
    _ = _git(cwd=clone, args=["checkout", "-q", "main"])
    # Write a .livespec.jsonc that pins canonical_branch to "main" in the
    # preferred `livespec-orchestrator-git-jsonl` block; the decoy block sits
    # FIRST so a fallback-order scan would elect its bogus branch.
    (clone / ".livespec.jsonc").write_text(
        "// hermetic test config\n"
        "{\n"
        '  "livespec-impl-decoy": {\n'
        '    "canonical_branch": "no-such-branch"\n'
        "  },\n"
        '  "livespec-orchestrator-git-jsonl": {\n'
        '    "canonical_branch": "main"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    result = _run_check(cwd=clone)
    assert result.returncode == 4, (
        f"expected exit 4 when canonical=main from .livespec.jsonc and spec/v003 is ahead; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "origin/main" in result.stderr


def test_canonical_branch_fallback_to_origin_head(*, tmp_path: Path) -> None:
    """No `.livespec.jsonc` → falls back to `origin/HEAD` symbolic-ref."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _ = _git(cwd=remote, args=["init", "--bare", "-q", "--initial-branch=trunk"])
    seed = tmp_path / "seed"
    seed.mkdir()
    _ = _git(cwd=seed, args=["init", "-q", "--initial-branch=trunk"])
    _ = _git(cwd=seed, args=["config", "user.email", "test@example.com"])
    _ = _git(cwd=seed, args=["config", "user.name", "Test"])
    (seed / "README.md").write_text("baseline\n", encoding="utf-8")
    _ = _git(cwd=seed, args=["add", "README.md"])
    _ = _git(cwd=seed, args=["commit", "-m", "baseline"])
    _ = _git(cwd=seed, args=["remote", "add", "origin", str(remote)])
    _ = _git(cwd=seed, args=["push", "-u", "origin", "trunk"])
    clone = tmp_path / "clone"
    _ = _git(cwd=tmp_path, args=["clone", "-q", str(remote), str(clone)])
    _ = _git(cwd=clone, args=["config", "user.email", "test@example.com"])
    _ = _git(cwd=clone, args=["config", "user.name", "Test"])
    # `git clone` defaults `origin/HEAD` to the cloned remote's default
    # branch ("trunk"), which the check should pick up. Build the stale
    # `spec/v003` branch directly off `trunk` (not `master`, which does
    # not exist in this hermetic remote).
    _ = _git(cwd=clone, args=["checkout", "-q", "-b", "spec/v003", "trunk"])
    (clone / "change.txt").write_text("change\n", encoding="utf-8")
    _ = _git(cwd=clone, args=["add", "change.txt"])
    _ = _git(cwd=clone, args=["commit", "-m", "work on spec/v003"])
    _ = _git(cwd=clone, args=["checkout", "-q", "trunk"])
    result = _run_check(cwd=clone)
    assert result.returncode == 4, (
        f"expected exit 4 with canonical=trunk via origin/HEAD; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "origin/trunk" in result.stderr


def test_canonical_branch_hard_coded_fallback_when_no_origin(*, tmp_path: Path) -> None:
    """No `.livespec.jsonc` and no `origin/HEAD` → falls back to `master`.

    With no remote configured, `git cherry origin/master <branch>` fails,
    the per-branch unlanded-count returns None, the check skips the branch
    with a warning, and exits 0 (no findings emitted).
    """
    repo = tmp_path / "solo"
    repo.mkdir()
    _ = _git(cwd=repo, args=["init", "-q", "--initial-branch=master"])
    _ = _git(cwd=repo, args=["config", "user.email", "test@example.com"])
    _ = _git(cwd=repo, args=["config", "user.name", "Test"])
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    _ = _git(cwd=repo, args=["add", "README.md"])
    _ = _git(cwd=repo, args=["commit", "-m", "baseline"])
    _make_branch_ahead(repo=repo, branch="spec/v003", commits=1)
    result = _run_check(cwd=repo)
    # No origin remote → the unlanded-count is None for the spec/v003
    # branch → branch is skipped with a warning → no stale-branch findings
    # → exit 0. This exercises the hard-coded `master` fallback branch
    # in `_resolve_canonical_branch`.
    assert result.returncode == 0, (
        f"expected exit 0 when origin is absent (warnings only); "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "could not evaluate landed-ness" in result.stderr


def test_jsonc_non_dict_top_level_falls_through(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` whose top-level is not an object → fallback chain continues."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    (clone / ".livespec.jsonc").write_text("// non-object root\n[]\n", encoding="utf-8")
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone)
    # Falls back through `origin/HEAD` (which is `master` for the clone)
    # → the stale branch is detected against origin/master.
    assert result.returncode == 4
    assert "origin/master" in result.stderr


def test_jsonc_other_impl_plugin_block_used_as_fallback(*, tmp_path: Path) -> None:
    """When `livespec-impl-git-jsonl` is absent, any other impl plugin block's key works."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    # No livespec-impl-git-jsonl block; instead a hypothetical sibling
    # impl plugin block carries the canonical_branch.
    (clone / ".livespec.jsonc").write_text(
        "{\n" '  "livespec-impl-other": {\n' '    "canonical_branch": "master"\n' "  }\n" "}\n",
        encoding="utf-8",
    )
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone)
    assert result.returncode == 4
    assert "origin/master" in result.stderr


def test_jsonc_empty_string_canonical_branch_ignored(*, tmp_path: Path) -> None:
    """An empty `canonical_branch` value → treated as absent, fallback continues."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    (clone / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-git-jsonl": {\n'
        '    "canonical_branch": ""\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone)
    # Falls back to origin/HEAD which is master for the clone.
    assert result.returncode == 4
    assert "origin/master" in result.stderr


def test_jsonc_non_dict_impl_plugin_block_skipped(*, tmp_path: Path) -> None:
    """A non-dict value under an impl-plugin key is skipped during the scan."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    (clone / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-impl-git-jsonl": "not a dict",\n'
        '  "livespec-impl-other": "also not a dict"\n'
        "}\n",
        encoding="utf-8",
    )
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone)
    # Falls all the way back to origin/HEAD (master).
    assert result.returncode == 4
    assert "origin/master" in result.stderr


def test_origin_head_returns_empty_stdout_falls_through(*, tmp_path: Path) -> None:
    """`git symbolic-ref` succeeds with empty stdout → fallback continues to default.

    Covers the `if not value: return None` branch in
    `_canonical_branch_from_origin_head`.
    """
    fake_path = _install_fake_git(
        tmp_path=tmp_path,
        symbolic_ref_stdout="",
        symbolic_ref_returncode=0,
        for_each_ref_stdout="",
        for_each_ref_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    # No spec/* branches → exit 0. The relevant assertion is that the
    # check ran to completion through the fall-through path.
    assert result.returncode == 0


def test_origin_head_returns_unprefixed_value(*, tmp_path: Path) -> None:
    """`git symbolic-ref` returns a non-`origin/`-prefixed value → returned verbatim.

    Covers the `return value` branch in
    `_canonical_branch_from_origin_head` (the unprefixed-fallthrough
    branch reached when the stdout, after strip, lacks the canonical
    `origin/` prefix).
    """
    fake_path = _install_fake_git(
        tmp_path=tmp_path,
        symbolic_ref_stdout="trunk",
        symbolic_ref_returncode=0,
        for_each_ref_stdout="spec/v003",
        for_each_ref_returncode=0,
        # `git cherry origin/trunk spec/v003` fails under the stub, so the
        # per-branch unlanded-count is unavailable and the branch skips.
        # Branch coverage for the unprefixed value handling is what we need.
        cherry_stdout="",
        cherry_returncode=1,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    # The unlanded-count is None → branch skipped with warning → exit 0.
    assert result.returncode == 0
    assert "trunk" in result.stderr  # diagnostic mentions origin/trunk via the warning


def test_for_each_ref_failure_returns_empty_list(*, tmp_path: Path) -> None:
    """`git for-each-ref` failure → empty branch list → exit 0.

    Covers the `if completed.returncode != 0: return []` branch in
    `_enumerate_spec_branches`.
    """
    fake_path = _install_fake_git(
        tmp_path=tmp_path,
        symbolic_ref_stdout="origin/master",
        symbolic_ref_returncode=0,
        for_each_ref_stdout="",
        for_each_ref_returncode=128,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0


def test_cherry_malformed_output_skips_branch(*, tmp_path: Path) -> None:
    """`git cherry` emits a line in neither `+ `/`- ` form → branch skipped, exit 0.

    Covers the unrecognized-line arm of the unlanded-count parse. Skipping
    is the fail-safe direction here: an unparseable answer must not be read
    as "nothing unlanded" and wave a real stale branch through.
    """
    fake_path = _install_fake_git(
        tmp_path=tmp_path,
        symbolic_ref_stdout="origin/master",
        symbolic_ref_returncode=0,
        for_each_ref_stdout="spec/v003",
        for_each_ref_returncode=0,
        cherry_stdout="garbage",
        cherry_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "could not evaluate landed-ness" in result.stderr


def test_cherry_all_landed_lines_pass(*, tmp_path: Path) -> None:
    """`git cherry` reporting only `- ` lines → nothing unlanded → exit 0.

    The `- ` prefix is git's own "an equivalent patch IS upstream" verdict,
    which is the whole discriminator stated in one line of plumbing output.
    """
    fake_path = _install_fake_git(
        tmp_path=tmp_path,
        symbolic_ref_stdout="origin/master",
        symbolic_ref_returncode=0,
        for_each_ref_stdout="spec/v003",
        for_each_ref_returncode=0,
        cherry_stdout="- 1111111111111111111111111111111111111111",
        cherry_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "spec/v003" not in result.stderr


def test_cherry_blank_lines_are_ignored(*, tmp_path: Path) -> None:
    """A blank line in `git cherry` output is not an unparseable line → exit 0.

    Covers the blank-line arm of the parse; the stub's heredoc emits exactly
    the trailing-newline-only shape a no-op `git cherry` produces.
    """
    fake_path = _install_fake_git(
        tmp_path=tmp_path,
        symbolic_ref_stdout="origin/master",
        symbolic_ref_returncode=0,
        for_each_ref_stdout="spec/v003",
        for_each_ref_returncode=0,
        cherry_stdout="",
        cherry_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "could not evaluate landed-ness" not in result.stderr


def test_jsonc_canonical_branch_non_string_value_falls_through(*, tmp_path: Path) -> None:
    """A `canonical_branch` value of non-string type is ignored; fallback continues.

    Covers the `if isinstance(value, str) and value` False-branch in the
    preferred-block path of `_canonical_branch_from_jsonc` (where the
    key is present but the value is e.g. an integer).
    """
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    (clone / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-git-jsonl": {\n'
        '    "canonical_branch": 42\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone)
    assert result.returncode == 4
    assert "origin/master" in result.stderr


def test_jsonc_other_impl_plugin_canonical_branch_non_string(*, tmp_path: Path) -> None:
    """A non-string `canonical_branch` under a non-preferred block is ignored.

    Covers the `if isinstance(candidate, str) and candidate` False-branch
    in the `for key, value in parsed.items()` loop.
    """
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    (clone / ".livespec.jsonc").write_text(
        "{\n" '  "livespec-impl-other": {\n' '    "canonical_branch": 99\n' "  }\n" "}\n",
        encoding="utf-8",
    )
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone)
    assert result.returncode == 4
    assert "origin/master" in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly via importlib (covers __name__ != "__main__" branch)."""
    import importlib.util

    module_name = "no_stale_revise_branches_for_import_test"
    spec = importlib.util.spec_from_file_location(module_name, str(_CHECK))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec_module so dataclasses can
    # resolve string annotations under `from __future__ import annotations`
    # (it looks the module up via `sys.modules[cls.__module__]`).
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        assert callable(module.main)
    finally:
        sys.modules.pop(module_name, None)


def test_module_re_import_with_vendor_in_sys_path() -> None:
    """Re-importing when _VENDOR_DIR is already on sys.path covers the False branch."""
    import importlib.util

    name1 = "no_stale_revise_branches_first_import"
    spec1 = importlib.util.spec_from_file_location(name1, str(_CHECK))
    assert spec1 is not None and spec1.loader is not None
    module1 = importlib.util.module_from_spec(spec1)
    sys.modules[name1] = module1
    try:
        spec1.loader.exec_module(module1)
        name2 = "no_stale_revise_branches_second_import"
        spec2 = importlib.util.spec_from_file_location(name2, str(_CHECK))
        assert spec2 is not None and spec2.loader is not None
        module2 = importlib.util.module_from_spec(spec2)
        sys.modules[name2] = module2
        try:
            spec2.loader.exec_module(module2)
            assert callable(module2.main)
        finally:
            sys.modules.pop(name2, None)
    finally:
        sys.modules.pop(name1, None)
