"""Mirror-paired test for `livespec_dev_tooling/checks/_red_green_replay_suite.py`.

The helper carries the suite-green leg's worker-count argv, replay routing,
and order-independent output checksum. Its progress-bounded runner has its
own cohesive mirror-paired test module.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest
import structlog

__all__: list[str] = []

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "_red_green_replay_suite.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_rgr_suite_under_test", str(_MODULE_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_argv_uses_test_nprocs_for_worker_count() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(
        environ={"test_nprocs": "4"}, xdist_available=True, visible_cpus=32
    )
    assert argv == [sys.executable, "-m", "pytest", "--tb=line", "-q", "-n", "4"]


def test_argv_accepts_staged_test_paths() -> None:
    """A test-only suite-green leg selects its staged test files."""
    mod = _load()
    assert "test_paths" in inspect.signature(mod.suite_pytest_argv).parameters
    argv = mod.suite_pytest_argv(
        environ={},
        test_paths=["tests/test_changed.py"],
        xdist_available=True,
        visible_cpus=32,
    )
    assert argv[-3:] == ["-n", "8", "tests/test_changed.py"]


def test_shared_test_support_excludes_documentation_but_keeps_executable_support() -> None:
    """Only material that can affect other tests broadens suite-green replay."""
    mod = _load()
    assert hasattr(mod, "has_shared_test_support")
    assert not mod.has_shared_test_support(
        staged_paths=["tests/test_changed.py", "tests/prompts/CLAUDE.md"]
    )
    assert mod.has_shared_test_support(staged_paths=["tests/test_changed.py", "tests/conftest.py"])
    assert mod.has_shared_test_support(
        staged_paths=["tests/test_changed.py", "tests/fixtures/user.json"]
    )


# Without `test_nprocs` (most consumers compute it in a script and never export
# it) the worker count follows the SAME lane-aware rule their justfiles use:
# `auto` only on the hosted CI lane, then LIVESPEC_TEST_PARALLELISM, then a
# quarter of the visible CPUs (min 1). Never a bare `auto` elsewhere: in a
# factory pod xdist's `auto` sees every HOST core (32-72) against a 4-cpu quota.
def test_argv_unset_uses_auto_only_on_the_hosted_lane() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(
        environ={"LIVESPEC_CI_LANE": "hosted"}, xdist_available=True, visible_cpus=32
    )
    assert argv[-2:] == ["-n", "auto"]


def test_argv_unset_honours_livespec_test_parallelism() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(
        environ={"test_nprocs": " ", "LIVESPEC_TEST_PARALLELISM": "6"},
        xdist_available=True,
        visible_cpus=32,
    )
    assert argv[-2:] == ["-n", "6"]


def test_argv_unset_uses_a_quarter_of_visible_cpus_minimum_one() -> None:
    mod = _load()
    cases = ((32, "8"), (72, "18"), (4, "1"), (1, "1"))
    for visible_cpus, expected in cases:
        argv = mod.suite_pytest_argv(environ={}, xdist_available=True, visible_cpus=visible_cpus)
        assert argv[-2:] == ["-n", expected]


def test_argv_falls_back_to_serial_without_xdist() -> None:
    mod = _load()
    argv = mod.suite_pytest_argv(
        environ={"test_nprocs": "4"}, xdist_available=False, visible_cpus=32
    )
    assert argv == [sys.executable, "-m", "pytest", "--tb=line", "-q"]


def test_xdist_importable_matches_find_spec() -> None:
    mod = _load()
    assert mod.xdist_importable() is (importlib.util.find_spec("xdist") is not None)


def test_progress_bound_runner_surface_is_reexported() -> None:
    mod = _load()
    assert mod.SuiteBound(stall_seconds=900, ceiling_seconds=None) == mod.suite_bound(environ={})


def test_checksum_ignores_line_order_and_duration() -> None:
    mod = _load()
    first = (
        "..F.  [ 50%]\n[gw0] PASSED a\n[gw1] PASSED b\nWARNING x\nWARNING y\n3 passed in 12.34s\n"
    )
    second = "created: 2/2 workers\nWARNING y\nWARNING x\n3 passed in 0.50s (0:00:00)\n"
    assert mod.canonical_output_checksum(output=first) == mod.canonical_output_checksum(
        output=second
    )
    assert mod.canonical_output_checksum(output=first).startswith("sha256:")


def test_checksum_differs_when_outcome_count_differs() -> None:
    mod = _load()
    one = mod.canonical_output_checksum(output="3 passed in 1.00s\n")
    other = mod.canonical_output_checksum(output="4 passed in 1.00s\n")
    assert one != other


def test_same_tree_full_pre_commit_evidence_reuses_the_aggregate_run(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A full pre-commit verdict on this index tree replaces a second suite run."""
    mod = _load()
    assert hasattr(mod, "handle_suite_green_mode")
    evidence = mod.PreCommitAggregateEvidence(
        tree_hash="same-tree",
        run_id="pre-commit-aggregate:run-123",
        output_checksum="sha256:aggregate-output",
        captured_at="2026-11-02T12:00:00Z",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "read_pre_commit_evidence", lambda **_kwargs: evidence)
    monkeypatch.setattr(mod, "staged_tree_hash", lambda **_kwargs: "same-tree")
    suite_runs: list[object] = []
    monkeypatch.setattr(mod, "run_suite", lambda **kwargs: suite_runs.append(kwargs))
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("refactor: behaviour-preserving change\n", encoding="utf-8")

    assert (
        mod.handle_suite_green_mode(
            msg_path=msg_path,
            log=structlog.get_logger(),
            staged_paths=["livespec_dev_tooling/example.py"],
        )
        == 0
    )
    assert suite_runs == []
    message = msg_path.read_text(encoding="utf-8")
    assert "TDD-Suite-Green-Output-Checksum: sha256:aggregate-output" in message
    assert "TDD-Suite-Green-Producer: pre-commit-aggregate:run-123" in message


