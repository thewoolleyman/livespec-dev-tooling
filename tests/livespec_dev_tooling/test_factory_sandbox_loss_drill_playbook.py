"""Integration coverage for the committed factory-sandbox-loss drill.

The test runs the real playbook through pinned ansible-core.  Its kubectl
stand-in is deliberately stateful: reads select a pod only when the run label
matches exactly, and a delete either makes that UID disappear or replaces the
same name with a new UID.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_PLAYBOOK = _ROOT / "ansible" / "factory-sandbox-loss-drill.yml"
_SERVER = "sandbox-drill-server"
_RUN = "Run_42.a"
_POD = "petri-run_42.a-l7"
_UID = "uid-before"
_UTC = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
_REPORT = re.compile(
    rf"Factory sandbox loss drill run (?P<run>\S+) pod (?P<pod>\S+) UID (?P<uid>\S+) "
    rf"delete issued (?P<issued>{_UTC}) UID gone (?P<gone>{_UTC})"
)

_KUBECTL = r"""#!/bin/sh
printf 'kubectl %s\n' "$*" >> "$DRILL_LOG"
pod='{"metadata":{"name":"'"$_POD"'","uid":"uid-before","labels":{"petri.run":"'"$_RUN"'","sandbox-driver-kubernetes/sandbox":"true"}}}'
case "$*" in
  *'get pods '*'--selector petri.run='*)
    case "$DRILL_MODE" in
      empty) printf '{"items":[]}' ;;
      multiple) printf '{"items":[%s,%s]}' "$pod" "$pod" ;;
      unlabelled) printf '{"items":[{"metadata":{"name":"%s","uid":"uid-before","labels":{"petri.run":"%s"}}}]}' "$_POD" "$_RUN" ;;
      *) printf '{"items":[%s]}' "$pod" ;;
    esac ;;
  *'delete pod '*)
    test "$DRILL_MODE" != delete_refused || { printf 'current UID uid-current\n' >&2; exit 1; }
    touch "$DRILL_STATE/deleted" ;;
  *'get pod '*)
    test -f "$DRILL_STATE/deleted" || { printf '%s' "$pod"; exit 0; }
    case "$DRILL_MODE" in
      stuck) printf '%s' "$pod" ;;
      replacement) printf '{"metadata":{"name":"%s","uid":"uid-after","labels":{"petri.run":"%s","sandbox-driver-kubernetes/sandbox":"true"}}}' "$_POD" "$_RUN" ;;
      *) printf 'NotFound\n' >&2; exit 1 ;;
    esac ;;
  *) printf 'unexpected kubectl invocation: %s\n' "$*" >&2; exit 1 ;;
