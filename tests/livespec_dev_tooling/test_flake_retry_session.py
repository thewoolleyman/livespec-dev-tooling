"""The flake-retry plugin's hooks run in a real pytest session and the replay legs honour it.

These tests exercise the plugin as pytest itself drives it: positional hook
calls, a real `pytest-rerunfailures` rerun, the `FLAKE-RETRIED` report and its
JSON record, and the red-green-replay legs that must never be fooled by a
retry (the untouched-test retry rule in non-functional-requirements.md).
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GIT_IDENTITY = ("-c", "user.email=flake@example.invalid", "-c", "user.name=flake")
_FLAKY_TEST = (
    "from pathlib import Path\n"
    "\n"
    "\n"
    "def test_flaky():\n"
    "    marker = Path(__file__).with_name('seen')\n"
    "    if not marker.exists():\n"
    "        marker.write_text('1')\n"
    "        raise AssertionError('first attempt fails')\n"
)
# Committed into the base, so the change set never contains it: it only takes
# the minute out of the retry delay for this throwaway session.
_NO_DELAY_CONFTEST = "import livespec_dev_tooling.flake_retry as flake_retry\n\nflake_retry.RETRY_DELAY_SECONDS = 0\n"


def _git(*, repo: Path, args: list[str]) -> None:
    _ = subprocess.run(["git", *_GIT_IDENTITY, *args], cwd=repo, check=True, capture_output=True)


def _flaky_repository(*, root: Path, touch_test: bool) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo=repo, args=["init", "-q", "-b", "master", "."])
    _ = (repo / "test_flaky.py").write_text(_FLAKY_TEST, encoding="utf-8")
    _ = (repo / "conftest.py").write_text(_NO_DELAY_CONFTEST, encoding="utf-8")
    _ = (repo / ".gitignore").write_text("seen\ntmp/\n", encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", "base"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", "HEAD"])
    if touch_test:
        _ = (repo / "test_flaky.py").write_text(_FLAKY_TEST + "# touched\n", encoding="utf-8")
    else:
        _ = (repo / "README.md").write_text("unrelated\n", encoding="utf-8")
        _git(repo=repo, args=["add", "README.md"])
        _git(repo=repo, args=["commit", "-qm", "unrelated change"])
    return repo


def _fixture_finalizer_repository(
    *, root: Path, scope: str, after_retry: bool = False, same_module: bool = False
) -> Path:
    """Create a fixture whose only user runs before the flaky test, in this or an earlier module."""
    repo = root / "repo"
    repo.mkdir()
    _git(repo=repo, args=["init", "-q", "-b", "master", "."])
    _ = (repo / "conftest.py").write_text(
        "from pathlib import Path\n"
        "\n"
        "import pytest\n"
        "\n"
        "import livespec_dev_tooling.flake_retry as flake_retry\n"
        "\n"
        "flake_retry.RETRY_DELAY_SECONDS = 0\n"
        "\n"
        "\n"
        f"@pytest.fixture(scope={scope!r})\n"
        "def resource():\n"
        "    yield\n"
        "    with Path('finalizer-log').open('a') as log:\n"
        "        log.write('finalized\\n')\n",
        encoding="utf-8",
    )
    user = "def test_uses_the_resource(resource) -> None:\n    assert resource is None\n"
    if same_module:
        _ = (repo / "test_early.py").write_text(user + "\n\n" + _FLAKY_TEST, encoding="utf-8")
    else:
        _ = (repo / "test_early.py").write_text(user, encoding="utf-8")
        _ = (repo / "test_later.py").write_text(_FLAKY_TEST, encoding="utf-8")
    if after_retry:
        _ = (repo / "test_last.py").write_text(
            "def test_after_the_retry() -> None:\n    assert True\n", encoding="utf-8"
        )
    _ = (repo / ".gitignore").write_text("seen\ntmp/\nfinalizer-log\n", encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", "base"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", "HEAD"])
    _ = (repo / "README.md").write_text("unrelated\n", encoding="utf-8")
    _git(repo=repo, args=["add", "README.md"])
    _git(repo=repo, args=["commit", "-qm", "unrelated change"])
    return repo


def _run_session(
    *, repo: Path, extra: tuple[str, ...] = (), test_paths: tuple[str, ...] = ("test_flaky.py",)
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:livespec_flake_retry",
            "-p",
            "livespec_dev_tooling.flake_retry",
            *extra,
            *test_paths,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=_environ_without_github(),
    )


@pytest.mark.integration
def test_a_rerun_keeps_a_session_fixture_finalizer_until_session_finish(*, tmp_path: Path) -> None:
    """A retry after a fixture's final user still tears that resource down once."""
    repo = _fixture_finalizer_repository(root=tmp_path, scope="session")

    completed = _run_session(repo=repo, test_paths=(".",))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "rerun" in completed.stdout
    assert (repo / "finalizer-log").read_text(encoding="utf-8") == "finalized\n"


