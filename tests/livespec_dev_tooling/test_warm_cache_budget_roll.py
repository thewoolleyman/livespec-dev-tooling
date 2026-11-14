"""The warm-cache converge rolls both warm uv DaemonSets on a budget change (livespec-dev-tooling-gry6tq).

Both DaemonSets read `warm-cache-budget` as configMapKeyRef env, fixed at pod
start, so the converge stamps the hash of the LIVE ConfigMap's `.data` onto
their pod templates. These tests drive the real converge against a stand-in
`kubectl` that records every call it receives.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_WARM_CACHE_DIR = _ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache"
_VALUES = _ROOT / "ci-runner" / "k3s" / "phase2" / "arc"
_DAEMONSETS = ("warm-uv-cache-populate", "warm-uv-cache-populate-hp")

_FAKE_KUBECTL = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${FAKE_KUBECTL_LOG}"
case "$*" in
  *"get configmap warm-cache-budget"*) cat "${FAKE_BUDGET_DATA}" ;;
  *"apply -f -"*) cat > /dev/null ;;
  *"--dry-run=client -o yaml"*) printf 'kind: ConfigMap\\n' ;;
esac
exit 0
"""


def _fake_bin(*, tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(_FAKE_KUBECTL)
    kubectl.chmod(0o755)
    return bin_dir


def _budget_data(*, files: str, nbytes: str) -> str:
    # kubectl renders a jsonpath map as compact JSON with sorted keys.
    data = {
        "actions-bytes": "500000000",
        "actions-files": "5000",
        "bytes": nbytes,
        "files": files,
    }
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def _converge(
    *, tmp_path: Path, script_dir: Path, budget_data: str, dry_run: bool
) -> tuple[str, list[str]]:
    run_dir = tmp_path / f"run-{len(list(tmp_path.glob('run-*')))}"
    run_dir.mkdir()
    log = run_dir / "kubectl.log"
    log.touch()
    data_file = run_dir / "budget.json"
    data_file.write_text(budget_data)
    env = {
        "PATH": f"{_fake_bin(tmp_path=run_dir)}:/usr/bin:/bin",
        "WARM_CACHE_VALUES_DIR": str(_VALUES),
        "FAKE_KUBECTL_LOG": str(log),
        "FAKE_BUDGET_DATA": str(data_file),
    }
    if not dry_run:
        env["KUBECONFIG"] = str(run_dir / "kubeconfig")
    argv = ["bash", str(script_dir / "converge-warm-cache.sh")]
    if dry_run:
        argv.append("--dry-run")
    completed = subprocess.run(argv, env=env, capture_output=True, text=True, check=True)
    return completed.stdout, log.read_text().splitlines()


def _budget_patches(*, calls: list[str]) -> dict[str, str]:
    patches: dict[str, str] = {}
    for call in calls:
        for daemonset in _DAEMONSETS:
            if f"patch daemonset {daemonset} " in call:
                payload = json.loads(call.split(" -p ", 1)[1])
                patches[daemonset] = payload["spec"]["template"]["metadata"]["annotations"][
                    "ci-runner.io/budget-hash"
                ]
    return patches


def test_a_converge_stamps_both_daemonsets_with_the_hash_of_the_live_budget_data(
    tmp_path: Path,
) -> None:
    budget_data = _budget_data(files="45000", nbytes="1350000000")
    _, calls = _converge(
        tmp_path=tmp_path, script_dir=_WARM_CACHE_DIR, budget_data=budget_data, dry_run=False
    )
    expected = hashlib.sha256(budget_data.encode()).hexdigest()[:16]
    assert _budget_patches(calls=calls) == {daemonset: expected for daemonset in _DAEMONSETS}


def test_a_changed_budget_changes_the_stamped_hash_so_both_daemonsets_roll(tmp_path: Path) -> None:
    _, old_calls = _converge(
        tmp_path=tmp_path,
        script_dir=_WARM_CACHE_DIR,
        budget_data=_budget_data(files="20000", nbytes="1000000000"),
        dry_run=False,
    )
    _, new_calls = _converge(
        tmp_path=tmp_path,
        script_dir=_WARM_CACHE_DIR,
        budget_data=_budget_data(files="45000", nbytes="1350000000"),
        dry_run=False,
    )
    old, new = _budget_patches(calls=old_calls), _budget_patches(calls=new_calls)
    assert set(old) == set(new) == set(_DAEMONSETS)
    for daemonset in _DAEMONSETS:
        assert old[daemonset] != new[daemonset]


def test_an_unchanged_budget_keeps_the_hash_after_a_comment_only_manifest_edit(
    tmp_path: Path,
) -> None:
    budget_data = _budget_data(files="45000", nbytes="1350000000")
    _, before = _converge(
        tmp_path=tmp_path, script_dir=_WARM_CACHE_DIR, budget_data=budget_data, dry_run=False
    )
    edited_dir = tmp_path / "warm-cache-edited"
    shutil.copytree(_WARM_CACHE_DIR, edited_dir)
    manifest = edited_dir / "warm-cache-cronjob.yaml"
    manifest.write_text(
        "# a comment-only edit\n" + manifest.read_text().replace('schedule: "', 'schedule:  "', 1)
    )
    _, after = _converge(
        tmp_path=tmp_path, script_dir=edited_dir, budget_data=budget_data, dry_run=False
    )
    assert _budget_patches(calls=before) == _budget_patches(calls=after)
    assert set(_budget_patches(calls=after)) == set(_DAEMONSETS)


def test_a_dry_run_prints_the_budget_hash_patch_for_both_daemonsets_and_reads_no_cluster(
    tmp_path: Path,
) -> None:
    stdout, calls = _converge(
        tmp_path=tmp_path,
        script_dir=_WARM_CACHE_DIR,
        budget_data=_budget_data(files="45000", nbytes="1350000000"),
        dry_run=True,
    )
    assert calls == []
    for daemonset in _DAEMONSETS:
        assert any(
            line.startswith("  would run: kubectl")
            and f"patch daemonset {daemonset} " in line
            and "ci-runner.io/budget-hash" in line
            for line in stdout.splitlines()
        )
