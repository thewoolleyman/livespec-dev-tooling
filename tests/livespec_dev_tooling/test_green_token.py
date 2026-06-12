"""Outside-in tests for `livespec_dev_tooling/green_token.py`.

The green-token module writes an advisory-local token keyed on the HEAD
tree-hash after a successful full `just check` aggregate, then lets
`check-pre-push` skip the aggregate when the token matches. CI remains
authoritative; any token miss falls back to the full aggregate.

Tests invoke the module as a subprocess against throwaway git repos
created in tmp_path, mirroring the sibling check-test style.

GIT_* hook passthrough vars are scrubbed so subprocess git calls land
in the fixture repo, not the surrounding CI/hook repo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = _REPO_ROOT / "livespec_dev_tooling" / "green_token.py"

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
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}


def _init_repo(*, repo: Path) -> None:
    """Initialize a throwaway git repo with a committed baseline."""
    env = _scrubbed_env()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True, env=env)
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"],
        cwd=str(repo),
        check=True,
        env=env,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo),
        check=True,
        env=env,
    )
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "chore: baseline"],
        cwd=str(repo),
        check=True,
        env=env,
    )


def _run_module(
    *,
    cwd: Path,
    command: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the green_token module as a subprocess."""
    resolved_env = env if env is not None else _scrubbed_env()
    return subprocess.run(
        [sys.executable, str(_MODULE), command],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=resolved_env,
    )


def _head_tree_hash(*, repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=_scrubbed_env(),
    )
    return result.stdout.strip()


def _git_dir(*, repo: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
        env=_scrubbed_env(),
    )
    return Path(result.stdout.strip())


def test_write_creates_token_with_correct_tree_hash(*, tmp_path: Path) -> None:
    """'write' exits 0 and writes a token file containing the HEAD tree-hash."""
    _init_repo(repo=tmp_path)
    result = _run_module(cwd=tmp_path, command="write")
    assert (
        result.returncode == 0
    ), f"expected exit 0; got {result.returncode}, stderr={result.stderr!r}"
    token_path = _git_dir(repo=tmp_path) / "livespec-green-token.json"
    assert token_path.exists(), f"token file not created at {token_path}"
    token = json.loads(token_path.read_text(encoding="utf-8"))
    expected_tree_hash = _head_tree_hash(repo=tmp_path)
    assert token.get("tree_hash") == expected_tree_hash, (
        f"token tree_hash mismatch: got {token.get('tree_hash')!r}, "
        f"expected {expected_tree_hash!r}"
    )


def test_write_logs_to_stderr(*, tmp_path: Path) -> None:
    """'write' emits a structured log line to stderr confirming the write."""
    _init_repo(repo=tmp_path)
    result = _run_module(cwd=tmp_path, command="write")
    assert result.returncode == 0
    assert "green token written" in result.stderr


def test_check_exits_0_when_token_matches_and_worktree_clean(*, tmp_path: Path) -> None:
    """'check' exits 0 when the token matches HEAD tree-hash and worktree is clean."""
    _init_repo(repo=tmp_path)
    write_result = _run_module(cwd=tmp_path, command="write")
    assert write_result.returncode == 0

    check_result = _run_module(cwd=tmp_path, command="check")
    assert check_result.returncode == 0, (
        f"expected exit 0 (token matched); got {check_result.returncode}, "
        f"stderr={check_result.stderr!r}"
    )
    assert "matched" in check_result.stderr


def test_check_exits_1_when_no_token(*, tmp_path: Path) -> None:
    """'check' exits 1 when no token file exists (cold path)."""
    _init_repo(repo=tmp_path)
    result = _run_module(cwd=tmp_path, command="check")
    assert (
        result.returncode == 1
    ), f"expected exit 1 (no token); got {result.returncode}, stderr={result.stderr!r}"
    assert "no token found" in result.stderr