@pytest.mark.parametrize("evidence_tree", [None, "different-tree"])
def test_missing_or_other_tree_pre_commit_evidence_runs_a_fresh_full_suite(
    *, evidence_tree: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only a matching, full aggregate may replace the staged-tree suite run."""
    from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

    mod = _load()
    assert hasattr(mod, "handle_suite_green_mode")
    evidence = (
        None
        if evidence_tree is None
        else mod.PreCommitAggregateEvidence(
            tree_hash=evidence_tree,
            run_id="pre-commit-aggregate:other",
            output_checksum="sha256:other-output",
            captured_at="2026-11-02T12:00:00Z",
        )
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "read_pre_commit_evidence", lambda **_kwargs: evidence)
    monkeypatch.setattr(mod, "staged_tree_hash", lambda **_kwargs: "same-tree")
    monkeypatch.setattr(
        mod,
        "run_replay",
        lambda **_kwargs: ReplayVerdict(local=True, reason="gates kubeconfig is not readable"),
    )
    monkeypatch.setattr(mod, "xdist_importable", lambda: False)
    suite_runs: list[object] = []

    def local_suite(**kwargs: object) -> object:
        suite_runs.append(kwargs)
        return mod.SuiteRun(returncode=0, output="5 passed in 1.00s\n", timed_out=False)

    monkeypatch.setattr(mod, "run_suite", local_suite)
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("refactor: behaviour-preserving change\n", encoding="utf-8")

    assert (
        mod.handle_suite_green_mode(
            msg_path=msg_path,
            log=structlog.get_logger(),
            staged_paths=["livespec_dev_tooling/example.py"],
        )
        == 0
    )
    assert len(suite_runs) == 1
    message = msg_path.read_text(encoding="utf-8")
    assert "TDD-Suite-Green-Output-Checksum: sha256:other-output" not in message
    assert "TDD-Suite-Green-Producer:" not in message


def test_suite_green_without_a_gates_credential_runs_locally_and_says_so(
    *, monkeypatch, tmp_path: Path
) -> None:
    """A sandbox keeps suite-green local even when its repository opts in."""
    from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

    mod = _load()
    assert hasattr(mod, "run_replay")
    monkeypatch.delenv("LIVESPEC_SUITE_GREEN_STALL_SECONDS", raising=False)
    monkeypatch.delenv("LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS", raising=False)
    monkeypatch.chdir(tmp_path)
    local_runs: list[list[str]] = []
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("chore: suite green\n", encoding="utf-8")
    log = _RecordingLog()

    monkeypatch.setattr(
        mod,
        "run_replay",
        lambda **_kwargs: ReplayVerdict(local=True, reason="gates kubeconfig is not readable"),
    )
    monkeypatch.setattr(mod, "xdist_importable", lambda: False)

    def local_suite(*, argv: list[str], bound):
        local_runs.append(argv)
        assert bound == mod.SuiteBound(stall_seconds=900, ceiling_seconds=None)
        return mod.SuiteRun(returncode=0, output="1 passed in 0.01s\n", timed_out=False)

    monkeypatch.setattr(mod, "run_suite", local_suite)

    assert (
        mod._handle_suite_green_mode(  # noqa: SLF001
            msg_path=message,
            log=log,
            staged_paths=["tests/test_changed.py"],
            tests_paths=["tests/test_changed.py"],
        )
        == 0
    )
    assert local_runs == [
        [sys.executable, "-m", "pytest", "--tb=line", "-q", "tests/test_changed.py"]
    ]
    assert "TDD-Suite-Green-Gate-Job" not in message.read_text(encoding="utf-8")
    assert [event for _level, event, _kwargs in log.records] == [
        "suite-green-candidate: product/test change without a Red leg; selecting replay scope",
        "suite-green-serial-fallback: pytest-xdist not importable; running the suite serially",
        "suite-green-argv: pytest invocation",
        "commit-time replay gated locally",
    ]


def test_suite_green_uses_job_evidence_and_falls_back_when_it_has_no_verdict(
    *, monkeypatch, tmp_path: Path
) -> None:
    """A Job verdict gates suite-green; an absent one reruns it on the committing host."""
    from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

    mod = _load()
    monkeypatch.delenv("LIVESPEC_SUITE_GREEN_STALL_SECONDS", raising=False)
    monkeypatch.delenv("LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS", raising=False)
    monkeypatch.chdir(tmp_path)
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("chore: suite green\n", encoding="utf-8")
    log = _RecordingLog()
    local_runs: list[list[str]] = []
    verdicts = iter(
        (
            ReplayVerdict(
                local=False,
                reason="the Job passed",
                job_name="gate-suite-1",
                tree_hash="a" * 40,
                exit_status=0,
                output_checksum="sha256:remote-output",
            ),
            ReplayVerdict(local=False, reason="the gate Job reached no verdict"),
        )
    )

    monkeypatch.setattr(mod, "run_replay", lambda **_kwargs: next(verdicts))
    monkeypatch.setattr(mod, "xdist_importable", lambda: False)

    def local_suite(*, argv: list[str], bound):
        local_runs.append(argv)
        assert bound == mod.SuiteBound(stall_seconds=900, ceiling_seconds=None)
        return mod.SuiteRun(returncode=0, output="1 passed in 0.01s\n", timed_out=False)

    monkeypatch.setattr(mod, "run_suite", local_suite)

    assert (
        mod._handle_suite_green_mode(  # noqa: SLF001
            msg_path=message,
            log=log,
            staged_paths=["tests/test_changed.py"],
            tests_paths=["tests/test_changed.py"],
        )
        == 0
    )
    remote_message = message.read_text(encoding="utf-8")
    assert local_runs == []
    assert "TDD-Suite-Green-Gate-Job: gate-suite-1" in remote_message
    assert f"TDD-Suite-Green-Staged-Tree: {'a' * 40}" in remote_message
    assert "TDD-Suite-Green-Output-Checksum: sha256:remote-output" in remote_message

    message.write_text("chore: suite green fallback\n", encoding="utf-8")
    assert (
        mod._handle_suite_green_mode(  # noqa: SLF001
            msg_path=message,
            log=log,
            staged_paths=["tests/test_changed.py"],
            tests_paths=["tests/test_changed.py"],
        )
        == 0
    )
    fallback_message = message.read_text(encoding="utf-8")
    assert local_runs == [
        [sys.executable, "-m", "pytest", "--tb=line", "-q", "tests/test_changed.py"]
    ]
    assert "TDD-Suite-Green-Gate-Job" not in fallback_message
    assert "TDD-Suite-Green-Output-Checksum: sha256:remote-output" not in fallback_message
    assert [event for _level, event, _kwargs in log.records if event.startswith("commit-time")] == [
        "commit-time replay gated by a gate Job",
        "commit-time replay gated locally",
    ]


def test_silent_suite_green_stall_names_the_window_and_missing_test_completion(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pre-test stall reports both the configured window and what never happened."""
    from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

    mod = _load()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "read_pre_commit_evidence", lambda **_kwargs: None)
    monkeypatch.setattr(mod, "staged_tree_hash", lambda **_kwargs: "staged-tree")
    monkeypatch.setattr(
        mod,
        "run_replay",
        lambda **_kwargs: ReplayVerdict(local=True, reason="gates kubeconfig is not readable"),
    )
    monkeypatch.setattr(mod, "xdist_importable", lambda: False)
    monkeypatch.setattr(
        mod,
        "run_suite",
        lambda **_kwargs: mod.SuiteRun(
            returncode=None,
            output="collecting tests\n",
            timed_out=True,
            kill_reason="stalled",
        ),
    )
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("chore: suite green\n", encoding="utf-8")
    log = _RecordingLog()

    assert (
        mod._handle_suite_green_mode(  # noqa: SLF001
            msg_path=message,
            log=log,
            staged_paths=["livespec_dev_tooling/example.py"],
        )
        == 1
    )
    _level, event, fields = log.records[-1]
    assert fields["stall_seconds"] == 900
    assert "900s" in event
    assert "no test had completed" in event


