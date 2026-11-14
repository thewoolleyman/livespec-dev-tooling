"""The repository's one hang guard: its value, its expiry report, and its sole definition.

Covers `SPECIFICATION/non-functional-requirements.md`, "Load-independent
concurrency waits", for the part plan homelab-k8s-worker-nodes owns: every
`tests/spec/test_homelab_worker_*.py` call that waits on a script is bounded by
the one guard in `tests/hang_guard.py`, and no such file carries a bound of its
own.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from tests import hang_guard
from tests.hang_guard import HANG_GUARD_SECONDS, run_under_hang_guard

_SPEC_TESTS = Path(__file__).resolve().parent / "spec"
_SPEC_MINIMUM_SECONDS = 120
_OWN_TIMEOUT = re.compile(r"\btimeout\s*=")


def test_the_guard_is_no_shorter_than_the_specification_allows() -> None:
    assert HANG_GUARD_SECONDS >= _SPEC_MINIMUM_SECONDS


def test_a_finished_command_returns_its_result_unchanged() -> None:
    result = run_under_hang_guard(
        [sys.executable, "-c", "import sys; print('done'); sys.exit(3)"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3
    assert result.stdout == "done\n"


def test_expiry_fails_the_test_as_a_hang_that_names_the_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The expiry is the outcome under test, so this one wait is bounded on purpose.
    monkeypatch.setattr(hang_guard, "HANG_GUARD_SECONDS", 1)
    with pytest.raises(pytest.fail.Exception) as raised:
        run_under_hang_guard([sys.executable, "-c", "import time; time.sleep(600)"])
    message = str(raised.value)
    assert message.startswith("HANG: ")
    assert "import time; time.sleep(600)" in message
    assert "after 1 s" in message


def test_no_homelab_worker_test_file_keeps_a_bound_of_its_own() -> None:
    files = sorted(_SPEC_TESTS.glob("test_homelab_worker_*.py"))
    assert files
    offenders = [
        f"{path.name}:{number}"
        for path in files
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _OWN_TIMEOUT.search(line)
    ]
    assert offenders == []
