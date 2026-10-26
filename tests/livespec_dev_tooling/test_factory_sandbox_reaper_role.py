"""The factory sandbox reaper keeps what it cannot prove is safe to delete.

Work-item `bd-ib-u5facl` (livespec-orchestrator-beads-fabro ledger). Petri stops
a Kubernetes sandbox at run end but never deletes it, so a `stopped` / `no-pod`
record and a ~0.5 G node workspace directory accumulate per run. The role's
`factory_sandbox_reaper.py` deletes them on a timer under a binding retention
rule: age-only (24 h) plus an evidence guard. These tests run the committed
script's decision functions and its whole pass against fake `fabro`,
`lithos-sandbox` and `git` runners, and read the committed play, defaults and
host_vars for the claims that are about wiring rather than behaviour.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "factory_sandbox_reaper"
_SCRIPT = _ROLE / "files" / "factory_sandbox_reaper.py"
_PLAY = _REPO_ROOT / "ansible" / "fabro-hosts.yml"
_GMKTEC_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars" / "gmktec-xubuntu.yml"


def _load() -> ModuleType:
    assert _SCRIPT.is_file(), f"{_SCRIPT.relative_to(_REPO_ROOT)} must exist"
    name = "factory_sandbox_reaper_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # No bytecode beside the script: a `.pyc` inside the role tree is a binary
    # file `check-ansible-hostname-free` cannot decode as UTF-8.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


reaper = _load()

_NOW = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)
_HORIZON = timedelta(hours=24)
_ORIGIN = "https://github.com/example/repo"
_HOUR_MS = 3_600_000


def _run(
    *,
    run_id: str = "01RUN",
    kind: str = "succeeded",
    hours_ago_ended: float | None = 30.0,
    dispatch_id: str | None = "d1",
    origin: str | None = _ORIGIN,
) -> object:
    """A Run whose end time is `hours_ago_ended` before _NOW (one hour of wall time)."""
    if hours_ago_ended is None:
        return reaper.Run(run_id, kind, None, None, dispatch_id, origin)
    started = _NOW - timedelta(hours=hours_ago_ended + 1)
    return reaper.Run(run_id, kind, started.isoformat(), _HOUR_MS, dispatch_id, origin)


def _sandbox(*, run_id: str | None = "01RUN", state: str = "stopped", sid: str = "sb-1") -> object:
    return reaper.Sandbox(sid, state, run_id)


def _verdicts(
    *,
    sandbox: object,
    run: object | None,
    refs: frozenset[str] | None = frozenset(),
    max_deletions: int = 50,
) -> list[object]:
    runs = {} if run is None else {run.run_id: run}
    keeps, candidates = reaper.classify(sandboxes=[sandbox], runs=runs, now=_NOW, min_age=_HORIZON)
    origins = {c[1].origin_url: refs for c in candidates if c[1].origin_url is not None}
    return keeps + reaper.finalize(
        candidates=candidates, preserved=origins, max_deletions=max_deletions
    )


def test_an_old_terminal_run_without_a_preserved_ref_is_deleted() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run())
    assert verdict.action == "delete", verdict.reason


def test_a_failed_run_is_as_deletable_as_a_succeeded_one() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(kind="failed"))
    assert verdict.action == "delete", verdict.reason


def test_a_run_that_ended_less_than_the_horizon_ago_is_kept() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(hours_ago_ended=23.0))
    assert verdict.action == "keep"
    assert "younger than the horizon" in verdict.reason


@pytest.mark.parametrize("state", ["running", "starting", "paused", ""])
def test_a_sandbox_that_is_not_stopped_is_kept(*, state: str) -> None:
    [verdict] = _verdicts(sandbox=_sandbox(state=state), run=_run())
    assert verdict.action == "keep"
    assert "not stopped" in verdict.reason


def test_a_run_missing_from_fabro_ps_is_kept_and_called_out() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=None)
    assert verdict.action == "keep"
    assert "UNKNOWN RUN" in verdict.reason


def test_a_sandbox_whose_name_carries_no_run_is_kept_as_unknown() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(run_id=None), run=_run())
    assert verdict.action == "keep"
    assert "UNKNOWN RUN" in verdict.reason


@pytest.mark.parametrize("kind", ["running", "starting", "blocked", "paused", ""])
def test_a_run_that_is_not_terminal_is_kept(*, kind: str) -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(kind=kind))
    assert verdict.action == "keep"
    assert "not terminal" in verdict.reason


def test_a_terminal_run_with_no_recorded_end_is_kept() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(hours_ago_ended=None))
    assert verdict.action == "keep"
    assert "end time unknown" in verdict.reason


def test_an_unparseable_start_time_keeps_the_sandbox() -> None:
    run = reaper.Run("01RUN", "succeeded", "not-a-date", _HOUR_MS, "d1", _ORIGIN)
    [verdict] = _verdicts(sandbox=_sandbox(), run=run)
    assert verdict.action == "keep"


def test_a_naive_start_time_is_read_as_utc() -> None:
    naive = (_NOW - timedelta(hours=40)).replace(tzinfo=None).isoformat()
    run = reaper.Run("01RUN", "succeeded", naive, _HOUR_MS, "d1", _ORIGIN)
    assert reaper.run_end(run=run) == _NOW - timedelta(hours=39)


def test_a_preserved_needs_human_ref_keeps_the_sandbox() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(), refs=frozenset({"d1", "other"}))
    assert verdict.action == "keep"
    assert "refs/heads/needs-human/d1" in verdict.reason


def test_a_preserved_ref_for_another_dispatch_does_not_keep_this_one() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(), refs=frozenset({"other"}))
    assert verdict.action == "delete", verdict.reason


def test_an_ls_remote_failure_keeps_the_sandbox() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(), refs=None)
    assert verdict.action == "keep"
    assert "ORIGIN UNOBSERVABLE" in verdict.reason


def test_a_run_with_no_origin_url_is_kept() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(origin=None))
    assert verdict.action == "keep"
    assert "ORIGIN UNOBSERVABLE" in verdict.reason


def test_a_run_with_no_dispatch_id_is_kept() -> None:
    [verdict] = _verdicts(sandbox=_sandbox(), run=_run(dispatch_id=None))
    assert verdict.action == "keep"
    assert "dispatch.id" in verdict.reason


def test_the_per_pass_cap_defers_the_rest_oldest_ended_first() -> None:
    sandboxes = [_sandbox(run_id=f"R{i}", sid=f"sb-{i}") for i in range(4)]
    runs = {f"R{i}": _run(run_id=f"R{i}", hours_ago_ended=30.0 + i) for i in range(4)}
    keeps, candidates = reaper.classify(sandboxes=sandboxes, runs=runs, now=_NOW, min_age=_HORIZON)
    verdicts = reaper.finalize(
        candidates=candidates, preserved={_ORIGIN: frozenset()}, max_deletions=2
    )
    assert keeps == []
    assert [(v.sandbox_id, v.action) for v in verdicts] == [
        ("sb-3", "delete"),
        ("sb-2", "delete"),
        ("sb-1", "keep"),
        ("sb-0", "keep"),
    ]
    assert "cap of 2" in verdicts[2].reason


def test_the_run_id_comes_from_the_petri_run_label_then_the_name() -> None:
    labelled = {"name": "x", "labels": {"petri.run": "01abc"}}
    named = {"name": "petri-01M5VK9D2241Y4WXVX92AGRR7T-l0"}
    assert reaper.sandbox_run_id(record=labelled) == "01ABC"
    assert reaper.sandbox_run_id(record=named) == "01M5VK9D2241Y4WXVX92AGRR7T"
    assert reaper.sandbox_run_id(record={"name": "something-else"}) is None
    assert reaper.sandbox_run_id(record={"name": "x", "labels": {"petri.run": ""}}) is None


def test_preserved_refs_are_read_from_ls_remote_lines() -> None:
    output = (
        "aaa\trefs/heads/needs-human/d1\n"
        "bbb\trefs/heads/needs-human/d2\n"
        "ccc\trefs/heads/needs-human/\n"
        "ddd\trefs/heads/feat/not-it\n"
    )
    assert reaper.preserved_dispatch_ids(output=output) == frozenset({"d1", "d2"})


# --- one whole pass against fake fabro / lithos-sandbox / git ----------------


class _FakeHost:
    """A recording runner standing in for fabro, lithos-sandbox and git."""

    def __init__(
        self, *, ls_remote_rc: int = 0, delete_rc: int = 0, list_rc: int = 0, ps_rc: int = 0
    ) -> None:
        self.calls: list[list[str]] = []
        self.ls_remote_rc = ls_remote_rc
        self.delete_rc = delete_rc
        self.list_rc = list_rc
        self.ps_rc = ps_rc

    def __call__(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        argv = list(argv)
        self.calls.append(argv)
        if argv[0] == "git":
            out = "aaa\trefs/heads/needs-human/dkeep\n" if self.ls_remote_rc == 0 else ""
            return subprocess.CompletedProcess(argv, self.ls_remote_rc, out, "")
        if argv[-1] == "list":
            return subprocess.CompletedProcess(argv, self.list_rc, json.dumps(_sandbox_list()), "")
        if argv[1] == "ps":
            return subprocess.CompletedProcess(argv, self.ps_rc, json.dumps(_ps_rows()), "")
        return subprocess.CompletedProcess(argv, self.delete_rc, "", "boom\n")

    def deletes(self) -> list[str]:
        return [c[-1] for c in self.calls if "delete" in c]


def _sandbox_list() -> list[dict[str, object]]:
    return [
        {
            "id": "sb-old",
            "name": "petri-OLD-l0",
            "state": "stopped",
            "labels": {"petri.run": "OLD"},
        },
        {
            "id": "sb-new",
            "name": "petri-NEW-l0",
            "state": "stopped",
            "labels": {"petri.run": "NEW"},
        },
        {"id": "sb-held", "name": "petri-HELD-l0", "state": "stopped"},
        {"id": "sb-live", "name": "petri-LIVE-l0", "state": "running"},
    ]


def _ps_row(*, run_id: str, hours_ago_ended: float, dispatch: str) -> dict[str, object]:
    started = _NOW - timedelta(hours=hours_ago_ended + 1)
    return {
        "run_id": run_id,
        "status": {"kind": "succeeded", "reason": "completed"},
        "start_time": started.isoformat(),
        "wall_time_ms": _HOUR_MS,
        "labels": {"livespec.dispatch.id": dispatch},
        "repo_origin_url": _ORIGIN,
    }


def _ps_rows() -> list[dict[str, object]]:
    return [
        _ps_row(run_id="OLD", hours_ago_ended=48.0, dispatch="dold"),
        _ps_row(run_id="NEW", hours_ago_ended=1.0, dispatch="dnew"),
        _ps_row(run_id="HELD", hours_ago_ended=48.0, dispatch="dkeep"),
        {"run_id": "LIVE", "status": {"kind": "running"}, "labels": None},
    ]


def _env(*, apply: str | None) -> dict[str, str]:
    env = {
        "REAPER_FABRO_BIN": "/f/fabro",
        "REAPER_FABRO_SERVER": "http://127.0.0.1:32276",
        "REAPER_LITHOS_BIN": "/u/lithos-sandbox",
    }
    return env if apply is None else env | {"REAPER_APPLY": apply}


def _pass(*, host: _FakeHost, apply: str | None) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = reaper.reap(env=_env(apply=apply), run=host, now=_NOW, emit=lines.append)
    return code, lines


def test_the_default_pass_is_a_dry_run_that_deletes_nothing() -> None:
    host = _FakeHost()
    code, lines = _pass(host=host, apply=None)
    assert code == 0
    assert host.deletes() == [], "the unset default must be report-only"
    text = "\n".join(lines)
    assert "DRY-RUN DELETE sb-old" in text
    assert "DRY-RUN KEEP   sb-new" in text and "younger than the horizon" in text
    assert "origin holds refs/heads/needs-human/dkeep" in text
    assert "not stopped" in text
    assert "1 to delete, 3 kept, 4 sandboxes" in text


def test_an_explicit_zero_is_also_a_dry_run() -> None:
    host = _FakeHost()
    _pass(host=host, apply="0")
    assert host.deletes() == []


def test_apply_deletes_only_what_the_decision_chose_through_the_driver() -> None:
    host = _FakeHost()
    code, lines = _pass(host=host, apply="1")
    assert code == 0
    assert host.deletes() == ["sb-old"]
    delete_call = next(c for c in host.calls if "delete" in c)
    assert delete_call == [
        "/u/lithos-sandbox", "--provider", "kubernetes", "--events", "off",
        "sandbox", "delete", "sb-old",
    ]  # fmt: skip
    assert "DELETED sb-old" in lines
    assert any(line.startswith("APPLY summary") for line in lines)


def test_a_failed_delete_is_reported_and_fails_the_pass() -> None:
    host = _FakeHost(delete_rc=3)
    code, lines = _pass(host=host, apply="1")
    assert code == 1
    assert any("delete of sb-old failed (rc 3): boom" in line for line in lines)


def test_an_ls_remote_failure_keeps_every_sandbox_of_that_repository() -> None:
    host = _FakeHost(ls_remote_rc=128)
    code, lines = _pass(host=host, apply="1")
    assert code == 0
    assert host.deletes() == []
    assert any("ORIGIN UNOBSERVABLE" in line for line in lines)


@pytest.mark.parametrize("failing", [{"list_rc": 1}, {"ps_rc": 1}])
def test_an_unreadable_sandbox_list_or_ps_deletes_nothing(*, failing: dict[str, int]) -> None:
    host = _FakeHost(**failing)
    code, lines = _pass(host=host, apply="1")
    assert code == 1
    assert host.deletes() == []
    assert lines[0].startswith("ERROR:")


def test_the_cap_and_horizon_come_from_the_environment() -> None:
    host = _FakeHost()
    lines: list[str] = []
    env = _env(apply="0") | {"REAPER_MIN_AGE_HOURS": "0.5", "REAPER_MAX_DELETIONS": "1"}
    reaper.reap(env=env, run=host, now=_NOW, emit=lines.append)
    text = "\n".join(lines)
    assert "DRY-RUN DELETE sb-old" in text
    assert "cap of 1" in text, "NEW and OLD are both past 0.5 h; the cap must defer one"


# --- the real subprocess runner and entry point --------------------------------


def test_the_real_runner_returns_a_completed_process() -> None:
    done = reaper.subprocess_runner([sys.executable, "-c", "print('hi')"])
    assert (done.returncode, done.stdout.strip()) == (0, "hi")


def test_the_real_runner_turns_a_missing_binary_into_a_failed_command() -> None:
    done = reaper.subprocess_runner(["/nonexistent/lithos-sandbox"])
    assert done.returncode == 127
    assert done.stderr


def test_the_real_runner_turns_a_timeout_into_a_failed_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reaper, "COMMAND_TIMEOUT_SECONDS", 0.2)
    done = reaper.subprocess_runner([sys.executable, "-c", "import time; time.sleep(5)"])
    assert done.returncode == 127


def test_the_real_runner_never_lets_git_prompt_for_credentials() -> None:
    code = "import os; print(os.environ['GIT_TERMINAL_PROMPT'])"
    assert reaper.subprocess_runner([sys.executable, "-c", code]).stdout.strip() == "0"


def test_main_runs_one_pass_with_the_process_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _FakeHost()
    monkeypatch.setattr(reaper, "subprocess_runner", host)
    for key, value in _env(apply=None).items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("REAPER_APPLY", raising=False)
    # Real "now" is days past every fixture run's end, so the old and new runs are
    # both eligible; the point here is only that main wires env, runner and print.
    assert reaper.main() == 0
    assert "DRY-RUN summary" in capsys.readouterr().out
    assert host.deletes() == []


# --- the committed wiring ------------------------------------------------------


def _text(*, path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(_REPO_ROOT)} must exist"
    return path.read_text(encoding="utf-8")


def test_the_sandbox_host_play_includes_the_role_with_its_own_tag_and_a_gate() -> None:
    play = _text(path=_PLAY)
    sandbox = play.split("hosts: sandbox_hosts", 1)[1].split("\n- name: ", 1)[0]
    entry = re.search(
        r"^    - role: factory_sandbox_reaper\n"
        r"      tags: \[factory_sandbox_reaper\]\n"
        r"      when: factory_sandbox_reaper_enabled \| default\(false\) \| bool$",
        sandbox,
        re.MULTILINE,
    )
    assert entry is not None, "the role needs its own tag and an opt-in `when`:\n" + sandbox


def test_deletion_and_enablement_default_off_in_the_role() -> None:
    defaults = _text(path=_ROLE / "defaults" / "main.yml")
    assert re.search(r"^factory_sandbox_reaper_enabled: false$", defaults, re.MULTILINE)
    assert re.search(r"^factory_sandbox_reaper_apply: false$", defaults, re.MULTILINE)
    assert re.search(r"^factory_sandbox_reaper_min_age_hours: 24$", defaults, re.MULTILINE)
    assert re.search(r"^factory_sandbox_reaper_max_deletions: 50$", defaults, re.MULTILINE)


def test_the_sandbox_host_declares_the_reaper_enabled_but_report_only() -> None:
    host_vars = _text(path=_GMKTEC_VARS)
    assert re.search(r"^factory_sandbox_reaper_enabled: true$", host_vars, re.MULTILINE)
    assert re.search(r"^factory_sandbox_reaper_apply: false$", host_vars, re.MULTILINE)


def test_the_service_passes_the_toggle_to_the_script_and_targets_the_fleet_instance() -> None:
    service = _text(path=_ROLE / "templates" / "livespec-factory-sandbox-reaper.service.j2")
    for variable in (
        "REAPER_APPLY",
        "REAPER_FABRO_BIN",
        "REAPER_FABRO_SERVER",
        "REAPER_LITHOS_BIN",
        "REAPER_PROVIDER",
        "REAPER_MIN_AGE_HOURS",
        "REAPER_MAX_DELETIONS",
    ):
        assert f"{variable}=" in service, variable
    assert "factory_sandbox_reaper_apply | bool else '0'" in service
    assert "User={{ factory_sandbox_reaper_user }}" in service
    defaults = _text(path=_ROLE / "defaults" / "main.yml")
    assert "factory_sandbox_reaper_instance_unit: fabro-server" in defaults


def test_the_converge_verifies_with_a_forced_report_only_pass_then_arms_the_timer() -> None:
    tasks = _text(path=_ROLE / "tasks" / "main.yml")
    verify = tasks.split("- name: Verify the installed reaper", 1)[1].split("- name: Arm", 1)[0]
    assert 'REAPER_APPLY: "0"' in verify
    arm = tasks.split("- name: Arm the factory sandbox reaper timer", 1)[1]
    assert "enabled: true" in arm and "state: started" in arm
    timer = _text(path=_ROLE / "templates" / "livespec-factory-sandbox-reaper.timer.j2")
    assert "OnCalendar=" in timer and "WantedBy=timers.target" in timer


def test_the_host_vars_doc_states_the_scope_and_the_toggle() -> None:
    doc = _text(path=_ROLE / "HOST_VARS.md")
    assert "mi-homelab" in doc and "NOT" in doc
    assert "factory_sandbox_reaper_apply: true" in doc
    assert "bd-ib-u5facl" in doc
