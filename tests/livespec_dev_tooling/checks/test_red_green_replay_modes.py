"""Mirror-paired test for `livespec_dev_tooling/checks/_red_green_replay_modes.py`.

The private sibling module carries the Red-leg, Green-leg, and
suite-green-leg handlers plus their git-trailer subprocess helpers
for `red_green_replay.py`. The leg handlers' behavioral coverage
lives in `test_red_green_replay.py` (they are exercised outside-in
through the parent supervisor's argv contract); THIS file carries
the module-surface and helper-unit tests, giving the helper module
the mirror-paired test file the incremental coverage gate resolves
(`_red_green_replay_modes.py` → `test_red_green_replay_modes.py`,
leading underscore stripped).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

__all__: list[str] = []


_HELPERS_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_modes.py"
)


def test_red_green_replay_modes_helpers_importable() -> None:
    """The sibling helper module exposes the expected leg handlers.

    The cycle 4c extraction moved `_handle_red_mode` and
    `_handle_green_mode` into the sibling `_red_green_replay_modes.py`
    so `red_green_replay.py` stays under the 200-LLOC ceiling; the
    green-verified leg added `_handle_suite_green_mode` alongside. The
    fleet-check-coverage split then relocated the git-trailer I/O
    helpers to `_red_green_replay_trailers.py` (covered by its own
    mirror). This test pins the leg-handler surface of the helper
    module.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_red_green_replay_modes_for_import_test",
        str(_HELPERS_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module._handle_red_mode)  # noqa: SLF001
    assert callable(module._handle_green_mode)  # noqa: SLF001
    assert callable(module._handle_suite_green_mode)  # noqa: SLF001


