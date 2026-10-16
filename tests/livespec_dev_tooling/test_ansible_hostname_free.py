"""Outside-in test for `livespec_dev_tooling/ansible_hostname_free.py`.

A machine is bound only through the inventory's groups and host variables
(livespec-dev-tooling-prdxxe). The check fails when a playbook's `hosts:` field
names an inventory host, and when a role value equals an inventory host name or
carries that host's tailnet name. The committed tree must pass it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "ansible_hostname_free.py"

_INVENTORY = """\
# A comment line that names no host.
all:
  children:
    legacy:
      children:
        dev_hosts:
          hosts:
            vps:
              ansible_connection: local
        ci_pool:
          hosts:
            # a comment inside the hosts block
            poweredge-xubuntu:
              cluster_role: server

            gmktec-xubuntu:
              cluster_role: agent
        sandbox_hosts:
          hosts:
            hp-xubuntu:
"""


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), "ansible_hostname_free check module should exist"
    spec = importlib.util.spec_from_file_location("ansible_hostname_free_under_test", _CHECK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckRun(NamedTuple):
    returncode: int
    findings: list[dict[str, object]]


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Invoke the check's `main()` in-process under `cwd` and parse its findings."""
    monkeypatch.chdir(cwd)
    rc = _load_check_module().main()
    captured = capsys.readouterr()
    findings = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    return _CheckRun(returncode=rc, findings=findings)


def _write(*, root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _tree(*, root: Path) -> Path:
    """Write a minimal clean ansible tree: an inventory and one group-targeted play."""
    _write(root=root, relative="ansible/inventory/legacy.yml", text=_INVENTORY)
    _write(root=root, relative="ansible/site.yml", text="- name: Pool\n  hosts: ci_pool\n")
    return root


def _tokens(*, run: _CheckRun) -> list[tuple[object, object, object]]:
    return [(item["kind"], item["path"], item["token"]) for item in run.findings]


def test_the_committed_tree_names_no_machine_outside_the_inventory(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every committed play targets a group and no committed role names a machine."""
    run = _run_check(cwd=_REPO_ROOT, monkeypatch=monkeypatch, capsys=capsys)
    assert run.findings == []
    assert run.returncode == 0


def test_a_clean_tree_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _run_check(cwd=_tree(root=tmp_path), monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0
    assert run.findings == []


def test_a_play_naming_an_inventory_host_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path)
    _write(
        root=root,
        relative="ansible/backup.yml",
        text="- name: Backup\n  hosts: poweredge-xubuntu\n",
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _tokens(run=run) == [("play-hosts", "ansible/backup.yml", "poweredge-xubuntu")]
    assert run.findings[0]["line"] == 2


def test_a_host_inside_a_play_pattern_fails_whatever_its_operator(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path)
    _write(
        root=root,
        relative="ansible/mixed.yaml",
        text='- hosts: "ci_pool:!gmktec-xubuntu"  # trailing comment\n- hosts: dev_hosts,vps\n',
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _tokens(run=run) == [
        ("play-hosts", "ansible/mixed.yaml", "gmktec-xubuntu"),
        ("play-hosts", "ansible/mixed.yaml", "vps"),
    ]


def test_a_host_known_only_from_host_vars_counts_as_a_host(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path)
    _write(root=root, relative="ansible/inventory/host_vars/spare-box.yaml", text="x: 1\n")
    _write(root=root, relative="ansible/spare.yml", text="- hosts: spare-box\n")
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert _tokens(run=run) == [("play-hosts", "ansible/spare.yml", "spare-box")]


def test_a_role_default_equal_to_a_host_name_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path)
    _write(
        root=root,
        relative="ansible/roles/node_labels/defaults/main.yml",
        text="# poweredge-xubuntu is named in this comment only\nnode_labels_server_host: 'poweredge-xubuntu'\n",
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _tokens(run=run) == [
        ("host-value", "ansible/roles/node_labels/defaults/main.yml", "poweredge-xubuntu")
    ]


def test_a_role_list_item_equal_to_a_host_name_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path)
    _write(
        root=root,
        relative="ansible/roles/r/vars/main.yaml",
        text="targets:\n  - hp-xubuntu\n",
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert _tokens(run=run) == [("host-value", "ansible/roles/r/vars/main.yaml", "hp-xubuntu")]


def test_a_tailnet_name_in_a_role_value_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path)
    _write(
        root=root,
        relative="ansible/roles/node_status_credential/defaults/main.yml",
        text="api: https://poweredge-xubuntu.perch-rudd.ts.net:6443  # was measured here\n",
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _tokens(run=run) == [
        (
            "tailnet-name",
            "ansible/roles/node_status_credential/defaults/main.yml",
            "poweredge-xubuntu.perch-rudd.ts.net",
        )
    ]


def test_prose_mentioning_a_host_inside_a_longer_value_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path)
    _write(
        root=root,
        relative="ansible/roles/r/tasks/main.yml",
        text="- name: Explain\n  ansible.builtin.debug:\n    msg: hp-xubuntu is served elsewhere\n",
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0


def test_a_template_assignment_of_a_host_or_tailnet_name_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path)
    _write(
        root=root,
        relative="ansible/roles/r/templates/app.conf.j2",
        text=(
            "{# vps.perch-rudd.ts.net in a Jinja comment\n   spanning two lines #}\n"
            "# vps.perch-rudd.ts.net in a rendered comment line\n"
            "; vps in an ini comment line\n"
            "server string = vps Arq backup source\n"
            "server = vps\n"
            "url: https://hp-xubuntu.perch-rudd.ts.net/\n"
        ),
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert [(item["kind"], item["line"], item["token"]) for item in run.findings] == [
        ("host-value", 6, "vps"),
        ("tailnet-name", 7, "hp-xubuntu.perch-rudd.ts.net"),
    ]


def test_files_outside_the_scanned_kinds_are_ignored(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """HOST_VARS.md, the repository's tests/ fixtures and host_vars are not role values."""
    root = _tree(root=tmp_path)
    _write(root=root, relative="ansible/roles/r/HOST_VARS.md", text="r_host: vps\n")
    _write(root=root, relative="tests/fixtures/play.yml", text="- hosts: vps\n")
    _write(
        root=root,
        relative="ansible/inventory/host_vars/vps.yml",
        text="serve: vps.perch-rudd.ts.net\n",
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0


def test_a_tree_with_no_inventory_reports_nothing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        root=tmp_path, relative="ansible/roles/r/defaults/main.yml", text="x: vps.example.ts.net\n"
    )
    _write(root=tmp_path, relative="ansible/roles/r/templates/t.j2", text="host = vps\n")
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0
