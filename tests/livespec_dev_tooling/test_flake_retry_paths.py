"""The flake-retry path analyzer is shipped as a mirrored source module."""

from __future__ import annotations

from pathlib import Path


def test_the_path_analyzer_module_is_shipped() -> None:
    """The focused analyzer module remains available to the retry plugin."""
    assert (
        Path(__file__).resolve().parents[2] / "livespec_dev_tooling/flake_retry_paths.py"
    ).is_file()
