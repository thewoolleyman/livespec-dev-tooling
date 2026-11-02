"""The ci_local_path_provisioner role converges ONE manifest and proves the live setup script equals git.

livespec-dev-tooling-5j5x. The only other path that applies the local-path
provisioner manifest is the whole-stack boot converge, so a fix to the
provisioner's volume `setup` script merged on 2026-11-02 (eb5cb575) could not
reach the cluster without re-applying Kueue and ARC under live CI. These tests
read the role's own tasks, because Ansible is not importable in this suite.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_ROLE = _REPO / "ansible" / "roles" / "ci_local_path_provisioner"
_TASKS = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
_DEFAULTS = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
_PLAY = (_REPO / "ansible" / "ci-pool.yml").read_text(encoding="utf-8")


def _task(*, name_fragment: str) -> str:
    chunks = [f"- name: {chunk}" for chunk in _TASKS.split("\n- name: ")[1:]]
    matching = [chunk for chunk in chunks if name_fragment in chunk.splitlines()[0]]
    assert (
        len(matching) == 1
    ), f"exactly one task named like {name_fragment!r}; found {len(matching)}"
    return matching[0]


def test_the_role_applies_only_the_committed_local_path_provisioner_manifest() -> None:
    assert "ci-runner/k3s/phase2/local-path-provisioner/local-path-provisioner.yaml" in _DEFAULTS
    apply = _task(name_fragment="Apply the committed")
    assert 'argv: [kubectl, apply, -f, "-"]' in apply
    assert "ci_local_path_provisioner_manifest" in apply
    assert _TASKS.count("kubectl, apply") == 1, "the role must apply nothing but that manifest"


def test_the_diff_runs_under_check_and_reports_drift_as_a_change() -> None:
    diff = _task(name_fragment="Diff the committed")
    assert 'argv: [kubectl, diff, -f, "-"]' in diff
    assert "check_mode: false" in diff
    assert "changed_when: ci_local_path_provisioner_diff.rc == 1" in diff
    assert "failed_when: ci_local_path_provisioner_diff.rc > 1" in diff


def test_the_role_fails_unless_the_live_setup_script_sha256_equals_git() -> None:
    read = _task(name_fragment="Read the live provisioner setup")
    assert "local-path-config" in read
    assert "jsonpath={.data.setup}" in read
    verify = _task(name_fragment="Fail unless the live setup")
    assert "ansible.builtin.assert:" in verify
    assert "hash('sha256')" in verify
    assert "selectattr('kind', 'equalto', 'ConfigMap')" in verify


def test_the_play_runs_the_role_on_the_server_under_its_own_tag() -> None:
    block = _PLAY.split("- role: ci_local_path_provisioner", 1)[1].split("- role:", 1)[0]
    assert "tags: [ci_local_path_provisioner]" in block
    assert "when: cluster_role == 'server'" in block
