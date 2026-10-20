"""Outside-in tests for `livespec_dev_tooling/green_token.py`.

The green-token module writes an advisory-local token keyed on the HEAD
tree-hash after a successful full `just check` aggregate, then lets
`check-pre-push` skip the aggregate when the token matches. CI remains
authoritative; any token miss falls back to the full aggregate.

Tests drive the module IN-PROCESS (`monkeypatch.setattr(sys, "argv", ...)`
+ `monkeypatch.chdir(...)` + `capsys` + `rc = main()`) against throwaway
git repos created in tmp_path, mirroring the sibling check-test style.
That replaces a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. `main()` parses
`sys.argv` through `argparse` and reads `Path.cwd()`, so the two
monkeypatches supply exactly what the child's argv list and `cwd=`
argument supplied; the assertion targets are unchanged — the int exit
code plus the structlog stderr text, now read off `capsys`.

The `git` spawns STAY. Creating the fixture repo, and reading its HEAD
tree-hash and git dir back, is real `git` behaviour this module is keyed
on — the token IS a tree-hash — so an in-process stand-in would be a test
that no longer tests what it claims. This file therefore KEEPS its
`subprocess_spawn_allowlist` entry.

GIT_* hook passthrough vars are scrubbed so those git calls land in the
fixture repo, not the surrounding CI/hook repo. `_scrubbed_env` NOW ALSO
DROPS `COVERAGE_PROCESS_START` and `COV_CORE_*`: it previously removed
only the GIT_* family, so those two reached every `git` child, and once
`main()` runs in-process they would reach the children it spawns itself.
Scrubbing them is the standing requirement on an allowlisted entry;
`_scrub_process_env` applies the same removals to this process so the
in-process path is scrubbed identically to the child path it replaced.

Branch parity with the retired spawn: the same fixtures drive the same
arms — `write` on a clean tree, `check` hit and miss, the missing-token
and dirty-tree misses, and the rewrite-on-second-write path. The
`if __name__ == "__main__": raise SystemExit(main())` line is the one
line the child reached that an in-process call cannot; it is already
excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so it was never measured here and no new
exclusion is introduced — and the vendored-path guard's two arms are
still driven directly by `test_module_re_import_with_vendor_in_sys_path`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

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


def _is_scrubbed(*, key: str) -> bool:
    """True iff `key` must be kept out of a `git` child this test spawns.

    Two families, for two different reasons. The GIT_* passthrough vars above
    would redirect git at the SURROUNDING repo. `COVERAGE_PROCESS_START` and
    `COV_CORE_*` would make a child self-instrument via the pth-installed
    startup hook and write `.coverage.*` files that race the parallel check
    dispatcher — the standing requirement on every entry in
    `subprocess_spawn_allowlist`, which this file is on for its `git` spawns.
    """
    return (
        key in _GIT_ENV_PASSTHROUGH_VARS
        or key == "COVERAGE_PROCESS_START"
        or key.startswith("COV_CORE_")
    )


def _scrubbed_env() -> dict[str, str]:
    """Return a copy of `os.environ` with the GIT_* and coverage vars removed."""
    return {k: v for k, v in os.environ.items() if not _is_scrubbed(key=k)}


def _scrub_process_env(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply `_scrubbed_env`'s removals to THIS process, for an in-process `main()`.

    `green_token.main()` resolves the repo from `Path.cwd()` and reaches git
    through its own children, so the scrub has to land on the process
    environment rather than on a `subprocess.run(env=...)` argument — this is
    what the retired child's `env=_scrubbed_env()` supplied, one frame earlier.
    """
    for key in [name for name in os.environ if _is_scrubbed(key=name)]:
        monkeypatch.delenv(key, raising=False)


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


