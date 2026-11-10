"""Outside-in test for `livespec_dev_tooling/ansible_get_url_checksum.py`.

`ansible.builtin.get_url` does not download under `--check`: it compares the
existing destination against an EMPTY temporary file, so a task with no
`checksum:` reports `changed` against a host that is already converged
(livespec-dev-tooling-7g5qba, measured on hetzner-xubuntu 2026-11-08). The check
fails when a get_url task under `ansible/roles/*/tasks` pins no checksum and
records no exemption naming why check mode cannot report it falsely. The
committed tree must pass it.
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
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "ansible_get_url_checksum.py"
_ONEPASSWORD_TASKS = _REPO_ROOT / "ansible/roles/onepassword_desktop/tasks/main.yml"
_ONEPASSWORD_DEFAULTS = _REPO_ROOT / "ansible/roles/onepassword_desktop/defaults/main.yml"
_VENDOR_POLICY_SHA256 = "c0c148807d8dc588750a9cc512c7243ed10a9cfd5519a5a6f0a038ad66a19c39"

_PINNED = """\
- name: Fetch the policy
  ansible.builtin.get_url:
    url: https://example.invalid/a.pol
    dest: /etc/a.pol
    checksum: "sha256:{{ role_policy_sha256 }}"
    mode: "0644"
  become: true
"""


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path (the tree the RGR hook inspects)."""
    assert _CHECK_PATH.is_file(), "ansible_get_url_checksum check module should exist"
    spec = importlib.util.spec_from_file_location(
        "ansible_get_url_checksum_under_test", _CHECK_PATH
    )
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
    """Invoke the check's `main()` in-process under `cwd` and parse what it logged."""
    monkeypatch.chdir(cwd)
    rc = _load_check_module().main()
    captured = capsys.readouterr()
    findings = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    return _CheckRun(returncode=rc, findings=findings)


def _tree(*, root: Path, tasks: str, relative: str = "ansible/roles/r/tasks/main.yml") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(tasks, encoding="utf-8")
    return root


def _pairs(*, run: _CheckRun) -> list[tuple[object, object, object]]:
    return [(item["kind"], item["path"], item["line"]) for item in run.findings]


def test_the_committed_tree_pins_or_exempts_every_role_get_url(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _run_check(cwd=_REPO_ROOT, monkeypatch=monkeypatch, capsys=capsys)
    assert run.findings == []
    assert run.returncode == 0


def test_the_onepassword_debsig_policy_is_pinned_to_the_vendor_bytes() -> None:
    tasks = _ONEPASSWORD_TASKS.read_text(encoding="utf-8")
    defaults = _ONEPASSWORD_DEFAULTS.read_text(encoding="utf-8")
    start = tasks.index("- name: Fetch the 1Password debsig policy")
    task = tasks[start : tasks.index("\n- name:", start + 1)]
    assert 'checksum: "sha256:{{ onepassword_desktop_debsig_policy_sha256 }}"' in task
    assert f"onepassword_desktop_debsig_policy_sha256: {_VENDOR_POLICY_SHA256}" in defaults


def test_a_pinned_get_url_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _run_check(
        cwd=_tree(root=tmp_path, tasks=_PINNED), monkeypatch=monkeypatch, capsys=capsys
    )
    assert run.returncode == 0
    assert run.findings == []


def test_a_get_url_with_no_checksum_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = _PINNED + (
        "\n- name: Fetch the key\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/key.asc\n"
        "    dest: /etc/key.asc\n"
        "    mode: '0644'\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 10)]
    assert run.findings[0]["task"] == "Fetch the key"


@pytest.mark.parametrize(
    "module_key", ["get_url", "ansible.legacy.get_url", "ansible.builtin.get_url"]
)
def test_every_spelling_of_the_module_is_read(
    *,
    module_key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tasks = f"- name: Fetch\n  {module_key}:\n    url: https://example.invalid/x\n    dest: /x\n"
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 2)]


def test_a_nameless_get_url_task_is_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = "- ansible.builtin.get_url:\n" "    url: https://example.invalid/x\n" "    dest: /x\n"
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 1)]


def test_a_folded_checksum_value_counts_as_a_pin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Fetch kubectl\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/kubectl\n"
        "    checksum: >-\n"
        "      sha256:https://example.invalid/kubectl.sha256\n"
        "    dest: /usr/local/bin/kubectl\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0
    assert run.findings == []


