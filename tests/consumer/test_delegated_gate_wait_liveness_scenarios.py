"""Consumer-tier: a delegated gate wait stays alive, and ends, whatever the cluster does.

Covers two scenarios in `SPECIFICATION/scenarios.md` that the delegated gate
client's terminal-state wait is bound to:

- a delegated gate Job that runs longer than the runner's stall window still ends
  with its own verdict, and
- a hung `kubectl` request on a delegated gate wait is timed out and the wait still
  ends.

The code under test is the REAL delegated gate client (`gate_remote_client.run_gate`
and the wait it owns) running its REAL `default_gate_command_runner`. The cluster is
a pair of executables on `PATH`: a `with-gates-kubeconfig` that only execs its
arguments, and a `kubectl` that plays a Job. The first scenario also runs the REAL
`dev-tooling/gate-run.sh`, so the runner's own stall bound is the thing that would
end the gate: a client that printed nothing and renewed nothing for the window would
come back `FAILED` (exit 124), which is what the first delivery of this wait did on
a Job that ran past 15 minutes.

Two bounds are shortened, and only those two, so the test costs seconds instead of
fifteen minutes. The stall window is shortened through its own documented setting,
`LIVESPEC_SUITE_GREEN_STALL_SECONDS`; the Job outlives it. The hung-request test's
outer 270 s `timeout` is replaced by a `timeout` shim that records the bound the
client asked for and runs the real `timeout` with a shorter one; the test asserts the
recorded bound is the production one and is inside the production stall window.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from returns.result import Failure

from livespec_dev_tooling.gate_credential import GATES_KUBECONFIG_ENV, GATES_WRAPPER
from livespec_dev_tooling.gate_remote_client import run_gate
from livespec_dev_tooling.gate_remote_request import GateRunRequest
from livespec_dev_tooling.install_worktree_pack import WORKTREE_PACK_FILES

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_PROJECT_ROOT = Path(__file__).parents[2]
_RUNNER = Path("dev-tooling") / "gate-run.sh"
_PRODUCTION_STALL_WINDOW_SECONDS = 900
_PRODUCTION_OUTER_BOUND = "270s"

_JOB = "gate-widget-7f2qd"
_CREATED = '{"apiVersion":"batch/v1","kind":"Job","metadata":{"name":"' + _JOB + '"}}'
_RUNNING = '{"spec":{"suspend":false},"status":{"startTime":"2026-11-14T00:00:00Z"}}'
_COMPLETE = (
    '{"spec":{"suspend":false},"status":{"startTime":"2026-11-14T00:00:00Z",'
    '"conditions":[{"type":"Complete","status":"True"}]}}'
)

# One `kubectl` that plays a gate Job. Every call is logged. What it does on a read
# is chosen by the environment: `STUB_JOB_SECONDS` is how long after `create` the
# Job takes to Complete; `STUB_HANG` names the read that never returns.
_KUBECTL_STUB = f"""#!/bin/sh
state="$STUB_STATE"
printf '%s\\n' "$*" >> "$state/kubectl.log"
case " $* " in
  *" create "*)
    cat >/dev/null
    date +%s > "$state/created-at"
    printf '%s\\n' '{_CREATED}'
    ;;
  *" --watch "*)
    if test "${{STUB_HANG:-}}" = watch; then exec sleep 3600; fi
    printf '%s\\n' '{_RUNNING}'
    created=$(cat "$state/created-at")
    remaining=$((created + STUB_JOB_SECONDS - $(date +%s)))
    if test "$remaining" -gt 0; then sleep "$remaining"; fi
    stamp_mtime=$(stat -c %Y "$LIVESPEC_GATE_RUN_PROGRESS_STAMP")
    echo $(( $(date +%s) - stamp_mtime )) > "$state/stamp-age-at-complete"
    printf '%s\\n' '{_COMPLETE}'
    ;;
  *" get job "*)
    if test "${{STUB_HANG:-}}" = admission; then
      sleep 31
      stamp_mtime=$(stat -c %Y "$LIVESPEC_GATE_RUN_PROGRESS_STAMP")
      echo $(( $(date +%s) - stamp_mtime )) > "$state/stamp-age-during-hang"
      exec sleep 3600
    fi
    printf '%s\\n' '{_RUNNING}'
    ;;
  *" logs "*) printf '%s\\n' 'gate output' ;;
