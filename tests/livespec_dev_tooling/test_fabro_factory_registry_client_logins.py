"""The registry role logs the Dispatcher host's Fabro client in to every registered factory.

`ansible/roles/fabro_factory_registry/tasks/main.yml`, "THE CLIENT LOGINS"
(livespec-dev-tooling-ko26ez.7). A newly registered factory, such as the arm64 container
workers' instance, must be readable by the Dispatcher the moment it is registered, so its
dev-token login comes from the committed role and never from a hand `fabro auth login`.
These tests read the committed tasks and run the role's own merge script against a stand-in
auth store with a mocked server.env on stdin. Every token here is the test's own.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

_ROLE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "fabro_factory_registry"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_GROUP_VARS = (
    Path(__file__).resolve().parents[2] / "ansible" / "inventory" / "group_vars" / "dev_hosts.yml"
)
_READ = "Read each registered factory's dev token on its own host"
_LOGIN = "Log this host's Fabro client in to each registered factory"
_URL = "https://factory-one.tailnet.example:32279"


def _task(name: str) -> dict[str, Any]:
    tasks = yaml.safe_load(_TASKS.read_text(encoding="utf-8"))
    [task] = [t for t in tasks if t.get("name") == name]
    return task


@dataclass(frozen=True, kw_only=True)
class _Merged:
    returncode: int
    stdout: str


def _merge(
    *, home: Path, server_env: str, monkeypatch: pytest.MonkeyPatch, url: str = _URL
) -> _Merged:
    """Run the role's own merge script in-process, as its command task would."""
    script = _task(_LOGIN)["ansible.builtin.command"]["argv"][2]
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FABRO_SERVER", url)
    monkeypatch.setattr(sys, "stdin", io.StringIO(server_env))
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out):
        try:
            exec(compile(script, str(_TASKS), "exec"), {"__name__": "__main__"})  # noqa: S102
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
    return _Merged(returncode=code, stdout=out.getvalue())


def _store(home: Path) -> dict[str, Any]:
    return json.loads((home / ".fabro" / "auth.json").read_text(encoding="utf-8"))


def test_a_registered_factory_gets_a_dev_token_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _merge(
        monkeypatch=monkeypatch,
        home=tmp_path,
        server_env="SESSION_SECRET=x\nFABRO_DEV_TOKEN=fabro_dev_one\n",
    )
    assert run.returncode == 0
    assert run.stdout.strip() == "changed"
    entry = _store(tmp_path)["servers"][_URL]
    assert entry["kind"] == "dev-token" and entry["token"] == "fabro_dev_one"
    assert ((tmp_path / ".fabro" / "auth.json").stat().st_mode & 0o777) == 0o600


def test_an_existing_equal_login_is_left_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = "FABRO_DEV_TOKEN=fabro_dev_one\n"
    assert _merge(monkeypatch=monkeypatch, home=tmp_path, server_env=env).returncode == 0
    before = (tmp_path / ".fabro" / "auth.json").read_bytes()
    run = _merge(monkeypatch=monkeypatch, home=tmp_path, server_env=env)
    assert run.stdout.strip() == "unchanged"
    assert (tmp_path / ".fabro" / "auth.json").read_bytes() == before
    assert not list((tmp_path / ".fabro").glob("auth.json.bak-*"))


def test_other_servers_logins_are_kept_and_a_backup_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = "https://factory-one.tailnet.example:32276"
    assert (
        _merge(
            monkeypatch=monkeypatch, home=tmp_path, server_env="FABRO_DEV_TOKEN=a\n", url=other
        ).returncode
        == 0
    )
    run = _merge(monkeypatch=monkeypatch, home=tmp_path, server_env="FABRO_DEV_TOKEN=b\n")
    assert run.returncode == 0
    servers = _store(tmp_path)["servers"]
    assert servers[other]["token"] == "a" and servers[_URL]["token"] == "b"
    [backup] = list((tmp_path / ".fabro").glob("auth.json.bak-*"))
    assert _URL not in json.loads(backup.read_text(encoding="utf-8"))["servers"]


def test_a_server_env_without_a_token_fails_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _merge(monkeypatch=monkeypatch, home=tmp_path, server_env="SESSION_SECRET=x\n")
    assert run.returncode != 0
    assert not (tmp_path / ".fabro" / "auth.json").exists()


def test_the_token_never_reaches_argv_environment_or_a_log() -> None:
    read, login = _task(_READ), _task(_LOGIN)
    assert read["no_log"] is True and login["no_log"] is True
    assert "ansible.builtin.slurp" in read and read["delegate_to"] == "{{ item.value.host }}"
    argv = login["ansible.builtin.command"]["argv"]
    assert not [a for a in argv if "item.content" in a or "{{" in a]
    assert "item.content" in login["ansible.builtin.command"]["stdin"]
    assert not [v for v in login["environment"].values() if "item.content" in v]


def test_logins_are_keyed_on_the_dispatcher_group_not_a_hostname() -> None:
    assert (
        yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))["fabro_factory_registry_client_login"]
        is False
    )
    assert (
        yaml.safe_load(_GROUP_VARS.read_text(encoding="utf-8"))[
            "fabro_factory_registry_client_login"
        ]
        is True
    )
    for name in (_READ, _LOGIN):
        assert "fabro_factory_registry_client_login | bool" in str(_task(name)["when"])
        assert _task(name)["loop"].startswith("{{ fabro_factory_registry_")
