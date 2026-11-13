"""Exercise the runtime manifest and its actual preflight payload without a cluster."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import runpy
import subprocess
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
import yaml
from jinja2.nativetypes import NativeEnvironment

from livespec_dev_tooling import mutation_kill_matrix_pytest_plugin as plugin
from livespec_dev_tooling.mutation_kill_matrix_cache import engine_source_digest

__all__: list[str] = []

pytestmark = pytest.mark.consumer
_ROOT = Path(__file__).resolve().parents[2]
_RENDERER = _ROOT / "ci-runner/k3s/phase2/rule26/render-runtime-job.sh"
_ARGS = [
    "--target-sha",
    "a" * 40,
    "--engine-sha",
    "b" * 40,
    "--workers",
    "2",
    "--run",
    "fixture",
    "--node",
    "fixture-node",
    "--memory",
    "1Gi",
    "--storage",
    "2Gi",
]


def _render(*, args: list[str]) -> list[dict[str, object]]:
    rendered = subprocess.run([str(_RENDERER), *args], check=True, capture_output=True, text=True)
    return cast("list[dict[str, object]]", list(yaml.safe_load_all(rendered.stdout)))


def _at(value: object, *keys: str) -> object:
    for key in keys:
        value = cast("dict[str, object]", value)[key]
    return value


def _script() -> str:
    job = _render(args=_ARGS)[2]
    containers = cast("list[dict[str, object]]", _at(job, "spec", "template", "spec", "containers"))
    return cast("list[str]", containers[0]["args"])[0]


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--target-sha", "abc"),
        ("--engine-sha", "z" * 40),
        ("--workers", "0"),
        ("--workers", "-1"),
        ("--run", "-"),
        ("--run", "../escape"),
        ("--node", "bad&node"),
        ("--memory", "1Gi\nkind: Job"),
        ("--storage", ""),
    ],
)
def test_invalid_inputs_produce_no_manifest(*, flag: str, value: str) -> None:
    args = _ARGS.copy()
    args[args.index(flag) + 1] = value
    refused = subprocess.run([str(_RENDERER), *args], check=False, capture_output=True, text=True)
    assert refused.returncode == 2
    assert refused.stdout == ""


@pytest.mark.parametrize("args", [[], ["--workers"], ["--unknown", "value"]])
def test_missing_or_unknown_inputs_are_refused(*, args: list[str]) -> None:
    refused = subprocess.run([str(_RENDERER), *args], check=False, capture_output=True, text=True)
    assert refused.returncode == 2
    assert refused.stdout == ""


def test_manifest_binds_resources_and_retained_storage_to_this_runtime_run() -> None:
    namespace, pvc, job = _render(args=_ARGS)
    assert _at(namespace, "metadata", "name") == "rule26-runtime"
    assert _at(pvc, "metadata", "namespace") == "rule26-runtime"
    assert _at(pvc, "spec", "resources", "requests", "storage") == "2Gi"
    assert _at(job, "metadata", "name") == "rule26-runtime-kill-matrix-fixture"
    assert _at(job, "spec", "activeDeadlineSeconds") == 86400
    assert _at(job, "spec", "template", "spec", "nodeSelector") == {
        "kubernetes.io/hostname": "fixture-node"
    }
    containers = cast("list[dict[str, object]]", _at(job, "spec", "template", "spec", "containers"))
    assert containers[0]["resources"] == {
        "requests": {"cpu": "2", "memory": "1Gi"},
        "limits": {"cpu": "2", "memory": "1Gi"},
    }
    assert _at(job, "spec", "template", "spec", "volumes") == [
        {"name": "data", "persistentVolumeClaim": {"claimName": "rule26-runtime"}}
    ]
    script = _script()
    checked = subprocess.run(
        ["bash", "-n"], input=script, check=False, capture_output=True, text=True
    )
    assert checked.returncode == 0, checked.stderr
    for code in re.findall(r"<<'PY'\n(.*?)\nPY", script, re.DOTALL):
        _ = compile(code, "runtime-job-payload", "exec")


def test_runtime_adapter_passes_its_inputs_through_the_shared_apply_role() -> None:
    role = _ROOT / "ansible/roles/rule26_kill_matrix"
    context = cast("dict[str, object]", yaml.safe_load((role / "defaults/main.yml").read_text()))
    context.update(
        {
            "rule26_runtime_sha": "a" * 40,
            "rule26_kill_matrix_engine_sha": "b" * 40,
            "rule26_runtime_workers": 2,
            "rule26_kill_matrix_run": "fixture",
            "rule26_runtime_memory": "1Gi",
            "rule26_runtime_storage": "2Gi",
            "inventory_hostname": "fixture-node",
            "playbook_dir": str(_ROOT / "ansible"),
        }
    )
    play = cast(
        "list[dict[str, object]]",
        yaml.safe_load((_ROOT / "ansible/rule26-runtime-kill-matrix.yml").read_text()),
    )[0]
    environment = NativeEnvironment()
    for key, value in cast("dict[str, object]", play["vars"]).items():
        if isinstance(value, list):
            context[key] = [
                environment.from_string(str(arg)).render(context)
                for arg in cast("list[object]", value)
            ]
        else:
            context[key] = environment.from_string(str(value)).render(context)
    tasks = cast("list[dict[str, object]]", yaml.safe_load((role / "tasks/main.yml").read_text()))
    launch = cast("list[dict[str, object]]", tasks[1]["block"])
    argv_template = cast("str", _at(launch[1], "ansible.builtin.command", "argv"))
    argv = cast("list[str]", environment.from_string(argv_template).render(context))
    completed = subprocess.run(argv, check=True, capture_output=True, text=True)
    job = cast("list[dict[str, object]]", list(yaml.safe_load_all(completed.stdout)))[2]
    assert _at(job, "metadata", "name") == "rule26-runtime-kill-matrix-fixture"
    assert context["rule26_kill_matrix_job_prefix"] == "rule26-runtime-kill-matrix"
    assert context["rule26_kill_matrix_pvc_name"] == "rule26-runtime"


@pytest.mark.parametrize(
    ("commit", "tag", "marker", "target", "error"),
    [
        ("c" * 40, "v1.208.0", "KILL_MATRIX_COLLECTED", "a" * 40, "consumer engine pin differs"),
        ("b" * 40, "v1.207.0", "KILL_MATRIX_COLLECTED", "a" * 40, "matching release tag"),
        ("b" * 40, "v1.208.0", "wrong", "a" * 40, "inventory repair"),
        ("b" * 40, "v1.208.0", "KILL_MATRIX_COLLECTED", "c" * 40, "checked-out commit"),
        ("b" * 40, "v1.208.0", "KILL_MATRIX_COLLECTED", "a" * 40, None),
    ],
)
def test_actual_preflight_payload_refuses_unbound_engine_or_target_before_recording_inputs(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    commit: str,
    tag: str,
    marker: str,
    target: str,
    error: str | None,
) -> None:
    code = re.findall(r"<<'PY'\n(.*?)\nPY", _script(), re.DOTALL)[1]
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / "uv.lock").write_text("fixture-lock\n")
    monkeypatch.setenv("RULE26_OUT", str(tmp_path))
    monkeypatch.setenv("RULE26_ENGINE_SHA", "b" * 40)
    monkeypatch.setenv("RULE26_TARGET_SHA", "a" * 40)
    monkeypatch.setattr(plugin, "COLLECTED_VARIABLE", marker, raising=False)
    distribution = Mock(version="1.208.0")
    distribution.read_text.return_value = json.dumps({"vcs_info": {"commit_id": commit}})
    monkeypatch.setattr(importlib.metadata, "distribution", Mock(return_value=distribution))

    def git(
        args: list[str], *, check: bool, capture_output: bool, text: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check and capture_output and text
        output = tag + "\n" if "tag" in args else target + "\n"
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(subprocess, "run", git)
    payload = tmp_path / "preflight.py"
    _ = payload.write_text(code)
    inputs = tmp_path / "inputs.json"
    if error is not None:
        with pytest.raises(SystemExit, match=error):
            _ = runpy.run_path(str(payload))
        assert not inputs.exists()
    else:
        _ = runpy.run_path(str(payload))
        recorded = json.loads(inputs.read_text())
        assert recorded["engine_commit"] == "b" * 40
        assert recorded["target_revision"] == "a" * 40
        assert recorded["executing_source_identity"] == engine_source_digest()
        assert recorded["lock_sha256"] == hashlib.sha256(b"fixture-lock\n").hexdigest()