def test_an_empty_checksum_value_is_not_a_pin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Fetch\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/x\n"
        "    checksum: ''\n"
        "    dest: /x\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 2)]


def test_an_empty_block_scalar_checksum_is_not_a_pin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Folded\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/x\n"
        "    checksum: >-\n"
        "    dest: /x\n"
        "- name: Literal\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/y\n"
        "    dest: /y\n"
        "    checksum: |\n"
        "\n"
        "- name: Kept\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/z\n"
        "    dest: /z\n"
        "    checksum: |+2\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [
        ("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 2),
        ("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 7),
        ("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 13),
    ]


def test_an_inline_checksum_argument_counts_as_a_pin(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Fetch\n"
        "  get_url: url=https://example.invalid/x dest=/x checksum=sha256:abc\n"
        "- name: Fetch unpinned\n"
        "  get_url: url=https://example.invalid/y dest=/y\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 4)]


def test_a_get_url_nested_in_a_block_and_loop_is_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Stage\n"
        "  block:\n"
        "    - name: Fetch each\n"
        "      ansible.builtin.get_url:\n"
        "        url: '{{ item }}'\n"
        "        dest: /srv\n"
        "      loop: '{{ urls }}'\n"
        "    - name: Next task\n"
        "      ansible.builtin.debug:\n"
        "        msg: checksum is only prose here\n"
    )
    run = _run_check(
        cwd=_tree(root=tmp_path, tasks=tasks, relative="ansible/roles/r/tasks/fetch.yaml"),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/fetch.yaml", 4)]


def test_an_exemption_with_a_reason_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Fetch\n"
        "  # check-mode-exempt: only runs when not ansible_check_mode\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/x\n"
        "    dest: /x\n"
        "  when: not ansible_check_mode\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0
    assert run.findings == []


def test_an_exemption_with_no_reason_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Fetch\n"
        "  # check-mode-exempt:\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/x\n"
        "    dest: /x\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 3)]


def test_an_exemption_on_a_neighbouring_task_does_not_leak(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Exempt\n"
        "  # check-mode-exempt: gated off under check mode\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/x\n"
        "    dest: /x\n"
        "\n"
        "- name: Not exempt\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/y\n"
        "    dest: /y\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 8)]


def test_an_exemption_on_a_later_task_does_not_exempt_a_nameless_dash_led_task(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- ansible.builtin.get_url:\n"
        "    url: https://example.invalid/x\n"
        "    dest: /x\n"
        "\n"
        "- name: Exempt\n"
        "  # check-mode-exempt: gated off under check mode\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/y\n"
        "    dest: /y\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 1)]


def test_a_nameless_dash_led_task_after_another_task_does_not_borrow_its_exemption(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = (
        "- name: Exempt\n"
        "  # check-mode-exempt: gated off under check mode\n"
        "  ansible.builtin.get_url:\n"
        "    url: https://example.invalid/x\n"
        "    dest: /x\n"
        "- ansible.builtin.get_url:\n"
        "    url: https://example.invalid/y\n"
        "    dest: /y\n"
        "    checksum: sha256:abc\n"
        "- ansible.builtin.get_url:\n"
        "    url: https://example.invalid/z\n"
        "    dest: /z\n"
    )
    run = _run_check(cwd=_tree(root=tmp_path, tasks=tasks), monkeypatch=monkeypatch, capsys=capsys)
    assert _pairs(run=run) == [("unpinned-get-url", "ansible/roles/r/tasks/main.yml", 10)]


def test_a_get_url_outside_role_tasks_is_out_of_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path, tasks=_PINNED)
    _ = _tree(
        root=root,
        tasks="- name: Drill\n  ansible.builtin.get_url:\n    url: https://example.invalid\n",
        relative="ansible/drill.yml",
    )
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 0


def test_a_tree_with_no_role_get_url_reports_itself_vacuous(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(root=tmp_path, tasks="- name: Nothing\n  ansible.builtin.debug:\n    msg: hi\n")
    run = _run_check(cwd=root, monkeypatch=monkeypatch, capsys=capsys)
    assert run.returncode == 1
    assert [item["kind"] for item in run.findings] == ["vacuous"]
