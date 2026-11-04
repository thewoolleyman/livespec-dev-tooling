"""Hook-template ConfigMap revisions outlive the runner pods that mount them.

livespec-dev-tooling-4oeffe: a ConfigMap volume refreshes inside RUNNING pods,
so when a converge removed `git-seed-hook.js` from the one mutable
`arc-hook-pod-template` ConfigMap, runner pods started before it still named
the vanished file and their teardown failed with "Executing the custom
container implementation failed". The converge now publishes each revision of
the hook files as an immutable, content-addressed ConfigMap, every scale set's
values mount the revision it just published, and an older revision is deleted
only when no pod in arc-runners mounts it.

These tests RUN the real converge against a stub `kubectl` on PATH, because no
cluster exists in the suite.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_ARC = _PHASE2 / "arc"
_CONVERGE = _ARC / "converge-hook-pod-template.sh"
_STACK = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_WARM_INSTALL = _PHASE2 / "warm-cache" / "install-warm-cache.sh"
_PLACEHOLDER = "arc-hook-pod-template-@HOOK_REVISION@"
_KEYS = ("hook-pod-template.yaml", "action-archive-entry.sh")

# The stub answers each kubectl read from a file the test writes, logs every
# call, and captures what `create -f -` was handed. A `get pods` exits 1 when
# the scenario says the pod listing fails.
_STUB = r"""#!/usr/bin/env bash
set -u
d="$STUB_DIR"
printf '%s\n' "$*" >> "$d/calls"
case "$*" in
  *"create configmap"*"--dry-run=client"*)
    name="$3"
    printf 'apiVersion: v1\ndata:\n  hook-pod-template.yaml: x\nkind: ConfigMap\nmetadata:\n  creationTimestamp: null\n  name: %s\n  namespace: arc-runners\n' "$name"
    ;;
  "create -f -") cat > "$d/created" ;;
  *"get configmap -l"*) cat "$d/revisions" ;;
  *"get configmap "*) grep -qxF "$5" "$d/existing" ;;
  *"get pods"*) [ ! -e "$d/pods-fail" ] || exit 1; cat "$d/pods" ;;
  *"get autoscalingrunnersets"*) cat "$d/sets" ;;
  *"delete configmap"*) : ;;