@pytest.mark.integration
def test_a_rerun_keeps_a_module_fixture_finalizer_when_its_last_user_ran_before_the_retry(
    *, tmp_path: Path
) -> None:
    """A retry later in the fixture's own module still tears that resource down once."""
    repo = _fixture_finalizer_repository(root=tmp_path, scope="module", same_module=True)

    completed = _run_session(repo=repo, test_paths=(".",))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "rerun" in completed.stdout
    assert (repo / "finalizer-log").read_text(encoding="utf-8") == "finalized\n"


@pytest.mark.integration
def test_a_rerun_keeps_an_earlier_module_fixture_finalizer_until_session_finish(
    *, tmp_path: Path
) -> None:
    """A retry after another module's final user still tears that resource down once."""
    repo = _fixture_finalizer_repository(root=tmp_path, scope="module")

    completed = _run_session(repo=repo, test_paths=(".",))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "rerun" in completed.stdout
    assert (repo / "finalizer-log").read_text(encoding="utf-8") == "finalized\n"


@pytest.mark.integration
def test_a_rerun_keeps_fixture_finalizers_when_a_test_follows_the_retry(*, tmp_path: Path) -> None:
    """A later test must not replace finalizers saved for the retry's fixture scope."""
    repo = _fixture_finalizer_repository(root=tmp_path, scope="session", after_retry=True)

    completed = _run_session(repo=repo, test_paths=(".",))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "rerun" in completed.stdout
    assert (repo / "finalizer-log").read_text(encoding="utf-8") == "finalized\n"


@pytest.mark.integration
def test_an_untouched_failing_test_is_retried_on_its_own_and_reported_as_a_flake(
    *, tmp_path: Path
) -> None:
    """A real session re-runs the failure, passes, and reports it loudly."""
    repo = _flaky_repository(root=tmp_path, touch_test=False)

    completed = _run_session(repo=repo)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "1 passed, 1 rerun" in completed.stdout
    assert "FLAKE-RETRIED" in completed.stdout
    assert "test_flaky.py::test_flaky: 2 attempts, passed" in completed.stdout
    records = (repo / "tmp" / "flake-retries" / "retries.jsonl").read_text(encoding="utf-8")
    assert [json.loads(line) for line in records.splitlines()] == [
        {"attempts": 2, "nodeid": "test_flaky.py::test_flaky", "outcome": "passed"}
    ]


@pytest.mark.integration
def test_a_failing_test_the_run_touched_fails_at_once_with_no_retry(*, tmp_path: Path) -> None:
    """The touched test fails on its first attempt and nothing is reported."""
    repo = _flaky_repository(root=tmp_path, touch_test=True)

    completed = _run_session(repo=repo)

    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "1 failed" in completed.stdout
    assert "rerun" not in completed.stdout
    assert "FLAKE-RETRIED" not in completed.stdout
    assert not (repo / "tmp" / "flake-retries").exists()


@pytest.mark.integration
def test_github_actions_annotates_every_retried_test(*, tmp_path: Path) -> None:
    """Under GitHub Actions each retried node id gets a `::warning` annotation."""
    repo = _flaky_repository(root=tmp_path, touch_test=False)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:livespec_flake_retry",
            "-p",
            "livespec_dev_tooling.flake_retry",
            "test_flaky.py",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={**_environ_without_github(), "GITHUB_ACTIONS": "true"},
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "::warning::FLAKE-RETRIED test_flaky.py::test_flaky" in completed.stdout


def _environ_without_github() -> dict[str, str]:
    """The parent environment minus GitHub Actions and coverage self-instrumentation."""
    import os

    return {
        key: value
        for key, value in os.environ.items()
        if key not in ("GITHUB_ACTIONS", "COVERAGE_PROCESS_START")
        and not key.startswith("COV_CORE_")
    }


