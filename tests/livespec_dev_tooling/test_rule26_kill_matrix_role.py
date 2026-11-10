"""The rule26_kill_matrix role launches the committed kill-matrix Job, or removes its namespace.

Plan fleet-mutation-testing-rule-26 (livespec-dev-tooling-fqnbtd). A hand
`kubectl apply` on a fleet host is refused by the fleet host guard, so the
launch is this role, run from the control node over committed source. These
tests read the role's own files, because Ansible is not importable in this
suite.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_ROLE = _REPO / "ansible" / "roles" / "rule26_kill_matrix"
_TASKS = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
_DEFAULTS = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
_PLAY = (_REPO / "ansible" / "rule26-kill-matrix.yml").read_text(encoding="utf-8")
_RENDERER = _REPO / "ci-runner" / "k3s" / "phase2" / "rule26" / "render-kill-matrix-job.sh"


def _task(*, name_fragment: str) -> str:
    chunks = [chunk for chunk in _TASKS.split("- name: ")[1:]]
    matching = [chunk for chunk in chunks if name_fragment in chunk.splitlines()[0]]
    assert (
        len(matching) == 1
    ), f"exactly one task named like {name_fragment!r}; found {len(matching)}"
    return matching[0]


def test_the_role_renders_with_the_committed_renderer_on_the_control_node() -> None:
    assert "ci-runner/k3s/phase2/rule26/render-kill-matrix-job.sh" in _DEFAULTS
    render = _task(name_fragment="Render the committed Job manifest")
    assert "rule26_kill_matrix_renderer" in render
    assert "delegate_to: localhost" in render
    assert "check_mode: false" in render
    for flag in ("--orchestrator-sha", "--engine-sha", "--workers", "--run"):
        assert flag in render


def test_the_run_inputs_are_validated_before_anything_renders() -> None:
    guard = _task(name_fragment="Fail unless the run's inputs")
    assert "rule26_kill_matrix_orchestrator_sha is match('^[0-9a-f]{40}$')" in guard
    assert "rule26_kill_matrix_engine_sha is match('^[0-9a-f]{40}$')" in guard
    assert _TASKS.index("Fail unless the run's inputs") < _TASKS.index("Render the committed")


def test_the_diff_runs_under_check_and_the_apply_follows_only_drift() -> None:
    diff = _task(name_fragment="Diff the rendered")
    assert 'argv: [kubectl, diff, -f, "-"]' in diff
    assert "check_mode: false" in diff
    assert "changed_when: rule26_kill_matrix_diff.rc == 1" in diff
    assert "failed_when: rule26_kill_matrix_diff.rc > 1" in diff
    apply = _task(name_fragment="Apply the rendered")
    assert 'argv: [kubectl, apply, -f, "-"]' in apply
    assert "rule26_kill_matrix_manifest.stdout" in apply
    assert "when: rule26_kill_matrix_diff.rc == 1" in apply
    assert _TASKS.count("kubectl, apply") == 1


def test_the_role_fails_unless_the_live_job_is_the_rendered_one() -> None:
    read = _task(name_fragment="Read the live kill-matrix Job")
    assert "rule26-orchestrator-kill-matrix-{{ rule26_kill_matrix_run }}" in read
    verify = _task(name_fragment="Fail unless the live Job")
    assert "ansible.builtin.assert:" in verify


def test_absent_deletes_the_namespace_and_present_never_does() -> None:
    assert "rule26_kill_matrix_state: present" in _DEFAULTS
    delete = _task(name_fragment="Delete the kill-matrix namespace")
    assert "kubectl, delete, namespace" in delete
    assert _TASKS.count("kubectl, delete") == 1
    removal = _TASKS.split("- name: Remove the kill-matrix namespace", 1)[1]
    assert "when: rule26_kill_matrix_state == 'absent'" in removal.splitlines()[1]


def test_the_play_runs_the_role_only_on_the_k3s_server() -> None:
    assert "hosts: ci_pool" in _PLAY
    assert "- role: rule26_kill_matrix" in _PLAY
    assert "when: cluster_role == 'server'" in _PLAY


def test_the_renderer_refuses_a_short_commit() -> None:
    refused = subprocess.run(
        [str(_RENDERER), "--orchestrator-sha", "abc", "--engine-sha", "0" * 40],
        capture_output=True,
        check=False,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert refused.returncode == 2
    assert "--orchestrator-sha must be a full 40-hex commit" in refused.stderr
