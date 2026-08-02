"""Outside-in test for `testing/cli_e2e.py` — the CLI e2e harness orchestrator.

Per `livespec/SPECIFICATION/contracts.md` section "CLI end-to-end harness contract",
the harness ships five components — driver, structural skill discovery,
per-skill fixtures loader, time-bomb coverage gate, step orchestrator — behind
the importable `test_workflow_full_round_trip` entry point, with the `claude -p`
subprocess as the one injectable seam (selected via `LIVESPEC_E2E_HARNESS`).

The driver and discovery components live in cohesive helper modules
(`_cli_e2e_driver`, `_cli_e2e_discovery`) exercised by their own mirror test
files. This file exercises the parent orchestration surface WITHOUT a real
`claude` binary or API key:

- **Self-test against a tiny single-skill fixture-plugin** (the committed
  `fixtures/single_skill_plugin/` tree) proving discovery + coverage gate +
  a fixture round-trip work in isolation, driven by a deterministic fake
  `CliRunner` that materializes the expected files.
- The time-bomb coverage gate (pass when covered or exempt; fail closed).
- The `LIVESPEC_E2E_HARNESS` selector (real → RealCliRunner; mock with an
  injected runner; mock with no injected runner → ValueError).
- The orchestrator's session resume, install-command first turn, exempt-skill
  skipping, and the failing-step assertion path.
- The re-export surface (`__all__` sorted + exhaustive over the module).

This module OWNS the synthetic plugin/fixture builders (`_make_plugin`,
`_make_fixture`) and the deterministic `_FakeCliRunner`; the discovery mirror
test module imports the builders from here (via the testing-test conftest
sys.path insertion). No subprocess is ever spawned by these tests.

Coverage target: 100% line + branch of `cli_e2e.py`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.testing import cli_e2e
from livespec_dev_tooling.testing.cli_e2e import (
    CliResult,
    CoverageGateError,
    HarnessConfig,
    RealCliRunner,
    WorkflowFailedError,
    assert_coverage,
    discover_fixtures,
    run_workflow,
    select_runner,
)

_VENDOR_DIR = Path(cli_e2e.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure, Success  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

# The canonical entry point is named `test_workflow_full_round_trip` (fixed by
# the contract's consumer import path). Importing that bare `test_*` name into
# a pytest module makes pytest try to COLLECT it as a test with a missing
# `config` fixture — so we import it under a non-`test_`-prefixed alias here.
# A consumer wires it into their own collection via a thin wrapper for the
# same reason.
run_full_round_trip = cli_e2e.test_workflow_full_round_trip

__all__: list[str] = []


_FIXTURE_PLUGIN_ROOT = Path(__file__).resolve().parent / "fixtures" / "single_skill_plugin"


# ---------------------------------------------------------------------------
# A deterministic fake CliRunner — the injected `claude -p` seam.
#
# It records every turn and, per a per-skill recipe, materializes the files a
# real `claude -p` run of that skill's slash command would create. This is the
# only mocked boundary; discovery / fixtures / coverage gate / orchestration
# all run for real against on-disk trees.
# ---------------------------------------------------------------------------


class _FakeCliRunner:
    """A canned `claude -p` runner that creates files + yields canned results."""

    def __init__(
        self,
        *,
        creates: dict[str, tuple[str, ...]] | None = None,
        exit_code: int = 0,
        session_ids: tuple[str | None, ...] = (),
    ) -> None:
        self._creates = creates if creates is not None else {}
        self._exit_code = exit_code
        self._session_ids = list(session_ids)
        self.turns: list[dict[str, object]] = []

    def run(
        self,
        *,
        prompt: str,
        home: Path,
        cwd: Path,
        resume_session_id: str | None,
    ) -> CliResult:
        self.turns.append(
            {"prompt": prompt, "home": str(home), "cwd": str(cwd), "resume": resume_session_id}
        )
        for rel in self._creates.get(prompt, ()):
            target = cwd / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            _ = target.write_text("created by fake claude\n", encoding="utf-8")
        session_id = self._session_ids.pop(0) if self._session_ids else None
        return CliResult(exit_code=self._exit_code, stdout="", stderr="", session_id=session_id)


def _make_plugin(*, root: Path, name: str, skills: dict[str, bool]) -> Path:
    """Write a minimal installed-plugin tree: plugin.json + skills/*/SKILL.md.

    `skills` maps skill-name → whether to write its `SKILL.md` (False writes the
    directory but no SKILL.md, exercising the discovery skip branch).
    """
    root.mkdir(parents=True, exist_ok=True)
    _ = (root / "plugin.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    skills_dir = root / "skills"
    skills_dir.mkdir(exist_ok=True)
    for skill, has_skill_md in skills.items():
        sd = skills_dir / skill
        sd.mkdir(exist_ok=True)
        if has_skill_md:
            _ = (sd / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
    return root


def _make_fixture(*, root: Path, skill: str, prompt: str, expected: tuple[str, ...] | None) -> None:
    sd = root / skill
    sd.mkdir(parents=True, exist_ok=True)
    _ = (sd / "prompt.md").write_text(prompt, encoding="utf-8")
    if expected is not None:
        _ = (sd / "expected_files.txt").write_text("\n".join(expected) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Self-test against the committed tiny single-skill fixture-plugin.
# ---------------------------------------------------------------------------


def test_self_test_single_skill_plugin_round_trip(*, tmp_path: Path) -> None:
    """The committed fixture-plugin drives discovery + gate + a fixture turn.

    Proves the full loop works in isolation with NO real claude binary: the
    fixture-plugin under `fixtures/single_skill_plugin/` exposes exactly one
    skill (`hello`), the fixtures tree carries a matching `hello/` fixture, and
    a fake runner materializes the one expected file.
    """
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    config = HarnessConfig(
        impl_plugin_id="fixture-impl",
        marketplace="local/marketplace.json",
        enabled_plugins=("fixture-plugin@local",),
        plugin_install_dirs=(_FIXTURE_PLUGIN_ROOT,),
        fixtures_root=_FIXTURE_PLUGIN_ROOT / "e2e-cli-fixtures",
    )
    fixtures = unsafe_perform_io(discover_fixtures(fixtures_root=config.fixtures_root).unwrap())
    prompt = fixtures["hello"].prompt
    runner = _FakeCliRunner(creates={prompt: ("hello-output.txt",)})
    result = run_full_round_trip(
        config=config,
        home=home,
        project_root=project,
        injected_runner=runner,
    ).unwrap()
    assert result.discovered_skills == ("hello",)
    assert result.fixtured_skills == ("hello",)
    assert result.passed is True
    assert (project / "hello-output.txt").exists()
    # settings.json was pre-populated under the tmp HOME.
    written = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert written["marketplaces"] == ["local/marketplace.json"]
    assert written["enabledPlugins"] == ["fixture-plugin@local"]


# ---------------------------------------------------------------------------
# Time-bomb coverage gate.
# ---------------------------------------------------------------------------


def test_assert_coverage_passes_when_every_skill_fixtured() -> None:
    assert_coverage(
        discovered_skills=("seed", "doctor"),
        fixtured_skills=frozenset({"seed", "doctor"}),
        exempt_skills=frozenset(),
    )


def test_assert_coverage_passes_when_gap_is_exempt() -> None:
    assert_coverage(
        discovered_skills=("seed", "help"),
        fixtured_skills=frozenset({"seed"}),
        exempt_skills=frozenset({"help"}),
    )


def test_assert_coverage_fails_closed_with_missing_list() -> None:
    with pytest.raises(CoverageGateError) as excinfo:
        assert_coverage(
            discovered_skills=("seed", "doctor", "help"),
            fixtured_skills=frozenset({"seed"}),
            exempt_skills=frozenset(),
        )
    message = str(excinfo.value)
    assert "doctor" in message
    assert "help" in message


def test_coverage_gate_error_is_exception() -> None:
    """The gate raises a plain Exception subclass — pytest fails the run on it,
    fail-closed, without a bare `assert` in product code."""
    assert issubclass(CoverageGateError, Exception)


# ---------------------------------------------------------------------------
# Runner selection via LIVESPEC_E2E_HARNESS.
# ---------------------------------------------------------------------------


def test_select_runner_real_unwraps_to_a_real_cli_runner(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `real` tier yields a `Success` CARRYING a `RealCliRunner`.

    The `unwrap()` half is the point. A conversion bug that hands the CONTAINER to
    the caller — dev-tooling shipped exactly that in `frozenset(IOResult.unwrap())`,
    which silently produced a set holding the wrapper — satisfies every assertion
    that only checks the call succeeded.

    Both conditions sit in ONE `assert` on purpose: this repo enforces 100%
    per-file coverage, and at the RED moment every line AFTER the first failing
    assertion is unexecuted and therefore uncovered. A Red leg must leave no line
    behind, which constrains a Red test to a single failing statement.
    """
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "real")

    outcome = select_runner(injected_runner=None)

    assert isinstance(outcome, Success) and isinstance(
        outcome.unwrap(), RealCliRunner
    ), f"the real tier must yield a Success carrying a RealCliRunner; got {outcome!r}"


def test_select_runner_mock_unwraps_to_the_injected_runner(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "mock")
    injected = _FakeCliRunner()

    outcome = select_runner(injected_runner=injected)

    assert (
        isinstance(outcome, Success) and outcome.unwrap() is injected
    ), f"the mock tier must yield a Success carrying the injected runner; got {outcome!r}"


def test_select_runner_default_is_mock(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVESPEC_E2E_HARNESS", raising=False)
    injected = _FakeCliRunner()

    outcome = select_runner(injected_runner=injected)

    assert (
        isinstance(outcome, Success) and outcome.unwrap() is injected
    ), f"an unset selector must default to the mock tier; got {outcome!r}"


def test_select_runner_mock_without_injected_is_a_failure(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `mock` selection with no injected runner lands on the FAILURE track.

    It used to raise `ValueError`. Ratified livespec v179 clause (a) disqualifies
    any `raise` from the no-expected-failure-mode member — deliberately, whichever
    flavour the raise is — so this is an ordinary conversion rather than an
    exemption: the misconfiguration is a real outcome a caller can act on.

    The call is INSIDE the assert so the statement is still executed at the Red
    moment, where the pre-conversion code raises instead of returning.
    """
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "mock")

    assert isinstance(
        select_runner(injected_runner=None), Failure
    ), "a mock selection with no injected runner must land on the failure track"


# ---------------------------------------------------------------------------
# Step orchestrator.
# ---------------------------------------------------------------------------


def _drove(
    *, config: HarnessConfig, runner: _FakeCliRunner, home: Path, project_root: Path
) -> cli_e2e.WorkflowResult:
    """`run_workflow`'s success VALUE, asserted to be on the success track first.

    `run_workflow` is on the `IOResult` railway since the `8o8e` pair-B
    conversion. Reading `.passed` straight off the CONTAINER would be the
    `frozenset(IOResult.unwrap())` bug this repo already shipped once —
    `.unwrap()` on an `IOResult` yields an `IO[...]`, not the payload — so the
    unwrap is spelled out rather than left implicit.
    """
    outcome = run_workflow(config=config, runner=runner, home=home, project_root=project_root)
    assert isinstance(outcome, IOSuccess), f"run_workflow landed on the failure track: {outcome!r}"
    return unsafe_perform_io(outcome.unwrap())


def _two_skill_config(*, plugin: Path, fixtures_root: Path) -> HarnessConfig:
    return HarnessConfig(
        impl_plugin_id="impl",
        marketplace="local",
        enabled_plugins=("livespec@local",),
        plugin_install_dirs=(plugin,),
        fixtures_root=fixtures_root,
    )


def test_run_workflow_drives_each_fixtured_skill(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=("out.md",))
    runner = _FakeCliRunner(creates={"/seed": ("out.md",)})
    result = _drove(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    assert result.passed is True
    assert result.steps[0].skill == "seed"
    assert result.steps[0].passed is True


def test_run_workflow_records_missing_expected_file_as_failure(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=("never.md",))
    runner = _FakeCliRunner(creates={})  # creates nothing → expected file missing
    result = _drove(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    assert result.passed is False
    assert result.steps[0].missing_files == ("never.md",)


def test_run_workflow_records_nonzero_exit_as_failure(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=None)
    runner = _FakeCliRunner(creates={}, exit_code=1)
    result = _drove(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    assert result.passed is False
    assert result.steps[0].exit_code == 1


def test_run_workflow_runs_install_command_first(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=None)
    runner = _FakeCliRunner(creates={})
    config = HarnessConfig(
        impl_plugin_id="impl",
        marketplace="local",
        enabled_plugins=("livespec@local",),
        plugin_install_dirs=(plugin,),
        fixtures_root=fixtures_root,
        install_command="/plugin install livespec@local",
    )
    _ = run_workflow(
        config=config,
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    assert runner.turns[0]["prompt"] == "/plugin install livespec@local"


def test_run_workflow_resumes_session_across_turns(*, tmp_path: Path) -> None:
    plugin = _make_plugin(
        root=tmp_path / "p", name="livespec", skills={"a-seed": True, "b-doctor": True}
    )
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="a-seed", prompt="/a", expected=None)
    _make_fixture(root=fixtures_root, skill="b-doctor", prompt="/b", expected=None)
    # First turn yields a session id; it MUST flow into the second turn's resume.
    runner = _FakeCliRunner(creates={}, session_ids=("sess-1", None))
    _ = run_workflow(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    assert runner.turns[0]["resume"] is None
    assert runner.turns[1]["resume"] == "sess-1"


def test_run_workflow_install_session_flows_into_first_skill(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=None)
    runner = _FakeCliRunner(creates={}, session_ids=("install-sess", None))
    config = HarnessConfig(
        impl_plugin_id="impl",
        marketplace="local",
        enabled_plugins=("livespec@local",),
        plugin_install_dirs=(plugin,),
        fixtures_root=fixtures_root,
        install_command="/plugin install x",
    )
    _ = run_workflow(
        config=config,
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    # The install turn's session id resumes into the first skill turn.
    assert runner.turns[1]["resume"] == "install-sess"


def test_run_workflow_skips_exempt_skill(*, tmp_path: Path) -> None:
    plugin = _make_plugin(
        root=tmp_path / "p", name="livespec", skills={"seed": True, "legacy": True}
    )
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=None)
    # `legacy` has NO fixture but is exempted → gate passes and it is not run.
    config = HarnessConfig(
        impl_plugin_id="impl",
        marketplace="local",
        enabled_plugins=("livespec@local",),
        plugin_install_dirs=(plugin,),
        fixtures_root=fixtures_root,
        exempt_skills=frozenset({"legacy"}),
    )
    runner = _FakeCliRunner(creates={})
    result = _drove(
        config=config,
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    assert [step.skill for step in result.steps] == ["seed"]


def test_run_workflow_raises_coverage_gate_before_running_steps(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"  # no fixtures at all
    fixtures_root.mkdir()
    runner = _FakeCliRunner(creates={})
    with pytest.raises(CoverageGateError):
        _ = run_workflow(
            config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
            runner=runner,
            home=tmp_path / "home",
            project_root=tmp_path / "proj",
        )
    assert runner.turns == []  # fail-closed BEFORE any skill turn ran


def test_run_workflow_reports_an_unreadable_fixtures_tree_instead_of_gating_on_it(
    *, tmp_path: Path
) -> None:
    """A fixtures tree that could not be READ is a value, not an input to the gate.

    ⛔ THE ORDER IS THE POINT, and it is the second of `run_workflow`'s two
    failure-track returns. The plugin walk SUCCEEDS here, so a version that
    checked only the skills read would sail on and hand the gate an empty
    fixture set — which is precisely a verdict manufactured from a read that
    never happened. Both discovery reads are checked BEFORE `assert_coverage`,
    and `runner.turns` proves nothing was driven.
    """
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures-is-a-file"
    _ = fixtures_root.write_text("not a directory", encoding="utf-8")
    runner = _FakeCliRunner(creates={})

    outcome = run_workflow(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )

    assert isinstance(outcome, IOFailure)
    assert unsafe_perform_io(outcome.failure()).reason == "fixtures-root-not-listed"
    assert runner.turns == []


# ---------------------------------------------------------------------------
# The entry point's failing-step assertion + WorkflowResult helpers.
# ---------------------------------------------------------------------------


def test_entry_point_asserts_on_failing_step(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=("never.md",))
    runner = _FakeCliRunner(creates={})  # never.md never created → step fails
    outcome = run_full_round_trip(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
        injected_runner=runner,
    )

    # A failing step is now a VALUE on the failure track, not a raise (v179).
    assert isinstance(outcome, Failure)
    assert isinstance(outcome.failure(), WorkflowFailedError)
    assert "failing step" in str(outcome.failure())


def test_workflow_result_passed_true_when_no_steps(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={})
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    runner = _FakeCliRunner(creates={})
    result = _drove(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    assert result.passed is True
    assert result.steps == ()


# ---------------------------------------------------------------------------
# The re-export surface + Python-version floor guard.
# ---------------------------------------------------------------------------


def test_module_all_is_sorted_and_exhaustive() -> None:
    """Guard: `__all__` stays sorted (a cheap drift catch on the public surface)."""
    assert cli_e2e.__all__ == sorted(cli_e2e.__all__)
    # Every name in __all__ resolves to a real attribute.
    for name in cli_e2e.__all__:
        assert hasattr(cli_e2e, name)


def test_python_version_floor_guard() -> None:
    """The module imports cleanly on the repo's 3.10 floor (no syntax-level use
    of newer-only features in the public surface)."""
    assert sys.version_info >= (3, 10)
    # The `os` import is used by the selector; assert the env-var contract name.
    assert os.environ.get("LIVESPEC_E2E_HARNESS", "mock") is not None
