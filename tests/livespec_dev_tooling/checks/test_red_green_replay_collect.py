"""The range gate collects each Red+Green commit's recorded test on that commit's own tree.

`check-red-green-replay`'s commit-range validation used to judge a pair-shaped
commit by the PRESENCE of its trailer keys alone, so a history rewrite that
bypassed the commit-time hooks could keep the trailers while the tree around
the recorded test changed under it (work-item livespec-dev-tooling-5be65c).
Every fixture here is a real git repository whose commits are collected by a
real child pytest: the property is about what a commit's OWN tree can import,
which no stand-in for the tree or the child can show.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest
import structlog
import structlog.testing
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.checks import _red_green_replay_collect as module
from livespec_dev_tooling.checks import red_green_replay
from livespec_dev_tooling.checks._red_green_replay_revert import ForgeProbeUnavailable
from livespec_dev_tooling.checks._red_green_replay_suite_runner import SuiteBound, SuiteRun

_CHECK_ID = "red-green-replay-range-recorded-test-uncollectable"
_MODULE_PATH = "tests/test_x.py"
_BASE_REF = "origin/master"
_NO_MODULE = "<none recorded>"
_OLD_IMPL = "def decode_historical_result() -> int:\n    return 1\n"
_NEW_IMPL = _OLD_IMPL + "\n\ndef decode_historical_reply() -> int:\n    return 2\n"
_TEST = (
    "from livespec.foo import decode_historical_reply\n"
    "\n"
    "\n"
    "def test_reply() -> None:\n"
    "    assert decode_historical_reply() == 2\n"
)
_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    'source_trees = ["livespec"]\n'
    'source_tree_prefixes = ["livespec/"]\n'
)
_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)


@pytest.fixture(autouse=True)
def _confine_children(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every child on the fixture repo and out of the suite's coverage session.

    An ambient `GIT_DIR` (exported while this repository's own commit hook runs
    the suite) would aim the check's git calls at the surrounding repository,
    and `COVERAGE_PROCESS_START` or `COV_CORE_*` would make the collecting
    pytest self-instrument and write data files that race the parallel gate.
    """
    for name in os.environ:
        if (
            name in _GIT_ENV_VARS
            or name == "COVERAGE_PROCESS_START"
            or name.startswith("COV_CORE_")
        ):
            monkeypatch.delenv(name)


class _History(NamedTuple):
    repo: Path
    shas: list[str]


def _git(*, repo: Path, args: list[str]) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _init_repo(*, repo: Path, extra_config: str = "") -> None:
    _git(repo=repo, args=["init", "-q"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])
    _git(repo=repo, args=["config", "user.name", "Test"])
    _git(repo=repo, args=["config", "commit.gpgsign", "false"])
    (repo / "pyproject.toml").write_text(_PYPROJECT + extra_config, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", "chore: base"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", "HEAD"])


def _commit(*, repo: Path, files: dict[str, str], message: str) -> str:
    for relative, text in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", message])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def _pair_message(*, red_test: str | None = _MODULE_PATH) -> str:
    lines = ["feat: record a Red+Green pair", ""]
    if red_test is not None:
        lines.append(f"TDD-Red-Test: {red_test}")
    lines += [
        "TDD-Red-Test-File-Checksum: sha256:deadbeef",
        "TDD-Green-Verified-At: 2026-11-10T00:00:00Z",
    ]
    return "\n".join(lines) + "\n"


def _measured_history(*, repo: Path) -> _History:
    """The measured shape: a pair whose test cannot import on its own tree, then a fix.

    The first commit records `tests/test_x.py` but its tree defines only
    `decode_historical_result`, exactly as the replayed commits of
    livespec-dev-tooling#3913 did. The second commit adds the name the test
    imports, so HEAD's tree collects while the first commit's own tree never did.
    """
    _init_repo(repo=repo)
    broken = _commit(
        repo=repo,
        files={"livespec/foo.py": _OLD_IMPL, _MODULE_PATH: _TEST},
        message=_pair_message(),
    )
    fixed = _commit(repo=repo, files={"livespec/foo.py": _NEW_IMPL}, message=_pair_message())
    return _History(repo=repo, shas=[broken, fixed])


def _one_pair(*, repo: Path, red_test: str | None, files: dict[str, str]) -> str:
    _init_repo(repo=repo)
    return _commit(repo=repo, files=files, message=_pair_message(red_test=red_test))


def _collect_range(*, shas: list[str]) -> tuple[int, list[dict[str, object]]]:
    with structlog.testing.capture_logs() as logs:
        returncode = module.collect_recorded_tests(
            shas=shas, base_ref=_BASE_REF, log=structlog.get_logger("collect")
        )
    return returncode, [dict(entry) for entry in logs]


