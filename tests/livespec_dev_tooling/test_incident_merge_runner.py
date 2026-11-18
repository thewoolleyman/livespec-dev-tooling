"""The incident-merge runner binds the principal's seams to the host and names every refusal.

Work-item livespec-dev-tooling-o6u7jm (child of livespec-dev-tooling-u3nbm3). The ratified
`Incident-merge principal.` contract is already implemented as a pure decision
(`merge_incident_repair`); these cases pin the production binding: the credential file's
three protection conditions, the runner's exit statuses, the three host seams, and the
oneshot unit that starts it once per pull request.
"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import jinja2
import pytest
import yaml
from returns.result import Failure

import livespec_dev_tooling._incident_merge_bindings as bindings
import livespec_dev_tooling.incident_merge_runner as runner
from livespec_dev_tooling._incident_app_installation import AppRefusal
from livespec_dev_tooling._incident_merge_bindings import (
    ArmIdentity,
    LedgerWriteError,
    graphql_queue_reader,
    ledger_recorder,
    read_arm_identity,
    run_text,
    token_forge_reader,
)
from livespec_dev_tooling._incident_merge_credential import load_merge_credential
from livespec_dev_tooling._incident_observer_store import record_path, save_record
from livespec_dev_tooling.incident_merge_app import MergeAppCredential
from livespec_dev_tooling.incident_merge_principal import (
    Merged,
    QueueUnreadableError,
    Refused,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-o6u7jm

_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _ROOT / "ansible" / "roles" / "incident_observer"
_BODY = "".join(chr(65 + index % 26) for index in range(130))
_KEY = f"-----BEGIN RSA PRIVATE KEY----- {_BODY} -----END RSA PRIVATE KEY-----"
_MERGE_ID, _RECOVERY_ID = 4242, 1717
_REPO = "o/r"
_UID = os.getuid()
_APP_TOKEN = "app-installation-token"
_SECRET = "secret-token-value"


def _credential(*, directory: Path, mode: int = 0o600, content: object = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "merge-app.json"
    body = {"app_id": str(_MERGE_ID), "private_key": _KEY} if content is None else content
    _ = path.write_text(body if isinstance(body, str) else json.dumps(body))
    path.chmod(mode)
    return path


def _load(*, path: Path, uid: int = _UID):
    return load_merge_credential(
        path=path,
        owner_uid=uid,
        merge_integration_id=_MERGE_ID,
        recovery_integration_id=_RECOVERY_ID,
    )


def _code(*, outcome: object) -> str:
    return outcome.code if isinstance(outcome, AppRefusal) else "loaded"


def test_the_credential_file_loads_only_when_root_owned_and_mode_0600(tmp_path):
    good = _credential(directory=tmp_path)
    loose = _credential(directory=tmp_path / "loose", mode=0o640)
    loaded = _load(path=good)
    wrong_owner = _load(path=good, uid=_UID + 1)
    mode_refusal = _load(path=loose)
    facts = [
        isinstance(loaded, MergeAppCredential),
        _code(outcome=wrong_owner) == "incident-merge-runner-credential-unprotected",
        f"uid {_UID + 1}" in wrong_owner.detail,
        "mode 0640, not 0600" in mode_refusal.detail,
    ]
    assert all(facts)


def test_the_credential_file_names_absent_unfit_and_malformed_conditions(tmp_path):
    link = tmp_path / "link.json"
    link.symlink_to(_credential(directory=tmp_path))
    outcomes = {
        "absent": _load(path=tmp_path / "nowhere.json"),
        "directory": _load(path=tmp_path),
        "symlink": _load(path=link),
        "not-json": _load(path=_credential(directory=tmp_path / "a", content="nope")),
        "app-id-number": _load(path=_credential(directory=tmp_path / "b", content={"app_id": 1})),
        "key-number": _load(
            path=_credential(directory=tmp_path / "c", content={"app_id": "1", "private_key": 5})
        ),
        "not-the-declared-app": _load(
            path=_credential(directory=tmp_path / "d", content={"app_id": "9", "private_key": _KEY})
        ),
    }
    codes = {name: _code(outcome=outcome) for name, outcome in outcomes.items()}
    facts = [
        codes["absent"] == "incident-merge-runner-credential-absent",
        codes["directory"] == "incident-merge-runner-credential-unprotected",
        codes["symlink"] == "incident-merge-runner-credential-unprotected",
        codes["not-json"] == "incident-merge-runner-credential-malformed",
        codes["app-id-number"] == "incident-merge-runner-credential-malformed",
        codes["key-number"] == "incident-merge-runner-credential-malformed",
        codes["not-the-declared-app"] == "incident-merge-app-not-the-declared-app",
    ]
    assert all(facts)


# --- the runner -------------------------------------------------------------------------

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


def _world(monkeypatch, *, outcome, identity=_IDENTITY, plugin=Path("/plugin")):
    """One runner world: every host dependency replaced, the principal's outcome chosen."""
    merge = (
        Mock(side_effect=outcome)
        if isinstance(outcome, BaseException)
        else Mock(return_value=outcome)
    )
    config = SimpleNamespace(
        incident_merge_integration_id=_MERGE_ID, recovery_bypass_integration_id=_RECOVERY_ID
    )
    monkeypatch.setattr(runner, "load_config", Mock(return_value=config))
    monkeypatch.setattr(runner, "read_arm_identity", Mock(return_value=identity))
    monkeypatch.setattr(runner, "merge_incident_repair", merge)
    if isinstance(plugin, Path):
        monkeypatch.setattr(runner, "registered_plugin_root", Mock(return_value=plugin))
    else:
        monkeypatch.setattr(runner, "registered_plugin_root", Mock(side_effect=plugin))
    return merge


