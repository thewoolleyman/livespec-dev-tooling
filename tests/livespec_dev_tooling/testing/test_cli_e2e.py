"""Outside-in test for `testing/cli_e2e.py` — the CLI e2e harness.

Per `livespec/SPECIFICATION/contracts.md` §"CLI end-to-end harness contract",
the harness ships five components — driver, structural skill discovery,
per-skill fixtures loader, time-bomb coverage gate, step orchestrator — behind
the importable `test_workflow_full_round_trip` entry point, with the `claude -p`
subprocess as the one injectable seam (selected via `LIVESPEC_E2E_HARNESS`).

This test exercises every component WITHOUT a real `claude` binary or API key:

- **Self-test against a tiny single-skill fixture-plugin** (the committed
  `fixtures/single_skill_plugin/` tree) proving discovery + coverage gate +
  a fixture round-trip work in isolation, driven by a deterministic fake
  `CliRunner` that materializes the expected files (the contract's
  acceptance criterion for Phase 2).
- The structural-discovery edge branches (missing manifest, unparsable
  manifest, non-dict manifest, missing/blank `name`, absent `skills/` dir,
  a `skills/` child that is a file or lacks `SKILL.md`).
- The fixtures loader edge branches (absent root, non-dir child, missing
  `prompt.md`, absent vs. present `expected_files.txt`, comment/blank lines).
- The time-bomb coverage gate (pass when covered or exempt; fail closed with
  the missing list otherwise).
- The `LIVESPEC_E2E_HARNESS` selector (real → RealCliRunner; mock with an
  injected runner; mock with no injected runner → ValueError).
- The orchestrator's session resume, install-command first turn, exempt-skill
  skipping, and the failing-step assertion path.
- `RealCliRunner.run` argv shape via a fake `claude` shim on PATH (no API).

Coverage target: 100% line + branch of `cli_e2e.py`.
"""

from __future__ import annotations

import json
import os
import stat
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
    discover_skills,
    run_workflow,
    select_runner,
)

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
    fixtures = discover_fixtures(fixtures_root=config.fixtures_root)
    prompt = fixtures["hello"].prompt
    runner = _FakeCliRunner(creates={prompt: ("hello-output.txt",)})
    result = run_full_round_trip(
        config=config,
        home=home,
        project_root=project,
        injected_runner=runner,
    )
    assert result.discovered_skills == ("hello",)
    assert result.fixtured_skills == ("hello",)
    assert result.passed is True
    assert (project / "hello-output.txt").exists()
    # settings.json was pre-populated under the tmp HOME.
    written = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert written["marketplaces"] == ["local/marketplace.json"]
    assert written["enabledPlugins"] == ["fixture-plugin@local"]


# ---------------------------------------------------------------------------
# Structural skill discovery.
# ---------------------------------------------------------------------------


def test_discover_skills_reads_prefix_and_walks_skill_dirs(*, tmp_path: Path) -> None:
    plugin = _make_plugin(
        root=tmp_path / "p", name="livespec", skills={"seed": True, "doctor": True}
    )
    discovered = discover_skills(plugin_install_dirs=(plugin,))
    assert discovered == {"livespec": ("doctor", "seed")}


