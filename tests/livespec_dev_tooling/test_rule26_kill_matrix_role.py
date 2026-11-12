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
    for flag in ("--orchestrator-sha", "--engine-sha", "--workers", "--run", "--node"):
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
    assert "or rule26_kill_matrix_diff.rc == 1" in apply
    assert _TASKS.count("kubectl, apply") == 1


def test_a_first_run_with_no_namespace_skips_the_diff_and_applies() -> None:
    """kubectl diff of namespaced objects fails while their namespace is absent."""
    found = _task(name_fragment="Find whether the kill-matrix namespace exists yet")
    assert "--ignore-not-found" in found
    assert "check_mode: false" in found
    assert "changed_when: false" in found
    first = _task(name_fragment="Report a first launch")
    assert "when: rule26_kill_matrix_namespace_found.stdout | length == 0" in first
    assert "changed_when: true" in first
    diff = _task(name_fragment="Diff the rendered")
    assert "when: rule26_kill_matrix_namespace_found.stdout | length > 0" in diff
    apply = _task(name_fragment="Apply the rendered")
    assert "rule26_kill_matrix_namespace_found.stdout | length == 0" in apply
    order = [
        _TASKS.index(name)
        for name in (
            "Find whether the kill-matrix namespace",
            "Diff the rendered",
            "Apply the rendered",
        )
    ]
    assert order == sorted(order)


def test_the_role_fails_unless_the_live_job_is_the_rendered_one() -> None:
    read = _task(name_fragment="Read the live kill-matrix Job")
    assert "rule26-orchestrator-kill-matrix-{{ rule26_kill_matrix_run }}" in read
    verify = _task(name_fragment="Fail unless the live Job")
    assert "ansible.builtin.assert:" in verify


def test_absent_deletes_the_namespace_and_present_never_does() -> None:
    assert "rule26_kill_matrix_state: present" in _DEFAULTS
    delete = _task(name_fragment="Delete the kill-matrix namespace")
    assert "kubectl, delete, namespace" in delete
    assert _TASKS.count("kubectl, delete, namespace") == 1
    removal = _TASKS.split("- name: Remove the kill-matrix namespace", 1)[1]
    assert "when: rule26_kill_matrix_state == 'absent'" in removal.splitlines()[1]


def test_job_absent_deletes_only_the_named_job_and_keeps_the_pvc() -> None:
    """Stopping a stuck run must not delete the PVC holding its mutants/ tree and logs."""
    assert "job-absent" in _DEFAULTS
    block = _TASKS.split("- name: Remove one kill-matrix Job and keep its namespace and PVC", 1)[1]
    assert "when: rule26_kill_matrix_state == 'job-absent'" in block.splitlines()[1]
    delete = _task(name_fragment="Delete the run's kill-matrix Job")
    assert "- namespace\n" not in delete
    assert "- delete\n" in delete
    assert '- "rule26-orchestrator-kill-matrix-{{ rule26_kill_matrix_run }}"' in delete
    assert "--cascade=foreground" in delete
    guard = _task(name_fragment="Fail unless a run id names the Job to remove")
    assert "rule26_kill_matrix_run is match('^[a-z0-9-]{1,40}$')" in guard
    before = _task(name_fragment="List the namespace's PVCs before the delete")
    assert "pvc" in before
    assert _TASKS.index("List the namespace's PVCs before") < _TASKS.index(
        "Delete the run's kill-matrix Job"
    )
    verify = _task(name_fragment="Fail unless the Job is gone and every PVC is kept")
    assert (
        "rule26_kill_matrix_pvcs_after.stdout_lines == rule26_kill_matrix_pvcs_before.stdout_lines"
        in verify
    )
    assert "job-absent" in _PLAY


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


def test_the_rendered_job_trusts_the_mise_config_of_both_clones() -> None:
    """The image's `uv` resolves through mise, which refuses an untrusted clone's config.

    The first launch, run 20261110t1, failed 22 s in with `Config files in
    /data/orchestrator/.mise.toml are not trusted`.
    """
    rendered = subprocess.run(
        [str(_RENDERER), "--orchestrator-sha", "a" * 40, "--engine-sha", "b" * 40, "--run", "t1"],
        capture_output=True,
        check=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    ).stdout
    job = rendered.split("kind: Job", 1)[1]
    env = job.split("env:", 1)[1].split("resources:", 1)[0]
    assert "- name: MISE_TRUSTED_CONFIG_PATHS\n" in env
    trusted = env.split("- name: MISE_TRUSTED_CONFIG_PATHS\n", 1)[1].splitlines()[0]
    assert trusted.strip() == "value: /data/orchestrator:/data/dev-tooling"
    assert (
        "git clone --quiet https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro /data/orchestrator"
        in job
    )
    assert "/data/dev-tooling" in job


def test_the_rendered_job_puts_the_engine_clone_on_pythonpath() -> None:
    """A re-sync of the target's venv to its lock must not swap the engine out mid-run."""
    rendered = subprocess.run(
        [str(_RENDERER), "--orchestrator-sha", "a" * 40, "--engine-sha", "b" * 40, "--run", "t3"],
        capture_output=True,
        check=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    ).stdout
    env = rendered.split("kind: Job", 1)[1].split("env:", 1)[1].split("resources:", 1)[0]
    assert "- name: PYTHONPATH\n" in env
    value = env.split("- name: PYTHONPATH\n", 1)[1].splitlines()[0]
    assert value.strip() == "value: /data/dev-tooling"


def _render(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_RENDERER), "--orchestrator-sha", "a" * 40, "--engine-sha", "b" * 40, *extra],
        capture_output=True,
        check=False,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )


def test_the_rendered_job_runs_on_the_named_node_with_that_nodes_own_pvc() -> None:
    """A local-path PV is bound to one node, so each node gets its own claim."""
    rendered = _render("--run", "t4", "--node", "hp-xubuntu")
    assert rendered.returncode == 0, rendered.stderr
    pvc = rendered.stdout.split("kind: PersistentVolumeClaim", 1)[1].split("---", 1)[0]
    assert "name: rule26-orchestrator-hp-xubuntu\n" in pvc
    job = rendered.stdout.split("kind: Job", 1)[1]
    assert "kubernetes.io/hostname: hp-xubuntu\n" in job
    assert "claimName: rule26-orchestrator-hp-xubuntu\n" in job
    assert "poweredge-xubuntu" not in job


def test_the_renderer_defaults_to_poweredge_and_refuses_a_bad_node_name() -> None:
    default = _render("--run", "t5")
    assert "kubernetes.io/hostname: poweredge-xubuntu\n" in default.stdout
    refused = _render("--node", "Bad/Node")
    assert refused.returncode == 2
    assert "--node must be a lowercase node name" in refused.stderr


def test_the_role_passes_a_validated_node_to_the_renderer() -> None:
    assert 'rule26_kill_matrix_node: ""' in _DEFAULTS
    guard = _task(name_fragment="Fail unless the run's inputs")
    assert "rule26_kill_matrix_node is match('^[a-z0-9]([a-z0-9.-]{0,61}[a-z0-9])?$')" in guard
    render = _task(name_fragment="Render the committed Job manifest")
    assert '- "{{ rule26_kill_matrix_node }}"' in render