def test_the_red_leg_never_loads_the_retry_plugin() -> None:
    """The Red leg proves a failure, so its pytest switches the retry plugin off."""
    modes = importlib.import_module("livespec_dev_tooling.checks._red_green_replay_modes")

    assert modes.RED_LEG_NO_RETRY_ARGS == ("-p", "no:livespec_flake_retry")
    source = (_REPO_ROOT / "livespec_dev_tooling/checks/_red_green_replay_modes.py").read_text(
        encoding="utf-8"
    )
    red_call = source[source.index("def _handle_red_mode") :]
    red_call = red_call[: red_call.index('trailer_prefix="Red"')]
    assert red_call.count("_red_pytest_argv(") == 2
    assert modes._red_pytest_argv(head=("pytest",), target="t.py") == [  # noqa: SLF001
        "pytest",
        "-p",
        "no:livespec_flake_retry",
        "t.py",
        "--tb=no",
        "-q",
    ]


def test_the_suite_checksum_ignores_rerun_progress_rows() -> None:
    """A rerun's `R` progress row is terminal noise, not part of the verdict."""
    suite = importlib.import_module("livespec_dev_tooling.checks._red_green_replay_suite")

    with_rerun = "R.                                                                       [100%]\n1 passed in 1.00s\n"
    without_rerun = "..                                                                      [100%]\n1 passed in 2.00s\n"

    assert suite.canonical_output_checksum(output=with_rerun) == suite.canonical_output_checksum(
        output=without_rerun
    )


