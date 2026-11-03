"""The ci_factory_quota role converges ONE ResourceQuota and proves its live spec.hard equals git.

Orchestrator plan bd-ib-nmuyjc, coordinator ruling (b) of 2026-11-03. The only
other path that applies the factory namespace manifest is the whole-stack boot
converge, so a change to the `factory-runs` quota could not reach the cluster
without re-applying Kueue and ARC under live CI. These tests read the role's
own tasks, because Ansible is not importable in this suite.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_ROLE = _REPO / "ansible" / "roles" / "ci_factory_quota"
_TASKS = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
_DEFAULTS = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
_PLAY = (_REPO / "ansible" / "ci-pool.yml").read_text(encoding="utf-8")
_MANIFEST = _REPO / "ci-runner" / "k3s" / "phase2" / "factory" / "factory-namespace.yaml"


def _task(*, name_fragment: str) -> str:
    chunks = [f"- name: {chunk}" for chunk in _TASKS.split("\n- name: ")[1:]]
    matching = [chunk for chunk in chunks if name_fragment in chunk.splitlines()[0]]
    assert (
        len(matching) == 1
    ), f"exactly one task named like {name_fragment!r}; found {len(matching)}"
    return matching[0]


def test_the_role_selects_only_the_resource_quota_from_the_committed_manifest() -> None:
    assert "ci-runner/k3s/phase2/factory/factory-namespace.yaml" in _DEFAULTS
    select = _task(name_fragment="Select the committed factory-runs")
    assert "from_yaml_all" in select
    assert "selectattr('kind', 'equalto', 'ResourceQuota')" in select
    guard = _task(name_fragment="Fail unless the manifest holds exactly one")
    assert "length == 1" in guard
    assert "'factory-runs'" in guard
    assert "'factory'" in guard


def test_the_committed_manifest_holds_exactly_one_resource_quota_factory_runs() -> None:
    documents = _MANIFEST.read_text(encoding="utf-8").split("\n---\n")
    quotas = [doc for doc in documents if "\nkind: ResourceQuota\n" in f"\n{doc}\n"]
    assert len(quotas) == 1, f"expected one ResourceQuota document; found {len(quotas)}"
    assert "name: factory-runs" in quotas[0]
    assert "namespace: factory" in quotas[0]


def test_the_role_applies_nothing_but_the_selected_quota() -> None:
    apply = _task(name_fragment="Apply the committed")
    assert 'argv: [kubectl, apply, -f, "-"]' in apply
    assert "ci_factory_quota_object[0] | to_json" in apply
    assert _TASKS.count("kubectl, apply") == 1, "the role must apply nothing but that quota"


def test_the_diff_runs_under_check_and_reports_drift_as_a_change() -> None:
    diff = _task(name_fragment="Diff the committed")
    assert 'argv: [kubectl, diff, -f, "-"]' in diff
    assert "check_mode: false" in diff
    assert "changed_when: ci_factory_quota_diff.rc == 1" in diff
    assert "failed_when: ci_factory_quota_diff.rc > 1" in diff


def test_the_role_fails_unless_the_live_spec_hard_equals_git() -> None:
    read = _task(name_fragment="Read the live factory-runs")
    assert "resourcequota" in read
    assert "jsonpath={.spec.hard}" in read
    verify = _task(name_fragment="Fail unless the live spec.hard")
    assert "ansible.builtin.assert:" in verify
    assert "from_json) == ci_factory_quota_object[0].spec.hard" in verify


def test_the_play_runs_the_role_on_the_server_under_its_own_tag() -> None:
    block = _PLAY.split("- role: ci_factory_quota", 1)[1].split("- role:", 1)[0]
    assert "tags: [ci_factory_quota]" in block
    assert "when: cluster_role == 'server'" in block
