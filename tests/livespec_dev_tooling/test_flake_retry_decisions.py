"""Unit coverage for the flake-retry closure decision module."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.flake_retry_decisions import retry_marker_for


def test_an_unrelated_change_keeps_the_bounded_retry_marker(*, tmp_path: Path) -> None:
    """The extracted decision preserves the untouched-test retry policy."""
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text("VALUE = 1\n", encoding="utf-8")

    marker = retry_marker_for(
        repo_root=tmp_path,
        test_path=test_path,
        change_paths={Path("README.md")},
    )

    assert marker == {"reruns": 3, "reruns_delay": 60}


def test_an_unsafe_change_withholds_the_retry_marker(*, tmp_path: Path) -> None:
    """Build configuration changes still disable every retry."""
    test_path = tmp_path / "test_example.py"
    _ = test_path.write_text("VALUE = 1\n", encoding="utf-8")

    marker = retry_marker_for(
        repo_root=tmp_path,
        test_path=test_path,
        change_paths={Path("pyproject.toml")},
    )

    assert marker is None
