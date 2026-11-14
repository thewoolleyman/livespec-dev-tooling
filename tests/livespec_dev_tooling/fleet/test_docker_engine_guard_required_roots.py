"""The Docker engine install guard's two roots come only from flags, never a live default.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Testing approach", bullet "Host-state isolation of CLIs", and the
scenarios "a state-writing CLI invoked without its state-path flag refuses
and touches no host state" in `SPECIFICATION/scenarios.md`.

A command-line entry point that writes host state at a location named by a
flag must refuse an invocation that omits the flag, and every argv the guard
builds to re-invoke itself -- the dead-man timer and the observe-triggered
rollback -- must carry the run's own roots, because the re-invoked command
no longer has anywhere to default them from.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

__all__: list[str] = []

_CLI_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_cli"
_PREFLIGHT_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_preflight_cli"
_GUARD_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard"
_OBSERVER_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_observer"
_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"
_WINDOW_SECONDS = 420


def test_the_guard_refuses_to_run_without_state_root_and_names_the_flag(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting `--state-root` exits non-zero and names the flag."""
    cli = importlib.import_module(_CLI_MODULE)

    with pytest.raises(SystemExit) as refusal:
        _ = cli.parse_request(argv=["reserve", "run-a", "--runtime-root", str(tmp_path / "run")])

    assert refusal.value.code != 0
    assert "--state-root" in capsys.readouterr().err


def test_the_guard_refuses_to_run_without_runtime_root_and_names_the_flag(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting `--runtime-root` exits non-zero and names the flag."""
    cli = importlib.import_module(_CLI_MODULE)

    with pytest.raises(SystemExit) as refusal:
        _ = cli.parse_request(argv=["reserve", "run-a", "--state-root", str(tmp_path / "var")])

    assert refusal.value.code != 0
    assert "--runtime-root" in capsys.readouterr().err


@pytest.mark.parametrize(
    "subcommand", [["record", "--run", "run-a"], ["refusals", "--declared", "x"]]
)
def test_the_preflight_refuses_to_run_without_state_root_and_touches_nothing(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    subcommand: list[str],
) -> None:
    """Either preflight subcommand without `--state-root` exits non-zero, naming the flag."""
    preflight = importlib.import_module(_PREFLIGHT_MODULE)
    seams = Mock()
    monkeypatch.setattr(preflight, "build_real_host", seams.build_real_host)

    with pytest.raises(SystemExit) as refusal:
        _ = preflight.main(argv=subcommand)

    assert refusal.value.code != 0
    assert "--state-root" in capsys.readouterr().err
    assert seams.mock_calls == []


def test_the_preflight_still_records_into_the_state_root_it_is_given(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With the flag present the preflight runs exactly as it did before."""
    preflight = importlib.import_module(_PREFLIGHT_MODULE)
    seams = Mock()
    monkeypatch.setattr(preflight, "build_real_host", seams.build_real_host)

    code = preflight.main(argv=["record", "--run", "run-a", "--state-root", str(tmp_path / "var")])

    assert code == 0
    paths = seams.build_real_host.call_args.kwargs["paths"]
    assert paths.state_root == tmp_path / "var"


@pytest.mark.parametrize("module", [_CLI_MODULE, _PREFLIGHT_MODULE])
def test_each_guard_command_line_still_prints_usage_for_help(
    *, module: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--help` is exempt from the required flags and exits zero."""
    entry = importlib.import_module(module)
    parse = entry.parse_request if module == _CLI_MODULE else entry.main

    with pytest.raises(SystemExit) as helped:
        _ = parse(argv=["--help"])

    assert helped.value.code == 0
    assert "usage" in capsys.readouterr().out


def _fake(*, root: Path) -> Any:
    """A `FakeHost` rooted at `root`, with the two guard state roots under it."""
    fake_module = importlib.import_module(_FAKE_MODULE)
    return fake_module.FakeHost(state_root=root / "var", runtime_root=root / "run")


def _env(*, root: Path, host: Any) -> Any:
    """A `GuardEnv` over the same two roots."""
    model = importlib.import_module(_MODEL_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    paths = model.GuardPaths(state_root=root / "var", runtime_root=root / "run")
    return state.GuardEnv(paths=paths, host=host, window_seconds=_WINDOW_SECONDS)


def _record_phase(*, root: Path, run: str, phase: str) -> None:
    """Put a reservation and a phase on disk the way the guard's records read."""
    state_root = root / "var"
    (state_root / "runs" / run).mkdir(parents=True, exist_ok=True)
    _ = (state_root / "run").write_text(run, encoding="utf-8")
    _ = (state_root / "runs" / run / "phase").write_text(phase, encoding="utf-8")


def _roots_tail(*, root: Path, run: str) -> tuple[str, ...]:
    """The tail a re-invoked `rollback <run>` has to end with."""
    return (
        "rollback",
        run,
        "--state-root",
        str(root / "var"),
        "--runtime-root",
        str(root / "run"),
    )


def test_the_dead_man_rolls_back_the_run_with_the_runs_own_roots(*, tmp_path: Path) -> None:
    """The dead-man timer starts `rollback <run>` with the run's `--state-root` and `--runtime-root`."""
    guard = importlib.import_module(_GUARD_MODULE)
    fake = _fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="published")

    outcome = guard.run_operation(operation="arm", run="run-a", env=_env(root=tmp_path, host=fake))

    assert outcome.exit_code == 0
    armed = fake.calls_named(name="systemd_run")[0].detail
    assert armed[-6:] == _roots_tail(root=tmp_path, run="run-a")


def test_the_observe_triggered_rollback_carries_the_runs_own_roots(*, tmp_path: Path) -> None:
    """A failed sample starts `rollback <run>` with the run's `--state-root` and `--runtime-root`."""
    observer = importlib.import_module(_OBSERVER_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    fake = _fake(root=tmp_path)
    fake.sample_result = {"passed": False, "probe": "dns", "error": "no answer"}
    _record_phase(root=tmp_path, run="run-a", phase="started")

    decision = model.Decision(verdict="proceed", reason="admitted by the dispatch table")
    _ = observer.observe(run="run-a", env=_env(root=tmp_path, host=fake), decision=decision)

    started = fake.calls_named(name="systemd_run")[0].detail
    assert started[-6:] == _roots_tail(root=tmp_path, run="run-a")
