"""Green-leg edges for `_red_green_replay_modes` — the Green leg's git-read failures.

A `*_edges.py`-convention sibling of `test_red_green_replay_modes.py`: the
Red-recorded test file of a Red→Green pair is byte-identity-bound, so tests
authored at the Green amend land beside it. `check_coverage_incremental`
selects `test_<stem>_*.py` siblings alongside the paired test.

WHAT THESE PIN — livespec-dev-tooling-qndn, epic 8o8e. `_handle_green_mode`
makes three git reads, and every one of them used to yield an empty string
when git failed:

- `head_trailer_value(key="TDD-Red-Test")` → `Path.cwd() / ""` is the REPO
  ROOT, whose `read_bytes()` raises `IsADirectoryError` out of the hook.
- `head_trailer_value(key="TDD-Red-Test-File-Checksum")` → the comparison
  reports `test-file-checksum-mismatch`, which tells the AUTHOR their test
  file changed between Red and Green and instructs them to author a new
  Red — remediation for a fault that was never theirs.
- `current_head_sha()` → an empty `TDD-Green-Parent-Reflog` trailer: the
  failure recorded INTO the commit as evidence.

Each is now an `IOFailure` that refuses the amend and names the command.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING

import pytest
import structlog
from returns.io import IOFailure, IOSuccess

from livespec_dev_tooling.checks._red_green_replay_trailers import GitCommandFailed

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__: list[str] = []


_MODES_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_modes.py"
)

# The refusal exit the ritual uses for every rejection.
_REFUSED = 1

_FAILED_READ = GitCommandFailed(argv="git log -1 --format=%B", detail="exit 128: fatal")


@pytest.fixture
def modes() -> Iterator[ModuleType]:
    """The handler module, loaded standalone the way its supervisor loads it.

    A fresh module object per test, so stubbing its imported names is
    isolated without monkeypatch's attribute bookkeeping.
    """
    spec = importlib.util.spec_from_file_location("_red_green_replay_modes_edges", _MODES_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("test")


def _assert_refused(*, rc: int, stderr: str) -> None:
    assert rc == _REFUSED, f"the amend must be REFUSED, not admitted; got {rc}"
    assert '"check_id": "red-green-replay-git-command-failed"' in stderr, stderr
    assert '"argv": "git log -1 --format=%B"' in stderr, stderr


def test_green_leg_refuses_when_the_recorded_red_test_cannot_be_read(
    *, tmp_path: Path, modes: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unread `TDD-Red-Test` used to resolve to the repo ROOT as a test path."""
    modes.head_trailer_value = lambda *, key: IOFailure(_FAILED_READ)  # noqa: ARG005
    rc = modes._handle_green_mode(  # noqa: SLF001
        msg_path=tmp_path / "COMMIT_EDITMSG", log=_logger(), impl_paths=["livespec/x.py"]
    )
    _assert_refused(rc=rc, stderr=capsys.readouterr().err)


def test_green_leg_refuses_when_the_recorded_checksum_cannot_be_read(
    *, tmp_path: Path, modes: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """The SECOND read failing must refuse too, not fall through to a mismatch."""
    reads: list[str] = []

    def _second_read_fails(*, key: str) -> object:
        reads.append(key)
        if len(reads) == 1:
            return IOSuccess("tests/sample.py")
        return IOFailure(_FAILED_READ)

    modes.head_trailer_value = _second_read_fails
    rc = modes._handle_green_mode(  # noqa: SLF001
        msg_path=tmp_path / "COMMIT_EDITMSG", log=_logger(), impl_paths=["livespec/x.py"]
    )
    _assert_refused(rc=rc, stderr=capsys.readouterr().err)
    assert reads == ["TDD-Red-Test", "TDD-Red-Test-File-Checksum"]


def test_green_leg_refuses_when_the_parent_sha_cannot_be_read(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    modes: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unread parent SHA used to be WRITTEN INTO the commit as an empty trailer.

    This arm sits AFTER the checksum comparison and the Green pytest re-run,
    so the fixture stands a real test file on disk, matches its checksum, and
    stubs the re-run green. The assertion that matters is the second one: no
    trailers are written at all, so the commit does not end up carrying
    `TDD-Green-Parent-Reflog:` with nothing after it.
    """
    test_file = tmp_path / "tests" / "sample.py"
    test_file.parent.mkdir(parents=True)
    _ = test_file.write_text("def test_x() -> None:\n    assert True\n", encoding="utf-8")
    checksum = f"sha256:{hashlib.sha256(test_file.read_bytes()).hexdigest()}"

    modes.head_trailer_value = lambda *, key: IOSuccess(
        "tests/sample.py" if key == "TDD-Red-Test" else checksum
    )
    modes.current_head_sha = lambda: IOFailure(_FAILED_READ)
    # The Green pytest re-run is not what this arm is about; force it green.
    modes.subprocess = SimpleNamespace(
        run=lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
    )
    written: list[object] = []
    modes.write_trailers = lambda *, msg_path, trailers: written.append(trailers)  # noqa: ARG005
    monkeypatch.chdir(tmp_path)

    rc = modes._handle_green_mode(  # noqa: SLF001
        msg_path=tmp_path / "COMMIT_EDITMSG", log=_logger(), impl_paths=["livespec/x.py"]
    )

    _assert_refused(rc=rc, stderr=capsys.readouterr().err)
    assert written == [], "no trailers may be written when the parent SHA is unknown"
