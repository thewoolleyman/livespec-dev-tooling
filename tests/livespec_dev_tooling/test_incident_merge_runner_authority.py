"""The merge runner executes only a root-owned authority build, and its unit starts sandboxed.

Work-item livespec-dev-tooling-o6u7jm, repair of an independent review. The runner is started
as ROOT by a oneshot unit and runs the canonical incident authority process. Resolving that
process from the candidate account's own plugin registry (`~ubuntu/.claude/...`) let that
account get code run as root, so the runner now takes the authority script the observer's
role already installs root-owned (`/opt/livespec-incident/reader/...`) and REFUSES BY NAME
unless the script and its interpreter, and every ancestor directory, are owned by root (or the
running account) and writable by neither group nor other, the same `protected_path` rule the
observer's loader applies to its own reader and principal.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import jinja2
import pytest
import yaml

import livespec_dev_tooling._incident_merge_bindings as bindings
import livespec_dev_tooling.incident_merge_runner as runner
from livespec_dev_tooling._incident_merge_bindings import ArmIdentity
from livespec_dev_tooling.incident_merge_principal import Merged

# This module concerns work item livespec-dev-tooling-o6u7jm, an ordinary pull request.

_INTERPRETER = Path("/usr/bin/env")
_APP_TOKEN = "app-installation-token"
_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _ROOT / "ansible" / "roles" / "incident_observer"
_IDENTITY = ArmIdentity(
    incident_id="inc-1",
    attempt_id="attempt-1",
    phase="repair",
    operation_id="op-1",
    generation=3,
    owner="owner-1",
)
_MERGED = Merged(
    incident_id="inc-1",
    pr_number=7,
    principal="incident-merge-app-4242",
    head_sha="c" * 40,
    master_sha="d" * 40,
    merged_at="2026-11-18T09:30:15Z",
    queue_ahead=(),
    endpoint="merge-async",
)


def _world(monkeypatch: pytest.MonkeyPatch, *, merge: Mock) -> None:
    config = SimpleNamespace(
        incident_merge_integration_id=4242, recovery_bypass_integration_id=1717
    )
    monkeypatch.setattr(runner, "load_config", Mock(return_value=config))
    monkeypatch.setattr(runner, "read_arm_identity", Mock(return_value=_IDENTITY))
    monkeypatch.setattr(runner, "merge_incident_repair", merge)
    monkeypatch.setattr(
        runner, "load_merge_credential", Mock(return_value=SimpleNamespace(app_id="4242"))
    )


def _ledger_root(*, directory: Path) -> Path:
    """A stand-in ledger root the protection rule accepts: 0644 files in 0755 directories."""
    root = directory / "ledger"
    (root / ".beads").mkdir(parents=True, mode=0o755, exist_ok=True)
    root.chmod(0o755)
    (root / ".beads").chmod(0o755)
    for name in (".beads/config.yaml", ".beads/metadata.json", ".livespec.jsonc"):
        target = root / name
        _ = target.write_text("{}\n")
        target.chmod(0o644)
    return root


def _go(*, tmp_path: Path, script: Path, run_text: Mock | None = None) -> int:
    return runner.run(
        argv=[
            "--pr",
            "7",
            "--credential",
            str(tmp_path / "credential.json"),
            "--project-root",
            str(tmp_path),
            "--authority-script",
            str(script),
            "--ledger-root",
            str(_ledger_root(directory=tmp_path)),
        ],
        owner_uid=0,
        interpreter=_INTERPRETER,
        connect=Mock(return_value=SimpleNamespace(token=_APP_TOKEN)),
        run_text_command=run_text or Mock(return_value=(0, "")),
        make_reader=Mock(),
    )


def _script(*, tmp_path: Path, mode: int) -> Path:
    directory = tmp_path / "reader"
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    script = directory / "incident_authority.py"
    _ = script.write_text("# authority\n")
    script.chmod(mode)
    return script


def test_an_authority_script_writable_by_group_or_other_is_refused_by_name(
    monkeypatch, tmp_path, capsys
):
    merge = Mock(return_value=_MERGED)
    _world(monkeypatch, merge=merge)
    status = _go(tmp_path=tmp_path, script=_script(tmp_path=tmp_path, mode=0o664))
    out = capsys.readouterr().out
    facts = [
        status == 2,
        "incident-merge-runner-authority-unprotected" in out,
        "incident_authority.py" in out,
        merge.call_count == 0,
    ]
    assert all(facts)


def test_an_absent_authority_script_is_refused_by_name(monkeypatch, tmp_path, capsys):
    merge = Mock(return_value=_MERGED)
    _world(monkeypatch, merge=merge)
    status = _go(tmp_path=tmp_path, script=tmp_path / "nowhere" / "incident_authority.py")
    out = capsys.readouterr().out
    assert all([status == 2, "incident-merge-runner-no-authority" in out, merge.call_count == 0])


def test_a_protected_authority_script_runs_under_the_serving_interpreter(monkeypatch, tmp_path):
    merge = Mock(return_value=_MERGED)
    _world(monkeypatch, merge=merge)
    script = _script(tmp_path=tmp_path, mode=0o644)
    authority = Mock(return_value="answer")
    monkeypatch.setattr(bindings, "call_authority", authority)
    status = _go(tmp_path=tmp_path, script=script)
    answer = merge.call_args.kwargs["chain"](incident_id="inc-1")
    command = authority.call_args.kwargs["command"]
    facts = [
        status == 0,
        answer == "answer",
        command == ["/usr/local/bin/with-livespec-env.sh", "--", str(_INTERPRETER), str(script)],
    ]
    assert all(facts)


def test_a_failed_ledger_write_after_a_merge_still_prints_the_merge_and_the_comment(
    monkeypatch, tmp_path, capsys
):
    def merged_then_unrecorded(**kwargs):
        kwargs["record"](
            incident_id="inc-1", text="incident-merge: merged\nmaster-sha: " + "d" * 40
        )
        return _MERGED

    _world(monkeypatch, merge=Mock(side_effect=merged_then_unrecorded))
    script = _script(tmp_path=tmp_path, mode=0o644)
    status = _go(tmp_path=tmp_path, script=script, run_text=Mock(return_value=(1, "ledger down")))
    out = capsys.readouterr().out
    facts = [
        status == 3,
        "incident-merge-runner-record-failed" in out,
        "incident-merge: merged" in out,
        "master-sha: " + "d" * 40 in out,
    ]
    assert all(facts)


def _unit() -> str:
    environment = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    template = environment.from_string(
        (_ROLE / "templates" / "livespec-incident-merge@.service.j2").read_text()
    )
    return template.render(
        ansible_managed="Ansible managed",
        incident_observer_merge_app_path="/etc/livespec-incident/merge-app.json",
        incident_observer_reference_dir="/var/lib/livespec-incident/reference",
        incident_observer_state_dir="/var/lib/livespec-incident/receipts",
        incident_observer_venv="/opt/livespec-incident/venv",
        incident_observer_merge_authority_script="/opt/livespec-incident/reader/x/incident_authority.py",
        incident_observer_merge_workdir="/opt/livespec-incident/merge-workdir",
    )


def _tasks() -> list[dict[str, object]]:
    return yaml.safe_load((_ROLE / "tasks" / "converge.yml").read_text())


def test_the_unit_names_the_root_owned_authority_script_and_fails_loudly_without_a_credential():
    lines = _unit().splitlines()
    exec_line = next(line for line in lines if line.startswith("ExecStart="))
    template_text = (_ROLE / "templates" / "livespec-incident-merge@.service.j2").read_text()
    facts = [
        "--authority-script /opt/livespec-incident/reader/x/incident_authority.py" in exec_line,
        "--registry" not in exec_line,
        ".claude" not in template_text,
        "AssertPathExists=/etc/livespec-incident/merge-app.json" in lines,
        not any(line.startswith("ConditionPathExists") for line in lines),
    ]
    assert all(facts)


def test_the_role_creates_roots_op_config_directory_before_the_unit_and_checks_the_script():
    tasks = _tasks()
    names = [str(task.get("name", "")) for task in tasks]
    config_dirs = [task for task in tasks if "op config directory" in str(task.get("name", ""))]
    installed = names.index("Install the incident-merge runner's templated oneshot unit")
    checks = [task for task in tasks if "authority script" in str(task.get("name", ""))]
    file_task = config_dirs[0]["ansible.builtin.file"]
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text())
    host_vars = yaml.safe_load(
        (_ROOT / "ansible" / "inventory" / "host_vars" / "vps.yml").read_text()
    )
    facts = [
        len(config_dirs) == 1,
        names.index(str(config_dirs[0]["name"])) < installed,
        file_task["state"] == "directory" and file_task["mode"] == "0700",
        file_task["owner"] == "root",
        "/root/.config/op" in str(config_dirs[0]),
        len(checks) >= 2,
        "incident_observer_merge_authority_script" in defaults,
        "incident_observer_merge_registry" not in defaults,
        "incident_observer_merge_registry" not in host_vars,
        "ReadWritePaths=-/root/.config/op" in _unit().splitlines(),
    ]
    assert all(facts)
