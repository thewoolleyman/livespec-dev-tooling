"""Outside-in test for `livespec_dev_tooling/checks/no_stale_revise_branches.py`.

Per `SPECIFICATION/proposed_changes/no-stale-revise-branches-check.md`
(child PC of livespec's `coordinating-epic-stale-revise-enforcement`),
the check enumerates local `refs/heads/spec/*` branches and fails when
any such branch is ahead of the canonical branch.

Test scenarios:

- No `spec/*` branches in the repo → exit 0.
- One `spec/*` branch even with origin/master (ahead=0) → exit 0.
- One `spec/*` branch ahead of origin/master by 1 → exit 4 with finding.
- Multiple stale branches → exit 4 with one finding per stale branch.
- `refs/heads/abandoned/spec/*` does NOT match the canonical pattern → exit 0.
- `--allow-stale-branches` override → exit 0 even with stale branches.
- `--help` / `-h` exits 0 with usage on stdout.
- `.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch` resolves
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
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_stale_revise_branches.py"


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


def _run_check(
    *,
    cwd: Path,
    extra_argv: list[str] | None = None,
    env_path: str | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(_CHECK)]
    if extra_argv is not None:
        argv.extend(extra_argv)
    env = {**os.environ, "PATH": env_path} if env_path is not None else None
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
    rev_list_stdout: str = "",
    rev_list_returncode: int = 0,
) -> str:
    """Install a fake `git` shell stub at tmp_path/bin/git; return PATH including it.

    Dispatches on argv[1] (`symbolic-ref`, `for-each-ref`, `rev-list`)
    and emits the configured stdout/returncode. Falls through to a
    real `/usr/bin/git` for everything else (`rev-parse`, `log`, etc.)
    so subordinate helpers still produce sensible output.
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
        "  rev-list)\n"
        f"    cat <<'STUB_EOF'\n{rev_list_stdout}\nSTUB_EOF\n"
        f"    exit {rev_list_returncode}\n"
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