esac
"""

_WRAPPER_STUB = '#!/bin/sh\nexec "$@"\n'

# Records the bound the client asked for, then runs the real `timeout` with the
# shorter bound the test chose, so a request that never returns still ends.
_TIMEOUT_SHIM = """#!/bin/sh
printf '%s\\n' "$1" >> "$STUB_STATE/timeout-bounds.log"
bound=$1
shift
if test "$bound" = "{production}"; then bound="$SHORT_OUTER_BOUND"; fi
exec "{real_timeout}" "$bound" "$@"
"""

_DRIVER = """
import sys
from pathlib import Path

import livespec_dev_tooling

sys.path.insert(0, str(Path(livespec_dev_tooling.__file__).parent / "_vendor"))

from returns.result import Failure

from livespec_dev_tooling.gate_remote_client import run_gate
from livespec_dev_tooling.gate_remote_request import GateRunRequest

outcome = run_gate(
    request=GateRunRequest(
        repo_root=Path.cwd(),
        mirror_url=sys.argv[1],
        manifest="kind: Job\\n",
        gate_ref="refs/gates/liveness-1",
    )
)
if isinstance(outcome, Failure):
    sys.stderr.write(outcome.failure().detail + "\\n")
    raise SystemExit(75)
raise SystemExit(0 if outcome.unwrap().terminal_state == "Complete" else 1)
"""


def _install_cluster(*, tmp_path: Path, real_timeout: str | None = None) -> tuple[Path, Path]:
    """Put the stub cluster on a `PATH` directory; return it and the state directory."""
    stub_bin = tmp_path / "stub-bin"
    state = tmp_path / "stub-state"
    _ = stub_bin.mkdir()
    _ = state.mkdir()
    stubs = {GATES_WRAPPER: _WRAPPER_STUB, "kubectl": _KUBECTL_STUB}
    if real_timeout is not None:
        stubs["timeout"] = _TIMEOUT_SHIM.format(
            production=_PRODUCTION_OUTER_BOUND, real_timeout=real_timeout
        )
    for name, body in stubs.items():
        _ = (stub_bin / name).write_text(body, encoding="utf-8")
        _ = (stub_bin / name).chmod(0o755)
    return stub_bin, state


def _git(*, args: list[str], cwd: Path) -> None:
    done = subprocess.run(
        ["git", *args], cwd=str(cwd), check=False, capture_output=True, text=True, env=os.environ
    )
    assert done.returncode == 0, done.stderr


def _gated_repository(*, tmp_path: Path) -> tuple[Path, Path]:
    """A committed repository with an `origin/master` ref and an empty bare mirror."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(args=["init", "--quiet", "--initial-branch=master"], cwd=root)
    _git(args=["config", "user.name", "Test User"], cwd=root)
    _git(args=["config", "user.email", "test@example.com"], cwd=root)
    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_gate = true\n", encoding="utf-8"
    )
    pack_dir = root / _RUNNER.parent
    _ = pack_dir.mkdir()
    for pack_file in WORKTREE_PACK_FILES:
        installed = pack_dir / pack_file.name
        _ = installed.write_text(pack_file.body, encoding="utf-8")
        _ = installed.chmod(0o755 if pack_file.executable else 0o644)
    _git(args=["add", "--all"], cwd=root)
    _git(args=["commit", "--quiet", "-m", "base"], cwd=root)
    _git(args=["update-ref", "refs/remotes/origin/master", "HEAD"], cwd=root)
    mirror = tmp_path / "mirror.git"
    _git(args=["init", "--quiet", "--bare", str(mirror)], cwd=tmp_path)
    return root, mirror


