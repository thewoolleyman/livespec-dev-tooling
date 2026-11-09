"""Mirror-paired test for the per-test record of one suite-green pytest run.

Governed by `SPECIFICATION/contracts.md` section "Suite-green replay leg"
**Progress bound** and the `SPECIFICATION/scenarios.md` scenarios "a suite-green
run that stops printing output for the stall window is ended" and "a suite-green
run ended before any test completed says that no test had completed".
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import suite_run_record as mod

__all__: list[str] = []


def _arm(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the record hooks at a record file the current directory owns."""
    record = tmp_path / "record.jsonl"
    record.touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(mod.RECORD_PATH_ENV, str(record))
    monkeypatch.setenv(mod.RECORD_ROOT_ENV, str(tmp_path))
    return record


def test_the_hooks_record_the_collected_count_and_each_completed_test(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record = _arm(monkeypatch=monkeypatch, tmp_path=tmp_path)

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")

    mod.pytest_collection_finish(SimpleNamespace(items=[object(), object(), object()]))
    mod.pytest_runtest_logstart("tests/test_a.py::test_one", ("tests/test_a.py", 0, "test_one"))
    mod.pytest_runtest_logfinish("tests/test_a.py::test_one", ("tests/test_a.py", 0, "test_one"))

    events = [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in events] == ["collected", "start", "finish"]
    assert events[0]["count"] == 3
    assert events[1]["nodeid"] == "tests/test_a.py::test_one"
    assert events[1]["worker"] == "gw3"
    assert isinstance(events[1]["at"], float)
    assert events[2]["nodeid"] == "tests/test_a.py::test_one"
    assert isinstance(events[2]["at"], float)


def test_a_serial_run_records_no_worker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    record = _arm(monkeypatch=monkeypatch, tmp_path=tmp_path)
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

    mod.pytest_runtest_logstart("tests/test_a.py::test_one", ("tests/test_a.py", 0, "test_one"))

    (event,) = [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]
    assert event["worker"] == ""


def test_the_hooks_record_nothing_without_a_record_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record = _arm(monkeypatch=monkeypatch, tmp_path=tmp_path)
    monkeypatch.delenv(mod.RECORD_PATH_ENV)

    mod.pytest_collection_finish(SimpleNamespace(items=[object()]))
    mod.pytest_runtest_logstart("tests/test_a.py::test_one", ("tests/test_a.py", 0, "test_one"))
    mod.pytest_runtest_logfinish("tests/test_a.py::test_one", ("tests/test_a.py", 0, "test_one"))

    assert record.read_text(encoding="utf-8") == ""


def test_the_hooks_ignore_a_pytest_run_started_from_another_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record = _arm(monkeypatch=monkeypatch, tmp_path=tmp_path)
    other = tmp_path / "nested-run"
    other.mkdir()
    monkeypatch.chdir(other)

    mod.pytest_collection_finish(SimpleNamespace(items=[object()]))
    mod.pytest_runtest_logstart("test_nested.py::test_x", ("test_nested.py", 0, "test_x"))
    mod.pytest_runtest_logfinish("test_nested.py::test_x", ("test_nested.py", 0, "test_x"))

    assert record.read_text(encoding="utf-8") == ""


def test_the_record_reads_back_the_counts_and_the_latest_completed_test(tmp_path: Path) -> None:
    record = tmp_path / "record.jsonl"
    lines = [
        {"event": "collected", "count": 3},
        {"event": "collected", "count": 3},
        {"event": "finish", "nodeid": "tests/test_a.py::one", "at": 100.0},
        {"event": "start", "nodeid": "tests/test_a.py::one", "worker": "gw0", "at": 99.0},
        {"event": "finish", "nodeid": "tests/test_a.py::one", "at": 100.0},
        {"event": "start", "nodeid": "tests/test_a.py::two", "worker": "gw1", "at": 101.0},
        {"event": "finish", "nodeid": "tests/test_a.py::two", "at": 130.5},
        {"event": "start", "nodeid": "tests/test_a.py::three", "worker": "gw1", "at": 131.0},
    ]
    record.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    result = mod.read_record(path=record)

    assert result.collected == 3
    assert result.completed == 2
    assert result.last_nodeid == "tests/test_a.py::two"
    assert result.last_completed_at == 130.5
    assert result.running == (
        mod.RunningTest(nodeid="tests/test_a.py::three", worker="gw1", started_at=131.0),
    )


def test_an_empty_record_says_nothing_was_collected_or_completed(tmp_path: Path) -> None:
    record = tmp_path / "record.jsonl"
    record.touch()

    result = mod.read_record(path=record)

    assert result.collected is None
    assert result.completed == 0
    assert result.last_nodeid is None
    assert result.last_completed_at is None
    assert result.running == ()


def test_a_description_names_elapsed_seconds_completed_of_collected_and_the_last_test() -> None:
    record = mod.SuiteRecord(
        collected=3,
        completed=1,
        last_nodeid="tests/test_a.py::test_one",
        last_completed_at=1_700_000_000.0,
    )

    text = mod.describe_record(
        record=record, elapsed_seconds=907.4, now=1_700_000_600.0, kind="stalled"
    )

    assert "907 seconds" in text
    assert "1 of 3 collected tests had completed" in text
    assert "tests/test_a.py::test_one" in text
    assert "2023-11-14T22:13:20Z" in text
    assert "no test was running" in text
    assert "stalled mid-suite" in text


def test_a_description_says_when_collection_had_not_finished_and_no_test_had_completed() -> None:
    record = mod.SuiteRecord(collected=None, completed=0, last_nodeid=None, last_completed_at=None)

    text = mod.describe_record(record=record, elapsed_seconds=902.0, now=0.0, kind="stalled")

    assert "902 seconds" in text
    assert "collection had not finished" in text
    assert "no test had completed" in text
    assert "collection or worker start-up" in text


def test_a_description_says_no_test_had_completed_after_collection_finished() -> None:
    record = mod.SuiteRecord(collected=5, completed=0, last_nodeid=None, last_completed_at=None)

    text = mod.describe_record(record=record, elapsed_seconds=10.0, now=0.0, kind="stalled")

    assert "0 of 5 collected tests had completed" in text
    assert "no test had completed" in text


def test_a_description_names_every_running_test_with_its_duration_and_worker() -> None:
    record = mod.SuiteRecord(
        collected=3,
        completed=1,
        last_nodeid="tests/test_a.py::one",
        last_completed_at=1_700_000_000.0,
        running=(
            mod.RunningTest(
                nodeid="tests/test_a.py::two", worker="gw0", started_at=1_700_000_100.0
            ),
            mod.RunningTest(nodeid="tests/test_a.py::three", worker="", started_at=1_700_000_050.0),
        ),
    )

    text = mod.describe_record(
        record=record, elapsed_seconds=60.0, now=1_700_000_200.0, kind="stalled"
    )

    assert "tests/test_a.py::two on worker gw0 for 100 seconds" in text
    assert "tests/test_a.py::three on the main process for 150 seconds" in text
    assert "stalled mid-suite" in text
    assert "collection or worker start-up" not in text


def test_a_run_that_stalls_after_every_collected_test_completed_says_so() -> None:
    record = mod.SuiteRecord(
        collected=2,
        completed=2,
        last_nodeid="tests/test_a.py::two",
        last_completed_at=1_700_000_000.0,
    )

    text = mod.describe_record(record=record, elapsed_seconds=950.0, now=0.0, kind="stalled")

    assert "2 of 2 collected tests had completed" in text
    assert "stalled after its last test rather than mid-suite" in text
    assert "tests/test_a.py::two" in text


def test_a_run_ended_at_the_operator_ceiling_says_so() -> None:
    record = mod.SuiteRecord(
        collected=2, completed=1, last_nodeid="t::one", last_completed_at=1_700_000_000.0
    )

    text = mod.describe_record(record=record, elapsed_seconds=3000.0, now=0.0, kind="ceiling")

    assert "ended at its ceiling mid-suite" in text
    assert "stalled" not in text


def test_the_record_environment_loads_the_plugin_beside_any_the_caller_already_names(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "record.jsonl"

    fresh = mod.record_environment(environ={}, record_path=record_path, root=tmp_path)
    shared = mod.record_environment(
        environ={"PYTEST_PLUGINS": "other_plugin"}, record_path=record_path, root=tmp_path
    )

    assert fresh["PYTEST_PLUGINS"] == mod.PLUGIN_MODULE
    assert shared["PYTEST_PLUGINS"] == f"other_plugin,{mod.PLUGIN_MODULE}"
    assert fresh[mod.RECORD_PATH_ENV] == str(record_path)
    assert fresh[mod.RECORD_ROOT_ENV] == str(tmp_path)