class _RecordingLog:
    """Minimal structured logger for suite-green route assertions."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.records.append(("info", event, kwargs))

    def warning(self, event: str, **kwargs: object) -> None:
        self.records.append(("warning", event, kwargs))

    def error(self, event: str, **kwargs: object) -> None:
        self.records.append(("error", event, kwargs))


def test_a_stalled_suite_green_refusal_carries_the_runs_attribution(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The refusal states the runner's attribution and carries the output the leg received."""
    from livespec_dev_tooling.commit_replay_delegate import ReplayVerdict

    mod = _load()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "read_pre_commit_evidence", lambda **_kwargs: None)
    monkeypatch.setattr(mod, "staged_tree_hash", lambda **_kwargs: "staged-tree")
    monkeypatch.setattr(
        mod,
        "run_replay",
        lambda **_kwargs: ReplayVerdict(local=True, reason="gates kubeconfig is not readable"),
    )
    monkeypatch.setattr(mod, "xdist_importable", lambda: False)
    attribution = "after 907 seconds, 1 of 3 collected tests had completed, the last was t::one"
    monkeypatch.setattr(
        mod,
        "run_suite",
        lambda **_kwargs: mod.SuiteRun(
            returncode=None,
            output=".\n",
            timed_out=True,
            kill_reason="stalled",
            attribution=attribution,
        ),
    )
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("chore: suite green\n", encoding="utf-8")
    log = _RecordingLog()

    assert (
        mod._handle_suite_green_mode(  # noqa: SLF001
            msg_path=message,
            log=log,
            staged_paths=["livespec_dev_tooling/example.py"],
        )
        == 1
    )
    _level, event, fields = log.records[-1]
    assert attribution in event
    assert fields["attribution"] == attribution
    assert fields["received_output"] == ".\n"
