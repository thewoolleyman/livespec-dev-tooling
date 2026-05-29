"""Outside-in test for `dev-tooling/checks/branch_protection_alignment.py`.

Guard Layer 1 mechanical check that prevents the v039-D1-style
drift between `.github/workflows/ci.yml`'s job matrix and master
branch protection's required-checks list.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "branch_protection_alignment.py"


def _run_check(*, cwd: Path, env_path: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run the check script with cwd set to tmp_path (or any path).

    Preserves the parent env (incl. COVERAGE_PROCESS_START) so pytest-cov's
    subprocess auto-init works; overrides only PATH when env_path is given.
    """
    env = {**os.environ, "PATH": env_path} if env_path is not None else None
    return subprocess.run(
        [sys.executable, str(_CHECK)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_missing_ci_yml_is_graceful(*, tmp_path: Path) -> None:
    """Empty cwd → ci.yml missing → exit 0 (graceful absence-handling).

    Per epic li-univck Phase 1.1 (li-chkabs), every canonical check
    MUST exit 0 cleanly when its precondition is absent so the check
    is safe to wire universally across the fleet. Consumers that have
    not configured GitHub Actions CI have no `.github/workflows/ci.yml`;
    the branch-protection alignment invariant is vacuously satisfied.
    """
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 0, (
        f"expected exit 0 on missing ci.yml (graceful absence-handling); "
        f"got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_empty_matrix_fails(*, tmp_path: Path) -> None:
    """ci.yml exists but has no parseable matrix → exit 1."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    _ = (workflows / "ci.yml").write_text("name: CI\non: push\n", encoding="utf-8")
    result = _run_check(cwd=tmp_path)
    assert result.returncode == 1, (
        f"expected exit 1 on empty matrix; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "matrix.target" in result.stderr


def test_gh_unavailable_skips_gracefully(*, tmp_path: Path) -> None:
    """No `gh` on PATH → exit 0 with a warning (local-dev tolerance)."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    ci_yml = textwrap.dedent("""\
        name: CI
        on: push
        jobs:
          check:
            strategy:
              matrix:
                target:
                  - check-foo
                  - check-bar
            runs-on: ubuntu-latest
        """)
    _ = (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")
    # Empty PATH → gh CLI not found by shutil.which.
    result = _run_check(cwd=tmp_path, env_path="")
    assert result.returncode == 0, (
        f"expected exit 0 when gh unavailable; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "gh CLI not on PATH" in result.stderr


def test_real_repo_passes(*, tmp_path: Path) -> None:  # noqa: ARG001
    """Run the check against the real repo cwd; expect exit 0.

    With the path-portability refactor, the check resolves the
    target repository from `git remote get-url origin` rather than
    a hardcoded constant. Authenticated `gh` produces either pass
    (no missing-from-ci.yml) or warning-only output. With `gh`
    unauthenticated OR with no branch protection set on master,
    the check still exits 0 (graceful skip). Either way: exit 0.
    """
    result = _run_check(cwd=_REPO_ROOT)
    assert result.returncode == 0, (
        f"expected exit 0 against real repo; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def _setup_repo_with_ci_yml(*, tmp_path: Path, matrix_targets: list[str]) -> None:
    """Write a synthetic ci.yml with the given matrix.target list."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    target_lines = "\n".join(f"          - {t}" for t in matrix_targets)
    ci_yml = (
        "name: CI\n"
        "on: push\n"
        "jobs:\n"
        "  check:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        f"{target_lines}\n"
        "    runs-on: ubuntu-latest\n"
    )
    _ = (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")


def _install_fake_gh(
    *,
    tmp_path: Path,
    stdout: str = "[]",
    stderr: str = "",
    returncode: int = 0,
    git_origin_url: str = "https://github.com/test-owner/test-repo.git",
    git_returncode: int = 0,
) -> str:
    """Install fake `gh` + `git` shell stubs at tmp_path/bin, return PATH including it.

    Both stubs are needed because the check resolves its target
    repository identifier from `git remote get-url origin` before
    invoking `gh api`. The git stub responds to `git remote get-url
    origin` with `git_origin_url` and the given `git_returncode`;
    every other git invocation exits 0 as a no-op so other code
    paths (e.g., subprocess-cov instrumentation hooks) are unaffected.

    The gh stub writes `stdout` to its stdout and `stderr` to its
    stderr, mirroring real `gh api`, which on an error puts the JSON
    error body on stdout AND a human `gh: <message> (HTTP <code>)`
    line on stderr.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    gh_stderr_block = "" if not stderr else f"cat >&2 <<'STUB_ERR_EOF'\n{stderr}\nSTUB_ERR_EOF\n"
    gh_script = (
        "#!/bin/sh\n"
        f"cat <<'STUB_EOF'\n{stdout}\nSTUB_EOF\n"
        f"{gh_stderr_block}"
        f"exit {returncode}\n"
    )
    _ = gh_path.write_text(gh_script, encoding="utf-8")
    gh_path.chmod(0o755)
    git_path = bin_dir / "git"
    git_script = (
        "#!/bin/sh\n"
        'if [ "$1" = "remote" ] && [ "$2" = "get-url" ] && [ "$3" = "origin" ]; then\n'
        f"  printf '%s\\n' '{git_origin_url}'\n"
        f"  exit {git_returncode}\n"
        "fi\n"
        "exit 0\n"
    )
    _ = git_path.write_text(git_script, encoding="utf-8")
    git_path.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def test_required_missing_from_ci_yml_fails(*, tmp_path: Path) -> None:
    """Required check absent from ci.yml matrix → exit 4 (check failed).

    Exit 4 is the documented "check failed (structured findings on
    stderr)" code (SPECIFICATION/contracts.md §"Exit-code table"),
    shared with the new protection-absent fail branch and with the
    sibling CI-alignment checks (`no_stale_revise_branches`,
    `primary_checkout_commit_refuse_hook_installed`).
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='["check-foo", "check-missing"]',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 4, (
        f"expected exit 4 when required check missing from ci.yml; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "check-missing" in result.stderr
    assert "required check has no matching ci.yml job" in result.stderr
    assert "required_check_missing_from_ci" in result.stderr


def test_aligned_lists_pass(*, tmp_path: Path) -> None:
    """Required list and ci.yml matrix match exactly → exit 0, no warnings.

    The protection-present + aligned case: the API succeeds and the
    required-checks list matches the ci.yml matrix exactly, so neither
    the protection-absent fail branch nor the alignment fail branch
    fires.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo", "check-bar"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='["check-foo", "check-bar"]',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "required check has no matching" not in result.stderr
    assert "no branch protection" not in result.stderr


def test_protection_absent_fails(*, tmp_path: Path) -> None:
    """API definitively reports master is unprotected → exit 4 (check failed).

    GitHub's branch-protection endpoints return the canonical
    `{"message": "Branch not protected", ..., "status": "404"}` body
    (and a `gh: Branch not protected (HTTP 404)` stderr line) ONLY when
    an admin-scoped token reads a genuinely unprotected branch. That is
    a definitive "absent" answer, so the check MUST fail rather than
    skip: an unprotected master lets PRs auto-merge before CI finishes
    and lets a red PR land. Cites the new merge-gate NFR.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=(
            '{"message": "Branch not protected", '
            '"documentation_url": "https://docs.github.com/rest", "status": "404"}'
        ),
        stderr="gh: Branch not protected (HTTP 404)",
        returncode=1,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 4, (
        f"expected exit 4 when master is definitively unprotected; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "no branch protection" in result.stderr
    assert "protection_absent" in result.stderr


def test_permission_error_skips_gracefully(*, tmp_path: Path) -> None:
    """API errors with a non-definitive 404 (no admin read access) → exit 0 skip.

    The default Actions `GITHUB_TOKEN` lacks the admin scope needed to
    READ branch protection; GitHub returns a generic `Not Found` /
    `Resource not accessible by integration` rather than the canonical
    `Branch not protected`. The check CANNOT distinguish "absent" from
    "can't-read" in this case, so it MUST skip (exit 0), not fail.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=(
            '{"message": "Resource not accessible by integration", '
            '"documentation_url": "https://docs.github.com/rest", "status": "403"}'
        ),
        stderr="gh: Resource not accessible by integration (HTTP 403)",
        returncode=1,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0, (
        f"expected exit 0 when protection is unreadable (no admin scope); "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "cannot distinguish absent protection from missing read access" in result.stderr
    assert "no branch protection" not in result.stderr


def test_blank_and_comment_lines_in_matrix_are_skipped(*, tmp_path: Path) -> None:
    """Blank lines and `# comment` lines within the matrix target bullets are skipped.

    Exercises the in-bullet-list `continue` branch in
    `_parse_ci_matrix` so an author may insert blank lines or
    comments to group jobs without breaking the parser.
    """
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    ci_yml = (
        "name: CI\n"
        "on: push\n"
        "jobs:\n"
        "  check:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        "          # a comment line\n"
        "          - check-foo\n"
        "\n"
        "          - check-bar\n"
        "    runs-on: ubuntu-latest\n"
    )
    _ = (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='["check-foo", "check-bar"]',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0, (
        f"expected exit 0 with blank/comment lines in matrix; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "required check has no matching" not in result.stderr


def test_extra_ci_job_warns(*, tmp_path: Path) -> None:
    """ci.yml has a job not in required list → exit 0 with warning."""
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo", "check-extra"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='["check-foo"]',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "check-extra" in result.stderr
    assert "not in branch-protection required list" in result.stderr


def test_gh_api_failure_skips_gracefully(*, tmp_path: Path) -> None:
    """gh available but API call fails → exit 0 with warning."""
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout="error", returncode=1)
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "gh api call failed" in result.stderr


def test_git_remote_failure_skips_gracefully(*, tmp_path: Path) -> None:
    """git available but `git remote get-url origin` fails → exit 0 with warning.

    Closes the `completed.returncode != 0` branch of
    `_resolve_owner_repo`: a tmp_path that is not a git work tree
    (or any other condition that produces a non-zero git exit)
    MUST skip cleanly rather than fail the check.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(tmp_path=tmp_path, git_returncode=128)
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0, (
        f"expected exit 0 when git remote fails; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "git remote get-url origin failed" in result.stderr


def test_non_github_remote_skips_gracefully(*, tmp_path: Path) -> None:
    """git returns a non-github.com remote URL → exit 0 with warning.

    Closes the `match is None` branch of `_resolve_owner_repo`:
    forks hosted on GitLab, self-hosted Gitea, mirrors, etc. fall
    outside this check's scope and MUST skip cleanly. Uses a
    gitlab.com URL as the canonical non-github example.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        git_origin_url="https://gitlab.com/some-org/some-repo.git",
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0, (
        f"expected exit 0 on non-github remote; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "origin URL did not match github.com pattern" in result.stderr


def test_unexpected_payload_shape(*, tmp_path: Path) -> None:
    """gh returns non-list payload → exit 0 with error log (no enforcement)."""
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout='{"not": "a list"}')
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "unexpected gh api response shape" in result.stderr


def test_payload_with_non_string_entries(*, tmp_path: Path) -> None:
    """gh list contains non-string entries → silently skip them (covers the False branch)."""
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='["check-foo", 42, null, "check-bar"]',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    # Only "check-foo" and "check-bar" are extracted as required;
    # ci.yml has only "check-foo", so "check-bar" is missing → exit 4.
    assert result.returncode == 4
    assert "check-bar" in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly via importlib (covers __name__ != "__main__" branch)."""
    import importlib.util

    module_name = "branch_protection_alignment_for_import_test"
    spec = importlib.util.spec_from_file_location(module_name, str(_CHECK))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec_module so the module's
    # dataclasses can resolve string annotations under
    # `from __future__ import annotations` (the dataclass machinery
    # looks the module up via `sys.modules[cls.__module__]`).
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        assert callable(module.main)
    finally:
        sys.modules.pop(module_name, None)


def test_module_re_import_with_vendor_in_sys_path() -> None:
    """Re-importing the module when _VENDOR_DIR is already on sys.path covers the False branch."""
    import importlib.util

    # First import — primes sys.path with _VENDOR_DIR (True branch of the guard).
    name1 = "branch_protection_alignment_first_import"
    spec1 = importlib.util.spec_from_file_location(name1, str(_CHECK))
    assert spec1 is not None and spec1.loader is not None
    module1 = importlib.util.module_from_spec(spec1)
    sys.modules[name1] = module1
    try:
        spec1.loader.exec_module(module1)
        # Second import — _VENDOR_DIR is already on sys.path, exercises the False branch.
        name2 = "branch_protection_alignment_second_import"
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
