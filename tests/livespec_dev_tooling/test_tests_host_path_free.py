"""Outside-in test for `livespec_dev_tooling/tests_host_path_free.py`.

A test that reads, stats or writes an absolute path under `/etc`, `/var`, `/usr`,
`/opt` or `/run` — or converges an Ansible task whose destination is one — grades
the machine pytest happens to run on rather than the committed tree
(livespec-dev-tooling-vxkmab, from the 2026-10-18 F-az incident). The check fails
such a module naming the file, the line and the path; it passes a module that
derives every path from `tmp_path`, and it passes a module that merely NAMES a
host path without reaching it. The committed tree must pass it.
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
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "tests_host_path_free.py"

# Three synthetic test modules, written into a throwaway `tests/` tree. Line
# numbers are load-bearing: the check must name the line its finding is about,
# so each arm below asserts the line as well as the path.

_OFFENDERS = """\
import os
from pathlib import Path

_MARKER = "/run/livespec/marker"
_ROOT = "/etc/livespec"
_REGISTRY: Path = Path(_ROOT) / "fabro-factories.json"
_TIMEOUT = 5
_UNSET: str


def test_reads_a_host_file() -> None:
    assert Path("/etc/livespec/sandbox-capabilities").read_text(encoding="utf-8")


def test_stats_a_host_file() -> None:
    assert Path("/var/lib/docker-sandbox-slice/restart-pending").is_file()


def test_writes_through_open() -> None:
    handle = open(_MARKER, "w", encoding="utf-8")
    handle.close()


def test_reads_the_module_constant() -> None:
    assert _REGISTRY.exists()


def test_stats_through_os() -> None:
    assert os.stat(path="/opt/livespec/codex-acp")
"""

_DESTINATIONS = """\
_DEST_VAR = "fabro_factory_registry_dest"
_DEFAULT = "/etc/livespec/fabro-factories.json"
_BASE = {"gather_facts": False}


def test_converges_the_real_destination() -> None:
    task = {
        "ansible.builtin.copy": {
            "content": "{}",
            "dest": "/etc/livespec/fabro-factories.json",
        }
    }
    extra = {**_BASE, _DEST_VAR: _DEFAULT, "timeout": 5}
    assert task and extra
"""

_CLEAN = """\
from pathlib import Path

_DOCUMENTED_DEFAULT = "/etc/livespec/fabro-factories.json"


def test_derives_every_path_from_tmp_path(*, tmp_path: Path) -> None:
    dest = tmp_path / "etc" / "livespec" / "fabro-factories.json"
    dest.parent.mkdir(parents=True)
    _ = dest.write_text("{}", encoding="utf-8")
    assert dest.read_text(encoding="utf-8") == "{}"


def test_names_the_documented_default_without_reaching_it() -> None:
    assert _DOCUMENTED_DEFAULT.startswith("/etc/")
"""


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), "tests_host_path_free check module should exist"
    spec = importlib.util.spec_from_file_location("tests_host_path_free_under_test", _CHECK_PATH)
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


def _reported(*, run: _CheckRun) -> list[tuple[object, object, object, object]]:
    """Each finding as the four facts the work-item requires it to name, plus its kind."""
    return [(item["path"], item["line"], item["target"], item["kind"]) for item in run.findings]


def test_the_committed_tests_tree_reaches_no_real_host_path(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No test under `tests/` reads, stats, writes or converges a real host path."""
    run = _run_check(cwd=_REPO_ROOT, monkeypatch=monkeypatch, capsys=capsys)
    assert run.findings == []
    assert run.returncode == 0


def test_a_read_a_stat_and_a_write_of_a_host_path_each_fail(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every finding names the file, the line number and the path."""
    _write(root=tmp_path, relative="tests/test_offenders.py", text=_OFFENDERS)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _reported(run=run) == [
        (
            "tests/test_offenders.py",
            12,
            "/etc/livespec/sandbox-capabilities",
            "method:read_text",
        ),
        (
            "tests/test_offenders.py",
            16,
            "/var/lib/docker-sandbox-slice/restart-pending",
            "method:is_file",
        ),
        ("tests/test_offenders.py", 20, "/run/livespec/marker", "call:open"),
        ("tests/test_offenders.py", 25, "/etc/livespec", "method:exists"),
        ("tests/test_offenders.py", 29, "/opt/livespec/codex-acp", "call:os.stat"),
    ]


def test_an_ansible_task_destination_naming_a_host_path_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `dest` the module hard-codes, and an extra-var key held in a constant, both fail."""
    _write(root=tmp_path, relative="tests/ansible/test_destinations.py", text=_DESTINATIONS)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _reported(run=run) == [
        (
            "tests/ansible/test_destinations.py",
            10,
            "/etc/livespec/fabro-factories.json",
            "destination:dest",
        ),
        (
            "tests/ansible/test_destinations.py",
            13,
            "/etc/livespec/fabro-factories.json",
            "destination:fabro_factory_registry_dest",
        ),
    ]


def test_a_tmp_path_derived_tree_and_a_mere_mention_both_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Naming a role's documented default is not reaching it, and `tmp_path` never matches."""
    _write(root=tmp_path, relative="tests/test_clean.py", text=_CLEAN)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.findings == []
    assert run.returncode == 0


def test_every_finding_carries_the_remediation_that_names_tmp_path(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal is actionable: it says what to derive the path from instead."""
    _write(root=tmp_path, relative="tests/test_offenders.py", text=_OFFENDERS)
    run = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert run.findings
    for item in run.findings:
        assert "tmp_path" in str(item["remediation"])
        assert item["level"] == "error"
