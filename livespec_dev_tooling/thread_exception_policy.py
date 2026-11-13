"""Make an unhandled worker-thread exception fail the pytest session."""

from __future__ import annotations

import pytest

__all__: list[str] = ["pytest_configure"]


def pytest_configure(config: pytest.Config) -> None:
    """Promote pytest's worker-thread warning to the test failure it represents."""
    config.addinivalue_line("filterwarnings", "error::pytest.PytestUnhandledThreadExceptionWarning")