def test_discover_skills_skips_plugin_with_missing_manifest(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "no-manifest"
    (plugin_dir / "skills").mkdir(parents=True)
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_skips_unparsable_manifest(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "bad-json"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text("{not json", encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_skips_non_dict_manifest(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "list-json"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text("[1, 2, 3]", encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_skips_manifest_missing_name(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "no-name"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_skips_manifest_blank_name(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "blank-name"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(json.dumps({"name": ""}), encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {}


def test_discover_skills_empty_when_no_skills_dir(*, tmp_path: Path) -> None:
    plugin_dir = tmp_path / "no-skills-dir"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(json.dumps({"name": "livespec"}), encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin_dir,))
    assert discovered == {"livespec": ()}


def test_discover_skills_skips_skill_child_without_skill_md(*, tmp_path: Path) -> None:
    plugin = _make_plugin(
        root=tmp_path / "p", name="livespec", skills={"good": True, "empty": False}
    )
    # A stray FILE inside skills/ must also be ignored.
    _ = (plugin / "skills" / "stray.txt").write_text("x", encoding="utf-8")
    discovered = discover_skills(plugin_install_dirs=(plugin,))
    assert discovered == {"livespec": ("good",)}


# ---------------------------------------------------------------------------
# Per-skill fixtures loader.
# ---------------------------------------------------------------------------


def test_discover_fixtures_absent_root_yields_empty(*, tmp_path: Path) -> None:
    assert discover_fixtures(fixtures_root=tmp_path / "nope") == {}


def test_discover_fixtures_loads_prompt_and_expected(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    _make_fixture(root=root, skill="seed", prompt="/livespec:seed go", expected=("a.md", "b.md"))
    fixtures = discover_fixtures(fixtures_root=root)
    assert set(fixtures) == {"seed"}
    assert fixtures["seed"].prompt == "/livespec:seed go"
    assert fixtures["seed"].expected_files == ("a.md", "b.md")


def test_discover_fixtures_absent_expected_files_means_no_assertions(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    _make_fixture(root=root, skill="help", prompt="/livespec:help", expected=None)
    fixtures = discover_fixtures(fixtures_root=root)
    assert fixtures["help"].expected_files == ()


def test_discover_fixtures_skips_non_dir_child(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    _ = (root / "README.md").write_text("not a fixture dir", encoding="utf-8")
    assert discover_fixtures(fixtures_root=root) == {}


def test_discover_fixtures_skips_dir_without_prompt(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    (root / "incomplete").mkdir(parents=True)
    assert discover_fixtures(fixtures_root=root) == {}


def test_discover_fixtures_strips_comments_and_blanks_in_expected(*, tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    sd = root / "seed"
    sd.mkdir(parents=True)
    _ = (sd / "prompt.md").write_text("/livespec:seed", encoding="utf-8")
    _ = (sd / "expected_files.txt").write_text(
        "# a comment\n\nSPECIFICATION/spec.md\n   \n# trailing\n",
        encoding="utf-8",
    )
    fixtures = discover_fixtures(fixtures_root=root)
    assert fixtures["seed"].expected_files == ("SPECIFICATION/spec.md",)


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


def test_select_runner_real_returns_real_cli_runner(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "real")
    runner = select_runner(injected_runner=None)
    assert isinstance(runner, RealCliRunner)


def test_select_runner_mock_returns_injected(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "mock")
    injected = _FakeCliRunner()
    assert select_runner(injected_runner=injected) is injected


def test_select_runner_default_is_mock(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVESPEC_E2E_HARNESS", raising=False)
    injected = _FakeCliRunner()
    assert select_runner(injected_runner=injected) is injected


def test_select_runner_mock_without_injected_raises(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVESPEC_E2E_HARNESS", "mock")
    with pytest.raises(ValueError, match="requires an injected"):
        _ = select_runner(injected_runner=None)


# ---------------------------------------------------------------------------
# Step orchestrator.
# ---------------------------------------------------------------------------


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
    result = run_workflow(
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
    result = run_workflow(
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
    result = run_workflow(
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
    result = run_workflow(
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


# ---------------------------------------------------------------------------
# The entry point's failing-step assertion + WorkflowResult helpers.
# ---------------------------------------------------------------------------


def test_entry_point_asserts_on_failing_step(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=("never.md",))
    runner = _FakeCliRunner(creates={})  # never.md never created → step fails
    with pytest.raises(WorkflowFailedError, match="failing step"):
        _ = run_full_round_trip(
            config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
            home=tmp_path / "home",
            project_root=tmp_path / "proj",
            injected_runner=runner,
        )


def test_workflow_result_passed_true_when_no_steps(*, tmp_path: Path) -> None:
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={})
    fixtures_root = tmp_path / "fixtures"
    fixtures_root.mkdir()
    runner = _FakeCliRunner(creates={})
    result = run_workflow(
        config=_two_skill_config(plugin=plugin, fixtures_root=fixtures_root),
        runner=runner,
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
    )
    assert result.passed is True
    assert result.steps == ()


# ---------------------------------------------------------------------------
# RealCliRunner argv shape — exercised against a fake `claude` shim on PATH.
# No API key, no network: the shim is a tiny script that echoes its argv.
# ---------------------------------------------------------------------------


def _install_fake_claude(*, bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "fake-claude"
    _ = shim.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdout.write(' '.join(sys.argv[1:]))\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def test_real_cli_runner_fresh_session_argv(*, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    shim = _install_fake_claude(bin_dir=bin_dir)
    runner = RealCliRunner(claude_binary=str(shim))
    result = runner.run(
        prompt="/livespec:seed",
        home=tmp_path / "home",
        cwd=tmp_path,
        resume_session_id=None,
    )
    assert result.exit_code == 0
    assert result.stdout == "-p /livespec:seed"
    assert result.session_id is None


def test_real_cli_runner_resume_session_argv(*, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    shim = _install_fake_claude(bin_dir=bin_dir)
    runner = RealCliRunner(claude_binary=str(shim))
    result = runner.run(
        prompt="/livespec:doctor",
        home=tmp_path / "home",
        cwd=tmp_path,
        resume_session_id="sess-9",
    )
    assert result.stdout == "--resume sess-9 -p /livespec:doctor"


def test_real_cli_runner_sets_home_env(*, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    home = tmp_path / "myhome"
    shim = bin_dir / "echo-home"
    bin_dir.mkdir(parents=True)
    _ = shim.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "sys.stdout.write(os.environ['HOME'])\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    runner = RealCliRunner(claude_binary=str(shim))
    result = runner.run(prompt="x", home=home, cwd=tmp_path, resume_session_id=None)
    assert result.stdout == str(home)


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
