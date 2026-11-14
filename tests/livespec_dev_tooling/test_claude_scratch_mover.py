"""The Claude scratch mover moves only session scratch it can prove is dead.

Role `dev_host_memory_bounds` caps /tmp at 8G, and Claude Code session scratch
under /tmp/claude-1000 stays in RAM until the planned bind mount. The role's
`claude_scratch_mover.py` runs on a timer and MOVES (never deletes) each dead,
idle session directory to the same relative path under /var/tmp/claude-1000.
These tests run the committed script against a fake /proc tree and temporary
RAM and disk roots. Nothing touches the real /proc, /tmp or /var/tmp.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import jinja2
import pytest
import yaml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "dev_host_memory_bounds"
_SCRIPT = _ROLE / "files" / "claude_scratch_mover.py"

_LIVE = "11111111-1111-4111-8111-111111111111"
_DEAD = "22222222-2222-4222-8222-222222222222"
_OTHER = "33333333-3333-4333-8333-333333333333"
_PROJECT = "-data-projects-example"
_HOURS = 3600.0


def _load() -> ModuleType:
    assert _SCRIPT.is_file(), f"{_SCRIPT.relative_to(_REPO_ROOT)} must exist"
    name = "claude_scratch_mover_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


mover = _load()


def _age(*, path: Path, seconds: float) -> None:
    stamp = time.time() - seconds
    for root, dirs, files in os.walk(path):
        for name in (*dirs, *files):
            os.utime(Path(root) / name, (stamp, stamp), follow_symlinks=False)
    os.utime(path, (stamp, stamp))


def _session(*, ram: Path, sid: str, age_seconds: float = 3 * _HOURS) -> Path:
    directory = ram / _PROJECT / sid
    (directory / "tasks").mkdir(parents=True)
    _ = (directory / "tasks" / "out.txt").write_text("x", encoding="utf-8")
    _age(path=directory, seconds=age_seconds)
    return directory


def _process(
    *,
    proc: Path,
    pid: int,
    environ: dict[str, str] | None = None,
    readable_environ: bool = True,
    cmdline: list[str] | None = None,
    cwd: str | None = None,
    fds: list[str] | None = None,
    maps: list[str] | None = None,
) -> None:
    entry = proc / str(pid)
    entry.mkdir(parents=True)
    if readable_environ:
        merged = {"PATH": "/usr/bin", **(environ or {})}
        body = "".join(f"{key}={value}\x00" for key, value in merged.items())
        _ = (entry / "environ").write_bytes(body.encode())
    if cmdline is not None:
        _ = (entry / "cmdline").write_bytes("\x00".join(cmdline).encode() + b"\x00")
    if cwd is not None:
        (entry / "cwd").symlink_to(cwd)
    if fds is not None:
        (entry / "fd").mkdir()
        for number, target in enumerate(fds):
            (entry / "fd" / str(number)).symlink_to(target)
    if maps is not None:
        _ = (entry / "maps").write_text("\n".join(maps) + "\n", encoding="utf-8")


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    ram, disk, proc = tmp_path / "ram", tmp_path / "disk", tmp_path / "proc"
    ram.mkdir()
    disk.mkdir()
    proc.mkdir()
    (proc / "self").mkdir()
    return ram, disk, proc


def _config(*, ram: Path, disk: Path, proc: Path, tmp_path: Path, apply: bool = True) -> object:
    return mover.Config(
        ram_root=ram,
        disk_root=disk,
        proc_root=proc,
        kill_switch=tmp_path / "disabled",
        min_age_seconds=2 * _HOURS,
        apply=apply,
    )


def _events(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def _run(*, config: object, proc: Path) -> int:
    return mover.run(
        config=config,
        references=lambda: mover.read_references(proc_root=proc),
        now=time.time,
        is_mount=lambda _path: False,
    )


def test_a_dead_idle_session_moves_to_the_same_path_on_disk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    _process(proc=proc, pid=10, environ={"CLAUDE_CODE_SESSION_ID": _LIVE})
    code = _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc)
    assert code == 0
    assert not dead.exists()
    assert (disk / _PROJECT / _DEAD / "tasks" / "out.txt").read_text(encoding="utf-8") == "x"
    events = _events(capsys)
    assert {"event": "moved", "path": str(dead), "to": str(disk)} in events
    assert events[-1] == {"apply": True, "event": "pass-complete", "failed": 0, "moved": 1}


def test_a_running_session_is_kept(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ram, disk, proc = _roots(tmp_path)
    live = _session(ram=ram, sid=_LIVE)
    _process(proc=proc, pid=10, environ={"PATH": "/usr/bin", "CLAUDE_CODE_SESSION_ID": _LIVE})
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    assert live.exists()
    assert {"event": "kept", "path": str(live), "reason": "session-running"} in _events(capsys)


@pytest.mark.parametrize("held_by", ["cwd", "fd", "maps", "cmdline", "environ"])
def test_a_session_any_process_still_references_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held_by: str
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    inside = str(dead / "tasks" / "out.txt")
    hold: dict[str, object] = {
        "cwd": {"cwd": str(dead)},
        "fd": {"fds": ["/dev/null", inside]},
        "maps": {"maps": ["7f00-7f01 r--p 00000000 00:00 0", f"7f01-7f02 r--p 0 00:00 1 {inside}"]},
        "cmdline": {"cmdline": ["tail", "-f", inside]},
        "environ": {"environ": {"TMPDIR": str(dead)}},
    }[held_by]
    _process(proc=proc, pid=10, **hold)  # type: ignore[arg-type]
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    assert dead.exists()
    assert {"event": "kept", "path": str(dead), "reason": "referenced"} in _events(capsys)


def test_a_held_string_without_the_session_id_does_not_hold_it(tmp_path: Path) -> None:
    ram, _, _ = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    references = mover.References(
        sessions=frozenset(), paths=frozenset({str(dead.parent / _OTHER), "/usr/bin/python3"})
    )
    assert not mover.is_referenced(directory=dead, references=references)


def test_a_recently_modified_session_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    young = _session(ram=ram, sid=_DEAD, age_seconds=3 * _HOURS)
    _ = (young / "tasks" / "fresh.txt").write_text("new", encoding="utf-8")
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    assert young.exists()
    assert {"event": "kept", "path": str(young), "reason": "recently-modified"} in _events(capsys)


def test_a_file_that_vanishes_during_the_age_walk_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ram, _, _ = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    real_lstat = os.lstat

    def flaky(path: object, *args: object, **kwargs: object) -> os.stat_result:
        if str(path).endswith("out.txt"):
            raise FileNotFoundError(path)
        return real_lstat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(mover.os, "lstat", flaky)
    assert mover.newest_mtime(directory=dead) < time.time() - _HOURS


def test_only_session_named_real_directories_are_considered(tmp_path: Path) -> None:
    ram, _, _ = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    (ram / _PROJECT / "not-a-session").mkdir()
    _ = (ram / _PROJECT / _OTHER).write_text("a file, not a directory", encoding="utf-8")
    (ram / _PROJECT / "33333333-3333-4333-8333-333333333334").symlink_to(dead)
    _ = (ram / "stray-file").write_text("x", encoding="utf-8")
    (ram / "linked-project").symlink_to(ram / _PROJECT)
    assert list(mover.session_dirs(ram_root=ram)) == [dead]


def test_a_session_that_resumes_between_the_scan_and_the_move_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    reads = iter(
        [
            mover.References(sessions=frozenset(), paths=frozenset()),
            mover.References(sessions=frozenset({_DEAD}), paths=frozenset()),
        ]
    )
    code = mover.run(
        config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path),
        references=lambda: next(reads),
        now=time.time,
        is_mount=lambda _path: False,
    )
    assert code == 0
    assert dead.exists()
    assert {"event": "kept", "path": str(dead), "reason": "session-running"} in _events(capsys)


def test_a_report_only_pass_moves_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    config = _config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path, apply=False)
    assert _run(config=config, proc=proc) == 0
    assert dead.exists()
    events = _events(capsys)
    assert {"event": "would-move", "path": str(dead)} in events
    assert events[-1] == {"apply": False, "event": "pass-complete", "failed": 0, "moved": 0}


def test_the_kill_switch_stops_the_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    _ = (tmp_path / "disabled").write_text("", encoding="utf-8")
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    assert dead.exists()
    assert _events(capsys) == [{"event": "disabled", "kill_switch": str(tmp_path / "disabled")}]


def test_a_mounted_ram_root_means_the_bind_is_live_and_nothing_moves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    code = mover.run(
        config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path),
        references=lambda: mover.read_references(proc_root=proc),
        now=time.time,
        is_mount=lambda path: path == str(ram),
    )
    assert code == 0
    assert dead.exists()
    assert _events(capsys)[0]["reason"] == "ram-root-is-mounted"


def test_an_absent_ram_root_is_nothing_to_move(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, disk, proc = _roots(tmp_path)
    config = _config(ram=tmp_path / "missing", disk=disk, proc=proc, tmp_path=tmp_path)
    assert _run(config=config, proc=proc) == 0
    assert _events(capsys)[0]["reason"] == "ram-root-absent"


def test_an_existing_destination_is_never_overwritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    (disk / _PROJECT / _DEAD).mkdir(parents=True)
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 1
    assert dead.exists()
    assert {"error": "destination-exists", "event": "move-failed", "path": str(dead)} in _events(
        capsys
    )


def test_a_move_that_fails_leaves_the_source_and_fails_the_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A regular file where the destination project directory belongs makes mv
    # fail with "Not a directory" for any user, root included.
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    _ = (disk / _PROJECT).write_text("not a directory", encoding="utf-8")
    code = _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc)
    assert code == 1
    assert dead.exists()
    failed = [event for event in _events(capsys) if event["event"] == "move-failed"]
    assert failed
    assert failed[0]["path"] == str(dead)


def test_a_new_destination_project_directory_copies_the_source_owner_and_mode(
    tmp_path: Path,
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    (ram / _PROJECT).chmod(0o700)
    outcome = mover.move(
        source=dead,
        ram_root=ram,
        disk_root=disk,
        owner_uid=ram.lstat().st_uid,
        references=lambda: mover.read_references(proc_root=proc),
    )
    assert outcome == ("moved", None)
    created = (disk / _PROJECT).stat()
    source = (ram / _PROJECT).stat()
    assert (created.st_uid, created.st_gid) == (source.st_uid, source.st_gid)
    assert created.st_mode & 0o7777 == 0o700


def test_main_reads_its_inputs_from_the_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    environ = {
        "MOVER_RAM_ROOT": str(ram),
        "MOVER_DISK_ROOT": str(disk),
        "MOVER_PROC_ROOT": str(proc),
        "MOVER_KILL_SWITCH": str(tmp_path / "disabled"),
        "MOVER_MIN_AGE_SECONDS": str(2 * _HOURS),
        "MOVER_APPLY": "1",
    }
    assert mover.main(environ=environ) == 0
    assert not dead.exists()
    assert _events(capsys)[-1]["moved"] == 1


def _render(*, template: str, variables: dict[str, object]) -> list[str]:
    text = (_ROLE / "templates" / template).read_text(encoding="utf-8")
    environment = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
    return environment.from_string(text).render(**variables).splitlines()


def test_the_role_runs_the_installed_script_on_a_timer_with_its_kill_switch() -> None:
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    variables = {
        **defaults,
        "ansible_managed": "Ansible managed",
        "dev_host_memory_bounds_rt_scratch_ram_dir": "/tmp/claude-1000",
        "dev_host_memory_bounds_rt_scratch_disk_dir": "/var/tmp/claude-1000",
    }
    service = _render(template="claude-scratch-mover.service.j2", variables=variables)
    assert (
        f"ExecStart=/usr/bin/python3 -I {defaults['dev_host_memory_bounds_scratch_mover_bin']}"
        in service
    )
    assert (
        f'Environment="MOVER_KILL_SWITCH={defaults["dev_host_memory_bounds_scratch_mover_kill_switch"]}"'
        in service
    )
    assert 'Environment="MOVER_RAM_ROOT=/tmp/claude-1000"' in service
    assert 'Environment="MOVER_DISK_ROOT=/var/tmp/claude-1000"' in service
    assert "IOSchedulingClass=idle" in service
    timer = _render(template="claude-scratch-mover.timer.j2", variables=variables)
    interval = defaults["dev_host_memory_bounds_scratch_mover_interval"]
    assert f"OnUnitInactiveSec={interval}" in timer
    assert f"Unit={defaults['dev_host_memory_bounds_scratch_mover_service']}" in timer
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "src: claude_scratch_mover.py" in tasks
    # The project directories already on disk are given to the scratchpad login.
    assert "- name: Give every on-disk project directory to the scratchpad login" in tasks


def test_a_scan_that_reads_no_process_environment_moves_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Processes exist but not one environment could be read, so no session can
    # be proven dead: CLAUDE_CODE_SESSION_ID is invisible. Fail closed.
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    _process(proc=proc, pid=10, readable_environ=False)
    _process(proc=proc, pid=11, readable_environ=False, cmdline=["sleep", "60"])
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    assert dead.exists()
    assert {"event": "kept", "path": str(dead), "reason": "liveness-scan-failed"} in _events(capsys)


def test_one_readable_environment_is_enough_to_trust_the_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    live = _session(ram=ram, sid=_LIVE)
    dead = _session(ram=ram, sid=_DEAD)
    _process(proc=proc, pid=10, environ={"CLAUDE_CODE_SESSION_ID": _LIVE})
    _process(proc=proc, pid=11, readable_environ=False)
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    assert live.exists()
    assert not dead.exists()
    assert {"event": "kept", "path": str(live), "reason": "session-running"} in _events(capsys)


@pytest.mark.parametrize(
    "hold",
    [
        {"cmdline": ["bash", "-c", "cd {dead} && ls"]},
        {"environ": {"PATH": "{dead}/bin:/usr/bin"}},
        {"cmdline": ["claude", "--resume", "{sid}"]},
    ],
    ids=["cd-then-and", "path-style", "resume-by-id"],
)
def test_the_session_id_anywhere_in_a_process_holds_the_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], hold: dict[str, object]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    filled = json.loads(json.dumps(hold).replace("{dead}", str(dead)).replace("{sid}", _DEAD))
    _process(proc=proc, pid=10, **filled)
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    assert dead.exists()
    assert {"event": "kept", "path": str(dead), "reason": "referenced"} in _events(capsys)


def test_a_symlinked_destination_project_is_refused_and_nothing_lands_at_its_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (disk / _PROJECT).symlink_to(elsewhere)
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 1
    assert dead.exists()
    assert list(elsewhere.iterdir()) == []
    assert {"error": "unsafe-destination", "event": "move-failed", "path": str(dead)} in _events(
        capsys
    )


def test_a_symlinked_ram_root_refuses_the_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    _ = _session(ram=ram, sid=_DEAD)
    linked = tmp_path / "linked-ram"
    linked.symlink_to(ram)
    config = _config(ram=linked, disk=disk, proc=proc, tmp_path=tmp_path)
    assert _run(config=config, proc=proc) == 1
    assert _events(capsys) == [
        {"event": "refused", "ram_root": str(linked), "reason": "ram-root-unsafe"}
    ]


def test_a_symlinked_disk_root_refuses_the_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    linked = tmp_path / "linked-disk"
    linked.symlink_to(disk)
    config = _config(ram=ram, disk=linked, proc=proc, tmp_path=tmp_path)
    assert _run(config=config, proc=proc) == 1
    assert dead.exists()
    assert _events(capsys) == [
        {"disk_root": str(linked), "event": "refused", "reason": "disk-root-unsafe"}
    ]


def test_a_directory_owned_by_another_user_is_not_a_safe_directory(tmp_path: Path) -> None:
    assert mover.real_dir(path=tmp_path, uid=tmp_path.lstat().st_uid)
    assert not mover.real_dir(path=tmp_path, uid=tmp_path.lstat().st_uid + 1)
    assert not mover.real_dir(path=tmp_path / "missing", uid=None)


def test_a_source_project_owned_by_another_user_is_refused(tmp_path: Path) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    outcome = mover.move(
        source=dead,
        ram_root=ram,
        disk_root=disk,
        owner_uid=ram.lstat().st_uid + 1,
        references=lambda: mover.read_references(proc_root=proc),
    )
    assert outcome == ("move-failed", "unsafe-source")
    assert dead.exists()


def test_an_existing_destination_project_takes_the_source_mode(tmp_path: Path) -> None:
    ram, disk, proc = _roots(tmp_path)
    _ = _session(ram=ram, sid=_DEAD)
    (ram / _PROJECT).chmod(0o700)
    (disk / _PROJECT).mkdir()
    (disk / _PROJECT).chmod(0o755)
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    assert (disk / _PROJECT).stat().st_mode & 0o7777 == 0o700
    assert (disk / _PROJECT / _DEAD).is_dir()


def test_a_session_referenced_once_staged_is_put_back_and_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    staged = dead.parent / f".{_DEAD}.moving"
    reads = iter(
        [
            mover.References(sessions=frozenset(), paths=frozenset()),
            mover.References(sessions=frozenset(), paths=frozenset()),
            mover.References(sessions=frozenset(), paths=frozenset({f"{staged}/tasks/out.txt"})),
        ]
    )
    code = mover.run(
        config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path),
        references=lambda: next(reads),
        now=time.time,
        is_mount=lambda _path: False,
    )
    assert code == 0
    assert dead.is_dir()
    assert not staged.exists()
    assert not (disk / _PROJECT / _DEAD).exists()
    assert {"event": "kept", "path": str(dead), "reason": "referenced-after-staging"} in _events(
        capsys
    )


def test_an_existing_staging_name_fails_the_move(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    (dead.parent / f".{_DEAD}.moving").mkdir()
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 1
    assert dead.exists()
    assert {"error": "staging-exists", "event": "move-failed", "path": str(dead)} in _events(capsys)


def test_a_staging_directory_a_crashed_pass_left_is_restored_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ram, disk, proc = _roots(tmp_path)
    project = ram / _PROJECT
    left = _session(ram=ram, sid=_DEAD)
    left.rename(project / f".{_DEAD}.moving")
    _ = (project / f".{_OTHER}.moving").write_text("a file, not a directory", encoding="utf-8")
    (project / ".not-a-staging-name").mkdir()
    live = _session(ram=ram, sid=_LIVE)
    (project / f".{_LIVE}.moving").mkdir()
    _process(proc=proc, pid=10, environ={"CLAUDE_CODE_SESSION_ID": _LIVE})
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 0
    events = _events(capsys)
    assert events[0] == {"event": "restored-staging", "path": str(project / _DEAD)}
    assert {"event": "moved", "path": str(project / _DEAD), "to": str(disk)} in events
    assert live.exists()
    assert (project / f".{_LIVE}.moving").exists()


def _fake_mv(*, returncode: int, perform: bool) -> object:
    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if perform:
            Path(argv[-2]).rename(argv[-1])
        stderr = "mv: boom" if returncode else ""
        return subprocess.CompletedProcess(argv, returncode, "", stderr)

    return run


@pytest.mark.parametrize(
    ("returncode", "perform", "detail", "restored"),
    [
        (1, False, "mv: boom", True),
        (0, False, "move-incomplete", True),
        (1, True, "mv: boom", False),
    ],
    ids=["mv-fails", "mv-claims-success-but-staging-remains", "mv-fails-after-moving"],
)
def test_a_failed_copy_puts_the_session_back_when_it_can(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int,
    perform: bool,
    detail: str,
    restored: bool,
) -> None:
    ram, disk, proc = _roots(tmp_path)
    dead = _session(ram=ram, sid=_DEAD)
    monkeypatch.setattr(mover.subprocess, "run", _fake_mv(returncode=returncode, perform=perform))
    assert _run(config=_config(ram=ram, disk=disk, proc=proc, tmp_path=tmp_path), proc=proc) == 1
    assert dead.exists() is restored
    assert not (dead.parent / f".{_DEAD}.moving").exists()
    assert {"error": detail, "event": "move-failed", "path": str(dead)} in _events(capsys)