def _failing(*, logs: list[dict[str, object]]) -> list[dict[str, str]]:
    assert len(logs) == 1
    assert logs[0]["check_id"] == _CHECK_ID
    failing = logs[0]["failing_commits"]
    assert isinstance(failing, list)
    return [dict(item) for item in failing]


def _run_check(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["red_green_replay"])
    returncode = red_green_replay.main()
    return returncode, capsys.readouterr().err


def test_range_fails_naming_the_commit_and_module_whose_recorded_test_cannot_be_collected(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    history = _measured_history(repo=tmp_path)

    returncode, stderr = _run_check(repo=history.repo, monkeypatch=monkeypatch, capsys=capsys)

    assert returncode == 1
    assert _CHECK_ID in stderr
    assert history.shas[0] in stderr
    assert _MODULE_PATH in stderr
    assert "decode_historical_reply" in stderr
    assert history.shas[1] not in stderr
    assert "range-missing-trailers" not in stderr


def test_range_passes_when_every_recorded_test_collects_on_its_own_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _one_pair(
        repo=tmp_path,
        red_test=_MODULE_PATH,
        files={"livespec/foo.py": _NEW_IMPL, _MODULE_PATH: _TEST},
    )

    returncode, stderr = _run_check(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert (returncode, _CHECK_ID in stderr) == (0, False)


def test_the_finding_lists_the_commit_the_module_and_the_first_collection_error(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = _measured_history(repo=tmp_path)
    monkeypatch.chdir(history.repo)

    returncode, logs = _collect_range(shas=history.shas)

    assert returncode == 1
    (finding,) = _failing(logs=logs)
    assert finding["sha"] == history.shas[0]
    assert finding["module"] == _MODULE_PATH
    assert finding["error"].startswith("E ")
    assert "cannot import name 'decode_historical_reply'" in finding["error"]
    assert "rewrite the range" in str(logs[0]["hint"])


def test_a_node_id_after_the_module_is_dropped(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = _one_pair(
        repo=tmp_path,
        red_test=f"{_MODULE_PATH}::test_reply",
        files={"livespec/foo.py": _NEW_IMPL, _MODULE_PATH: _TEST},
    )
    monkeypatch.chdir(tmp_path)

    assert _collect_range(shas=[sha]) == (0, [])


@pytest.mark.parametrize(
    ("red_test", "module_shown", "problem"),
    [
        (None, _NO_MODULE, "no TDD-Red-Test trailer"),
        ("livespec/foo.py", "livespec/foo.py", "not a .py file under a configured test tree"),
        ("tests/notes.txt", "tests/notes.txt", "not a .py file under a configured test tree"),
        ("../tests/test_x.py", "../tests/test_x.py", "not a .py file under a configured test tree"),
        (
            "/tmp/tests/test_x.py",
            "/tmp/tests/test_x.py",
            "not a .py file under a configured test tree",
        ),
        ("tests/missing.py", "tests/missing.py", "does not exist in the commit's tree"),
    ],
)
def test_a_recorded_module_that_cannot_be_judged_fails_the_range(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    red_test: str | None,
    module_shown: str,
    problem: str,
) -> None:
    sha = _one_pair(
        repo=tmp_path,
        red_test=red_test,
        files={"livespec/foo.py": _NEW_IMPL, _MODULE_PATH: _TEST},
    )
    monkeypatch.chdir(tmp_path)

    returncode, logs = _collect_range(shas=[sha])

    assert returncode == 1
    (finding,) = _failing(logs=logs)
    assert (finding["sha"], finding["module"]) == (sha, module_shown)
    assert problem in finding["error"]


def test_a_recorded_module_that_collects_no_test_fails_the_range(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = _one_pair(
        repo=tmp_path,
        red_test=_MODULE_PATH,
        files={"livespec/foo.py": _NEW_IMPL, _MODULE_PATH: "VALUE = 1\n"},
    )
    monkeypatch.chdir(tmp_path)

    returncode, logs = _collect_range(shas=[sha])

    assert returncode == 1
    assert "no tests collected" in _failing(logs=logs)[0]["error"]


def test_a_mirror_pairing_test_tree_is_a_configured_test_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(
        repo=tmp_path,
        extra_config='mirror_pairings = [{ source_tree = "livespec", test_tree = "spec_tests" }]\n',
    )
    sha = _commit(
        repo=tmp_path,
        files={"livespec/foo.py": _NEW_IMPL, "spec_tests/test_x.py": _TEST},
        message=_pair_message(red_test="spec_tests/test_x.py"),
    )
    monkeypatch.chdir(tmp_path)

    assert _collect_range(shas=[sha]) == (0, [])


def test_collection_leaves_the_callers_working_tree_and_index_untouched(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = _measured_history(repo=tmp_path)
    (history.repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(repo=history.repo, args=["add", "staged.txt"])
    (history.repo / "livespec" / "foo.py").write_text("# edited, unstaged\n", encoding="utf-8")
    (history.repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    probes = (["status", "--porcelain"], ["ls-files", "-s"], ["worktree", "list"])
    before = [_git(repo=history.repo, args=probe) for probe in probes]
    monkeypatch.chdir(history.repo)

    returncode, _ = _collect_range(shas=history.shas)

    assert returncode == 1
    assert [_git(repo=history.repo, args=probe) for probe in probes] == before
    assert (history.repo / "livespec" / "foo.py").read_text(
        encoding="utf-8"
    ) == "# edited, unstaged\n"


def test_a_collection_that_stalls_fails_the_range_naming_the_bound(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = _one_pair(
        repo=tmp_path,
        red_test=_MODULE_PATH,
        files={
            "livespec/foo.py": _NEW_IMPL,
            _MODULE_PATH: "import time\n\ntime.sleep(60)\n\n\ndef test_never() -> None:\n    pass\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIVESPEC_SUITE_GREEN_STALL_SECONDS", "1")

    returncode, logs = _collect_range(shas=[sha])

    assert returncode == 1
    assert "stalled" in _failing(logs=logs)[0]["error"]


def test_a_tree_that_cannot_be_materialized_is_a_collection_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(repo=tmp_path)
    monkeypatch.chdir(tmp_path)

    problem = module._collect(sha="0" * 40, module=_MODULE_PATH)  # noqa: SLF001

    assert problem is not None
    assert "could not be materialized" in problem


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        (SuiteRun(returncode=3, output="", timed_out=False), "pytest exited 3 with no output"),
        (
            SuiteRun(returncode=2, output="x\r\nE   boom\r\nE   later\r\n", timed_out=False),
            "E   boom",
        ),
        (
            SuiteRun(returncode=5, output="x\r\n\r\nno tests ran\r\n", timed_out=False),
            "no tests ran",
        ),
        (SuiteRun(returncode=0, output="", timed_out=False), None),
    ],
)
def test_the_first_collection_error_line_is_the_one_reported(
    *, run: SuiteRun, expected: str | None
) -> None:
    bound = SuiteBound(stall_seconds=900, ceiling_seconds=None)

    assert module._collection_problem(run=run, bound=bound) == expected  # noqa: SLF001


def test_a_collection_ended_by_the_operator_ceiling_names_the_ceiling() -> None:
    run = SuiteRun(returncode=None, output="", timed_out=True, kill_reason="ceiling")
    bound = SuiteBound(stall_seconds=900, ceiling_seconds=5)

    problem = module._collection_problem(run=run, bound=bound)  # noqa: SLF001

    assert problem is not None
    assert "ceiling" in problem


@pytest.mark.parametrize(
    "message",
    [
        "fix: suite shaped\n\nTDD-Suite-Green-Captured-At: 2026-11-10T00:00:00Z\n",
        "fix: red only\n\nTDD-Red-Test: tests/test_x.py\nTDD-Red-Test-File-Checksum: sha256:00\n",
    ],
)
def test_a_commit_without_the_pair_shape_is_not_collected(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    _init_repo(repo=tmp_path)
    sha = _commit(repo=tmp_path, files={"livespec/foo.py": _OLD_IMPL}, message=message)
    monkeypatch.chdir(tmp_path)

    assert _collect_range(shas=[sha]) == (0, [])


def test_a_pair_shaped_commit_touching_no_product_file_is_not_collected(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(repo=tmp_path)
    sha = _commit(repo=tmp_path, files={_MODULE_PATH: _TEST}, message=_pair_message())
    monkeypatch.chdir(tmp_path)

    assert _collect_range(shas=[sha]) == (0, [])


def test_a_recorded_incident_exempts_a_commit_from_collection(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = _measured_history(repo=tmp_path)
    monkeypatch.chdir(history.repo)
    monkeypatch.setattr(module, "admitted_by_recorded_incident", lambda **_kw: True)

    assert _collect_range(shas=history.shas[:1]) == (0, [])


def test_a_verified_forge_authored_revert_exempts_a_commit_from_collection(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = _measured_history(repo=tmp_path)
    monkeypatch.chdir(history.repo)
    monkeypatch.setattr(module, "is_forge_authored_revert", lambda **_kw: IOSuccess(True))  # noqa: FBT003

    assert _collect_range(shas=history.shas[:1]) == (0, [])


def test_an_exemption_that_could_not_be_evaluated_exempts_nothing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = _measured_history(repo=tmp_path)
    monkeypatch.chdir(history.repo)
    unavailable = ForgeProbeUnavailable(argv="gpg", detail="not found")
    monkeypatch.setattr(module, "is_forge_authored_revert", lambda **_kw: IOFailure(unavailable))

    returncode, logs = _collect_range(shas=history.shas[:1])

    assert returncode == 1
    assert _failing(logs=logs)[0]["sha"] == history.shas[0]