def _go(*, tmp_path, connect=None, argv=("--pr", "7"), run_text_command=None, make_reader=None):
    path = _credential(directory=tmp_path / "cred")
    return runner.run(
        argv=[
            *argv,
            "--credential",
            str(path),
            "--project-root",
            str(tmp_path),
            "--registry",
            str(tmp_path / "registry.json"),
        ],
        owner_uid=_UID,
        connect=connect or Mock(return_value=SimpleNamespace(token=_APP_TOKEN)),
        run_text_command=run_text_command or Mock(return_value=(0, "{}")),
        make_reader=make_reader or Mock(),
    )


def test_a_merged_pull_request_exits_zero_and_names_the_master_commit(
    monkeypatch, tmp_path, capsys
):
    merge = _world(monkeypatch, outcome=_MERGED)
    status = _go(tmp_path=tmp_path)
    kwargs = merge.call_args.kwargs
    facts = [
        status == 0,
        "incident-merge-runner-merged: pr 7 master " + "d" * 40 in capsys.readouterr().out,
        kwargs["incident_id"] == "inc-1",
        kwargs["pr_number"] == 7,
        kwargs["principal"] == "incident-merge-app-4242",
        kwargs["repo"] == "livespec-ai/livespec-dev-tooling",
    ]
    assert all(facts)


def test_a_refusal_exits_one_and_is_named_on_standard_output(monkeypatch, tmp_path, capsys):
    _ = _world(monkeypatch, outcome=Refused(reason="checks-not-green", detail="lint pending"))
    status = _go(tmp_path=tmp_path)
    assert (status, capsys.readouterr().out) == (
        1,
        "incident-merge-runner-refused: checks-not-green: lint pending\n",
    )


def test_a_failed_ledger_write_exits_three_and_says_the_merge_may_have_happened(
    monkeypatch, tmp_path, capsys
):
    _ = _world(monkeypatch, outcome=LedgerWriteError(incident_id="inc-1", code=1, detail="down"))
    status = _go(tmp_path=tmp_path)
    out = capsys.readouterr().out
    assert all([status == 3, "record-failed" in out, "may already be merged" in out])


def test_the_runner_does_not_start_without_a_fit_credential(monkeypatch, tmp_path, capsys):
    merge = _world(monkeypatch, outcome=_MERGED)
    status = runner.run(
        argv=[
            "--pr",
            "7",
            "--credential",
            str(tmp_path / "absent.json"),
            "--project-root",
            str(tmp_path),
            "--registry",
            str(tmp_path / "registry.json"),
        ],
        owner_uid=_UID,
    )
    out = capsys.readouterr().out
    facts = [
        status == 2,
        "incident-merge-runner-refused: incident-merge-runner-credential-absent" in out,
        merge.call_count == 0,
    ]
    assert all(facts)


