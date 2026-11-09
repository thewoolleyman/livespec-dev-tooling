"""Integration coverage for the shipped untouched-test retry pytest plugin."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_plugin_declares_the_bounded_single_test_retry_policy() -> None:
    """An untouched failure receives three retries, each one minute apart."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "flake_retry.py"
    assert module_path.is_file(), "the flake-retry pytest plugin must be shipped"

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    assert plugin.RETRY_ATTEMPTS == 3
    assert plugin.RETRY_DELAY_SECONDS == 60


def test_pytest_loads_the_plugin_from_the_shared_entry_point() -> None:
    """Consumers receive the retry policy without per-repository conftest wiring."""
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    pytest11 = re.search(
        r"^\[project\.entry-points\.pytest11\]$(?P<body>.*?)(?=^\[|\Z)",
        pyproject,
        re.MULTILINE | re.DOTALL,
    )

    assert pytest11 is not None
    assert 'livespec_flake_retry = "livespec_dev_tooling.flake_retry"' in pytest11.group("body")


@pytest.mark.integration
def test_an_untouched_test_is_marked_for_a_bounded_single_test_retry(*, tmp_path: Path) -> None:
    """Closure analysis enables the pytest-rerunfailures marker only when safe."""
    _ = (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text("import app\nassert app.VALUE == 1\n", encoding="utf-8")

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    marker = plugin.retry_marker_for(
        repo_root=tmp_path,
        test_path=test_path,
        change_paths={Path("README.md")},
    )

    assert marker == {"reruns": 3, "reruns_delay": 60}


@pytest.mark.integration
def test_a_changed_path_does_not_match_a_bare_ancestor_directory_literal(*, tmp_path: Path) -> None:
    """A closure literal must name the changed path, not merely one of its segments."""
    tests = tmp_path / "tests"
    tests.mkdir()
    _ = (tests / "conftest.py").write_text('_vendor = "livespec_dev_tooling"\n', encoding="utf-8")
    test_path = tests / "test_example.py"
    _ = test_path.write_text("assert True\n", encoding="utf-8")

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    marker = plugin.retry_marker_for(
        repo_root=tmp_path,
        test_path=test_path,
        change_paths={Path("tests/livespec_dev_tooling/changed.py")},
    )

    assert marker == {"reruns": 3, "reruns_delay": 60}


@pytest.mark.integration
@pytest.mark.parametrize(
    ("changed", "source"),
    [
        ("app.py", "import app\n"),
        ("fixtures", 'FIXTURE_DIR = "fixtures"\n'),
        ("pyproject.toml", "import app\n"),
    ],
)
def test_a_touched_or_session_unsafe_test_has_no_retry_marker(
    *, tmp_path: Path, changed: str, source: str
) -> None:
    """Changed closure modules, literal paths, and build files fail immediately."""
    _ = (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text(source, encoding="utf-8")

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    assert (
        plugin.retry_marker_for(
            repo_root=tmp_path,
            test_path=test_path,
            change_paths={Path(changed)},
        )
        is None
    )


def test_retried_results_are_written_and_rendered_without_hiding_final_failure(
    *, tmp_path: Path
) -> None:
    """Retried tests leave one machine-readable record and a terminal-summary row."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    record = plugin.RetryResult(nodeid="test_example.py::test_flaky", attempts=4, outcome="failed")

    output = plugin.write_retry_records(repo_root=tmp_path, results=[record])

    assert output == tmp_path / "tmp" / "flake-retries" / "retries.jsonl"
    assert [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()] == [
        {"attempts": 4, "nodeid": "test_example.py::test_flaky", "outcome": "failed"}
    ]
    assert "FLAKE-RETRIED" in plugin.retry_summary(results=[record])
    assert "failed" in plugin.retry_summary(results=[record])


@pytest.mark.integration
def test_a_test_file_outside_the_repository_root_gets_no_retry_marker(*, tmp_path: Path) -> None:
    """An outside-root test is unanalysable, so it fails at once rather than crashing collection."""
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "scratch"
    outside.mkdir()
    test_path = outside / "test_outside.py"
    _ = test_path.write_text("def test_it():\n    assert True\n", encoding="utf-8")

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    marker = plugin.retry_marker_for(
        repo_root=repo, test_path=test_path, change_paths={Path("README.md")}
    )

    assert marker is None


@pytest.mark.integration
def test_an_outside_root_test_does_not_change_the_decision_for_an_inside_root_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collection marks the inside-root test and skips the outside-root one without raising."""
    repo = tmp_path / "repo"
    repo.mkdir()
    inside = repo / "test_inside.py"
    _ = inside.write_text("def test_it():\n    assert True\n", encoding="utf-8")
    outside = tmp_path / "scratch" / "test_outside.py"
    outside.parent.mkdir()
    _ = outside.write_text("def test_it():\n    assert True\n", encoding="utf-8")

    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")

    def _change_paths(*, repo_root: Path) -> set[Path]:
        assert repo_root == repo
        return {Path("README.md")}

    monkeypatch.setattr(plugin, "change_paths", _change_paths)

    class _Item:
        def __init__(self, *, path: Path) -> None:
            self.path = path
            self.markers: list[object] = []

        def add_marker(self, marker: object) -> None:
            self.markers.append(marker)

    inside_item = _Item(path=inside)
    outside_item = _Item(path=outside)

    withheld = plugin.mark_untouched_tests(root=repo, items=[outside_item, inside_item])

    assert withheld is None
    assert outside_item.markers == []
    assert len(inside_item.markers) == 1
