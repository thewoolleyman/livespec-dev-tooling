"""`first_seen` evidence includes the history an in-progress merge brings in.

A factory refresh-repair merges the moved default branch into a publish branch,
and the commit hook judges the MERGE before it is committed. The rows that merge
brings into `tests/heading-coverage.json` were introduced by commits reachable
only from MERGE_HEAD. `first_seen_dates` walked `git log`, which defaults to
HEAD's history alone, so those rows had no first-seen evidence and the debt
register refused the merge. That happened on bd-ib-yuwftp run 01M6GK2VGVRT
(2026-11-03), after the full suite had passed.

The corrected rule: while a merge is in progress, the walk covers HEAD and every
MERGE_HEAD. A row keeps the date of the earliest commit, on either side, whose
registry carried it as `TODO`. Outside a merge the walk is unchanged.

Driven in-process against real git repositories, like
`test_heading_coverage_debt.py`, whose fixture shapes these cases mirror.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "heading_coverage_debt.py"

_ON_BOTH: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "spec_file": "spec.md",
    "heading": "## On both sides",
    "test": "TODO",
    "reason": "owed integration-tier test",
    "work_item": "livespec-dev-tooling-aaa",
}
_FROM_MASTER: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "spec_file": "spec.md",
    "heading": "## Brought in by master",
    "test": "TODO",
    "reason": "owed integration-tier test",
    "work_item": "livespec-dev-tooling-bbb",
}
_FROM_BRANCH: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "spec_file": "spec.md",
    "heading": "## Added on the branch",
    "test": "TODO",
    "reason": "owed integration-tier test",
    "work_item": "livespec-dev-tooling-ccc",
}
_KEY_ON_BOTH = ("SPECIFICATION", "spec.md", "## On both sides")
_KEY_FROM_MASTER = ("SPECIFICATION", "spec.md", "## Brought in by master")
_KEY_FROM_BRANCH = ("SPECIFICATION", "spec.md", "## Added on the branch")


def _load_module() -> ModuleType:
    """Import the on-disk module by path, registered in `sys.modules` for `@dataclass`."""
    spec = importlib.util.spec_from_file_location(
        "heading_coverage_debt_merge_history_under_test", str(_MODULE_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def _git(*, cwd: Path, args: list[str], committed_at: str | None = None) -> None:
    # S603/S607: argv is a fixed list of literal git args; no untrusted shell input.
    env = {"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"}
    if committed_at is not None:
        env["GIT_AUTHOR_DATE"] = committed_at
        env["GIT_COMMITTER_DATE"] = committed_at
    _ = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, env=env
    )


def _commit_registry(*, repo: Path, entries: list[dict[str, object]], committed_at: str) -> None:
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    _ = (tests_dir / "heading-coverage.json").write_text(
        json.dumps(entries, indent=2) + "\n", encoding="utf-8"
    )
    _git(cwd=repo, args=["add", "tests/heading-coverage.json"])
    _git(
        cwd=repo,
        args=["commit", "-q", "-m", f"registry at {committed_at}"],
        committed_at=committed_at,
    )


def _branch_behind_a_master_that_added_a_row(*, repo: Path) -> None:
    """`feature` forked from a base carrying one row; `master` then added a second row.

    The branch's own registry change lands on a different line, so the merge of
    master auto-resolves the registry and stages master's row.
    """
    _git(cwd=repo, args=["init", "-q", "--initial-branch=master"])
    _git(cwd=repo, args=["config", "user.email", "test@example.com"])
    _git(cwd=repo, args=["config", "user.name", "Test"])
    _commit_registry(repo=repo, entries=[_ON_BOTH], committed_at="2026-01-02T00:00:00+00:00")
    _git(cwd=repo, args=["checkout", "-q", "-b", "feature"])
    _ = (repo / "README.md").write_text("the branch's own change\n", encoding="utf-8")
    _git(cwd=repo, args=["add", "README.md"])
    _git(
        cwd=repo,
        args=["commit", "-q", "-m", "branch work"],
        committed_at="2026-02-03T00:00:00+00:00",
    )
    _git(cwd=repo, args=["checkout", "-q", "master"])
    _commit_registry(
        repo=repo, entries=[_ON_BOTH, _FROM_MASTER], committed_at="2026-03-04T00:00:00+00:00"
    )
    _git(cwd=repo, args=["checkout", "-q", "feature"])


def test_an_in_progress_merge_dates_the_rows_it_brings_in_from_their_own_commits(
    *, tmp_path: Path
) -> None:
    """Master's row is dated from master's commit; the shared row keeps its oldest date."""
    _branch_behind_a_master_that_added_a_row(repo=tmp_path)
    _git(cwd=tmp_path, args=["merge", "-q", "--no-ff", "--no-commit", "master"])

    dates = _MODULE.first_seen_dates(cwd=tmp_path)

    assert dates == {_KEY_ON_BOTH: "2026-01-02", _KEY_FROM_MASTER: "2026-03-04"}


def test_outside_a_merge_the_walk_is_head_history_only(*, tmp_path: Path) -> None:
    """The control: a branch behind master does not borrow dates from master's history."""
    _branch_behind_a_master_that_added_a_row(repo=tmp_path)
    _commit_registry(
        repo=tmp_path, entries=[_ON_BOTH, _FROM_BRANCH], committed_at="2026-04-05T00:00:00+00:00"
    )

    dates = _MODULE.first_seen_dates(cwd=tmp_path)

    assert dates == {_KEY_ON_BOTH: "2026-01-02", _KEY_FROM_BRANCH: "2026-04-05"}