def test_the_runner_does_not_start_when_the_app_the_arm_or_the_authority_is_missing(
    monkeypatch, tmp_path, capsys
):
    merge = _world(monkeypatch, outcome=_MERGED)
    refused = _go(
        tmp_path=tmp_path, connect=Mock(return_value=AppRefusal(code="app-x", detail="d"))
    )
    _ = _world(monkeypatch, outcome=_MERGED, identity="no pre-merge arm is recorded for o/r")
    no_arm = _go(tmp_path=tmp_path)
    _ = _world(monkeypatch, outcome=_MERGED, plugin=OSError())
    no_authority = _go(tmp_path=tmp_path)
    out = capsys.readouterr().out
    facts = [
        (refused, no_arm, no_authority) == (2, 2, 2),
        "incident-merge-runner-refused: app-x: d" in out,
        "incident-merge-runner-no-arm: no pre-merge arm is recorded for o/r" in out,
        "incident-merge-runner-no-authority" in out,
        merge.call_count == 0,
    ]
    assert all(facts)


def test_the_runner_refuses_by_name_when_no_arm_record_exists_for_the_pull_request(
    monkeypatch, tmp_path, capsys
):
    merge = _world(monkeypatch, outcome=_MERGED)
    monkeypatch.undo()
    config = SimpleNamespace(
        incident_merge_integration_id=_MERGE_ID, recovery_bypass_integration_id=_RECOVERY_ID
    )
    merge = Mock(return_value=_MERGED)
    monkeypatch.setattr(runner, "load_config", Mock(return_value=config))
    monkeypatch.setattr(runner, "merge_incident_repair", merge)
    credential = _credential(directory=tmp_path / "cred")
    state = tmp_path / "state"
    state.mkdir()
    status = runner.run(
        argv=[
            "--pr",
            "7",
            "--credential",
            str(credential),
            "--project-root",
            str(tmp_path),
            "--registry",
            str(tmp_path / "registry.json"),
            "--state-dir",
            str(state),
            "--repository",
            _REPO,
        ],
        owner_uid=_UID,
        connect=Mock(return_value=SimpleNamespace(token=_APP_TOKEN)),
    )
    out = capsys.readouterr().out
    facts = [
        status == 2,
        "incident-merge-runner-no-arm: no pre-merge arm is recorded for o/r" in out,
        merge.call_count == 0,
    ]
    assert all(facts)


def test_the_runner_requires_a_pull_request_number(tmp_path):
    with pytest.raises(SystemExit) as raised:
        runner.run(
            argv=["--credential", str(tmp_path / "x"), "--registry", str(tmp_path / "r")],
            owner_uid=_UID,
        )
    assert raised.value.code == 2


def test_the_seams_handed_to_the_principal_reach_the_host_through_the_bindings(
    monkeypatch, tmp_path
):
    merge = _world(monkeypatch, outcome=_MERGED)
    host = Mock(return_value=(0, ""))
    forge_read = Mock(
        return_value=SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"data": {"repository": {"mergeQueue": None}}}),
            stderr="",
        )
    )
    authority = Mock(return_value="chain-answer")
    monkeypatch.setattr(bindings, "call_authority", authority)
    make_reader = Mock(return_value=forge_read)
    _ = _go(tmp_path=tmp_path, run_text_command=host, make_reader=make_reader)
    kwargs = merge.call_args.kwargs
    answer = kwargs["chain"](incident_id="inc-1")
    mismatch = kwargs["chain"](incident_id="inc-2")
    ahead = kwargs["queue"](repo=_REPO, pr_number=7)
    kwargs["record"](incident_id="inc-1", text="note")
    flags = authority.call_args.kwargs["flags"]
    facts = [
        answer == "chain-answer",
        isinstance(mismatch, Failure) and "inc-2" in mismatch.failure().detail,
        flags["item"] == "inc-1" and flags["generation"] == "3" and flags["phase"] == "repair",
        authority.call_args.kwargs["action"] == "read-current",
        ahead == (),
        host.call_args.kwargs["argv"][-4:] == ["bd", "comment", "inc-1", "note"],
        merge.call_args.kwargs["check_reader"] is forge_read,
        make_reader.call_args.kwargs == {"token": _APP_TOKEN},
        forge_read.call_count == 1,
    ]
    assert all(facts)