def _load_green_token() -> ModuleType:
    """Import the module fresh from its file path.

    Loaded by path (not `from livespec_dev_tooling import green_token`) so the
    test drives the on-disk module the Red-Green-Replay hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location("green_token_under_test", str(_MODULE))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GREEN_TOKEN = _load_green_token()


class _ModuleRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_module(
    *,
    cwd: Path,
    command: str,
    targets: tuple[str, ...] = (),
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _ModuleRun:
    """Invoke `green_token.main()` in-process with `command` as its argv tail.

    `main()` parses `sys.argv` through `argparse` and reads `Path.cwd()`, so
    the argv and cwd monkeypatches supply exactly what the retired child's
    argv list and `cwd=` argument supplied. The `env` parameter is gone with
    the spawn: every call site took its default, and the scrub it selected now
    lands on the process environment through `_scrub_process_env`.

    `targets` carries the check-target names the purity subcommands take as
    their positional tail; the two token subcommands take none.

    `SystemExit` is CAUGHT and reported as the exit code it carries, because
    that is what the retired child reported too: `argparse` terminates the
    process on an argv it cannot parse, and a caller of this module sees that
    as a non-zero exit rather than as an exception. Letting it propagate would
    make an unparseable argv an ERROR in the suite instead of the exit code the
    assertion is about.
    """
    _scrub_process_env(monkeypatch=monkeypatch)
    monkeypatch.setattr(sys, "argv", ["green-token", command, *targets])
    monkeypatch.chdir(cwd)
    try:
        returncode = _GREEN_TOKEN.main()
    except SystemExit as exit_request:
        returncode = exit_request.code if isinstance(exit_request.code, int) else 1
    captured = capsys.readouterr()
    return _ModuleRun(returncode=returncode, stdout=captured.out, stderr=captured.err)


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


def test_write_creates_token_with_correct_tree_hash(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'write' exits 0 and writes a token file containing the HEAD tree-hash."""
    _init_repo(repo=tmp_path)
    result = _run_module(cwd=tmp_path, command="write", monkeypatch=monkeypatch, capsys=capsys)
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


