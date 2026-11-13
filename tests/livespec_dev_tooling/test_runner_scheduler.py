"""The `ci-runner-scheduler` second kube-scheduler (livespec-dev-tooling-mtvxde).

Runner pods request only one `ci-runner.io/churn-slot`, so under the default
scheduler's LeastAllocated scoring on cpu/memory requests they inherited each
node's NON-CI requests as their ranking: on 2026-11-04 gmktec-xubuntu got zero
runners while hp-xubuntu filled first. SPECIFICATION/non-functional-requirements.md
section "Runner-pool node rebuild recipe", paragraph **Runner placement follows
admission capacity** (v129) requires a scheduler profile the runner pods select by name,
committed in this tree and applied by the CI stack converge, with the default
profile unchanged.

These tests read the REAL manifest, values files and converge scripts, and RUN
the converge's `--dry-run`, because no cluster exists in the suite.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_DIR = _PHASE2 / "runner-scheduler"
_MANIFEST = _DIR / "runner-scheduler.yaml"
_CONVERGE = _DIR / "converge-runner-scheduler.sh"
_STACK = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_UNIT_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit" / "defaults" / "main.yml"
_ARC = _PHASE2 / "arc"
_SCHEDULER = "ci-runner-scheduler"
# Scale sets that name the runner scheduler. R301 (legacy-coordinator-agent,
# 2026-11-04) held it to one canary until the fail-open reconciler was live;
# that was proven 2026-11-09 (gate 20261109T083643Z-3789908 drill,
# livespec-dev-tooling-mtvxde), runtime followed 2026-11-11, and on 2026-11-13
# the coordinator widened it to EVERY scale set whose runner pods request a
# churn slot: with two schedulers binding churn-slot pods from separate caches,
# both bound into a node's last free slot and the kubelet refused the loser
# (OutOfci-runner.io/churn-slot). The template names it so a new repository's
# set joins the one scheduler. The host-unique sets (poweredge-xubuntu-k3s and
# arc/worker/) request no churn slot and stay on the default scheduler.
_RUNNER_SCHEDULER_SETS = {
    "values-EXAMPLE-repo.yaml",
    "values-fabro.yaml",
    "values-livespec-console-beads-fabro.yaml",
    "values-livespec-dev-tooling-arm64.yaml",
    "values-livespec-dev-tooling-master.yaml",
    "values-livespec-dev-tooling.yaml",
    "values-livespec-driver-claude.yaml",
    "values-livespec-driver-codex.yaml",
    "values-livespec-driver-pi.yaml",
    "values-livespec-orchestrator-beads-fabro.yaml",
    "values-livespec-orchestrator-git-jsonl.yaml",
    "values-livespec-orchestrator-master.yaml",
    "values-livespec-overseer.yaml",
    "values-livespec-runtime.yaml",
    "values-livespec.yaml",
}
_CHURN_SLOT = "ci-runner.io/churn-slot"


def _docs() -> list[dict]:
    return [d for d in yaml.safe_load_all(_MANIFEST.read_text(encoding="utf-8")) if d]


def _kind(kind: str) -> dict:
    found = [d for d in _docs() if d["kind"] == kind]
    assert len(found) == 1, f"expected exactly one {kind} in {_MANIFEST.name}, found {len(found)}"
    return found[0]


def _scheduler_config() -> dict:
    return yaml.safe_load(_kind("ConfigMap")["data"]["config.yaml"])


def test_the_runner_profile_scores_on_churn_slot_use_only() -> None:
    """LeastAllocated over the churn slot and nothing else is the clause's ranking."""
    profiles = _scheduler_config()["profiles"]
    assert [p["schedulerName"] for p in profiles] == [_SCHEDULER], (
        "the manifest must carry exactly one profile, the runner one; a second "
        "scheduler process that also served `default-scheduler` would race the "
        f"cluster's own; got {[p['schedulerName'] for p in profiles]}"
    )
    fit = [c for c in profiles[0]["pluginConfig"] if c["name"] == "NodeResourcesFit"]
    assert len(fit) == 1
    strategy = fit[0]["args"]["scoringStrategy"]
    assert strategy["type"] == "LeastAllocated"
    assert [r["name"] for r in strategy["resources"]] == ["ci-runner.io/churn-slot"], (
        "cpu or memory in the scoring resources would bring back the ranking by "
        f"other pods' requests; got {strategy['resources']}"
    )


