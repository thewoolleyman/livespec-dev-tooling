"""The root runner reads the ledger only from a root-owned tree, for `bd` and for the authority.

Work-item livespec-dev-tooling-o6u7jm, repair of the second independent re-review. Both of the
runner's ledger paths take their destination from a working directory: `bd` from its
`.beads` pointer, and the canonical authority (`--repo`) from its `.livespec.jsonc` connection
block and the same pointer. Neither may resolve a host, a port or an executable from a tree the
observer or candidate account can write, so the runner now takes `--ledger-root`, a root-owned
tree the role installs, refuses by name unless every file `bd` and the authority read from it is
protected, and runs the authority with that tree as `--repo` and as its working directory.
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

__all__: list[str] = []

# This module concerns work item livespec-dev-tooling-o6u7jm, an ordinary pull request.

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
_FILES = (".beads/config.yaml", ".beads/metadata.json", ".livespec.jsonc")
_APP_TOKEN = "app-installation-token"


def _world(monkeypatch: pytest.MonkeyPatch) -> Mock:
    merge = Mock(return_value=_MERGED)
    config = SimpleNamespace(
        incident_merge_integration_id=4242, recovery_bypass_integration_id=1717
    )
    monkeypatch.setattr(runner, "load_config", Mock(return_value=config))
    monkeypatch.setattr(runner, "read_arm_identity", Mock(return_value=_IDENTITY))
    monkeypatch.setattr(runner, "merge_incident_repair", merge)
    monkeypatch.setattr(
        runner, "load_merge_credential", Mock(return_value=SimpleNamespace(app_id="4242"))
    )
    return merge


def _ledger_root(*, tmp_path: Path, file_mode: int = 0o644) -> Path:
    root = tmp_path / "ledger"
    (root / ".beads").mkdir(parents=True, mode=0o755)
    root.chmod(0o755)
    (root / ".beads").chmod(0o755)
    for name in _FILES:
        target = root / name
        _ = target.write_text("{}\n")
        target.chmod(file_mode)
    return root


def _script(*, tmp_path: Path) -> Path:
    directory = tmp_path / "reader"
    directory.mkdir(mode=0o755, exist_ok=True)
    directory.chmod(0o755)
    script = directory / "incident_authority.py"
    _ = script.write_text("# authority\n")
    script.chmod(0o644)
    return script


def _go(*, tmp_path: Path, ledger_root: Path | None) -> int:
    argv = [
        "--pr",
        "7",
        "--credential",
        str(tmp_path / "credential.json"),
        "--project-root",
        str(tmp_path / "reference"),
        "--authority-script",
        str(_script(tmp_path=tmp_path)),
    ]
    if ledger_root is not None:
        argv += ["--ledger-root", str(ledger_root)]
    return runner.run(
        argv=argv,
        owner_uid=0,
        interpreter=Path("/usr/bin/env"),
        connect=Mock(return_value=SimpleNamespace(token=_APP_TOKEN)),
        run_text_command=Mock(return_value=(0, "")),
        make_reader=Mock(),
    )


def test_the_authority_runs_with_the_ledger_root_as_its_repo_and_working_directory(
    monkeypatch, tmp_path
):
    merge = _world(monkeypatch)
    authority = Mock(return_value="answer")
    monkeypatch.setattr(bindings, "call_authority", authority)
    ledger = _ledger_root(tmp_path=tmp_path)
    status = _go(tmp_path=tmp_path, ledger_root=ledger)
    _ = merge.call_args.kwargs["chain"](incident_id="inc-1")
    call = authority.call_args.kwargs
    facts = [
        status == 0,
        call["cwd"] == ledger,
        call["flags"]["repo"] == str(ledger),
        str(tmp_path / "reference") not in {str(call["cwd"]), call["flags"]["repo"]},
    ]
    assert all(facts)


def test_a_missing_ledger_root_is_refused_by_name_before_any_merge(monkeypatch, tmp_path, capsys):
    merge = _world(monkeypatch)
    absent = _go(tmp_path=tmp_path, ledger_root=None)
    out_absent = capsys.readouterr().out
    gone = _go(tmp_path=tmp_path, ledger_root=tmp_path / "nowhere")
    out_gone = capsys.readouterr().out
    facts = [
        (absent, gone) == (2, 2),
        "incident-merge-runner-no-ledger-root" in out_absent,
        "incident-merge-runner-no-ledger-root" in out_gone,
        merge.call_count == 0,
    ]
    assert all(facts)


@pytest.mark.parametrize("name", _FILES)
def test_a_ledger_root_file_writable_by_group_or_other_is_refused_naming_it(
    monkeypatch, tmp_path, capsys, name
):
    merge = _world(monkeypatch)
    ledger = _ledger_root(tmp_path=tmp_path)
    (ledger / name).chmod(0o664)
    status = _go(tmp_path=tmp_path, ledger_root=ledger)
    out = capsys.readouterr().out
    facts = [
        status == 2,
        "incident-merge-runner-ledger-root-unprotected" in out,
        str(ledger / name) in out,
        merge.call_count == 0,
    ]
    assert all(facts)


# --- the unit and the role --------------------------------------------------------------


def _unit() -> list[str]:
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
        incident_observer_merge_authority_script="/declared/reader/incident_authority.py",
        incident_observer_merge_workdir="/declared/merge-workdir",
    ).splitlines()


def test_the_unit_passes_the_ledger_root_and_pins_the_beads_binary():
    lines = _unit()
    execs = [line for line in lines if line.startswith("ExecStart=")]
    facts = [
        len(execs) == 1,
        "--ledger-root /declared/merge-workdir" in execs[0],
        "Environment=LIVESPEC_BD_PATH=/usr/local/bin/bd" in lines,
        "WorkingDirectory=/declared/merge-workdir" in lines,
    ]
    assert all(facts)


def _task(*, name: str) -> dict:
    tasks = yaml.safe_load((_ROLE / "tasks" / "converge.yml").read_text())
    named = [task for task in tasks if task.get("name") == name]
    return named[0] if named else {}


def test_the_role_installs_the_connection_block_and_a_rooted_pointer_beside_the_config():
    block = _task(name="Install the incident-merge runner's root-owned connection block")
    pointer = _task(name="Write the incident-merge runner's root-owned ledger pointer")
    directories = _task(name="Create the incident-merge runner's root-owned working directory")
    block_copy = block.get("ansible.builtin.copy", {})
    pointer_copy = pointer.get("ansible.builtin.copy", {})
    facts = [
        str(block_copy.get("dest", "")).endswith("/.livespec.jsonc"),
        "role_path" in str(block_copy.get("src", "")),
        str(block_copy.get("src", "")).endswith("/.livespec.jsonc"),
        (block_copy.get("owner"), block_copy.get("mode")) == ("root", "0644"),
        str(pointer_copy.get("dest", "")).endswith("/.beads/metadata.json"),
        (pointer_copy.get("owner"), pointer_copy.get("mode")) == ("root", "0644"),
        "incident_observer_tenant_project_id" in str(pointer_copy.get("content", "")),
        "| int" in str(pointer_copy.get("content", "")),
        "incident_observer_merge_workdir" in str(pointer_copy.get("dest", "")),
        directories.get("ansible.builtin.file", {}).get("owner") == "root",
    ]
    assert all(facts)