def test_write_logs_to_stderr(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'write' emits a structured log line to stderr confirming the write."""
    _init_repo(repo=tmp_path)
    result = _run_module(cwd=tmp_path, command="write", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    assert "green token written" in result.stderr


def test_check_exits_0_when_token_matches_and_worktree_clean(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'check' exits 0 when the token matches HEAD tree-hash and worktree is clean."""
    _init_repo(repo=tmp_path)
    write_result = _run_module(
        cwd=tmp_path, command="write", monkeypatch=monkeypatch, capsys=capsys
    )
    assert write_result.returncode == 0

    check_result = _run_module(
        cwd=tmp_path, command="check", monkeypatch=monkeypatch, capsys=capsys
    )
    assert check_result.returncode == 0, (
        f"expected exit 0 (token matched); got {check_result.returncode}, "
        f"stderr={check_result.stderr!r}"
    )
    assert "matched" in check_result.stderr


def test_check_exits_1_when_no_token(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'check' exits 1 when no token file exists (cold path)."""
    _init_repo(repo=tmp_path)
    result = _run_module(cwd=tmp_path, command="check", monkeypatch=monkeypatch, capsys=capsys)
    assert (
        result.returncode == 1
    ), f"expected exit 1 (no token); got {result.returncode}, stderr={result.stderr!r}"
    assert "no token found" in result.stderr


def test_check_exits_1_when_tree_hash_mismatch(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'check' exits 1 when the stored tree-hash differs from the current HEAD."""
    _init_repo(repo=tmp_path)
    write_result = _run_module(
        cwd=tmp_path, command="write", monkeypatch=monkeypatch, capsys=capsys
    )
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

    check_result = _run_module(
        cwd=tmp_path, command="check", monkeypatch=monkeypatch, capsys=capsys
    )
    assert check_result.returncode == 1, (
        f"expected exit 1 (tree hash mismatch); got {check_result.returncode}, "
        f"stderr={check_result.stderr!r}"
    )
    assert "mismatch" in check_result.stderr


def test_check_exits_1_when_worktree_dirty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'check' exits 1 when the worktree has uncommitted modifications."""
    _init_repo(repo=tmp_path)
    write_result = _run_module(
        cwd=tmp_path, command="write", monkeypatch=monkeypatch, capsys=capsys
    )
    assert write_result.returncode == 0

    (tmp_path / "README.md").write_text("dirty\n", encoding="utf-8")

    check_result = _run_module(
        cwd=tmp_path, command="check", monkeypatch=monkeypatch, capsys=capsys
    )
    assert check_result.returncode == 1, (
        f"expected exit 1 (dirty worktree); got {check_result.returncode}, "
        f"stderr={check_result.stderr!r}"
    )
    assert "uncommitted changes" in check_result.stderr


def test_check_exits_1_with_invalid_token_format(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'check' exits 1 when the token file content is not valid JSON."""
    _init_repo(repo=tmp_path)
    token_path = _git_dir(repo=tmp_path) / "livespec-green-token.json"
    token_path.write_text("not valid json", encoding="utf-8")

    result = _run_module(cwd=tmp_path, command="check", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"expected exit 1 (invalid token); got {result.returncode}"
    assert "unreadable" in result.stderr


def test_check_exits_1_with_missing_tree_hash_field(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'check' exits 1 when the token JSON lacks the 'tree_hash' field."""
    _init_repo(repo=tmp_path)
    token_path = _git_dir(repo=tmp_path) / "livespec-green-token.json"
    token_path.write_text(json.dumps({}), encoding="utf-8")

    result = _run_module(cwd=tmp_path, command="check", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"expected exit 1 (missing tree_hash); got {result.returncode}"
    assert "invalid token format" in result.stderr


def test_check_exits_1_with_non_object_token_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """'check' exits 1 when the token JSON parses but its root is not an object.

    Valid JSON whose root is a list has no 'tree_hash' field to read, so
    it joins the missing-field report path rather than crashing on the
    absent mapping interface.
    """
    _init_repo(repo=tmp_path)
    token_path = _git_dir(repo=tmp_path) / "livespec-green-token.json"
    token_path.write_text(json.dumps(["tree_hash"]), encoding="utf-8")

    result = _run_module(cwd=tmp_path, command="check", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, f"expected exit 1 (non-object token); got {result.returncode}"
    assert "invalid token format" in result.stderr


def test_write_overwrites_existing_token(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A second 'write' call updates the token to the new HEAD tree-hash."""
    _init_repo(repo=tmp_path)
    _run_module(cwd=tmp_path, command="write", monkeypatch=monkeypatch, capsys=capsys)

    (tmp_path / "newfile.txt").write_text("change\n", encoding="utf-8")
    env = _scrubbed_env()
    subprocess.run(["git", "add", "newfile.txt"], cwd=str(tmp_path), check=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "chore: second commit"],
        cwd=str(tmp_path),
        check=True,
        env=env,
    )

    second_write = _run_module(
        cwd=tmp_path, command="write", monkeypatch=monkeypatch, capsys=capsys
    )
    assert second_write.returncode == 0

    token_path = _git_dir(repo=tmp_path) / "livespec-green-token.json"
    token = json.loads(token_path.read_text(encoding="utf-8"))
    expected = _head_tree_hash(repo=tmp_path)
    assert token.get("tree_hash") == expected


def test_world_reading_prints_the_members_the_token_must_not_memoize(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`world-reading` names exactly the given targets the token may not stand in for.

    The token memoizes only tree-pure members, so the pre-push gate has to be
    able to ask which of ITS OWN check set reads state outside the tree. A
    repository's aggregate is the population, not this library's slug set, so
    the subcommand takes the targets rather than discovering them — which is
    what lets the livespec justfile make the same decision without its own copy
    of the list.
    """
    _ = (tmp_path / "check-targets.txt").write_text(
        "check-local-pure  # purity: tree-pure\ncheck-local-world  # purity: world-reading\n",
        encoding="utf-8",
    )
    given = (
        "check-master-ci-green",
        "check-file-lloc",
        "check-local-world",
        "check-local-pure",
        "check-undeclared-member",
    )

    run = _run_module(
        cwd=tmp_path,
        command="world-reading",
        targets=given,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert run.returncode == 0, f"stderr={run.stderr!r}"
    assert run.stdout.splitlines() == [
        "check-master-ci-green",
        "check-local-world",
        "check-undeclared-member",
    ], (
        f"the printed set must be exactly the given targets declared world-reading OR "
        f"carrying no declaration — a shipped world gate, a repo-private world-reading "
        f"member, and an undeclared one which defaults to world-reading — and must omit "
        f"every tree-pure member; stdout={run.stdout!r}"
    )


def test_world_reading_refuses_an_empty_target_list(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No targets is no evidence, and an empty answer here reads as "memoize everything"."""
    run = _run_module(cwd=tmp_path, command="world-reading", monkeypatch=monkeypatch, capsys=capsys)

    assert run.returncode != 0, (
        f"an empty target list must FAIL rather than print nothing: a caller that reads an "
        f"empty answer as 'no member reads outside the tree' would memoize the whole "
        f"aggregate, which is the defect this subcommand exists to close; "
        f"stdout={run.stdout!r} stderr={run.stderr!r}"
    )


def test_world_reading_refuses_a_malformed_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A declaration outside the vocabulary cannot be acted on, so nothing is memoized."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "check-local-only  # purity: fairly-pure\n", encoding="utf-8"
    )

    run = _run_module(
        cwd=tmp_path,
        command="world-reading",
        targets=("check-local-only",),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert run.returncode != 0, f"stdout={run.stdout!r}"
    assert "fairly-pure" in run.stderr, (
        f"the refusal must name the value it could not read, or the operator has no way "
        f"to find the typo; stderr={run.stderr!r}"
    )


def test_undeclared_names_every_member_carrying_no_purity_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second safeguard: an undeclared member is named, not quietly defaulted."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "check-local-pure  # purity: tree-pure\ncheck-local-bare\n", encoding="utf-8"
    )

    run = _run_module(
        cwd=tmp_path,
        command="undeclared",
        targets=("check-local-pure", "check-local-bare", "check-file-lloc"),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert run.returncode != 0, f"stdout={run.stdout!r} stderr={run.stderr!r}"
    assert run.stdout.splitlines() == ["check-local-bare"], f"stdout={run.stdout!r}"
    assert "check-local-bare" in run.stderr, (
        f"`just check` relays this report, and the ratified scenario requires the "
        f"aggregate's output to NAME the member; stderr={run.stderr!r}"
    )


def test_undeclared_exits_zero_when_every_member_declares_its_purity(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fully-declared aggregate is the normal case and must cost nothing."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "check-local-pure  # purity: tree-pure\n", encoding="utf-8"
    )

    run = _run_module(
        cwd=tmp_path,
        command="undeclared",
        targets=("check-local-pure", "check-master-ci-green"),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert run.returncode == 0, f"stdout={run.stdout!r} stderr={run.stderr!r}"
    assert run.stdout == "", f"stdout={run.stdout!r}"


def test_undeclared_refuses_an_empty_target_list(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An aggregate that passed this gate with no members audited proved nothing."""
    run = _run_module(cwd=tmp_path, command="undeclared", monkeypatch=monkeypatch, capsys=capsys)

    assert run.returncode != 0, f"stdout={run.stdout!r} stderr={run.stderr!r}"


def test_undeclared_refuses_a_malformed_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A value outside the vocabulary fails the aggregate too, naming the member."""
    _ = (tmp_path / "check-targets.txt").write_text(
        "check-local-only  # purity: fairly-pure\n", encoding="utf-8"
    )

    run = _run_module(
        cwd=tmp_path,
        command="undeclared",
        targets=("check-local-only",),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert run.returncode != 0, f"stdout={run.stdout!r}"
    assert "check-local-only" in run.stderr, f"stderr={run.stderr!r}"


def test_an_unknown_subcommand_is_refused_rather_than_defaulted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The subcommand set is CLOSED: a name this module does not know exits non-zero.

    Load-bearing for a shell caller. `scripts/just/check.sh` branches on this
    module's exit status, so a mistyped or renamed subcommand that fell through
    to a default would make the aggregate act on an answer about something
    else — and `world-reading` and `undeclared` mean opposite things to their
    caller. Refusing names the mistake instead.
    """
    run = _run_module(
        cwd=tmp_path, command="world-readings", monkeypatch=monkeypatch, capsys=capsys
    )

    assert run.returncode != 0, f"stdout={run.stdout!r} stderr={run.stderr!r}"
    assert run.stdout == "", (
        f"a refused subcommand must print no member names: a caller reading an empty "
        f"stdout beside a zero exit would memoize everything; stdout={run.stdout!r}"
    )


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