esac
"""


def _stub(tmp_path: Path, *, existing: str = "", revisions: str = "", pods: str = "") -> Path:
    stub_dir = tmp_path / "stub"
    bin_dir = stub_dir / "bin"
    bin_dir.mkdir(parents=True)
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(_STUB, encoding="utf-8")
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IXUSR)
    (stub_dir / "calls").write_text("", encoding="utf-8")
    (stub_dir / "existing").write_text(existing, encoding="utf-8")
    (stub_dir / "revisions").write_text(revisions, encoding="utf-8")
    (stub_dir / "pods").write_text(pods, encoding="utf-8")
    (stub_dir / "sets").write_text('{"items": []}', encoding="utf-8")
    return stub_dir


def _run(stub_dir: Path, *args: str, script: Path = _CONVERGE) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{stub_dir / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "KUBECONFIG": str(stub_dir / "kubeconfig"),
        "STUB_DIR": str(stub_dir),
    }
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=60,
    )


def _revision(arc_dir: Path = _ARC) -> str:
    digest = hashlib.sha256()
    for key in _KEYS:
        digest.update(key.encode() + b"\0" + (arc_dir / key).read_bytes() + b"\0")
    return f"arc-hook-pod-template-{digest.hexdigest()[:12]}"


def test_the_revision_name_carries_the_content_hash_of_every_hook_file(tmp_path: Path) -> None:
    out = _run(_stub(tmp_path), "--name")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == _revision()

    copy = tmp_path / "arc"
    copy.mkdir()
    for name in (_CONVERGE.name, *_KEYS):
        shutil.copy2(_ARC / name, copy / name)
    with (copy / "action-archive-entry.sh").open("a", encoding="utf-8") as entry:
        entry.write("# a changed entry point\n")
    changed = _run(_stub(tmp_path / "second"), "--name", script=copy / _CONVERGE.name)
    assert changed.stdout.strip() == _revision(copy)
    assert (
        changed.stdout.strip() != out.stdout.strip()
    ), "a changed hook file must be a new revision"


def test_publish_creates_the_revision_immutable_labelled_and_with_every_key(tmp_path: Path) -> None:
    stub_dir = _stub(tmp_path)
    out = _run(stub_dir, "--publish")
    assert out.returncode == 0, out.stderr
    created = (stub_dir / "created").read_text(encoding="utf-8")
    assert f"  name: {_revision()}\n" in created
    assert "\nimmutable: true\n" in created
    assert "  labels:\n    ci-runner.io/hook-template: revision\n" in created
    calls = (stub_dir / "calls").read_text(encoding="utf-8")
    for key in _KEYS:
        assert f"--from-file={key}={_ARC / key}" in calls, key
    assert "published" in out.stdout and _revision() in out.stdout


def test_publish_leaves_an_already_published_revision_untouched(tmp_path: Path) -> None:
    stub_dir = _stub(tmp_path, existing=f"{_revision()}\n")
    out = _run(stub_dir, "--publish")
    assert out.returncode == 0, out.stderr
    assert not (stub_dir / "created").exists()
    assert "already published" in out.stdout


def test_every_scale_set_values_file_renders_to_the_published_revision(tmp_path: Path) -> None:
    stub_dir = _stub(tmp_path)
    values_files = sorted(_ARC.glob("values-*.yaml"))
    assert len(values_files) == 13
    for values in values_files:
        text = values.read_text(encoding="utf-8")
        assert f"name: {_PLACEHOLDER}\n" in text, values.name
        assert "name: arc-hook-pod-template\n" not in text, values.name
        rendered = tmp_path / values.name
        out = _run(stub_dir, "--render-values", str(values), str(rendered))
        assert out.returncode == 0, out.stderr
        body = rendered.read_text(encoding="utf-8")
        assert f"name: {_revision()}\n" in body and "@HOOK_REVISION@" not in body, values.name


def test_render_refuses_values_that_do_not_mount_the_revision(tmp_path: Path) -> None:
    stray = tmp_path / "values-stray.yaml"
    stray.write_text("configMap:\n  name: arc-hook-pod-template\n", encoding="utf-8")
    out = _run(_stub(tmp_path), "--render-values", str(stray), str(tmp_path / "out.yaml"))
    assert out.returncode == 1
    assert _PLACEHOLDER in out.stderr


def test_the_stack_converge_publishes_renders_upgrades_then_prunes() -> None:
    text = _STACK.read_text(encoding="utf-8")
    publish = text.index('"${ARC_DIR}/converge-hook-pod-template.sh" --publish')
    render = text.index('"${ARC_DIR}/converge-hook-pod-template.sh" --render-values')
    helm = text.index('-f "$rendered_values"')
    prune = text.index('"${ARC_DIR}/converge-hook-pod-template.sh" --prune')
    assert publish < render < helm < prune
    assert '-f "$values_file" \\\n' not in text, "an unrendered values file must never reach helm"
    warm = _WARM_INSTALL.read_text(encoding="utf-8")
    assert '"${SCRIPT_DIR}/../arc/converge-hook-pod-template.sh" --publish' in warm


def test_prune_keeps_a_revision_a_live_pod_mounts_and_deletes_an_unmounted_one(
    tmp_path: Path,
) -> None:
    current = _revision()
    stub_dir = _stub(
        tmp_path,
        revisions=f"{current}\narc-hook-pod-template-aaaaaaaaaaaa\narc-hook-pod-template-bbbbbbbbbbbb\n",
        pods=(
            "runner-1 arc-hook-pod-template-aaaaaaaaaaaa\n"
            "runner-2 arc-hook-pod-template-aaaaaaaaaaaa\n"
            f"runner-3 {current}\n"
            "workflow-9 some-other-configmap\n"
        ),
    )
    out = _run(stub_dir, "--prune")
    assert out.returncode == 0, out.stderr
    assert (
        "kept arc-hook-pod-template-aaaaaaaaaaaa: still mounted by live pod(s) runner-1,runner-2"
        in out.stdout
    )
    assert f"kept {current}: the revision this converge published" in out.stdout
    assert (
        "deleted arc-hook-pod-template-bbbbbbbbbbbb: no pod in arc-runners mounts it" in out.stdout
    )
    calls = (stub_dir / "calls").read_text(encoding="utf-8").splitlines()
    deletes = [call for call in calls if "delete configmap" in call]
    assert deletes == ["-n arc-runners delete configmap arc-hook-pod-template-bbbbbbbbbbbb"]


def test_prune_keeps_a_revision_a_runner_set_template_still_names(tmp_path: Path) -> None:
    stub_dir = _stub(tmp_path, revisions="arc-hook-pod-template-cccccccccccc\n")
    (stub_dir / "sets").write_text(
        '{"items": [{"spec": {"template": {"spec": {"volumes": '
        '[{"configMap": {"name": "arc-hook-pod-template-cccccccccccc"}}]}}}}]}',
        encoding="utf-8",
    )
    out = _run(stub_dir, "--prune")
    assert out.returncode == 0, out.stderr
    assert "kept arc-hook-pod-template-cccccccccccc: still named by a runner set" in out.stdout
    assert "delete configmap" not in (stub_dir / "calls").read_text(encoding="utf-8")


def test_prune_deletes_nothing_when_the_pod_listing_fails(tmp_path: Path) -> None:
    stub_dir = _stub(tmp_path, revisions="arc-hook-pod-template-dddddddddddd\n")
    (stub_dir / "pods-fail").write_text("", encoding="utf-8")
    out = _run(stub_dir, "--prune")
    assert out.returncode == 0, out.stderr
    assert "pruning nothing" in out.stdout
    assert "delete configmap" not in (stub_dir / "calls").read_text(encoding="utf-8")


def test_the_dry_run_names_the_revision_and_touches_nothing(tmp_path: Path) -> None:
    stub_dir = _stub(tmp_path)
    out = _run(stub_dir, "--dry-run")
    assert out.returncode == 0, out.stderr
    assert f"kubectl create configmap {_revision()}" in out.stdout
    assert (stub_dir / "calls").read_text(encoding="utf-8") == ""