def test_the_score_plugins_that_read_cpu_or_images_are_disabled() -> None:
    disabled = {
        d["name"] for d in _scheduler_config()["profiles"][0]["plugins"]["score"]["disabled"]
    }
    assert {"NodeResourcesBalancedAllocation", "ImageLocality"} <= disabled


def test_the_scheduler_keeps_its_own_leader_lease() -> None:
    election = _scheduler_config()["leaderElection"]
    assert election["leaderElect"] is True
    assert election["resourceName"] == _SCHEDULER, (
        "sharing the default `kube-scheduler` lease would make this process "
        "contend with the cluster's own scheduler for leadership"
    )


def test_the_image_is_pinned_by_digest_at_the_cluster_version() -> None:
    image = _kind("Deployment")["spec"]["template"]["spec"]["containers"][0]["image"]
    assert re.fullmatch(
        r"registry\.k8s\.io/kube-scheduler:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", image
    ), f"the scheduler image must be tag-and-digest pinned; got {image}"


def test_the_deployment_runs_two_replicas_on_the_runner_profile_config() -> None:
    spec = _kind("Deployment")["spec"]
    assert spec["replicas"] == 2
    pod = spec["template"]["spec"]
    assert pod["serviceAccountName"] == _SCHEDULER
    assert "--config=/etc/ci-runner-scheduler/config.yaml" in pod["containers"][0]["command"]
    assert "schedulerName" not in pod, "the scheduler itself is placed by the default scheduler"


def _template_spec(values: Path) -> dict:
    return (yaml.safe_load(values.read_text(encoding="utf-8")).get("template") or {}).get(
        "spec"
    ) or {}


def test_every_churn_slot_scale_set_names_the_runner_scheduler() -> None:
    """One scheduler binds every churn-slot runner pod, so no two caches race for a slot."""
    naming = {
        values.name
        for values in sorted(_ARC.glob("values-*.yaml"))
        if _template_spec(values).get("schedulerName") == _SCHEDULER
    }
    assert naming == _RUNNER_SCHEDULER_SETS, f"scale sets naming {_SCHEDULER}: {sorted(naming)}"


def test_a_set_names_the_runner_scheduler_exactly_when_its_runner_requests_a_churn_slot() -> None:
    for values in sorted([*_ARC.glob("values-*.yaml"), *(_ARC / "worker").glob("values-*.yaml")]):
        spec = _template_spec(values)
        runner = [c for c in spec.get("containers") or [] if c.get("name") == "runner"]
        requests = ((runner[0].get("resources") or {}).get("requests") or {}) if runner else {}
        assert (spec.get("schedulerName") == _SCHEDULER) == (
            _CHURN_SLOT in requests
        ), f"{values.name}: a churn-slot runner must name {_SCHEDULER}, and only such a runner"


def test_the_stack_converge_applies_the_scheduler_before_the_scale_sets() -> None:
    text = _STACK.read_text(encoding="utf-8")
    scheduler = text.index('"${RUNNER_SCHEDULER_DIR}/converge-runner-scheduler.sh"')
    scale_sets = text.index('log "7. Install/upgrade all')
    assert scheduler < scale_sets


def test_the_converge_unit_installs_the_scheduler_files() -> None:
    text = _UNIT_DEFAULTS.read_text(encoding="utf-8")
    for member in (
        "runner-scheduler/converge-runner-scheduler.sh",
        "runner-scheduler/runner-scheduler.yaml",
    ):
        assert f"src: {member}" in text, f"{member} is not installed beside converge-ci-stack.sh"
    assert re.search(r"^  - runner-scheduler$", text, re.MULTILINE)


def test_the_converge_dry_run_touches_nothing() -> None:
    out = subprocess.run(
        ["bash", str(_CONVERGE), "--dry-run"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    assert f"would run: kubectl apply -f {_MANIFEST}" in out
    assert "DRY RUN: nothing was applied." in out
