"""POST /bind authenticates its merged run as the recovery App and never spawns gh."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from livespec_dev_tooling._incident_observer_types import ObserverArm
from livespec_dev_tooling.incident_observer_admission import arm_before_merge
from livespec_dev_tooling.incident_observer_control import ObserverControl
from livespec_dev_tooling.incident_recovery_app import RecoveryForge

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-x3wwwc
_REPOSITORY = "owner/repo"
_MERGE = "a" * 40
_PEM = "-----BEGIN RSA PRIVATE KEY----- QUJD -----END RSA PRIVATE KEY-----"
_RUN = {
    "id": 91,
    "event": "push",
    "head_branch": "master",
    "head_sha": _MERGE,
    "path": ".github/workflows/ci.yml",
    "repository": {"full_name": _REPOSITORY},
    "head_repository": {"full_name": _REPOSITORY},
}
_PULL = {
    "number": 55,
    "merged": True,
    "state": "closed",
    "merge_commit_sha": _MERGE,
    "head": {"sha": "c" * 40},
    "base": {"ref": "master", "repo": {"full_name": _REPOSITORY}},
}


def _arm() -> ObserverArm:
    return ObserverArm(
        repository=_REPOSITORY,
        incident_item_id="incident-1",
        attempt_id="repair-1",
        operation_id="operation-1",
        generation=1,
        owner="owner",
        phase="repair",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("coverage",),
        controller_release="v1.0.0",
        controller_revision="b" * 40,
        authority_receipt=b"receipt",
    )


def _installation(*, root: Path) -> Any:
    return cast(
        "Any",
        SimpleNamespace(
            repository=_REPOSITORY,
            state=root / "state",
            config=root / "controller.json",
            target_branch="master",
        ),
    )


def test_bind_mints_a_read_token_from_the_protected_credential_and_spawns_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "state").mkdir(mode=0o700)
    credential = tmp_path / "recovery-app.json"
    credential.write_text(json.dumps({"app_id": "1", "private_key": _PEM}))
    credential.chmod(0o600)
    armed = arm_before_merge(
        directory=tmp_path / "state",
        arm=_arm(),
        expected_arm_id=None,
        authorize_current=Mock(return_value=True),
        released_controller=Mock(return_value=True),
    )
    forge = Mock(repository=_REPOSITORY)
    forge.request.side_effect = [(200, _PULL), (200, _RUN)]
    connect = Mock(return_value=forge)
    spawn = Mock(return_value=subprocess.CompletedProcess([], 1, "", "not authenticated"))
    monkeypatch.setattr(RecoveryForge, "connect", connect)
    monkeypatch.setattr(subprocess, "run", spawn)
    reply = ObserverControl(installation=_installation(root=tmp_path)).execute(
        path="/bind",
        payload={"repository": _REPOSITORY, "head_sha": _MERGE, "run_id": 91},
    )
    facts = (
        armed.status == "armed",
        reply["status"] == "admitted",
        spawn.call_count == 0,
        [call.kwargs.get("access") for call in connect.call_args_list] == ["read"],
        [call.kwargs["path"] for call in forge.request.call_args_list]
        == ["pulls/55", "actions/runs/91"],
    )
    assert all(facts), (reply, facts)
