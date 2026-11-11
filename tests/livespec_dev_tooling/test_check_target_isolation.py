"""Platform-specific process-exit detection stays type-checkable."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling import _check_target_isolation as isolation

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]


def test_darwin_uses_poll_instead_of_linux_waitid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Darwin host must not touch Linux-only ``os.waitid`` attributes."""
    polled: list[None] = []

    class Process:
        pid = 123

        def poll(self) -> int:
            polled.append(None)
            return 0

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(os, "waitid", lambda *_args: None)
    assert not isolation.wait_for_exit(process=Process(), deadline_seconds=0)
    assert polled == [None]


def test_linux_waitid_observes_exit_without_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux retains WNOWAIT-based observation so the leader is not reaped early."""
    calls: list[tuple[object, ...]] = []

    polled: list[None] = []

    class Process:
        pid = 123

        def poll(self) -> int:
            polled.append(None)
            return 0

    def waitid(*args: object) -> object:
        calls.append(args)
        return object()

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "waitid", waitid)
    process = Process()
    assert not isolation.wait_for_exit(process=process, deadline_seconds=0)
    assert polled == []
    assert process.poll() == 0
    assert calls == [(os.P_PID, 123, os.WEXITED | os.WNOHANG | os.WNOWAIT)]


def test_check_types_runs_pyright_for_linux_and_darwin() -> None:
    """The type gate catches platform-specific standard-library attributes."""
    script = _ROOT / "scripts" / "just" / "check-types.sh"
    assert script.is_file()
    assert script.read_text(encoding="utf-8") == (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "uv run pyright --pythonplatform Linux\n"
        "uv run pyright --pythonplatform Darwin\n"
    )
    justfile = (_ROOT / "justfile").read_text(encoding="utf-8")
    recipe = "check-types:\n    scripts/just/check-types.sh\n"
    assert recipe in justfile
