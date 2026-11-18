"""Behavioural and shape tests for the breakage_pass host-timer role (bd-ib-voazyv, S3).

The runner script is executed for real against a stub dispatcher, so the closing
journal line and the success marker are observed rather than read from the source.
The role's own files are read for the properties the Definition of Done and the
2026-11-13 reboot note require: a schedule of at most 30 minutes, stable paths, and a
hold that starts nothing until the host variables enable it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "breakage_pass"
_RUNNER = _ROLE / "files" / "livespec-breakage-pass"
_CACHE_SEGMENT = "/.claude/plugins/cache/"


_BRANCH = "master"
_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
_DISPATCHER = Path(".claude-plugin") / "scripts" / "bin" / "dispatcher.py"


def _git(*, cwd: Path, args: list[str]) -> str:
    done = subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            *args,
        ],
        cwd=cwd,
        env=_GIT_ENV,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


class _World:
    """An origin, a seed clone that publishes to it, and the host's detached checkout."""

    def __init__(self, *, tmp_path: Path, body: str) -> None:
        self.origin = tmp_path / "origin.git"
        self.seed = tmp_path / "seed"
        self.checkout = tmp_path / "checkout"
        self.state = tmp_path / "state"
        self.state.mkdir()
        _ = _git(cwd=tmp_path, args=["init", "--bare", "-b", _BRANCH, str(self.origin)])
        _ = _git(cwd=tmp_path, args=["clone", str(self.origin), str(self.seed)])
        _ = _git(cwd=self.seed, args=["checkout", "-b", _BRANCH])
        self.publish(body=body)
        _ = _git(cwd=tmp_path, args=["clone", str(self.origin), str(self.checkout)])
        _ = _git(cwd=self.checkout, args=["checkout", "--detach"])

    def publish(self, *, body: str) -> str:
        target = self.seed / _DISPATCHER
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(body, encoding="utf-8")
        _ = _git(cwd=self.seed, args=["add", "-A"])
        _ = _git(cwd=self.seed, args=["commit", "-q", "-m", "publish"])
        _ = _git(cwd=self.seed, args=["push", "-q", "origin", _BRANCH])
        return _git(cwd=self.seed, args=["rev-parse", "HEAD"])

    def run(
        self,
        *,
        checkout: Path | None = None,
        proc_root: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        path = checkout if checkout is not None else self.checkout
        env = dict(_GIT_ENV)
        if proc_root is not None:
            env["LIVESPEC_BREAKAGE_PROC_ROOT"] = str(proc_root)
        return subprocess.run(
            [
                "/bin/bash",
                str(_RUNNER),
                "alpha",
                str(path),
                str(path / ".claude-plugin"),
                "/usr/bin/python3",
                str(self.state),
                str(path),
                _BRANCH,
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )


def _run_runner(*, tmp_path: Path, body: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    world = _World(tmp_path=tmp_path, body=body)
    return world.run(), world.state


def test_a_passing_pass_journals_its_verdicts_then_a_result_line_and_marks_success(
    *, tmp_path: Path
) -> None:
    done, state = _run_runner(tmp_path=tmp_path, body="print('breakage-pass wf.yml run=u green')\n")

    lines = done.stdout.splitlines()
    assert done.returncode == 0
    assert lines[0].startswith("breakage-pass-sync repo=alpha path=")
    assert lines[0].endswith("action=current")
    assert lines[1:] == [
        "breakage-pass wf.yml run=u green",
        "breakage-pass-result repo=alpha rc=0",
    ]
    assert (state / "alpha.last-success").is_file()


def test_a_failing_pass_keeps_its_status_and_leaves_no_success_marker(*, tmp_path: Path) -> None:
    done, state = _run_runner(tmp_path=tmp_path, body="import sys\nsys.exit(1)\n")

    assert done.returncode == 1
    assert done.stdout.splitlines()[-1] == "breakage-pass-result repo=alpha rc=1"
    assert not (state / "alpha.last-success").exists()


def test_a_repository_watching_no_workflow_still_journals_the_result_line(
    *, tmp_path: Path
) -> None:
    done, _ = _run_runner(tmp_path=tmp_path, body="")

    assert done.stdout.splitlines()[-1] == "breakage-pass-result repo=alpha rc=0"
    assert len(done.stdout.splitlines()) == 2


def test_a_checkout_behind_origin_is_fast_forwarded_before_the_pass_runs(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('old reader')\n")
    tip = world.publish(body="print('new reader')\n")

    done = world.run()

    lines = done.stdout.splitlines()
    assert done.returncode == 0
    assert f"head={tip} origin={tip} action=advanced" in lines[0]
    assert lines[1] == "new reader"
    assert _git(cwd=world.checkout, args=["rev-parse", "HEAD"]) == tip
    # The acceptance read-back the docs prescribe: the fix is an ancestor of the reader.
    _ = _git(cwd=world.checkout, args=["merge-base", "--is-ancestor", tip, "HEAD"])


def _refused(*, done: subprocess.CompletedProcess[str], world: _World, reason: str) -> None:
    lines = done.stdout.splitlines()
    assert done.returncode == 70
    assert lines[0].startswith("breakage-pass-sync-refused repo=alpha path=")
    assert lines[0].endswith(f"reason={reason}")
    assert lines[1:] == ["breakage-pass-result repo=alpha rc=70"]
    assert "reader" not in done.stdout
    assert not (world.state / "alpha.last-success").exists()


def test_a_checkout_on_another_branch_is_refused_and_no_pass_runs(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    _ = _git(cwd=world.checkout, args=["checkout", "-q", "-b", "feature"])

    _refused(done=world.run(), world=world, reason="on-branch-feature")


def test_a_checkout_with_a_modified_tracked_file_is_refused(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    _ = (world.checkout / _DISPATCHER).write_text("print('edited reader')\n", encoding="utf-8")

    _refused(done=world.run(), world=world, reason="modified-tracked-files")


def test_a_checkout_holding_a_commit_origin_lacks_is_refused(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    _ = (world.checkout / _DISPATCHER).write_text("print('local reader')\n", encoding="utf-8")
    _ = _git(cwd=world.checkout, args=["commit", "-q", "-am", "local only"])

    _refused(done=world.run(), world=world, reason="not-fast-forward")


def test_an_unreachable_origin_is_refused(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    _ = _git(
        cwd=world.checkout,
        args=["remote", "set-url", "origin", str(tmp_path / "missing.git")],
    )

    _refused(done=world.run(), world=world, reason="fetch-failed")


def test_a_path_that_is_not_a_git_checkout_is_refused(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    plain = tmp_path / "plain"
    plain.mkdir()

    _refused(done=world.run(checkout=plain), world=world, reason="not-a-git-checkout")


def test_an_untracked_file_does_not_stop_the_pass(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    _ = (world.checkout / "stray.txt").write_text("x", encoding="utf-8")

    done = world.run()

    assert done.returncode == 0
    assert "reader ran" in done.stdout


def _defaults() -> dict[str, object]:
    loaded: dict[str, object] = yaml.safe_load(
        (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    )
    return loaded


def test_the_role_defaults_hold_the_timers_and_start_nothing() -> None:
    defaults = _defaults()

    assert defaults["breakage_pass_enabled"] is False
    assert defaults["breakage_pass_repos"] == []


def test_the_schedule_stays_within_thirty_minutes() -> None:
    defaults = _defaults()
    interval = int(str(defaults["breakage_pass_interval_minutes"]))
    timeout = int(str(defaults["breakage_pass_timeout_seconds"]))
    stop = int(str(defaults["breakage_pass_stop_timeout_seconds"]))

    assert stop == 90
    assert interval + (timeout + stop) / 60 <= 30
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "breakage_pass_stop_timeout_seconds | int" in tasks
    timer = (_ROLE / "templates" / "breakage-pass.timer.j2").read_text(encoding="utf-8")
    assert "OnUnitInactiveSec={{ breakage_pass_interval_minutes }}min" in timer


def test_no_role_default_path_names_a_versioned_plugin_cache_or_tmp() -> None:
    defaults = _defaults()

    for key in (
        "breakage_pass_plugin_root",
        "breakage_pass_runner_bin",
        "breakage_pass_state_dir",
    ):
        value = str(defaults[key])
        assert _CACHE_SEGMENT not in value
        assert not value.startswith("/tmp")


def test_the_service_runs_the_pass_under_the_tenant_credential_wrapper() -> None:
    service = (_ROLE / "templates" / "breakage-pass.service.j2").read_text(encoding="utf-8")

    assert (
        "ExecStart={{ breakage_pass_tenant_wrap_bin }} -- {{ breakage_pass_runner_bin }}" in service
    )
    assert "Environment=TW_REPO={{ item.repo }}" in service
    assert "TimeoutStartSec={{ breakage_pass_timeout_seconds }}" in service


def test_a_pass_cannot_overlap_itself() -> None:
    service = (_ROLE / "templates" / "breakage-pass.service.j2").read_text(encoding="utf-8")
    timer = (_ROLE / "templates" / "breakage-pass.timer.j2").read_text(encoding="utf-8")

    assert "Type=oneshot" in service
    assert "TimeoutStopSec={{ breakage_pass_stop_timeout_seconds }}" in service
    # Counted from the end of the previous pass, so a running pass is never restarted.
    assert "OnUnitInactiveSec=" in timer
    assert "OnCalendar" not in timer
    assert "OnUnitActiveSec" not in timer


def test_the_role_preflights_each_repository_and_guards_arming_under_check_mode() -> None:
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")

    assert "'/.livespec.jsonc'" in tasks
    assert "/scripts/bin/dispatcher.py" in tasks
    assert "livespec-tenant-wrap.sh --resolve" in tasks
    assert "check_mode: false" in tasks
    assert "not ansible_check_mode or item.stat.exists" in tasks


def test_the_staleness_unit_alerts_through_on_failure_and_the_dev_host_names_the_target() -> None:
    service = (_ROLE / "templates" / "breakage-pass-staleness.service.j2").read_text(
        encoding="utf-8"
    )
    host_vars = (_ANSIBLE / "inventory" / "host_vars" / "vps.yml").read_text(encoding="utf-8")

    assert "OnFailure={{ breakage_pass_staleness_on_failure }}" in service
    assert re.search(
        r"^breakage_pass_staleness_on_failure: host-unit-alert@%n\.service$",
        host_vars,
        re.MULTILINE,
    )


def test_the_revert_removes_unit_files_and_the_docs_say_so_and_name_the_apply_order() -> None:
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    docs = (_ROLE / "HOST_VARS.md").read_text(encoding="utf-8")

    assert "state: absent" in tasks
    assert "breakage_pass_unwanted | length > 0" in tasks
    assert "NOT currently installed" in docs
    assert "`reconcile_runs` must be reviewed and applied first" in docs
    assert "removes every breakage pass unit file" in docs


def test_the_dev_host_playbook_carries_the_role_and_the_host_variables_enable_it() -> None:
    playbook = (_ANSIBLE / "dev-host.yml").read_text(encoding="utf-8")
    host_vars = (_ANSIBLE / "inventory" / "host_vars" / "vps.yml").read_text(encoding="utf-8")

    assert re.search(r"- role: breakage_pass\n\s+tags: \[breakage_pass\]", playbook)
    assert re.search(r"^breakage_pass_enabled: true$", host_vars, re.MULTILINE)
    assert "/home/ubuntu/workspace/livespec-orchestrator-beads-fabro" in host_vars


def test_the_service_hands_the_runner_the_orchestrator_checkout_and_branch() -> None:
    service = (_ROLE / "templates" / "breakage-pass.service.j2").read_text(encoding="utf-8")

    assert (
        "{{ breakage_pass_state_dir }} {{ breakage_pass_orchestrator_checkout }}"
        " {{ breakage_pass_branch }}"
    ) in service
    assert _defaults()["breakage_pass_branch"] == "master"


def test_the_role_refuses_a_missing_checkout_or_branch_and_the_docs_name_the_acceptance_readback() -> (
    None
):
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    docs = (_ROLE / "HOST_VARS.md").read_text(encoding="utf-8")

    assert "breakage_pass_orchestrator_checkout | string | length > 0" in tasks
    assert "breakage_pass_branch | string | length > 0" in tasks
    assert "COMMITTED IS NOT CONVERGED" in docs
    assert "merge-base --is-ancestor" in docs
    assert "exit 70" in docs


def _fake_proc(
    *,
    root: Path,
    pid: int,
    argv: list[str],
    cwd: Path | None,
) -> None:
    """One fake /proc/<pid> entry: a NUL-separated cmdline and an optional cwd link."""
    entry = root / str(pid)
    entry.mkdir(parents=True)
    _ = (entry / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    if cwd is not None:
        (entry / "cwd").symlink_to(cwd)


def _skipped(*, done: subprocess.CompletedProcess[str], world: _World) -> list[str]:
    """Assert a skip: exit 0, no success marker, no pass, checkout untouched."""
    assert done.returncode == 0
    assert not (world.state / "alpha.last-success").exists()
    assert "reader ran" not in done.stdout
    assert "breakage-pass-result" not in done.stdout
    assert "breakage-pass-sync" not in done.stdout
    return done.stdout.splitlines()


def test_a_live_dispatcher_script_in_the_checkout_skips_the_whole_pass(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    before = _git(cwd=world.checkout, args=["rev-parse", "HEAD"])
    tip = world.publish(body="print('reader ran again')\n")
    procs = tmp_path / "proc"
    _fake_proc(
        root=procs,
        pid=4242,
        argv=["bash", str(world.checkout / "dispatch-dual.sh"), "--tick"],
        cwd=tmp_path,
    )

    lines = _skipped(done=world.run(proc_root=procs), world=world)

    assert lines == [
        "breakage-pass-skipped repo=alpha reason=dispatcher-live pid=4242 "
        "script=dispatch-dual.sh detail=script-path"
    ]
    # No fetch and no fast-forward: origin moved, the checkout did not.
    assert _git(cwd=world.checkout, args=["rev-parse", "HEAD"]) == before != tip


def test_a_live_dispatcher_whose_cwd_is_the_checkout_skips_the_pass(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    sub = world.checkout / "tmp"
    sub.mkdir()
    elsewhere = tmp_path / "elsewhere"
    procs = tmp_path / "proc"
    # The script lives on another tree, but the process works in this one.
    _fake_proc(
        root=procs,
        pid=77,
        argv=["bash", str(elsewhere / "resume-capped.sh")],
        cwd=sub,
    )

    lines = _skipped(done=world.run(proc_root=procs), world=world)

    assert lines == [
        "breakage-pass-skipped repo=alpha reason=dispatcher-live pid=77 "
        "script=resume-capped.sh detail=cwd"
    ]


def test_a_skip_leaves_an_earlier_success_marker_untouched(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    marker = world.state / "alpha.last-success"
    _ = marker.write_text("", encoding="utf-8")
    os.utime(marker, (1_000_000, 1_000_000))
    procs = tmp_path / "proc"
    _fake_proc(
        root=procs,
        pid=9,
        argv=[str(world.checkout / "dispatch-dual.sh")],
        cwd=None,
    )

    done = world.run(proc_root=procs)

    assert done.returncode == 0
    assert "breakage-pass-skipped" in done.stdout
    assert marker.stat().st_mtime == 1_000_000


def test_a_dispatcher_on_another_tree_does_not_hold_the_pass_back(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    procs = tmp_path / "proc"
    _fake_proc(
        root=procs,
        pid=500,
        argv=["bash", str(elsewhere / "dispatch-dual.sh")],
        cwd=elsewhere,
    )
    # An unrelated process that merely mentions the name later in its argv.
    _fake_proc(
        root=procs,
        pid=501,
        argv=["vim", "a", "b", "c", str(world.checkout / "dispatch-dual.sh")],
        cwd=world.checkout,
    )

    done = world.run(proc_root=procs)

    assert done.returncode == 0
    assert "breakage-pass-skipped" not in done.stdout
    assert "reader ran" in done.stdout
    assert (world.state / "alpha.last-success").exists()


def test_a_dispatcher_whose_cwd_cannot_be_read_and_names_no_tree_fails_closed(
    *, tmp_path: Path
) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    elsewhere = tmp_path / "elsewhere"
    procs = tmp_path / "proc"
    _fake_proc(
        root=procs,
        pid=600,
        argv=["bash", str(elsewhere / "dispatch-dual.sh")],
        cwd=None,
    )

    lines = _skipped(done=world.run(proc_root=procs), world=world)

    assert lines == [
        "breakage-pass-skipped repo=alpha reason=dispatcher-live pid=600 "
        "script=dispatch-dual.sh detail=cwd-unreadable"
    ]


def test_with_no_dispatcher_live_the_pass_fast_forwards_and_runs_as_before(
    *, tmp_path: Path
) -> None:
    world = _World(tmp_path=tmp_path, body="print('old reader')\n")
    tip = world.publish(body="print('reader ran')\n")
    procs = tmp_path / "proc"
    procs.mkdir()

    done = world.run(proc_root=procs)

    lines = done.stdout.splitlines()
    assert done.returncode == 0
    assert f"head={tip} origin={tip} action=advanced" in lines[0]
    assert "reader ran" in lines[1]
    assert (world.state / "alpha.last-success").exists()


def test_a_real_dispatcher_process_in_the_checkout_skips_the_pass(*, tmp_path: Path) -> None:
    world = _World(tmp_path=tmp_path, body="print('reader ran')\n")
    script = world.checkout / "dispatch-dual.sh"
    _ = script.write_text("#!/bin/bash\nsleep 60\n", encoding="utf-8")
    script.chmod(0o755)
    with subprocess.Popen(["/bin/bash", str(script)], cwd=tmp_path) as live:
        try:
            done = world.run()
        finally:
            live.kill()

    lines = done.stdout.splitlines()
    assert done.returncode == 0
    assert lines == [
        f"breakage-pass-skipped repo=alpha reason=dispatcher-live pid={live.pid} "
        "script=dispatch-dual.sh detail=script-path"
    ]
    assert not (world.state / "alpha.last-success").exists()


def test_the_docs_describe_the_live_dispatcher_skip_and_its_staleness_bound() -> None:
    docs = (_ROLE / "HOST_VARS.md").read_text(encoding="utf-8")
    assert "breakage-pass-skipped" in docs
    assert "reason=dispatcher-live" in docs
    assert "dispatch-dual.sh" in docs
    assert "resume-capped.sh" in docs
    assert "breakage_pass_stale_after_seconds" in docs