esac
"""


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    root: Path
    bin_dir: Path
    state: Path
    log: Path
    origin: Path

    @property
    def commands(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []


def _git(*, cwd: Path, args: str) -> None:
    _ = subprocess.run(args.split(), cwd=cwd, check=True, capture_output=True, text=True)


def _origin(*, root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    _git(cwd=source, args="git init --initial-branch main")
    _git(cwd=source, args="git config user.email drill@example.test")
    _git(cwd=source, args="git config user.name Drill")
    _ = (source / "tracked").write_text("base\n", encoding="utf-8")
    _git(cwd=source, args="git add tracked")
    _git(cwd=source, args="git commit -m base")
    origin = root / "origin.git"
    _git(cwd=root, args=f"git clone --bare {source} {origin}")
    _git(cwd=source, args=f"git remote add origin {origin}")
    _ = (source / "tracked").write_text("preserved\n", encoding="utf-8")
    _git(cwd=source, args="git commit -am preserved")
    _git(cwd=source, args="git push origin HEAD:refs/heads/preserved")
    return origin


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    _ = kubectl.write_text(_KUBECTL, encoding="utf-8")
    kubectl.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    return _Scratch(
        root=tmp_path,
        bin_dir=bin_dir,
        state=state,
        log=tmp_path / "log",
        origin=_origin(root=tmp_path),
    )


def _inventory(*, scratch: _Scratch) -> Path:
    path = scratch.root / "inventory.yml"
    _ = path.write_text(
        "all:\n  children:\n    ci_pool:\n      hosts:\n"
        f"        {_SERVER}:\n          ansible_connection: local\n          cluster_role: server\n",
        encoding="utf-8",
    )
    return path


def _run(
    *,
    scratch: _Scratch,
    confirm: str | None = _SERVER,
    run_id: str | None = _RUN,
    namespace: str = "factory",
    preserved_ref: str | None = "refs/heads/preserved",
    mode: str = "gone",
) -> tuple[int, str]:
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} must exist"
    env = {key: value for key, value in os.environ.items() if not key.startswith("COV_CORE_")}
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "DRILL_LOG": str(scratch.log),
            "DRILL_STATE": str(scratch.state),
            "DRILL_MODE": mode,
            "_POD": _POD,
            "_RUN": _RUN,
        }
    )
    variables = [
        "factory_sandbox_loss_drill_wait_interval=0",
        "factory_sandbox_loss_drill_wait_retries=2",
        f"factory_sandbox_loss_drill_namespace={namespace}",
        f"factory_sandbox_loss_drill_run_repository={scratch.origin}",
        "factory_sandbox_loss_drill_default_branch=main",
    ]
    if confirm is not None:
        variables.append(f"factory_sandbox_loss_drill_confirm={confirm}")
    if run_id is not None:
        variables.append(f"factory_sandbox_loss_drill_run_id={run_id}")
    if preserved_ref is not None:
        variables.append(f"factory_sandbox_loss_drill_preserved_ref={preserved_ref}")
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            "ansible-core==2.18.9",
            "ansible-playbook",
            "-i",
            str(_inventory(scratch=scratch)),
            *[argument for variable in variables for argument in ("-e", variable)],
            str(_PLAYBOOK),
        ],
        cwd=scratch.root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    return completed.returncode, completed.stdout + completed.stderr


@pytest.mark.parametrize(("confirm", "run_id"), [(None, _RUN), ("other", _RUN), (_SERVER, None)])
def test_unconsented_or_unnamed_runs_do_not_read_or_change(
    *, scratch: _Scratch, confirm: str | None, run_id: str | None
) -> None:
    code, output = _run(scratch=scratch, confirm=confirm, run_id=run_id)
    assert code == 0, output
    assert scratch.commands == [], output


@pytest.mark.parametrize(("run_id", "namespace"), [("bad/value", "factory"), (_RUN, "not-factory")])
def test_invalid_target_is_refused_before_kubectl(
    *, scratch: _Scratch, run_id: str, namespace: str
) -> None:
    code, output = _run(scratch=scratch, run_id=run_id, namespace=namespace)
    assert code != 0, output
    assert scratch.commands == [], output


@pytest.mark.parametrize("mode", ["empty", "multiple", "unlabelled"])
def test_ambiguous_or_non_sandbox_selection_never_writes(*, scratch: _Scratch, mode: str) -> None:
    code, output = _run(scratch=scratch, mode=mode)
    assert code != 0, output
    assert [line for line in scratch.commands if " delete " in line] == [], output


def test_preservation_refusals_happen_before_a_cluster_write(*, scratch: _Scratch) -> None:
    for ref in (None, "refs/heads/missing", "refs/heads/main"):
        code, output = _run(scratch=scratch, preserved_ref=ref)
        assert code != 0, output
        assert [line for line in scratch.commands if " delete " in line] == [], output


def test_deletes_exactly_one_uid_and_reports_the_api_observed_times(*, scratch: _Scratch) -> None:
    code, output = _run(scratch=scratch)
    assert code == 0, output
    report = _REPORT.search(output)
    assert report is not None, output
    assert report["run"] == _RUN and report["pod"] == _POD and report["uid"] == _UID
    deletes = [line for line in scratch.commands if "delete pod" in line]
    assert len(deletes) == 1 and "--precondition=uid=uid-before" in deletes[0], scratch.commands


def test_replacement_ends_the_wait_without_deleting_the_new_uid(*, scratch: _Scratch) -> None:
    code, output = _run(scratch=scratch, mode="replacement")
    assert code == 0, output
    assert "uid-after" in output
    assert len([line for line in scratch.commands if "delete pod" in line]) == 1


def test_still_listed_uid_times_out_without_a_second_delete(*, scratch: _Scratch) -> None:
    code, output = _run(scratch=scratch, mode="stuck")
    assert code != 0, output
    assert len([line for line in scratch.commands if "delete pod" in line]) == 1


def test_uid_precondition_refusal_names_resolved_and_api_reported_uids(
    *, scratch: _Scratch
) -> None:
    code, output = _run(scratch=scratch, mode="delete_refused")
    assert code != 0, output
    assert "resolved UID uid-before" in output
    assert "API reports UID uid-current" in output
    assert len([line for line in scratch.commands if "delete pod" in line]) == 1