def _wait_for_verdict(*, run_dir: Path, seconds: float) -> str:
    exit_code = run_dir / "exit_code"
    deadline = time.monotonic() + seconds
    while not exit_code.is_file():
        assert time.monotonic() < deadline, f"no verdict in {run_dir} within {seconds} s"
        time.sleep(0.25)
    return exit_code.read_text(encoding="utf-8").strip()


def test_a_job_that_outlives_the_stall_window_still_ends_with_its_own_verdict(
    *, tmp_path: Path
) -> None:
    """Scenario: a delegated gate Job that runs longer than the stall window ends with its verdict.

    `gate-run.sh start` runs the real gate client over a Job that Completes 45 s
    after submit, with the stall window shortened to 35 s. The client prints nothing
    while it waits, so only its progress stamp keeps the runner from ending the gate
    at 35 s with the stall-bound `FAILED` (exit 124). The run must instead record the
    Job's own verdict, a PASS; the stamp must have been renewed within the heartbeat
    period when the Job completed; and the whole wait must have used one admission
    read and one watch rather than a `kubectl` per poll interval.
    """
    root, mirror = _gated_repository(tmp_path=tmp_path)
    stub_bin, state = _install_cluster(tmp_path=tmp_path)
    fake_bin = tmp_path / "fake-bin"
    _ = fake_bin.mkdir()
    _ = (fake_bin / "uv").write_text('#!/bin/sh\nshift 3\nexec python3 "$@"\n', encoding="utf-8")
    _ = (fake_bin / "uv").chmod(0o755)
    driver = tmp_path / "driver.py"
    _ = driver.write_text(_DRIVER, encoding="utf-8")
    credential = tmp_path / "gates.kubeconfig"
    _ = credential.write_text("kind: Config\napiVersion: v1\n", encoding="utf-8")
    environment = dict(os.environ)
    environment.update(
        {
            "PATH": os.pathsep.join([str(fake_bin), str(stub_bin), environment["PATH"]]),
            "PYTHONPATH": os.pathsep.join(
                [str(_PROJECT_ROOT), *filter(None, [environment.get("PYTHONPATH")])]
            ),
            GATES_KUBECONFIG_ENV: str(credential),
            "LIVESPEC_SUITE_GREEN_STALL_SECONDS": "35",
            "STUB_STATE": str(state),
            "STUB_JOB_SECONDS": "45",
        }
    )

    launched = subprocess.run(
        ["bash", str(root / _RUNNER), "start", "--", sys.executable, str(driver), str(mirror)],
        cwd=str(root),
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert launched.returncode == 0, launched.stderr
    run_dir = root / "tmp" / "gate-runs" / launched.stdout.strip()
    code = _wait_for_verdict(run_dir=run_dir, seconds=120.0)

    output = (run_dir / "output.log").read_text(encoding="utf-8")
    assert code == "0", f"exit_code {code!r}; output.log:\n{output}"
    assert "the stall window" not in output
    assert int((state / "stamp-age-at-complete").read_text(encoding="utf-8")) < 30
    reads = [
        line
        for line in (state / "kubectl.log").read_text(encoding="utf-8").splitlines()
        if " get job " in f" {line} "
    ]
    assert sum(" --watch " in f" {line} " for line in reads) == 1
    assert len(reads) == 2


def test_a_hung_admission_read_is_timed_out_before_the_stall_window_and_the_stamp_stays_fresh(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: a hung kubectl request on the admission wait is timed out and the wait ends.

    The client's `kubectl get job` never returns. The client asks for its 270 s
    bound, which is inside the 900 s stall window; the shim runs it as 36 s, so the
    request ends there. While it hung, the progress stamp (aged by the test) was
    renewed by the heartbeat, and the wait ended in a no-verdict failure naming the
    timed-out call rather than hanging.
    """
    real_timeout = shutil.which("timeout")
    assert real_timeout is not None
    stub_bin, state = _install_cluster(tmp_path=tmp_path, real_timeout=real_timeout)
    root, mirror = _gated_repository(tmp_path=tmp_path)
    stamp = tmp_path / "progress.stamp"
    stamp.touch()
    aged = time.time() - 1000
    os.utime(stamp, (aged, aged))
    credential = tmp_path / "gates.kubeconfig"
    _ = credential.write_text("kind: Config\napiVersion: v1\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(credential))
    monkeypatch.setenv("LIVESPEC_GATE_RUN_PROGRESS_STAMP", str(stamp))
    monkeypatch.setenv("STUB_STATE", str(state))
    monkeypatch.setenv("STUB_HANG", "admission")
    monkeypatch.setenv("SHORT_OUTER_BOUND", "36s")
    request = GateRunRequest(
        repo_root=root,
        mirror_url=str(mirror),
        manifest="kind: Job\n",
        gate_ref="refs/gates/hung-admission-1",
        poll_interval_seconds=1.0,
        admission_timeout_seconds=1.0,
    )

    started = time.monotonic()
    outcome = run_gate(request=request)
    elapsed = time.monotonic() - started

    assert isinstance(outcome, Failure)
    assert "kubectl admission-state read timed out" in outcome.failure().detail
    assert elapsed < 80.0
    bounds = (state / "timeout-bounds.log").read_text(encoding="utf-8").split()
    assert bounds[0] == _PRODUCTION_OUTER_BOUND
    assert int(_PRODUCTION_OUTER_BOUND.removesuffix("s")) < _PRODUCTION_STALL_WINDOW_SECONDS
    assert int((state / "stamp-age-during-hang").read_text(encoding="utf-8")) < 10


def test_a_hung_terminal_watch_is_timed_out_and_the_wait_ends_naming_the_timed_out_call(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: a hung kubectl request on the terminal-state wait is timed out and the wait ends.

    The Job is admitted, then every terminal-state watch hangs. The shim runs the
    client's 270 s bound as 2 s, so each watch is ended and re-armed without a sleep
    until the 5 s poll budget is spent; the wait then ends in a no-verdict failure
    that names the timed-out watch, and the client deletes the abandoned Job.
    """
    real_timeout = shutil.which("timeout")
    assert real_timeout is not None
    stub_bin, state = _install_cluster(tmp_path=tmp_path, real_timeout=real_timeout)
    root, mirror = _gated_repository(tmp_path=tmp_path)
    credential = tmp_path / "gates.kubeconfig"
    _ = credential.write_text("kind: Config\napiVersion: v1\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(credential))
    monkeypatch.setenv("LIVESPEC_GATE_RUN_PROGRESS_STAMP", str(tmp_path / "progress.stamp"))
    monkeypatch.setenv("STUB_STATE", str(state))
    monkeypatch.setenv("STUB_HANG", "watch")
    monkeypatch.setenv("SHORT_OUTER_BOUND", "2s")
    request = GateRunRequest(
        repo_root=root,
        mirror_url=str(mirror),
        manifest="kind: Job\n",
        gate_ref="refs/gates/hung-watch-1",
        poll_interval_seconds=1.0,
        poll_timeout_seconds=5.0,
    )

    started = time.monotonic()
    outcome = run_gate(request=request)
    elapsed = time.monotonic() - started

    assert isinstance(outcome, Failure)
    assert "kubectl terminal-state watch timed out" in outcome.failure().detail
    assert elapsed < 30.0
    log = (state / "kubectl.log").read_text(encoding="utf-8").splitlines()
    assert sum(" --watch " in f" {line} " for line in log) >= 2
    assert any(line.endswith(f"delete job {_JOB}") for line in log)