def test_no_spec_branches_passes(*, tmp_path: Path) -> None:
    """A clone with only `master` and no `spec/*` branches → exit 0."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    result = _run_check(cwd=clone)
    assert result.returncode == 0, (
        f"expected exit 0 when no spec/* branches exist; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )


def test_even_spec_branch_passes(*, tmp_path: Path) -> None:
    """A `spec/*` branch even with `master` (ahead=0) → exit 0, no findings."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _ = _git(cwd=clone, args=["checkout", "-q", "-b", "spec/in-sync", "master"])
    _ = _git(cwd=clone, args=["checkout", "-q", "master"])
    result = _run_check(cwd=clone)
    assert result.returncode == 0, (
        f"expected exit 0 when spec/* branch is even with master; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "is 1 commit" not in result.stderr


def test_single_stale_branch_fails(*, tmp_path: Path) -> None:
    """One `spec/*` branch ahead of master by 1 → exit 4, finding lists branch."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone)
    assert result.returncode == 4, (
        f"expected exit 4 with one stale branch; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "spec/v003" in result.stderr
    assert "1 commit" in result.stderr


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


def test_allow_stale_branches_override_exits_zero(*, tmp_path: Path) -> None:
    """`--allow-stale-branches` → exit 0 even when stale branches exist, info-level only."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    _make_branch_ahead(repo=clone, branch="spec/v003", commits=1)
    result = _run_check(cwd=clone, extra_argv=["--allow-stale-branches"])
    assert (
        result.returncode == 0
    ), f"expected exit 0 with override; got {result.returncode}, stderr={result.stderr!r}"
    # The finding still surfaces, but as info-level (not error-level).
    findings = [
        json.loads(line) for line in result.stderr.splitlines() if line.strip().startswith("{")
    ]
    info_findings = [f for f in findings if f.get("status") == "info"]
    assert any(f.get("branch") == "spec/v003" for f in info_findings)
    assert not any(f.get("status") == "fail" for f in findings)


def test_help_flag_exits_zero(*, tmp_path: Path) -> None:
    """`--help` exits 0 with usage text on stdout (per contracts.md §"CLI surface")."""
    result = _run_check(cwd=tmp_path, extra_argv=["--help"])
    assert result.returncode == 0
    assert "no-stale-revise-branches" in result.stdout or "usage" in result.stdout.lower()


def test_canonical_branch_from_livespec_jsonc(*, tmp_path: Path) -> None:
    """`.livespec.jsonc`'s `livespec-impl-plaintext.canonical_branch` overrides default."""
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
    # Write a .livespec.jsonc that pins canonical_branch to "main".
    (clone / ".livespec.jsonc").write_text(
        "// hermetic test config\n"
        "{\n"
        '  "livespec-impl-plaintext": {\n'
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

    With no remote configured, `git rev-list origin/master...<branch>`
    fails, the per-branch ahead-count returns None, the check skips the
    branch with a warning, and exits 0 (no findings emitted).
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
    # No origin remote → ahead-count is None for the spec/v003 branch
    # → branch is skipped with a warning → no stale-branch findings →
    # exit 0. This exercises the hard-coded `master` fallback branch
    # in `_resolve_canonical_branch`.
    assert result.returncode == 0, (
        f"expected exit 0 when origin is absent (warnings only); "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "could not compute ahead-count" in result.stderr


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
    """When `livespec-impl-plaintext` is absent, any other impl plugin block's key works."""
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    # No livespec-impl-plaintext block; instead a hypothetical sibling
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
        "{\n" '  "livespec-impl-plaintext": {\n' '    "canonical_branch": ""\n' "  }\n" "}\n",
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
        '  "livespec-impl-plaintext": "not a dict",\n'
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
        # rev-list will be called with `origin/trunk...spec/v003`; the
        # stub returns nothing successful, so the per-branch ahead-count
        # parses 0 entries and skips. Branch coverage for the unprefixed
        # value handling is what we need.
        rev_list_stdout="",
        rev_list_returncode=1,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    # ahead_count is None → branch skipped with warning → exit 0.
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


def test_rev_list_malformed_output_skips_branch(*, tmp_path: Path) -> None:
    """`git rev-list` returns malformed (non-2-part) output → branch skipped, exit 0.

    Covers the `if len(parts) != 2: return None` branch in `_ahead_count`.
    """
    fake_path = _install_fake_git(
        tmp_path=tmp_path,
        symbolic_ref_stdout="origin/master",
        symbolic_ref_returncode=0,
        for_each_ref_stdout="spec/v003",
        for_each_ref_returncode=0,
        rev_list_stdout="garbage",
        rev_list_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "could not compute ahead-count" in result.stderr


def test_rev_list_non_digit_ahead_skips_branch(*, tmp_path: Path) -> None:
    """`git rev-list` returns 2 parts but ahead is non-digit → skipped, exit 0.

    Covers the `if not ahead_raw.isdigit(): return None` branch in `_ahead_count`.
    """
    fake_path = _install_fake_git(
        tmp_path=tmp_path,
        symbolic_ref_stdout="origin/master",
        symbolic_ref_returncode=0,
        for_each_ref_stdout="spec/v003",
        for_each_ref_returncode=0,
        rev_list_stdout="0\tabc",
        rev_list_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "could not compute ahead-count" in result.stderr


def test_jsonc_canonical_branch_non_string_value_falls_through(*, tmp_path: Path) -> None:
    """A `canonical_branch` value of non-string type is ignored; fallback continues.

    Covers the `if isinstance(value, str) and value` False-branch in the
    preferred-block path of `_canonical_branch_from_jsonc` (where the
    key is present but the value is e.g. an integer).
    """
    _, clone = _make_remote_and_clone(tmp_path=tmp_path)
    (clone / ".livespec.jsonc").write_text(
        "{\n" '  "livespec-impl-plaintext": {\n' '    "canonical_branch": 42\n' "  }\n" "}\n",
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
