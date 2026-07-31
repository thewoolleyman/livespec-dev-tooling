"""Green-leg edges for `primary_checkout_commit_refuse_hook_installed` — the tree scan.

A second `*_edges.py` sibling of
`test_primary_checkout_commit_refuse_hook_installed.py`. The first
(`*_probe_edges.py`) is itself the Red-recorded file of a Red→Green pair and so
is byte-identity-bound; this arm was authored at the Green amend and lands
here. `check_coverage_incremental` selects every `test_<stem>_*.py` sibling, so
both count toward the parent impl's coverage.

WHAT THIS PINS. `find_vendored_hook_copies` walks the whole work tree with
`rglob` looking for a file that should NOT be there, and returns a list. An
empty list is the PASS. So a walk that raised part-way — an unreadable
subdirectory is ordinary for a non-root operator, and this suite runs as root
where it cannot be produced by mode alone — would unwind to no list at all
before the conversion, and any handling that recovered to `[]` would be a
silent pass on the arm whose entire job is to notice that file.

That asymmetry is why this arm went on the railway even though the offender
count never convicted it: `find_vendored_hook_copies` is a private name, so
v178 clause 0 disqualifies it, and the check that governs this epic cannot see
it at all.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed import main
from livespec_dev_tooling.install_commit_refuse_hooks import CANONICAL_HOOK_BODY

__all__: list[str] = []

# Vars git sets when invoking hooks; under a lefthook run they would redirect
# the check's probes at the SURROUNDING repo instead of the tmp_path fixture.
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

_FAIL_EXIT = 4


def _repo_with_canonical_hooks(*, tmp_path: Path) -> Path:
    """A real git repo whose three hooks are canonical and executable.

    The hooks are correct so the only thing the check can report is the scan
    arm; a fixture with drifted hooks would produce a fail this test would
    happily mistake for its own.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    for args in (
        ["init", "--quiet"],
        ["config", "--local", "user.name", "Test User"],
        ["config", "--local", "user.email", "test@example.com"],
    ):
        _ = subprocess.run(["git", *args], cwd=str(project_root), check=True, env=env)
    hooks_dir = project_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook_name in ("pre-commit", "pre-push", "commit-msg"):
        hook = hooks_dir / hook_name
        _ = hook.write_bytes(CANONICAL_HOOK_BODY.encode("utf-8"))
        hook.chmod(0o755)
    return project_root


def test_fails_when_the_vendored_copy_scan_cannot_walk_the_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scan that could not finish must not report the tree clean.

    ⛔ The fixture patches `rglob` rather than removing a directory's read bit,
    because this suite runs as ROOT: a `chmod 000` subdirectory is still walked,
    the arm still returns `[]`, and the assertion would never fire — a green
    proving nothing, inside the epic that exists to remove them.

    The negative control is the assertion on `vendored_copy_present`: were the
    arm to recover to an empty list, the run would exit 0 and fail the first
    assertion; were it to report the incomplete walk as a FOUND copy, it would
    fail the last.
    """
    project_root = _repo_with_canonical_hooks(tmp_path=tmp_path)

    def _rglob(_self: Path, pattern: str) -> list[Path]:
        raise OSError(13, f"synthetic scan failure on {pattern}")

    monkeypatch.setattr(Path, "rglob", _rglob)
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(project_root)

    rc = main()
    stderr = capsys.readouterr().err

    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}"
    assert '"failure_mode": "hook_unreadable"' in stderr, stderr
    assert "synthetic scan failure" in stderr, stderr
    assert "vendored_copy_present" not in stderr, stderr