def test_main_reads_the_pull_request_only_from_the_command_line(monkeypatch, tmp_path, capsys):
    absent = tmp_path / "absent.json"
    argv = ["runner", "--pr", "5", "--credential", str(absent), "--registry", str(absent)]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as raised:
        _ = runpy.run_path(str(Path(runner.__file__)), run_name="__main__")
    assert (raised.value.code, "credential-absent" in capsys.readouterr().out) == (2, True)


# --- the three host seams -----------------------------------------------------------------


def _arm(*, pr_number: int = 7) -> dict[str, object]:
    arm: dict[str, object] = {
        "repository": _REPO,
        "incident_item_id": "inc-1",
        "attempt_id": "attempt-1",
        "operation_id": "op-1",
        "owner": "owner-1",
        "phase": "repair",
        "base_sha": "b" * 40,
        "head_sha": "c" * 40,
        "controller_release": "v1",
        "controller_revision": "r1",
        "authority_receipt": "ab",
        "generation": 3,
        "pr_number": pr_number,
        "required_jobs": ["check-lint"],
    }
    return {
        "observer_arm": arm,
        "observer_arm_id": hashlib.sha256(json.dumps(arm, sort_keys=True).encode()).hexdigest(),
    }


def test_the_arm_identity_is_read_only_for_the_armed_pull_request(tmp_path):
    save_record(path=record_path(directory=tmp_path, repository=_REPO), record=_arm())
    armed = read_arm_identity(state_dir=tmp_path, repository=_REPO, pr_number=7)
    other = read_arm_identity(state_dir=tmp_path, repository=_REPO, pr_number=8)
    unarmed = read_arm_identity(state_dir=tmp_path, repository="o/other", pr_number=7)
    corrupt_path = record_path(directory=tmp_path, repository="o/bad")
    _ = corrupt_path.write_text("{not json")
    corrupt = read_arm_identity(state_dir=tmp_path, repository="o/bad", pr_number=7)
    facts = [
        armed == _IDENTITY,
        "is for pull request 7, not 8" in other,
        unarmed == "no pre-merge arm is recorded for o/other",
        "unreadable" in corrupt,
    ]
    assert all(facts)


def _read(*, code: int, text: str) -> Mock:
    return Mock(return_value=SimpleNamespace(returncode=code, stdout=text, stderr=""))


def test_the_queue_reader_parses_the_graphql_answer_and_names_an_unreadable_one():
    nodes = [
        {"position": 1, "pullRequest": {"number": 5}},
        {"position": 2, "pullRequest": {"number": 7}},
    ]
    answer = {"data": {"repository": {"mergeQueue": {"entries": {"nodes": nodes}}}}}
    good = graphql_queue_reader(read=_read(code=0, text=json.dumps(answer)))
    failed = graphql_queue_reader(read=_read(code=1, text="boom"))
    garbled = graphql_queue_reader(read=_read(code=0, text="not json"))
    with pytest.raises(QueueUnreadableError, match="exited 1"):
        _ = failed(repo=_REPO, pr_number=7)
    with pytest.raises(QueueUnreadableError, match="not JSON"):
        _ = garbled(repo=_REPO, pr_number=7)
    assert good(repo=_REPO, pr_number=7) == (5,)


def test_the_gating_reader_carries_the_app_token_in_the_environment_and_nowhere_else():
    answer = SimpleNamespace(returncode=0, stdout="{}", stderr="")
    spawn = Mock(side_effect=[answer, FileNotFoundError("no gh")])
    reader = token_forge_reader(token=_SECRET, spawn=spawn)
    read = reader(args=["api", "repos/o/r"])
    lost = reader(args=["api", "repos/o/r/pulls/1"])
    first = spawn.call_args_list[0]
    facts = [
        read.returncode == 0,
        first.kwargs["env"]["GH_TOKEN"] == _SECRET,
        first.kwargs["env"]["GH_PROMPT_DISABLED"] == "1",
        all(_SECRET not in part for part in first.args[0]),
        _SECRET not in repr(read) + repr(lost),
        lost.returncode != 0,
    ]
    assert all(facts)


