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

from pathlib import Path

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


def _suite_run_cls():
    _load_modes()  # puts the checks dir on sys.path
    from _red_green_replay_suite import SuiteRun

    return SuiteRun
