"""Outside-in test for `livespec_dev_tooling/tdd_commit.py` — TDD-ritual helper.

`tdd_commit` mechanizes the Red-commit-then-Green-amend ritual: it stages
the test file ALONE and commits (Red), then stages the impl file(s) and
amends (Green), producing one commit that carries the test, the impl, and
(in a hooked repo) both `TDD-Red-*` / `TDD-Green-*` trailer sets.

These tests drive the helper against a throwaway `tmp_path` git repo that
has NO lefthook / red-green-replay hooks installed, so they exercise the
helper's orchestration mechanics (stage-test-alone → commit → stage-impl →
amend) directly. The `git_prefix=["git"]` argument runs a bare git (the
`--no-mise` equivalent) since the fixture repo has no `mise` config. A fake
`git` shim covers the per-step failure branches.

Coverage target: 100% line + branch of `tdd_commit.py`.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

from livespec_dev_tooling import tdd_commit

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "tdd_commit.py"


# When this test suite runs inside a git hook (lefthook pre-commit /
# pre-push / commit-msg), git sets GIT_DIR / GIT_WORK_TREE /
# GIT_INDEX_FILE / friends pointing at the SURROUNDING repo. These vars
# are inherited by subprocess children and would redirect every `git ...`
# call to the outer repo instead of the tmp_path mini-repo the test
# constructs. Scrubbing them confines git to the fixture's `.git`. Mirrors
# the discipline in `test_red_green_replay.py`.
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


def _scrubbed_env() -> dict[str, str]:
    """Return a copy of `os.environ` with GIT_* hook vars removed."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}


def _init_repo(*, repo: Path) -> None:
    """Initialize a throwaway git repo with a committed baseline."""
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True, env=_scrubbed_env())
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"],
        cwd=str(repo),
        check=True,
        env=_scrubbed_env(),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo),
        check=True,
        env=_scrubbed_env(),
    )
    # A baseline commit so the Red commit is not the repo's root commit
    # (keeps `git commit --amend` semantics ordinary).
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True, env=_scrubbed_env())
    subprocess.run(
        ["git", "commit", "-m", "chore: baseline"],
        cwd=str(repo),
        check=True,
        env=_scrubbed_env(),
    )


def _commit_subjects(*, repo: Path) -> list[str]:
    """Return the repo's commit subjects, newest first."""
    result = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=_scrubbed_env(),
    )
    return [line for line in result.stdout.splitlines() if line]


def _files_in_head(*, repo: Path) -> set[str]:
    """Return the set of file paths tracked at HEAD."""
    result = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=_scrubbed_env(),
    )
    return {line for line in result.stdout.splitlines() if line}


