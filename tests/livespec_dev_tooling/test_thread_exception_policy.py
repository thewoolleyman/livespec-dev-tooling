"""Tests for the pytest policy that surfaces crashed worker threads."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from livespec_dev_tooling.thread_exception_policy import pytest_configure


def test_the_plugin_promotes_unhandled_worker_thread_warnings_to_errors() -> None:
    config = Mock(spec=pytest.Config)

    pytest_configure(config)

    config.addinivalue_line.assert_called_once_with(
        "filterwarnings", "error::pytest.PytestUnhandledThreadExceptionWarning"
    )
