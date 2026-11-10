"""Tests for livespec_dev_tooling/workflow_checks/actionlint_workflows.py.

`actionlint_workflows` closes a false-green measured 2026-11-03
(work-item livespec-dev-tooling-f3q7r7): a `release-please.yml` whose job
`if:` was an unquoted YAML scalar containing `: ` passed the commit gate, the
push gate and PR CI, and GitHub then refused to parse it. Only actionlint
reports that shape, as a `syntax-check` finding. The check runs actionlint
over `.github/workflows/*.yml` and refuses on every `syntax-check` finding,
naming the file, the line and actionlint's own message. With no flag it judges
the STAGED workflow files, as the pre-commit gate needs; `--tree` judges every
workflow file in the working tree, as the push gate and CI need.

Tests drive `main()` IN-PROCESS against throwaway directories, running the
REAL actionlint the repository pins in `.mise.toml`, so the refusal these
tests read is the refusal a committer reads. Two cases stand a throwaway
executable in for actionlint, because a binary that is absent or that cannot
run is a state the real one cannot be put in.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PRE_COMMIT = _REPO_ROOT / "scripts" / "just" / "check-pre-commit.sh"
_WORKFLOW = ".github/workflows/release-please.yml"

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

_HEAD = "name: release\non: push\njobs:\n  release:\n"
_TAIL = "    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
_CLEAN = _HEAD + "    if: github.ref == 'refs/heads/master'\n" + _TAIL
# The livespec-dev-tooling-aplxhg shape: an unquoted scalar holding `: `.
_UNPARSEABLE = (
    _HEAD + "    if: github.event.head_commit.message == chore(master): release\n" + _TAIL
)
# actionlint reports this, but as `runner-label`, which GitHub still parses.
_UNKNOWN_LABEL = _HEAD + "    runs-on: no-such-runner-label\n    steps:\n      - run: echo hi\n"


def _git(*, repo: Path, args: list[str]) -> None:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    _ = subprocess.run(["git", *args], cwd=str(repo), check=True, env=env)


def _write(*, repo: Path, rel: str, body: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(body, encoding="utf-8")


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo=repo, args=["init", "-q"])
    return repo


def _invoke_main(*, monkeypatch: pytest.MonkeyPatch, cwd: Path, argv: list[str]) -> int:
    from livespec_dev_tooling.workflow_checks import actionlint_workflows

    monkeypatch.chdir(cwd)
    monkeypatch.delenv("COVERAGE_PROCESS_START", raising=False)
    monkeypatch.setattr(sys, "argv", ["actionlint_workflows", *argv])
    return actionlint_workflows.main()


def _events(*, capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    err = capsys.readouterr().err
    return [json.loads(line) for line in err.splitlines() if line.startswith("{")]


def _refusals(*, events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [event for event in events if event.get("level") == "error"]


def _fake_actionlint(*, tmp_path: Path, body: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "actionlint"
    _ = fake.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    fake.chmod(0o755)
    return bin_dir


def test_a_staged_unparseable_workflow_is_refused_naming_file_line_and_message(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _write(repo=repo, rel=_WORKFLOW, body=_UNPARSEABLE)
    _git(repo=repo, args=["add", _WORKFLOW])
    rc = _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[])
    refusals = _refusals(events=_events(capsys=capsys))
    assert rc == 4
    assert len(refusals) == 1
    assert refusals[0]["path"] == _WORKFLOW
    assert refusals[0]["line"] == 5
    assert refusals[0]["message"] == (
        "could not parse as YAML: mapping values are not allowed in this context"
    )
    assert refusals[0]["kind"] == "syntax-check"
    assert f"{_WORKFLOW}:5:" in str(refusals[0]["event"])


def test_staged_mode_judges_the_index_not_the_working_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _write(repo=repo, rel=_WORKFLOW, body=_UNPARSEABLE)
    _git(repo=repo, args=["add", _WORKFLOW])
    _write(repo=repo, rel=_WORKFLOW, body=_CLEAN)
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[]) == 4


def test_staged_mode_passes_when_only_the_working_tree_is_unparseable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _write(repo=repo, rel=_WORKFLOW, body=_CLEAN)
    _git(repo=repo, args=["add", _WORKFLOW])
    _write(repo=repo, rel=_WORKFLOW, body=_UNPARSEABLE)
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[]) == 0


def test_staged_mode_ignores_files_outside_the_workflows_directory(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _write(repo=repo, rel="docs/example.yml", body=_UNPARSEABLE)
    _write(repo=repo, rel=".github/workflows/notes.md", body=_UNPARSEABLE)
    _write(repo=repo, rel=".github/workflows/sub/inner.yml", body=_UNPARSEABLE)
    _git(repo=repo, args=["add", "."])
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[]) == 0


def test_a_finding_that_is_not_a_parse_failure_does_not_refuse(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _write(repo=repo, rel=".github/workflows/ci.yml", body=_UNKNOWN_LABEL)
    _git(repo=repo, args=["add", ".github/workflows/ci.yml"])
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[]) == 0


def test_nothing_staged_passes(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path=tmp_path)
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[]) == 0


def test_a_missing_actionlint_is_a_precondition_error_not_a_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _write(repo=repo, rel=".github/workflows/ci.yml", body=_CLEAN)
    _git(repo=repo, args=["add", ".github/workflows/ci.yml"])
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    rc = _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[])
    refusals = _refusals(events=_events(capsys=capsys))
    assert rc == 3
    assert "mise install actionlint" in str(refusals[0]["remedy"])


def test_an_actionlint_that_cannot_run_is_a_precondition_error_not_a_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _write(repo=repo, rel=".github/workflows/ci.yml", body=_CLEAN)
    _git(repo=repo, args=["add", ".github/workflows/ci.yml"])
    bin_dir = _fake_actionlint(tmp_path=tmp_path, body="echo 'could not read input' >&2\nexit 3\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    rc = _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[])
    refusals = _refusals(events=_events(capsys=capsys))
    assert rc == 3
    assert refusals[0]["path"] == ".github/workflows/ci.yml"
    assert "could not read input" in str(refusals[0]["stderr"])


def test_an_actionlint_whose_output_is_not_json_is_a_precondition_error(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _write(repo=repo, rel=".github/workflows/ci.yml", body=_CLEAN)
    _git(repo=repo, args=["add", ".github/workflows/ci.yml"])
    bin_dir = _fake_actionlint(tmp_path=tmp_path, body="echo 'not json'\nexit 1\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo, argv=[]) == 3


def test_help_exits_zero(*, monkeypatch: pytest.MonkeyPatch) -> None:
    from livespec_dev_tooling.workflow_checks import actionlint_workflows

    monkeypatch.setattr(sys, "argv", ["actionlint_workflows", "--help"])
    with pytest.raises(SystemExit) as exc:
        _ = actionlint_workflows.main()
    assert exc.value.code == 0


def test_check_pre_commit_runs_the_staged_mode_before_any_aggregate_run() -> None:
    script = _CHECK_PRE_COMMIT.read_text(encoding="utf-8")
    invocation = script.index("livespec_dev_tooling.workflow_checks.actionlint_workflows")
    assert invocation < script.index("just red_staged=")
    assert invocation < script.index("just hook_gate=1 check")
    assert invocation < script.index("just check-pre-commit-doc-only")