def test_the_ledger_recorder_comments_through_the_wrapper_and_names_a_failed_write():
    ok = Mock(return_value=(0, ""))
    ledger_recorder(run=ok)(incident_id="inc-1", text="merged")
    with pytest.raises(LedgerWriteError, match="inc-1"):
        ledger_recorder(run=Mock(return_value=(1, "denied")))(incident_id="inc-1", text="x")
    wrapper = "/usr/local/bin/with-livespec-env.sh"
    assert ok.call_args.kwargs["argv"] == [wrapper, "--", "bd", "comment", "inc-1", "merged"]


def test_run_text_reports_an_exit_its_output_or_why_it_never_ran(monkeypatch):
    done = SimpleNamespace(returncode=0, stdout="out", stderr="err")
    failed = SimpleNamespace(returncode=3, stdout="out", stderr="err")
    monkeypatch.setattr(bindings.subprocess, "run", Mock(return_value=done))
    first = run_text(argv=["x"])
    monkeypatch.setattr(bindings.subprocess, "run", Mock(return_value=failed))
    second = run_text(argv=["x"])
    monkeypatch.setattr(bindings.subprocess, "run", Mock(side_effect=FileNotFoundError("gone")))
    third = run_text(argv=["x"])
    assert (first, second, third[0]) == ((0, "out"), (3, "err"), -1)


# --- the oneshot unit ----------------------------------------------------------------------


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
        incident_observer_merge_registry="/declared/by/host_vars/installed_plugins.json",
    )


def test_the_unit_runs_the_runner_once_for_the_instance_pull_request_and_never_without_one():
    exec_lines = [line for line in _unit().splitlines() if line.startswith("ExecStart=")]
    tasks = yaml.safe_load((_ROLE / "tasks" / "converge.yml").read_text())
    installs = [task for task in tasks if "templated oneshot unit" in task.get("name", "")]
    facts = [
        len(exec_lines) == 1,
        "-m livespec_dev_tooling.incident_merge_runner --pr %i " in exec_lines[0],
        "Type=oneshot" in _unit(),
        "User=root" in _unit(),
        "ConditionPathExists=/etc/livespec-incident/merge-app.json" in _unit(),
        len(installs) == 1,
        installs[0]["ansible.builtin.template"]["src"] == "livespec-incident-merge@.service.j2",
        installs[0]["ansible.builtin.template"]["mode"] == "0644",
    ]
    assert all(facts)


def test_the_unit_is_hardened_and_the_registry_is_a_declared_host_fact_never_a_guess():
    unit = _unit()
    tasks = yaml.safe_load((_ROLE / "tasks" / "converge.yml").read_text())
    names = [task.get("name", "") for task in tasks]
    refusals = [
        task
        for task in tasks
        if "incident-merge plugin registry" in task.get("name", "")
        and "ansible.builtin.assert" in task
    ]
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text())
    host_vars = yaml.safe_load(
        (_ROOT / "ansible" / "inventory" / "host_vars" / "vps.yml").read_text()
    )
    template_text = (_ROLE / "templates" / "livespec-incident-merge@.service.j2").read_text()
    facts = [
        all(
            line in unit.splitlines()
            for line in (
                "NoNewPrivileges=yes",
                "ProtectSystem=strict",
                "ProtectHome=read-only",
                "PrivateTmp=yes",
            )
        ),
        [line for line in unit.splitlines() if line.startswith("ReadWritePaths")]
        == ["ReadWritePaths=-/root/.config/op"],
        "Environment=OPENV_KEEP_PRIVILEGES=1" in unit.splitlines(),
        "--registry /declared/by/host_vars/installed_plugins.json" in unit,
        ".claude" not in template_text,
        defaults["incident_observer_merge_registry"] == "",
        host_vars["incident_observer_merge_registry"].endswith("/installed_plugins.json"),
        len(refusals) == 2,
        any("Look for the declared incident-merge plugin registry" in name for name in names),
        names.index("Look for the declared incident-merge plugin registry")
        < names.index("Install the incident-merge runner's templated oneshot unit"),
    ]
    assert all(facts)
