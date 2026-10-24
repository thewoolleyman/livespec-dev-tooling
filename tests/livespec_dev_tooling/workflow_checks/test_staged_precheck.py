"""Tests for livespec_dev_tooling/workflow_checks/staged_precheck.py.

`staged_precheck` is the commit-hook workflow check that heads
`just check-pre-commit` (work-item livespec-dev-tooling-nil6v7; the
"Hooks and CI" section of non-functional-requirements.md and the workflow
checks of contracts.md). It lints the staged Python files and type-checks
those the repository's type-checker configuration covers, refusing on any
finding with the tools' own `file:line` + rule lines, BEFORE the full
pre-commit aggregate starts.

Pure-function tests pin the type-checker scope filter. The CLI `main()`
is invoked IN-PROCESS against a throwaway git repo carrying a minimal
`pyproject.toml`, running the REAL ruff and pyright from this venv, so
the refusal text these tests read (at the file-descriptor level, since
the tools write straight to the inherited stdout) is the text a committer
reads. The children are ruff and pyright through `sys.executable -m`; the
coverage start hook is removed from their environment so no child
self-instruments (the same pollution `test_red_leg_scope` avoids by staying
in-process). The two scenario tests carry the `integration` marker: they
drive the shipped check end-to-end against a real git repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from livespec_dev_tooling.workflow_checks.staged_precheck import typecheck_scope

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PRE_COMMIT = _REPO_ROOT / "scripts" / "just" / "check-pre-commit.sh"

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

_PYPROJECT = """\
[project]
name = "fixture"
version = "0.0.0"

[tool.ruff]
line-length = 100
extend-exclude = ["**/_vendor/**"]

[tool.ruff.lint]
select = ["F"]

[tool.pyright]
include = ["pkg"]
exclude = ["**/_vendor/**"]
typeCheckingMode = "strict"
"""

_CLEAN = "def ok() -> int:\n    return 1\n"
_TYPE_ERROR = "def bad() -> int:\n    return 'not an int'\n"
_LINT_ERROR = "def unused() -> int:\n    return undefined_name\n"


# ---------------------------------------------------------------------------
# typecheck_scope — which staged files the type checker judges
# ---------------------------------------------------------------------------


def test_scope_keeps_files_under_an_include_root() -> None:
    assert typecheck_scope(staged=["pkg/a.py", "pkg/sub/b.py"], include=["pkg"], exclude=[]) == [
        "pkg/a.py",
        "pkg/sub/b.py",
    ]


def test_scope_drops_files_outside_every_include_root() -> None:
    assert typecheck_scope(staged=["tests/test_a.py", "pkg/a.py"], include=["pkg"], exclude=[]) == [
        "pkg/a.py"
    ]


def test_scope_drops_excluded_files_even_inside_an_include_root() -> None:
    assert (
        typecheck_scope(staged=["pkg/_vendor/lib.py"], include=["pkg"], exclude=["**/_vendor/**"])
        == []
    )


def test_scope_matches_a_leading_double_star_exclude_at_the_top_level() -> None:
    assert (
        typecheck_scope(staged=["_vendor/lib.py"], include=["."], exclude=["**/_vendor/**"]) == []
    )


def test_scope_treats_a_dot_include_as_the_whole_tree() -> None:
    assert typecheck_scope(staged=["a.py", "x/b.py"], include=["."], exclude=[]) == [
        "a.py",
        "x/b.py",
    ]


def test_scope_does_not_treat_a_name_prefix_as_a_directory() -> None:
    assert typecheck_scope(staged=["pkgextra/a.py"], include=["pkg"], exclude=[]) == []


# ---------------------------------------------------------------------------
# main() against a throwaway repo, with the real ruff and pyright
# ---------------------------------------------------------------------------


def _git(*, repo: Path, args: list[str]) -> None:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    subprocess.run(["git", *args], cwd=str(repo), check=True, env=env)


def _repo_with(*, tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo=repo, args=["init", "-q"])
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    for rel, body in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(body, encoding="utf-8")
    _git(repo=repo, args=["add", *files])
    return repo


def _invoke_main(*, monkeypatch: pytest.MonkeyPatch, cwd: Path) -> int:
    from livespec_dev_tooling.workflow_checks import staged_precheck

    monkeypatch.chdir(cwd)
    monkeypatch.delenv("COVERAGE_PROCESS_START", raising=False)
    monkeypatch.setattr(sys, "argv", ["staged_precheck"])
    return staged_precheck.main()


@pytest.mark.integration
def test_a_staged_type_error_among_ten_files_is_refused_in_seconds_naming_file_line_and_rule(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    files = {f"pkg/m{i}.py": _CLEAN for i in range(9)}
    files["pkg/broken.py"] = _TYPE_ERROR
    repo = _repo_with(tmp_path=tmp_path, files=files)
    started = time.monotonic()
    rc = _invoke_main(monkeypatch=monkeypatch, cwd=repo)
    elapsed = time.monotonic() - started
    out = capfd.readouterr().out
    assert rc == 4
    assert elapsed < 60
    assert "broken.py:2:" in out
    assert "reportReturnType" in out


@pytest.mark.integration
def test_a_staged_lint_error_is_refused_naming_file_line_and_rule(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    repo = _repo_with(tmp_path=tmp_path, files={"tests/test_x.py": _LINT_ERROR})
    rc = _invoke_main(monkeypatch=monkeypatch, cwd=repo)
    out = capfd.readouterr().out
    assert rc == 4
    assert "tests/test_x.py:2:" in out
    assert "F821" in out


def test_clean_staged_files_pass(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo_with(tmp_path=tmp_path, files={"pkg/a.py": _CLEAN, "tests/test_a.py": _CLEAN})
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo) == 0


def test_a_type_error_outside_the_type_checker_scope_is_not_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_with(
        tmp_path=tmp_path,
        files={"tests/test_t.py": _TYPE_ERROR, "pkg/_vendor/v.py": _TYPE_ERROR},
    )
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo) == 0


def test_a_pyrightconfig_json_scope_wins_over_pyproject(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_with(tmp_path=tmp_path, files={"pkg/broken.py": _TYPE_ERROR})
    _ = (repo / "pyrightconfig.json").write_text('{"include": ["other"]}', encoding="utf-8")
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo) == 0


def test_no_staged_python_passes_without_running_a_tool(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_with(tmp_path=tmp_path, files={"README.md": "doc\n"})
    assert _invoke_main(monkeypatch=monkeypatch, cwd=repo) == 0


def test_help_exits_zero(*, monkeypatch: pytest.MonkeyPatch) -> None:
    from livespec_dev_tooling.workflow_checks import staged_precheck

    monkeypatch.setattr(sys, "argv", ["staged_precheck", "--help"])
    with pytest.raises(SystemExit) as exc:
        _ = staged_precheck.main()
    assert exc.value.code == 0


def test_check_pre_commit_runs_the_precheck_before_any_aggregate_run() -> None:
    script = _CHECK_PRE_COMMIT.read_text(encoding="utf-8")
    precheck = script.index("livespec_dev_tooling.workflow_checks.staged_precheck")
    first_aggregate = script.index("just red_staged=")
    assert precheck < first_aggregate
    assert precheck < script.index("just hook_gate=1 check")