def test_red_leg_uses_a_delegated_verdict_and_records_its_job_evidence(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A delegated Red learns failure from the Job without running pytest locally."""
    from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

    modes = _load_modes()
    assert hasattr(modes, "run_replay")
    test_path = tmp_path / "tests" / "test_red.py"
    test_path.parent.mkdir()
    test_path.write_text("def test_red() -> None:\n    assert False\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    local_pytest = Mock()
    recorded: list[tuple[str, str]] = []

    def delegated(*, repo_root: Path, pytest_argv: list[str]) -> ReplayVerdict:
        assert repo_root == tmp_path
        assert str(test_path) in pytest_argv
        return ReplayVerdict(
            local=False,
            reason="the Job reported a failing Red test",
            job_name="gate-red-1",
            tree_hash="a" * 40,
            exit_status=1,
            output_checksum="sha256:remote-output",
        )

    def record(*, msg_path: Path, trailers: tuple[tuple[str, str], ...]) -> None:
        assert msg_path.name == "COMMIT_EDITMSG"
        recorded.extend(trailers)

    monkeypatch.setattr(modes, "run_replay", delegated)
    monkeypatch.setattr(modes.subprocess, "run", local_pytest)
    monkeypatch.setattr(modes, "write_trailers", record)
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("feat: red\n", encoding="utf-8")

    assert (
        modes._handle_red_mode(  # noqa: SLF001
            msg_path=message,
            log=_RecordingLog(),
            tests_paths=["tests/test_red.py"],
        )
        == 0
    )
    assert local_pytest.call_count == 0
    assert ("TDD-Red-Output-Checksum", "sha256:remote-output") in recorded
    assert ("TDD-Red-Gate-Job", "gate-red-1") in recorded
    assert ("TDD-Red-Staged-Tree", "a" * 40) in recorded


def test_green_leg_uses_a_delegated_verdict_and_records_its_job_evidence(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A delegated Green learns success from the Job without running pytest locally."""
    from returns.io import IOSuccess

    from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

    modes = _load_modes()
    test_path = tmp_path / "tests" / "test_green.py"
    test_path.parent.mkdir()
    test_bytes = b"def test_green() -> None:\n    assert True\n"
    test_path.write_bytes(test_bytes)
    checksum = f"sha256:{hashlib.sha256(test_bytes).hexdigest()}"
    monkeypatch.chdir(tmp_path)
    local_pytest = Mock()
    recorded: list[tuple[str, str]] = []

    def delegated(*, repo_root: Path, pytest_argv: list[str]) -> ReplayVerdict:
        assert repo_root == tmp_path
        assert str(test_path) in pytest_argv
        return ReplayVerdict(
            local=False,
            reason="the Job reported a passing Green test",
            job_name="gate-green-1",
            tree_hash="b" * 40,
            exit_status=0,
            output_checksum="sha256:remote-output",
        )

    def trailer(*, key: str) -> object:
        return IOSuccess("tests/test_green.py" if key == "TDD-Red-Test" else checksum)

    def record(*, msg_path: Path, trailers: tuple[tuple[str, str], ...]) -> None:
        assert msg_path.name == "COMMIT_EDITMSG"
        recorded.extend(trailers)

    monkeypatch.setattr(modes, "run_replay", delegated)
    monkeypatch.setattr(modes, "head_trailer_value", trailer)
    monkeypatch.setattr(modes, "current_head_sha", lambda: IOSuccess("c" * 40))
    monkeypatch.setattr(modes.subprocess, "run", local_pytest)
    monkeypatch.setattr(modes, "write_trailers", record)
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("feat: green\n", encoding="utf-8")

    assert (
        modes._handle_green_mode(  # noqa: SLF001
            msg_path=message,
            log=_RecordingLog(),
            impl_paths=["livespec/widget.py"],
        )
        == 0
    )
    assert local_pytest.call_count == 0
    assert {
        ("TDD-Green-Gate-Job", "gate-green-1"),
        ("TDD-Green-Staged-Tree", "b" * 40),
        ("TDD-Green-Output-Checksum", "sha256:remote-output"),
    } <= set(recorded)


def test_an_absent_remote_verdict_runs_the_replay_locally(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No remote outcome falls through to pytest and carries no remote trailers."""
    from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

    modes = _load_modes()
    monkeypatch.chdir(tmp_path)
    log = _RecordingLog()
    monkeypatch.setattr(
        modes,
        "run_replay",
        lambda **_kwargs: ReplayVerdict(
            local=False,
            reason="the gate Job reached no verdict",
        ),
    )
    monkeypatch.setattr(
        modes.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=(), returncode=1, stdout="local failure\n", stderr=""
        ),
    )

    replay = modes._run_replay_test(  # noqa: SLF001
        log=log,
        pytest_argv=["pytest", "tests/test_red.py"],
        trailer_prefix="Red",
    )

    assert replay.returncode == 1
    assert replay.output == "local failure\n"
    assert replay.trailers == ()
    assert [event for _level, event, _kwargs in log.records] == ["commit-time replay gated locally"]


class _RecordingLog:
    """Minimal structlog stand-in recording (level, event, kwargs)."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.records.append(("info", event, kwargs))

    def warning(self, event: str, **kwargs: object) -> None:
        self.records.append(("warning", event, kwargs))

    def error(self, event: str, **kwargs: object) -> None:
        self.records.append(("error", event, kwargs))

    def check_ids(self, level: str) -> list[object]:
        return [kw.get("check_id") for lvl, _event, kw in self.records if lvl == level]


def _load_modes():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("_rgr_modes_for_suite_test", str(_HELPERS_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_suite_leg(
    monkeypatch,
    tmp_path: Path,
    *,
    suite_run,
    xdist: bool = True,
):
    modes = _load_modes()
    import _red_green_replay_suite as suite

    seen: dict[str, object] = {}

    def fake_run_suite(*, argv: list[str], timeout_seconds: int):
        seen["argv"] = argv
        seen["timeout"] = timeout_seconds
        return suite_run

    monkeypatch.setattr(suite, "run_suite", fake_run_suite)
    monkeypatch.setattr(suite, "xdist_importable", lambda: xdist)
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("chore: x\n", encoding="utf-8")
    log = _RecordingLog()
    rc = modes._handle_suite_green_mode(  # noqa: SLF001
        msg_path=msg, log=log, staged_paths=["a.py"]
    )
    return rc, log, msg.read_text(encoding="utf-8"), seen, modes


def test_suite_green_passes_n_from_test_nprocs_and_writes_unchanged_trailers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run = _suite_run_cls()(returncode=0, output="5 passed in 1.00s\n", timed_out=False)
    monkeypatch.setenv("test_nprocs", "4")
    monkeypatch.delenv("LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS", raising=False)
    rc, log, message, seen, _ = _run_suite_leg(monkeypatch, tmp_path, suite_run=run)
    assert rc == 0
    assert seen["argv"][-2:] == ["-n", "4"]  # type: ignore[index]
    assert seen["timeout"] == 2400
    assert "TDD-Suite-Green-Scope: full-suite" in message
    assert "TDD-Suite-Green-Output-Checksum: sha256:" in message
    assert "TDD-Suite-Green-Captured-At:" in message
    assert log.check_ids("error") == []


def test_suite_green_logs_and_runs_serially_without_xdist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run = _suite_run_cls()(returncode=0, output="5 passed in 1.00s\n", timed_out=False)
    rc, log, _message, seen, _ = _run_suite_leg(monkeypatch, tmp_path, suite_run=run, xdist=False)
    assert rc == 0
    assert "-n" not in seen["argv"]  # type: ignore[operator]
    assert log.check_ids("warning") == ["red-green-replay-suite-green-serial-fallback"]


def test_suite_green_timeout_rejects_with_named_check_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run = _suite_run_cls()(returncode=None, output="", timed_out=True)
    monkeypatch.setenv("LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS", "77")
    rc, log, message, _seen, _ = _run_suite_leg(monkeypatch, tmp_path, suite_run=run)
    assert rc == 1
    assert "TDD-Suite-Green" not in message
    assert log.check_ids("error") == ["red-green-replay-suite-green-timeout"]
    event = next(e for lvl, e, _kw in log.records if lvl == "error")
    assert "suite-green" in event
    assert "77" in event
    assert "LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS" in event


def test_suite_green_nonzero_and_exit_five_still_reject_without_trailers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    for code in (1, 5):
        run = _suite_run_cls()(returncode=code, output="boom\n", timed_out=False)
        rc, log, message, _seen, _ = _run_suite_leg(monkeypatch, tmp_path, suite_run=run)
        assert rc == 1
        assert "TDD-Suite-Green" not in message
        assert log.check_ids("error") == ["red-green-replay-suite-red"]


def test_suite_red_summary_names_every_failure_after_long_progress_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Suite-red prefers pytest's failure summary over long progress output."""
    run = _suite_run_cls()(
        returncode=1,
        output=(
            f"{' .' * 250}\n"
            "=========================== short test summary info ============================\n"
            "FAILED tests/test_epoch.py::test_fractional_start[0.65] - assertion failed\n"
            "FAILED tests/test_epoch.py::test_fractional_start[0.75] - assertion failed\n"
        ),
        timed_out=False,
    )
    rc, log, _message, _seen, _ = _run_suite_leg(monkeypatch, tmp_path, suite_run=run)

    assert rc == 1
    failure_event = next(kwargs for level, _event, kwargs in log.records if level == "error")
    summary = failure_event["failure_summary"]
    assert isinstance(summary, str)
    assert "tests/test_epoch.py::test_fractional_start[0.65]" in summary
    assert "tests/test_epoch.py::test_fractional_start[0.75]" in summary


def test_suite_red_summary_names_erroring_tests_and_collection_modules(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Suite-red reports pytest's erroring test and collection module ids."""
    run = _suite_run_cls()(
        returncode=1,
        output=(
            f"{' .' * 250}\n"
            "=========================== short test summary info ============================\n"
            "ERROR tests/test_setup.py::test_requires_fixture - fixture setup failed\n"
            "ERROR tests/test_collection.py - import failed\n"
        ),
        timed_out=False,
    )
    rc, log, _message, _seen, _ = _run_suite_leg(monkeypatch, tmp_path, suite_run=run)

    assert rc == 1
    failure_event = next(kwargs for level, _event, kwargs in log.records if level == "error")
    summary = failure_event["failure_summary"]
    assert isinstance(summary, str)
    assert "tests/test_setup.py::test_requires_fixture" in summary
    assert "tests/test_collection.py" in summary


def _suite_run_cls():
    _load_modes()  # puts the checks dir on sys.path
    from _red_green_replay_suite import SuiteRun

    return SuiteRun
