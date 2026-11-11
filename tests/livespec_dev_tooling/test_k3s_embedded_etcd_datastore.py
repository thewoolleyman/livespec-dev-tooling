"""The k3s server's move to embedded etcd: drop-in, tmpfs remount, pinned defrag.

livespec-dev-tooling-qy2nzf (plan k3s-embedded-etcd-datastore, epic qql3lo).
Four committed properties, each read from the files the ci-pool converge installs:

- the datastore selection (embedded etcd, its quota, snapshots off, an explicit
  compaction interval) lives ONLY in a server drop-in. The k3s_config role
  installs it only on request, and removes it only on an explicit rollback, so
  no routine apply can arm or disarm the conversion;
- the datastore tmpfs is sized for that quota, and a size change reaches the
  MOUNTED tmpfs by `mount -o remount`, never by stopping or restarting the mount
  (a restart empties the datastore and, through the k3s drop-in's
  RequiresMountsFor=, stops k3s);
- a checksum-verified etcdctl and an enabled daily timer defragment the embedded
  etcd. The timer's service is inert until the datastore is etcd, skips cleanly
  while k3s is not active, and never runs a missed defrag late;
- the defrag role is wired into the server's ci-pool play.

No assertion here reads a committed VALUE (a size, a quota, a version, a path, a
schedule, a flag default). Those change as config, without a test edit
(coordinator-duties §12). Only relations between files, and the shape of the
tasks and units, are asserted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import yaml

_REPO = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO / "ci-runner" / "k3s" / "phase2"
_CONFIG = _PHASE2 / "k3s-config" / "config.yaml"
_DROP_IN = _PHASE2 / "k3s-config" / "config.yaml.d" / "50-embedded-etcd.yaml"
_MOUNT_UNIT = _PHASE2 / "datastore-tmpfs" / "var-lib-rancher-k3s-server-db.mount"
_K3S_CONFIG_ROLE = _REPO / "ansible" / "roles" / "k3s_config"
_TMPFS_ROLE = _REPO / "ansible" / "roles" / "datastore_tmpfs"
_DEFRAG_ROLE = _REPO / "ansible" / "roles" / "k3s_etcd_defrag"
_CI_POOL = _REPO / "ansible" / "ci-pool.yml"

_DATASTORE_KEYS = ("cluster-init", "etcd-disable-snapshots", "etcd-arg", "kube-apiserver-arg")
_REMOUNT_FIRST = "Read the mounted datastore tmpfs and its size"
_REMOUNT_LAST = "Refuse a remount that did not take the size or did not keep the datastore"

_GIB = 1024**3
_UNIT_BYTES = {"K": 1024, "M": 1024**2, "G": _GIB, "T": 1024**4}


def _yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _mapping(path: Path) -> dict[str, object]:
    loaded = _yaml(path)
    assert isinstance(loaded, dict), path
    return cast("dict[str, object]", loaded)


def _tasks(path: Path) -> list[dict[str, object]]:
    loaded = _yaml(path)
    assert isinstance(loaded, list)
    items = cast("list[object]", loaded)
    return [cast("dict[str, object]", task) for task in items if isinstance(task, dict)]


def _module(task: dict[str, object], *names: str) -> dict[str, object] | None:
    for name in names:
        for key in (name, f"ansible.builtin.{name}"):
            body = task.get(key)
            if isinstance(body, dict):
                return cast("dict[str, object]", body)
    return None


def _when(task: dict[str, object]) -> list[str]:
    when = task.get("when", [])
    clauses = cast("list[object]", when) if isinstance(when, list) else [when]
    return [str(clause) for clause in clauses]


def _size_bytes(size: str) -> int:
    match = re.fullmatch(r"(?P<n>[0-9]+)(?P<unit>[KMGT]?)", size)
    assert match is not None, size
    return int(match["n"]) * _UNIT_BYTES.get(match["unit"], 1)


def _mount_option_size() -> str:
    match = re.search(
        r"(?m)^Options=size=([0-9]+[KMGT]?),", _MOUNT_UNIT.read_text(encoding="utf-8")
    )
    assert match is not None
    return match.group(1)


def _mount_point() -> str:
    match = re.search(r"(?m)^Where=(\S+)$", _MOUNT_UNIT.read_text(encoding="utf-8"))
    assert match is not None
    return match.group(1)


def _quota_bytes() -> int:
    args = _mapping(_DROP_IN)["etcd-arg"]
    assert isinstance(args, list)
    prefix = "quota-backend-bytes="
    quotas = [
        str(arg).removeprefix(prefix)
        for arg in cast("list[object]", args)
        if str(arg).startswith(prefix)
    ]
    assert len(quotas) == 1, args
    assert quotas[0].isdigit() and int(quotas[0]) > 0, quotas
    return int(quotas[0])


def test_the_datastore_selection_lives_only_in_the_server_drop_in() -> None:
    drop_in = _mapping(_DROP_IN)
    for key in _DATASTORE_KEYS:
        assert key in drop_in, key
    _ = _quota_bytes()
    compaction = drop_in["kube-apiserver-arg"]
    assert isinstance(compaction, list)
    assert any(str(arg).startswith("etcd-compaction-interval=") for arg in compaction)
    # One key each: a duplicated top-level key would silently override the first.
    text = _DROP_IN.read_text(encoding="utf-8")
    for key in _DATASTORE_KEYS:
        assert len(re.findall(rf"(?m)^{re.escape(key)}:", text)) == 1, key
    # The shared server config, which EVERY ci-pool apply installs, carries none of
    # them (or any other drop-in key): a key there would arm the conversion on a
    # routine apply, and a drop-in key of the same name REPLACES the shared one.
    shared = _mapping(_CONFIG)
    assert not set(shared) & set(drop_in), sorted(set(shared) & set(drop_in))


def test_the_role_installs_the_drop_in_only_on_request_and_removes_it_only_on_rollback() -> None:
    defaults = _mapping(_K3S_CONFIG_ROLE / "defaults" / "main.yml")
    for key in (
        "k3s_config_embedded_etcd",
        "k3s_config_embedded_etcd_rollback",
        "k3s_config_embedded_etcd_drop_in",
    ):
        assert key in defaults, key
    assert str(defaults["k3s_config_embedded_etcd_drop_in"]).startswith(
        f"{defaults['k3s_config_drop_in_dir']}/"
    )
    tasks = _tasks(_K3S_CONFIG_ROLE / "tasks" / "main.yml")
    dest = "{{ k3s_config_embedded_etcd_drop_in }}"
    writes = [
        task
        for task in tasks
        if (body := _module(task, "copy", "template")) is not None and body.get("dest") == dest
    ]
    assert len(writes) == 1
    source = str(_module(writes[0], "copy")["src"])  # type: ignore[index]
    assert source.endswith(f"/{_DROP_IN.relative_to(_PHASE2).as_posix()}")
    assert _DROP_IN.is_file()
    assert _when(writes[0]) == [
        "k3s_config_cluster_role == 'server'",
        "k3s_config_embedded_etcd | bool",
    ]
    removals = [
        task
        for task in tasks
        if (body := _module(task, "file")) is not None
        and body.get("path") == dest
        and body.get("state") == "absent"
    ]
    # A false request removes NOTHING: the only removal is the explicit rollback.
    assert len(removals) == 1
    assert _when(removals[0]) == [
        "k3s_config_cluster_role == 'server'",
        "k3s_config_embedded_etcd_rollback | bool",
    ]
    # Nothing in the role keys a write or a removal on the request being false.
    for task in tasks:
        assert all("not k3s_config_embedded_etcd" not in clause for clause in _when(task)), task[
            "name"
        ]
    # An agent request, or install and rollback together, is refused before either.
    guards = [
        task
        for task in tasks
        if (body := _module(task, "assert")) is not None
        and any("k3s_config_embedded_etcd_rollback" in str(that) for that in body["that"])  # type: ignore[union-attr]
    ]
    assert len(guards) == 1
    assert tasks.index(guards[0]) < min(tasks.index(writes[0]), tasks.index(removals[0]))


def test_the_datastore_tmpfs_holds_the_quota_a_defrag_copy_and_the_wal() -> None:
    # The backend quota plus a full defragmentation copy must fit, with room for the WAL.
    assert _size_bytes(_mount_option_size()) >= 2 * _quota_bytes() + _GIB


def test_the_role_reads_the_size_it_remounts_with_from_the_committed_unit() -> None:
    defaults = (_TMPFS_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    pattern = re.search(r"regex_findall\('(?P<pattern>[^']+)', multiline=True\)", defaults)
    assert pattern is not None
    # The defaults apply the same expression to the same unit file.
    assert "datastore_tmpfs_mount_unit" in defaults
    match = re.search(pattern["pattern"], _MOUNT_UNIT.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None
    assert match.group(1) == _mount_option_size()


def test_a_changed_size_reaches_the_mounted_tmpfs_by_remount_and_nothing_stops_or_restarts_it() -> (
    None
):
    tasks = _tasks(_TMPFS_ROLE / "tasks" / "main.yml")
    handlers = _tasks(_TMPFS_ROLE / "handlers" / "main.yml")
    names = [task.get("name") for task in tasks]
    remount_block = tasks[names.index(_REMOUNT_FIRST) : names.index(_REMOUNT_LAST) + 1]
    remounts = [
        task
        for task in tasks
        if (body := _module(task, "command")) is not None and body.get("argv", [None])[0] == "mount"  # type: ignore[index]
    ]
    assert len(remounts) == 1
    assert remounts[0] in remount_block
    argv = _module(remounts[0], "command")["argv"]  # type: ignore[index]
    assert argv == [
        "mount",
        "-o",
        "remount,size={{ datastore_tmpfs_size }}",
        "{{ datastore_tmpfs_mount_point }}",
    ]
    assert "not ansible_check_mode" in str(remounts[0]["when"])
    # No task or handler of this role stops, restarts or reloads a unit, and the
    # remount block notifies nothing.
    for task in tasks + handlers:
        body = _module(task, "systemd_service", "systemd", "service")
        if body is not None:
            assert "state" not in body, task["name"]
    assert all("notify" not in task for task in remount_block)
    # The block's last task proves the size took and the datastore file survived.
    survived = str(_module(remount_block[-1], "assert"))
    assert "datastore_tmpfs_size_bytes" in survived
    assert "inode" in survived


def test_a_checksummed_etcdctl_and_an_enabled_daily_timer_defragment_the_embedded_etcd() -> None:
    defaults = _mapping(_DEFRAG_ROLE / "defaults" / "main.yml")
    for key in (
        "k3s_etcd_defrag_etcd_version",
        "k3s_etcd_defrag_tarball_sha256",
        "k3s_etcd_defrag_tls_dir",
        "k3s_etcd_defrag_etcd_data_dir",
        "k3s_etcd_defrag_on_calendar",
    ):
        assert key in defaults, key
    assert "{{ k3s_etcd_defrag_etcd_version }}" in str(defaults["k3s_etcd_defrag_tarball_url"])
    # The service is conditioned on the etcd data dir, so it must live on the
    # datastore tmpfs the mount unit provides.
    assert str(defaults["k3s_etcd_defrag_etcd_data_dir"]).startswith(f"{_mount_point()}/")
    tasks = _tasks(_DEFRAG_ROLE / "tasks" / "main.yml")
    downloads = [_module(task, "get_url") for task in tasks if _module(task, "get_url") is not None]
    assert len(downloads) == 1
    assert downloads[0]["checksum"] == "sha256:{{ k3s_etcd_defrag_tarball_sha256 }}"  # type: ignore[index]
    assert downloads[0]["url"] == "{{ k3s_etcd_defrag_tarball_url }}"  # type: ignore[index]
    service = (_DEFRAG_ROLE / "templates" / "k3s-etcd-defrag.service.j2").read_text(
        encoding="utf-8"
    )
    assert "ConditionPathExists={{ k3s_etcd_defrag_etcd_data_dir }}" in service
    tls = r"\{\{ k3s_etcd_defrag_tls_dir \}\}/"
    exec_start = rf"(?s)ExecStart=\{{\{{ k3s_etcd_defrag_bin \}}\}}.*--cacert={tls}.*--cert={tls}.*--key={tls}.*\bdefrag\b"
    assert re.search(exec_start, service)
    # k3s is ordered before, never a dependency: a stopped k3s skips the run
    # cleanly, and no failure of this unit reaches k3s's transaction.
    assert re.search(r"(?m)^After=k3s\.service$", service)
    assert re.search(r"(?m)^ExecCondition=/bin/systemctl is-active --quiet k3s\.service$", service)
    assert not re.search(r"(?m)^(Requisite|Requires|BindsTo|PartOf)=", service)
    timer = (_DEFRAG_ROLE / "templates" / "k3s-etcd-defrag.timer.j2").read_text(encoding="utf-8")
    assert "OnCalendar={{ k3s_etcd_defrag_on_calendar }}" in timer
    assert "WantedBy=timers.target" in timer
    # A missed defrag is skipped, never run late at boot, when etcd is fresh.
    assert not re.search(r"(?m)^Persistent=", timer)
    enables = [
        body
        for task in tasks
        if (body := _module(task, "systemd_service")) is not None
        and body.get("name") == "{{ k3s_etcd_defrag_unit }}.timer"
    ]
    assert enables == [
        {
            "name": "{{ k3s_etcd_defrag_unit }}.timer",
            "enabled": True,
            "state": "started",
            "daemon_reload": True,
        }
    ]


def test_the_defrag_role_runs_in_the_server_play() -> None:
    play = _CI_POOL.read_text(encoding="utf-8")
    assert re.search(
        r"(?m)^    - role: k3s_etcd_defrag\n      tags: \[k3s_etcd_defrag\]\n      when: cluster_role == 'server'$",
        play,
    )