def _write_fake_git(*, path: Path, fail_on_subcommand: str) -> None:
    """Write an executable fake-`git` shim that fails on one subcommand.

    The shim exits non-zero (with a recognizable stderr token) when its
    first argument equals `fail_on_subcommand`, and exits 0 otherwise.
    Used to drive `run_tdd_commit`'s per-step failure-return branches
    without a real git failure.
    """
    path.write_text(
        "#!/usr/bin/env bash\n"
        f'if [ "$1" = "{fail_on_subcommand}" ]; then\n'
        '  echo "fake-git: forced failure on $1" >&2\n'
        "  exit 17\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Happy path — full Red→Green ritual against a real (hook-less) tmp repo.
# ---------------------------------------------------------------------------


def test_run_tdd_commit_produces_single_commit_with_test_and_impl(*, tmp_path: Path) -> None:
    """The ritual yields ONE commit carrying both the test and the impl file."""
    _init_repo(repo=tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text(
        "def test_foo() -> None:\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "foo.py").write_text("VALUE: int = 1\n", encoding="utf-8")

    exit_code = tdd_commit.run_tdd_commit(
        repo=tmp_path,
        test_path="tests/test_foo.py",
        impl_paths=["foo.py"],
        subject="feat: add foo",
        git_prefix=["git"],
        env=_scrubbed_env(),
    )

    assert exit_code == 0, f"ritual should succeed; got exit_code={exit_code}"
    subjects = _commit_subjects(repo=tmp_path)
    # Exactly two commits total: the baseline + the single feature commit
    # (the Green amend folds into the Red commit, not a third commit).
    assert subjects == [
        "feat: add foo",
        "chore: baseline",
    ], f"expected a single feature commit amended onto baseline; got {subjects!r}"
    head_files = _files_in_head(repo=tmp_path)
    assert "tests/test_foo.py" in head_files, f"test file must be in the commit; got {head_files!r}"
    assert "foo.py" in head_files, f"impl file must be in the commit; got {head_files!r}"


def test_run_tdd_commit_amends_multiple_impl_files(*, tmp_path: Path) -> None:
    """Repeated `--impl` paths all land in the single Green-amended commit."""
    _init_repo(repo=tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_bar.py").write_text(
        "def test_bar() -> None:\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "bar.py").write_text("A: int = 1\n", encoding="utf-8")
    (tmp_path / "baz.py").write_text("B: int = 2\n", encoding="utf-8")

    exit_code = tdd_commit.run_tdd_commit(
        repo=tmp_path,
        test_path="tests/test_bar.py",
        impl_paths=["bar.py", "baz.py"],
        subject="fix: add bar and baz",
        git_prefix=["git"],
        env=_scrubbed_env(),
    )

    assert exit_code == 0
    head_files = _files_in_head(repo=tmp_path)
    assert (
        {"tests/test_bar.py", "bar.py", "baz.py"} <= head_files
    ), f"all impl files plus the test must be in the single commit; got {head_files!r}"
    assert _commit_subjects(repo=tmp_path) == ["fix: add bar and baz", "chore: baseline"]


# ---------------------------------------------------------------------------
# Per-step failure branches — each returns the failing git exit code.
# ---------------------------------------------------------------------------


def test_run_tdd_commit_red_add_failure_returns_nonzero(*, tmp_path: Path) -> None:
    """A failure on the Red `git add` short-circuits and returns its exit code."""
    fake_git = tmp_path / "fake-git"
    _write_fake_git(path=fake_git, fail_on_subcommand="add")

    exit_code = tdd_commit.run_tdd_commit(
        repo=tmp_path,
        test_path="tests/test_x.py",
        impl_paths=["x.py"],
        subject="feat: x",
        git_prefix=[str(fake_git)],
        env=_scrubbed_env(),
    )

    assert exit_code == 17, f"red-add failure must propagate the git exit code; got {exit_code}"


def test_run_tdd_commit_red_commit_failure_returns_nonzero(*, tmp_path: Path) -> None:
    """A failure on the Red `git commit` short-circuits before the Green steps.

    Mirrors a real red-green-replay `test-passed-at-red` rejection: the
    commit-msg hook rejects the Red commit, so the ritual stops with that
    non-zero code.
    """
    fake_git = tmp_path / "fake-git"
    _write_fake_git(path=fake_git, fail_on_subcommand="commit")

    exit_code = tdd_commit.run_tdd_commit(
        repo=tmp_path,
        test_path="tests/test_x.py",
        impl_paths=["x.py"],
        subject="feat: x",
        git_prefix=[str(fake_git)],
        env=_scrubbed_env(),
    )

    assert exit_code == 17, f"red-commit failure must propagate the git exit code; got {exit_code}"


def test_run_tdd_commit_green_add_failure_returns_nonzero(*, tmp_path: Path) -> None:
    """A failure on the Green `git add` (after a clean Red) returns its exit code.

    The fake git succeeds for `add` of the test (the shim only fails on a
    chosen subcommand, so to isolate the GREEN add we drive a real repo
    where the impl path does not exist, making the second `git add`
    fail).
    """
    _init_repo(repo=tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "def test_x() -> None:\n    assert True\n", encoding="utf-8"
    )

    exit_code = tdd_commit.run_tdd_commit(
        repo=tmp_path,
        test_path="tests/test_x.py",
        impl_paths=["does_not_exist.py"],
        subject="feat: x",
        git_prefix=["git"],
        env=_scrubbed_env(),
    )

    assert exit_code != 0, f"green-add of a missing impl path must fail; got {exit_code}"
    # The Red commit DID land (the ritual short-circuits at green-add).
    assert _commit_subjects(repo=tmp_path) == ["feat: x", "chore: baseline"]


def test_run_tdd_commit_green_amend_failure_returns_nonzero(*, tmp_path: Path) -> None:
    """A failure on the Green `git commit --amend` returns its exit code.

    A subcommand-keyed shim cannot isolate the amend (its `commit` would
    also fail the Red commit). So this shim fails only when `--amend`
    appears in argv: `add` and the Red `commit` succeed, and the Green
    amend is the single rejected step.
    """
    fake_git = tmp_path / "fake-git"
    # Fail only when `--amend` appears in argv (the Green step); `add` and
    # the Red `commit` succeed.
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        'for arg in "$@"; do\n'
        '  if [ "$arg" = "--amend" ]; then\n'
        '    echo "fake-git: forced amend failure" >&2\n'
        "    exit 23\n"
        "  fi\n"
        "done\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    exit_code = tdd_commit.run_tdd_commit(
        repo=tmp_path,
        test_path="tests/test_x.py",
        impl_paths=["x.py"],
        subject="feat: x",
        git_prefix=[str(fake_git)],
        env=_scrubbed_env(),
    )

    assert exit_code == 23, f"green-amend failure must propagate the git exit code; got {exit_code}"


# ---------------------------------------------------------------------------
# `_resolve_git_prefix` — precedence of env override / --no-mise / default.
# ---------------------------------------------------------------------------


def test_resolve_git_prefix_defaults_to_mise_exec() -> None:
    """With no override and no --no-mise, the prefix is `mise exec -- git`."""
    prefix = tdd_commit._resolve_git_prefix(no_mise=False, env={})  # noqa: SLF001
    assert prefix == ["mise", "exec", "--", "git"], f"unexpected default prefix: {prefix!r}"


def test_resolve_git_prefix_no_mise_uses_bare_git() -> None:
    """`--no-mise` selects a bare `git` invocation."""
    prefix = tdd_commit._resolve_git_prefix(no_mise=True, env={})  # noqa: SLF001
    assert prefix == ["git"], f"--no-mise should yield bare git; got {prefix!r}"


def test_resolve_git_prefix_env_override_wins() -> None:
    """A non-blank `LIVESPEC_TDD_COMMIT_GIT` env override wins over --no-mise."""
    prefix = tdd_commit._resolve_git_prefix(  # noqa: SLF001
        no_mise=True,
        env={"LIVESPEC_TDD_COMMIT_GIT": "/usr/bin/env git"},
    )
    assert prefix == ["/usr/bin/env", "git"], f"env override should win; got {prefix!r}"


def test_resolve_git_prefix_blank_env_override_ignored() -> None:
    """A blank/whitespace env override is ignored (falls back to --no-mise/default)."""
    prefix = tdd_commit._resolve_git_prefix(  # noqa: SLF001
        no_mise=False,
        env={"LIVESPEC_TDD_COMMIT_GIT": "   "},
    )
    assert prefix == [
        "mise",
        "exec",
        "--",
        "git",
    ], f"blank override must fall through to default; got {prefix!r}"


# ---------------------------------------------------------------------------
# `_scrubbed_git_env` — strips GIT_* hook-passthrough vars, keeps the rest.
# ---------------------------------------------------------------------------


def test_scrubbed_git_env_removes_git_passthrough_vars() -> None:
    """Every GIT_* hook-passthrough var is dropped from the returned env."""
    raw_env = {
        "GIT_DIR": "/outer/.git",
        "GIT_INDEX_FILE": "/outer/.git/index",
        "GIT_WORK_TREE": "/outer",
        "GIT_OBJECT_DIRECTORY": "/outer/.git/objects",
        "GIT_COMMON_DIR": "/outer/.git",
        "GIT_NAMESPACE": "ns",
        "GIT_LITERAL_PATHSPECS": "1",
        "GIT_PREFIX": "sub/",
        "PATH": "/usr/bin",
        "HOME": "/home/dev",
    }
    scrubbed = tdd_commit._scrubbed_git_env(env=raw_env)  # noqa: SLF001
    for var in tdd_commit._GIT_ENV_PASSTHROUGH_VARS:  # noqa: SLF001
        assert var not in scrubbed, f"{var} must be scrubbed; got {scrubbed!r}"
    # Non-GIT vars survive untouched.
    assert scrubbed["PATH"] == "/usr/bin"
    assert scrubbed["HOME"] == "/home/dev"


def test_scrubbed_git_env_passes_through_clean_env() -> None:
    """An env with no GIT_* hook vars is returned with all entries intact."""
    raw_env = {"PATH": "/usr/bin", "LANG": "C.UTF-8"}
    scrubbed = tdd_commit._scrubbed_git_env(env=raw_env)  # noqa: SLF001
    assert scrubbed == raw_env, f"clean env must pass through unchanged; got {scrubbed!r}"


# ---------------------------------------------------------------------------
# CLI surface — module-as-script invocation, repo default, --help.
# ---------------------------------------------------------------------------


def test_cli_drives_full_ritual_with_no_mise(*, tmp_path: Path) -> None:
    """`python -m ...tdd_commit --no-mise` drives the ritual against `--repo`."""
    _init_repo(repo=tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_cli.py").write_text(
        "def test_cli() -> None:\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "cli_mod.py").write_text("X: int = 1\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(_MODULE_PATH),
            "--test",
            "tests/test_cli.py",
            "--impl",
            "cli_mod.py",
            "--subject",
            "feat: cli mod",
            "--repo",
            str(tmp_path),
            "--no-mise",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert (
        result.returncode == 0
    ), f"CLI ritual should exit 0; stdout={result.stdout!r} stderr={result.stderr!r}"
    assert _commit_subjects(repo=tmp_path) == ["feat: cli mod", "chore: baseline"]
    head_files = _files_in_head(repo=tmp_path)
    assert {"tests/test_cli.py", "cli_mod.py"} <= head_files


def test_cli_defaults_repo_to_cwd(*, tmp_path: Path) -> None:
    """Omitting `--repo` defaults the working tree to the process cwd."""
    _init_repo(repo=tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_cwd.py").write_text(
        "def test_cwd() -> None:\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "cwd_mod.py").write_text("Y: int = 2\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(_MODULE_PATH),
            "--test",
            "tests/test_cwd.py",
            "--impl",
            "cwd_mod.py",
            "--subject",
            "feat: cwd mod",
            "--no-mise",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert (
        result.returncode == 0
    ), f"CLI ritual (cwd default) should exit 0; stderr={result.stderr!r}"
    assert _commit_subjects(repo=tmp_path) == ["feat: cwd mod", "chore: baseline"]


def test_cli_help_flag_exits_zero(*, tmp_path: Path) -> None:
    """`--help` exits 0 with usage text naming the tdd-commit program."""
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH), "--help"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )
    assert result.returncode == 0
    assert "tdd-commit" in result.stdout


def test_cli_missing_required_flag_exits_nonzero(*, tmp_path: Path) -> None:
    """Omitting a required flag (--subject) makes argparse exit non-zero."""
    result = subprocess.run(
        [
            sys.executable,
            str(_MODULE_PATH),
            "--test",
            "tests/test_x.py",
            "--impl",
            "x.py",
            "--no-mise",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )
    assert result.returncode != 0, "argparse must reject a missing required flag"


def test_module_importable_without_running_main() -> None:
    """The module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("tdd_commit_for_import_test", str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
    assert callable(module.run_tdd_commit)