def test_check_exits_1_when_tree_hash_mismatch(*, tmp_path: Path) -> None:
    """'check' exits 1 when the stored tree-hash differs from the current HEAD."""
    _init_repo(repo=tmp_path)
    write_result = _run_module(cwd=tmp_path, command="write")
    assert write_result.returncode == 0

    (tmp_path / "newfile.txt").write_text("change\n", encoding="utf-8")
    env = _scrubbed_env()
    subprocess.run(["git", "add", "newfile.txt"], cwd=str(tmp_path), check=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "chore: another commit"],
        cwd=str(tmp_path),
        check=True,
        env=env,
    )

    check_result = _run_module(cwd=tmp_path, command="check")
    assert check_result.returncode == 1, (
        f"expected exit 1 (tree hash mismatch); got {check_result.returncode}, "
        f"stderr={check_result.stderr!r}"
    )
    assert "mismatch" in check_result.stderr


def test_check_exits_1_when_worktree_dirty(*, tmp_path: Path) -> None:
    """'check' exits 1 when the worktree has uncommitted modifications."""
    _init_repo(repo=tmp_path)
    write_result = _run_module(cwd=tmp_path, command="write")
    assert write_result.returncode == 0

    (tmp_path / "README.md").write_text("dirty\n", encoding="utf-8")

    check_result = _run_module(cwd=tmp_path, command="check")
    assert check_result.returncode == 1, (
        f"expected exit 1 (dirty worktree); got {check_result.returncode}, "
        f"stderr={check_result.stderr!r}"
    )
    assert "uncommitted changes" in check_result.stderr


def test_check_exits_1_with_invalid_token_format(*, tmp_path: Path) -> None:
    """'check' exits 1 when the token file content is not valid JSON."""
    _init_repo(repo=tmp_path)
    token_path = _git_dir(repo=tmp_path) / "livespec-green-token.json"
    token_path.write_text("not valid json", encoding="utf-8")

    result = _run_module(cwd=tmp_path, command="check")
    assert result.returncode == 1, f"expected exit 1 (invalid token); got {result.returncode}"
    assert "unreadable" in result.stderr


def test_check_exits_1_with_missing_tree_hash_field(*, tmp_path: Path) -> None:
    """'check' exits 1 when the token JSON lacks the 'tree_hash' field."""
    _init_repo(repo=tmp_path)
    token_path = _git_dir(repo=tmp_path) / "livespec-green-token.json"
    token_path.write_text(json.dumps({}), encoding="utf-8")

    result = _run_module(cwd=tmp_path, command="check")
    assert result.returncode == 1, f"expected exit 1 (missing tree_hash); got {result.returncode}"
    assert "invalid token format" in result.stderr


def test_write_overwrites_existing_token(*, tmp_path: Path) -> None:
    """A second 'write' call updates the token to the new HEAD tree-hash."""
    _init_repo(repo=tmp_path)
    _run_module(cwd=tmp_path, command="write")

    (tmp_path / "newfile.txt").write_text("change\n", encoding="utf-8")
    env = _scrubbed_env()
    subprocess.run(["git", "add", "newfile.txt"], cwd=str(tmp_path), check=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "chore: second commit"],
        cwd=str(tmp_path),
        check=True,
        env=env,
    )

    second_write = _run_module(cwd=tmp_path, command="write")
    assert second_write.returncode == 0

    token_path = _git_dir(repo=tmp_path) / "livespec-green-token.json"
    token = json.loads(token_path.read_text(encoding="utf-8"))
    expected = _head_tree_hash(repo=tmp_path)
    assert token.get("tree_hash") == expected


def test_module_importable_without_running_main() -> None:
    """The module imports cleanly (covers the __name__ != '__main__' branch)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "green_token_import_test",
        str(_MODULE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_module_re_import_with_vendor_in_sys_path() -> None:
    """Re-importing when _VENDOR_DIR is already on sys.path covers the False branch."""
    import importlib.util

    spec1 = importlib.util.spec_from_file_location(
        "green_token_first_import",
        str(_MODULE),
    )
    assert spec1 is not None and spec1.loader is not None
    module1 = importlib.util.module_from_spec(spec1)
    spec1.loader.exec_module(module1)

    spec2 = importlib.util.spec_from_file_location(
        "green_token_second_import",
        str(_MODULE),
    )
    assert spec2 is not None and spec2.loader is not None
    module2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(module2)
    assert callable(module2.main)
