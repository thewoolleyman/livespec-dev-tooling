"""The k3s server's move to embedded etcd: config, tmpfs remount, pinned defrag.

livespec-dev-tooling-qy2nzf (plan k3s-embedded-etcd-datastore, epic qql3lo).
Three committed properties, each read from the files the ci-pool converge installs:

- the server config selects embedded etcd with its quota, its snapshots off and an
  explicit compaction interval;
- the datastore tmpfs is sized for that quota, and a size change reaches the
  MOUNTED tmpfs by `mount -o remount`, never by stopping or restarting the mount
  (a restart empties the datastore and, through the k3s drop-in's
  RequiresMountsFor=, stops k3s);
- a pinned etcdctl and an enabled daily timer defragment the embedded etcd, and
  the timer's service is inert until the datastore is etcd.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO / "ci-runner" / "k3s" / "phase2"
_CONFIG = _PHASE2 / "k3s-config" / "config.yaml"
_MOUNT_UNIT = _PHASE2 / "datastore-tmpfs" / "var-lib-rancher-k3s-server-db.mount"
_TMPFS_ROLE = _REPO / "ansible" / "roles" / "datastore_tmpfs"
_DEFRAG_ROLE = _REPO / "ansible" / "roles" / "k3s_etcd_defrag"
_CI_POOL = _REPO / "ansible" / "ci-pool.yml"

_GIB = 1024**3
_UNIT_BYTES = {"K": 1024, "M": 1024**2, "G": _GIB, "T": 1024**4}


def _yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _tasks(path: Path) -> list[dict[str, object]]:
    loaded = _yaml(path)
    assert isinstance(loaded, list)
    return [task for task in loaded if isinstance(task, dict)]


def _module(task: dict[str, object], *names: str) -> dict[str, object] | None:
    for name in names:
        for key in (name, f"ansible.builtin.{name}"):
            body = task.get(key)
            if isinstance(body, dict):
                return body
    return None


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


def test_the_server_config_selects_embedded_etcd_with_its_quota_snapshots_off_and_compaction() -> (
    None
):
    config = _yaml(_CONFIG)
    assert isinstance(config, dict)
    assert config["cluster-init"] is True
    assert config["etcd-disable-snapshots"] is True
    assert config["etcd-arg"] == [f"quota-backend-bytes={2 * _GIB}"]
    assert config["kube-apiserver-arg"] == ["etcd-compaction-interval=5m"]
    # One key each: a duplicated top-level key would silently override the first.
    text = _CONFIG.read_text(encoding="utf-8")
    for key in ("cluster-init", "etcd-disable-snapshots", "etcd-arg", "kube-apiserver-arg"):
        assert len(re.findall(rf"(?m)^{re.escape(key)}:", text)) == 1, key


def test_the_datastore_tmpfs_holds_the_quota_a_defrag_copy_and_the_wal() -> None:
    size = _size_bytes(_mount_option_size())
    assert size == 6 * _GIB
    quota = int(_yaml(_CONFIG)["etcd-arg"][0].split("=", 1)[1])  # type: ignore[index]
    # The backend quota plus a full defragmentation copy must fit, with room for the WAL.
    assert size >= 2 * quota + _GIB


def test_the_role_reads_the_size_it_remounts_with_from_the_committed_unit() -> None:
    defaults = (_TMPFS_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    pattern = re.search(r"regex_findall\('(?P<pattern>[^']+)', multiline=True\)", defaults)
    assert pattern is not None
    # The defaults apply the same expression to the same unit file.
    assert "datastore_tmpfs_mount_unit" in defaults
    match = re.search(pattern["pattern"], _MOUNT_UNIT.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None
    assert match.group(1) == _mount_option_size() == "6G"


def test_a_changed_size_reaches_the_mounted_tmpfs_by_remount_and_nothing_stops_or_restarts_it() -> (
    None
):
    tasks = _tasks(_TMPFS_ROLE / "tasks" / "main.yml")
    handlers = _tasks(_TMPFS_ROLE / "handlers" / "main.yml")
    remounts = [
        task
        for task in tasks
        if (body := _module(task, "command")) is not None and body.get("argv", [None])[0] == "mount"  # type: ignore[index]
    ]
    assert len(remounts) == 1
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
    remount_block = tasks[tasks.index(remounts[0]) - 3 : tasks.index(remounts[0]) + 4]
    assert all("notify" not in task for task in remount_block)
    # The read-back proves the size took and the datastore file survived.
    asserts = [task for task in tasks if _module(task, "assert") is not None]
    survived = str(asserts[-1])
    assert "datastore_tmpfs_size_bytes" in survived
    assert "inode" in survived


def test_a_pinned_etcdctl_and_an_enabled_daily_timer_defragment_the_embedded_etcd() -> None:
    defaults = _yaml(_DEFRAG_ROLE / "defaults" / "main.yml")
    assert isinstance(defaults, dict)
    assert defaults["k3s_etcd_defrag_etcd_version"] == "3.6.12"
    assert re.fullmatch(r"[0-9a-f]{64}", defaults["k3s_etcd_defrag_tarball_sha256"])
    tasks = _tasks(_DEFRAG_ROLE / "tasks" / "main.yml")
    downloads = [_module(task, "get_url") for task in tasks if _module(task, "get_url") is not None]
    assert len(downloads) == 1
    assert downloads[0]["checksum"] == "sha256:{{ k3s_etcd_defrag_tarball_sha256 }}"  # type: ignore[index]
    service = (_DEFRAG_ROLE / "templates" / "k3s-etcd-defrag.service.j2").read_text(
        encoding="utf-8"
    )
    assert "ConditionPathExists={{ k3s_etcd_defrag_etcd_data_dir }}" in service
    assert re.search(
        r"(?s)ExecStart=\{\{ k3s_etcd_defrag_bin \}\}.*--cacert=.*server-ca\.crt.*--cert=.*client\.crt.*--key=.*client\.key.*\bdefrag\b",
        service,
    )
    assert defaults["k3s_etcd_defrag_tls_dir"] == "/var/lib/rancher/k3s/server/tls/etcd"
    assert defaults["k3s_etcd_defrag_etcd_data_dir"] == "/var/lib/rancher/k3s/server/db/etcd"
    timer = (_DEFRAG_ROLE / "templates" / "k3s-etcd-defrag.timer.j2").read_text(encoding="utf-8")
    assert "OnCalendar={{ k3s_etcd_defrag_on_calendar }}" in timer
    assert "WantedBy=timers.target" in timer
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
    play = _CI_POOL.read_text(encoding="utf-8")
    assert re.search(
        r"(?m)^    - role: k3s_etcd_defrag\n      tags: \[k3s_etcd_defrag\]\n      when: cluster_role == 'server'$",
        play,
    )