def test_the_hooks_are_positional_adapters_over_keyword_only_work() -> None:
    """pytest calls hooks positionally, so each hook is a bound `__call__`."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    for name in (
        "pytest_collection_modifyitems",
        "pytest_runtest_logreport",
        "pytest_terminal_summary",
    ):
        hook = getattr(plugin, name)
        assert hook.__name__ == "__call__", name


def _only_test_changed_changed(**_: object) -> set[Path]:
    return {Path("test_changed.py")}


def _unknown_change_set(**_: object) -> None:
    return None


def _config_with_rerunfailures(*, active: bool) -> SimpleNamespace:
    return SimpleNamespace(pluginmanager=SimpleNamespace(hasplugin=Mock(return_value=active)))


def _capturing_reporter(*, into: list[str]) -> SimpleNamespace:
    def write_sep(*args: str, **_: object) -> None:
        into.append(args[1])

    return SimpleNamespace(write_sep=write_sep, write_line=into.append)


def test_the_collection_hook_marks_only_untouched_tests(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The collection adapter hands pytest's positional arguments to the marker."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    _ = (tmp_path / "test_safe.py").write_text("X = 1\n", encoding="utf-8")
    _ = (tmp_path / "test_changed.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(plugin, "change_paths", _only_test_changed_changed)
    markers: dict[str, list[object]] = {"test_safe.py": [], "test_changed.py": []}

    def item(name: str) -> object:
        return SimpleNamespace(path=tmp_path / name, add_marker=markers[name].append)

    session = SimpleNamespace(config=SimpleNamespace(rootpath=tmp_path))
    plugin.pytest_collection_modifyitems(
        session,
        _config_with_rerunfailures(active=True),
        [item("test_safe.py"), item("test_changed.py")],
    )

    assert len(markers["test_safe.py"]) == 1
    assert markers["test_changed.py"] == []


def test_the_collection_hook_marks_nothing_without_the_rerunfailures_plugin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session without pytest-rerunfailures gets no `flaky` marker it cannot honour."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    _ = (tmp_path / "test_safe.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(plugin, "change_paths", _only_test_changed_changed)
    added: list[object] = []
    config = _config_with_rerunfailures(active=False)

    plugin.pytest_collection_modifyitems(
        SimpleNamespace(config=SimpleNamespace(rootpath=tmp_path)),
        config,
        [SimpleNamespace(path=tmp_path / "test_safe.py", add_marker=added.append)],
    )

    assert added == []
    config.pluginmanager.hasplugin.assert_called_once_with("rerunfailures")


def test_the_collection_hook_marks_nothing_when_the_change_set_is_unknown(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An uncomputable change set means touched, so no test is marked."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    _ = (tmp_path / "test_safe.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(plugin, "change_paths", _unknown_change_set)
    added: list[object] = []

    plugin.mark_untouched_tests(
        root=tmp_path,
        items=[
            cast(
                pytest.Item,
                SimpleNamespace(path=tmp_path / "test_safe.py", add_marker=added.append),
            )
        ],
    )

    assert added == []


def test_the_report_hook_counts_every_attempt_of_a_retried_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three failed attempts then a pass record four attempts, ending passed."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(plugin, "_RESULTS", {})
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    def report(outcome: str, when: str = "call") -> object:
        return SimpleNamespace(when=when, nodeid="t.py::t", outcome=outcome)

    plugin.pytest_runtest_logreport(report("passed", when="setup"))
    plugin.pytest_runtest_logreport(report("passed"))
    for _ in range(3):
        plugin.pytest_runtest_logreport(report("rerun"))
    plugin.pytest_runtest_logreport(report("passed"))
    written: list[str] = []
    reporter = _capturing_reporter(into=written)
    plugin.pytest_terminal_summary(reporter, 0, SimpleNamespace(rootpath=tmp_path))

    assert written == ["FLAKE-RETRIED", "t.py::t: 4 attempts, passed"]
    records = (tmp_path / "tmp" / "flake-retries" / "retries.jsonl").read_text(encoding="utf-8")
    assert json.loads(records) == {"attempts": 4, "nodeid": "t.py::t", "outcome": "passed"}


def test_the_summary_hook_is_silent_when_nothing_was_retried(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session with no retry writes no record and prints no block."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(plugin, "_RESULTS", {})
    written: list[str] = []
    reporter = _capturing_reporter(into=written)

    plugin.pytest_terminal_summary(reporter, 0, SimpleNamespace(rootpath=tmp_path))

    assert written == []
    assert not (tmp_path / "tmp").exists()


@pytest.mark.integration
def test_xdist_controller_reports_a_reason_workers_withheld_retries(*, tmp_path: Path) -> None:
    """The controller summary preserves a withholding reason discovered by workers."""
    repo = tmp_path / "repo"
    _init_repo(repo=repo)
    _ = (repo / "test_flaky.py").write_text(
        "def test_failure() -> None:\n    assert False\n", encoding="utf-8"
    )
    _git(repo=repo, args=["add", "test_flaky.py"])
    _git(repo=repo, args=["commit", "-qm", "failing test"])

    completed = _run_session(repo=repo, extra=("-n", "2"))
    output = completed.stdout + completed.stderr

    assert completed.returncode == 1, output
    assert "FLAKE-RETRY-WITHHELD" in output
    assert "no failing test is retried this session" in output
    assert "git rev-parse --verify --quiet HEAD^2" in output


def _init_repo(*, repo: Path) -> None:
    repo.mkdir()
    _git(repo=repo, args=["init", "-q", "-b", "master", "."])
    _ = (repo / "a.py").write_text("A = 1\n", encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", "base"])


@pytest.mark.integration
def test_the_change_set_spans_committed_staged_unstaged_and_untracked_paths(
    *, tmp_path: Path
) -> None:
    """Every kind of change since the merge-base is in the change set."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    repo = tmp_path / "repo"
    _init_repo(repo=repo)
    _ = (repo / "b.py").write_text("B = 1\n", encoding="utf-8")
    _git(repo=repo, args=["add", "b.py"])
    _git(repo=repo, args=["commit", "-qm", "b"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/main", "HEAD~1"])
    _ = (repo / "c.py").write_text("C = 1\n", encoding="utf-8")
    _git(repo=repo, args=["add", "c.py"])
    _ = (repo / "a.py").write_text("A = 2\n", encoding="utf-8")
    _ = (repo / "d.py").write_text("D = 1\n", encoding="utf-8")

    assert plugin.change_paths(repo_root=repo) == {
        Path("a.py"),
        Path("b.py"),
        Path("c.py"),
        Path("d.py"),
    }


@pytest.mark.integration
def test_head_at_the_merge_base_compares_against_its_parent(*, tmp_path: Path) -> None:
    """On the default branch itself, the change set is HEAD's own commit."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    repo = tmp_path / "repo"
    _init_repo(repo=repo)
    _ = (repo / "b.py").write_text("B = 1\n", encoding="utf-8")
    _git(repo=repo, args=["add", "b.py"])
    _git(repo=repo, args=["commit", "-qm", "b"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", "HEAD"])
    _git(repo=repo, args=["symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master"])

    assert plugin.change_paths(repo_root=repo) == {Path("b.py")}


@pytest.mark.integration
def test_a_repository_with_no_known_default_branch_has_no_change_set(*, tmp_path: Path) -> None:
    """Without origin/HEAD, origin/main or origin/master the change set is unknown."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    repo = tmp_path / "repo"
    _init_repo(repo=repo)

    assert plugin.change_paths(repo_root=repo) is None


@pytest.mark.integration
def test_a_failing_git_query_leaves_the_change_set_unknown(*, tmp_path: Path) -> None:
    """A merge-base git cannot compute, or a directory git cannot run in, means unknown."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    repo = tmp_path / "repo"
    _init_repo(repo=repo)
    _git(repo=repo, args=["checkout", "-q", "--orphan", "other"])
    _git(repo=repo, args=["commit", "-qm", "unrelated root"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", "master"])

    assert plugin.change_paths(repo_root=repo) is None
    assert plugin.change_paths(repo_root=tmp_path / "missing") is None


def test_the_closure_follows_relative_imports_and_the_conftest_chain(*, tmp_path: Path) -> None:
    """A changed sibling module, package member or conftest touches the test."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    package = tmp_path / "pkg"
    package.mkdir()
    _ = (package / "__init__.py").write_text("", encoding="utf-8")
    _ = (package / "helper.py").write_text("H = 1\n", encoding="utf-8")
    _ = (package / "other.py").write_text("O = 1\n", encoding="utf-8")
    _ = (package / "conftest.py").write_text("C = 1\n", encoding="utf-8")
    test_path = package / "test_x.py"
    _ = test_path.write_text(
        "from . import helper\nfrom .other import O\nimport os\n", encoding="utf-8"
    )

    def marker(changed: str) -> object:
        return plugin.retry_marker_for(
            repo_root=tmp_path, test_path=test_path, change_paths={Path(changed)}
        )

    assert marker("pkg/helper.py") is None
    assert marker("pkg/other.py") is None
    assert marker("pkg/conftest.py") is None
    assert marker("unrelated.txt") == {"reruns": 3, "reruns_delay": 60}


def test_a_closure_module_that_cannot_be_parsed_means_touched(*, tmp_path: Path) -> None:
    """An unparseable module in the closure disables the retry."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    _ = (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    test_path = tmp_path / "test_x.py"
    _ = test_path.write_text("import broken\n", encoding="utf-8")

    assert (
        plugin.retry_marker_for(
            repo_root=tmp_path, test_path=test_path, change_paths={Path("README.md")}
        )
        is None
    )


def test_a_segmented_path_literal_matches_only_its_full_named_directory(*, tmp_path: Path) -> None:
    """A shared ancestor alone does not touch a path assembled segment by segment."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    test_path = tmp_path / "test_gate.py"
    _ = test_path.write_text(
        "from pathlib import Path\n"
        "_ROOT = Path(__file__).resolve().parents[2]\n"
        "_GATE_SCRIPT = (\n"
        "    _ROOT\n"
        "    / 'ci-runner'\n"
        "    / 'k3s'\n"
        "    / 'phase2'\n"
        "    / 'gates'\n"
        "    / 'render-gate-job-exit-tests.sh'\n"
        ")\n",
        encoding="utf-8",
    )

    def marker(changed: str) -> object:
        return plugin.retry_marker_for(
            repo_root=tmp_path, test_path=test_path, change_paths={Path(changed)}
        )

    assert marker("ci-runner/k3s/phase2/factory/DERIVATION.md") == {
        "reruns": 3,
        "reruns_delay": 60,
    }
    assert marker("ci-runner/k3s/phase2/gates/render-gate-job-exit-tests.sh") is None
    assert marker("ci-runner/k3s/phase2/gates/other.sh") is None


def test_an_existing_segmented_directory_does_not_name_its_parent(*, tmp_path: Path) -> None:
    """The root conftest's vendor directory does not withhold unrelated retries."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    vendor = tmp_path / "livespec_dev_tooling" / "_vendor" / "structlog"
    vendor.mkdir(parents=True)
    _ = (vendor / "__init__.py").write_text("", encoding="utf-8")
    _ = (tmp_path / "conftest.py").write_text(
        "from pathlib import Path\n"
        "_VENDOR_DIR = (\n"
        "    Path(__file__).resolve().parent.parent\n"
        "    / 'livespec_dev_tooling'\n"
        "    / '_vendor'\n"
        ")\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    test_path = tests / "test_target.py"
    _ = test_path.write_text("VALUE = 1\n", encoding="utf-8")

    def marker(changed: str) -> object:
        return plugin.retry_marker_for(
            repo_root=tmp_path, test_path=test_path, change_paths={Path(changed)}
        )

    assert marker("livespec_dev_tooling/pre_commit_delegate.py") == {
        "reruns": 3,
        "reruns_delay": 60,
    }
    assert marker("livespec_dev_tooling/_vendor/structlog/__init__.py") is None


def test_a_partly_dynamic_path_expression_means_touched(*, tmp_path: Path) -> None:
    """A path expression with a dynamic segment cannot safely receive a retry."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    test_path = tmp_path / "test_dynamic.py"
    _ = test_path.write_text(
        "from pathlib import Path\n"
        "_ROOT = Path(__file__).resolve().parents[2]\n"
        "segment = 'gates'\n"
        "_TARGET = _ROOT / 'ci-runner' / segment\n",
        encoding="utf-8",
    )

    assert (
        plugin.retry_marker_for(
            repo_root=tmp_path,
            test_path=test_path,
            change_paths={Path("README.md")},
        )
        is None
    )


def test_a_change_to_the_plugin_itself_disables_every_retry(*, tmp_path: Path) -> None:
    """Touching the flake-retry plugin turns retries off for the whole session."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    test_path = tmp_path / "test_x.py"
    _ = test_path.write_text("X = 1\n", encoding="utf-8")

    assert (
        plugin.retry_marker_for(
            repo_root=tmp_path,
            test_path=test_path,
            change_paths={Path("livespec_dev_tooling/flake_retry.py")},
        )
        is None
    )


def test_a_root_level_relative_import_is_followed(*, tmp_path: Path) -> None:
    """`from . import x` beside a root-level test reaches the sibling; an outside import is skipped."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    _ = (tmp_path / "sibling.py").write_text("S = 1\n", encoding="utf-8")
    test_path = tmp_path / "test_root.py"
    _ = test_path.write_text("from . import sibling\nfrom os import path\n", encoding="utf-8")

    touched = plugin.retry_marker_for(
        repo_root=tmp_path, test_path=test_path, change_paths={Path("sibling.py")}
    )
    untouched = plugin.retry_marker_for(
        repo_root=tmp_path, test_path=test_path, change_paths={Path("other.txt")}
    )

    assert (touched, untouched) == (None, {"reruns": 3, "reruns_delay": 60})


def test_a_module_reached_twice_is_read_once(*, tmp_path: Path) -> None:
    """A test module that is also its own conftest is analysed once, not twice."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    test_path = tmp_path / "conftest.py"
    _ = test_path.write_text("X = 1\n", encoding="utf-8")

    marker = plugin.retry_marker_for(
        repo_root=tmp_path, test_path=test_path, change_paths={Path("other.txt")}
    )

    assert marker == {"reruns": 3, "reruns_delay": 60}


def test_the_summary_hook_annotates_each_retry_under_github_actions(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under GitHub Actions the summary adds one `::warning` line per retried node id."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    monkeypatch.setattr(plugin, "_RESULTS", {})
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    plugin.pytest_runtest_logreport(SimpleNamespace(when="call", nodeid="t.py::t", outcome="rerun"))
    plugin.pytest_runtest_logreport(
        SimpleNamespace(when="call", nodeid="t.py::t", outcome="passed")
    )
    written: list[str] = []

    plugin.pytest_terminal_summary(
        _capturing_reporter(into=written), 0, SimpleNamespace(rootpath=tmp_path)
    )

    assert written[-1] == "::warning::FLAKE-RETRIED t.py::t"


@pytest.mark.integration
def test_a_consumer_without_rerunfailures_collects_under_strict_markers(*, tmp_path: Path) -> None:
    """With pytest-rerunfailures absent the session runs: the failure stands, unretried."""
    repo = _flaky_repository(root=tmp_path, touch_test=False)

    completed = _run_session(repo=repo, extra=("-p", "no:rerunfailures", "--strict-markers"))
    output = completed.stdout + completed.stderr

    assert "INTERNALERROR" not in output
    assert completed.returncode == 1, output
    assert "1 failed" in output
    assert "FLAKE-RETRIED" not in output
