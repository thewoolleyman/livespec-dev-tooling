"""Consumer-tier coverage for the declared and replay gate-Job resource scenarios."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from returns.result import Success

from livespec_dev_tooling._gate_remote_assembly import declared_gate_job_resources
from livespec_dev_tooling.gate_remote_delegate import gate_remote_request, run_delegated_gate
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_verdict import GATE_FAILED, GATE_NO_VERDICT, GateVerdict

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RENDERER = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"
_QUEUE = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "kueue" / "cluster-queue-gates.yaml"
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_ORIGIN = "git@github.com:acme/widget.git"
_CPU_PARALLELISM_HEADING = (
    "## Scenario: a repository that declares gate_cpu 9 and gate_parallelism 8 gets a gate Job "
    "requesting 9 CPUs whose coverage run uses 8 xdist workers"
)
_DEFAULTS_HEADING = (
    "## Scenario: a repository that declares no gate resources keeps the default gate Job size"
)
_NON_POSITIVE_HEADING = (
    "## Scenario: a non-positive declared gate resource is refused before any gate Job is submitted"
)
_MALFORMED_HEADING = "## Scenario: a malformed declared gate resource refuses a delegated commit instead of gating it locally"
_REPLAY_SIZE_HEADING = "## Scenario: a Red-leg replay Job requests the small replay size whatever the repository declares"
_REPLAY_OOM_HEADING = (
    "## Scenario: a Red-leg replay Job killed for memory is an absent verdict, not a valid Red"
)


class _World:
    """Canned host commands with the real renderer as the consumer-visible seam."""

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (stdin, stream)
        if argv[0] == str(_RENDERER):
            completed = subprocess.run(
                argv, cwd=str(cwd), capture_output=True, text=True, check=False
            )
            return Success(
                GateCommandResult(
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )
        stdout = (
            f"{_TREE}\n" if "rev-parse" in argv else f"{_ORIGIN}\n" if "get-url" in argv else ""
        )
        return Success(GateCommandResult(returncode=0, stdout=stdout, stderr=""))


def _consumer(*, tmp_path: Path, declaration: str) -> Path:
    """Create a fixture consumer whose own configuration the client reads."""
    root = tmp_path / "widget"
    root.mkdir()
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(
        "jobs:\n  test:\n    runs-on: self-hosted\n    container:\n"
        "      image: ghcr.io/example/sandbox:python-v1.11.1\n",
        encoding="utf-8",
    )
    _ = (root / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n" + declaration,
        encoding="utf-8",
    )
    fixture_renderer = root / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"
    fixture_queue = root / "ci-runner" / "k3s" / "phase2" / "kueue" / "cluster-queue-gates.yaml"
    fixture_renderer.parent.mkdir(parents=True)
    fixture_queue.parent.mkdir(parents=True)
    _ = fixture_renderer.write_text(_RENDERER.read_text(encoding="utf-8"), encoding="utf-8")
    _ = fixture_queue.write_text(_QUEUE.read_text(encoding="utf-8"), encoding="utf-8")
    return root


def _gate_job(*, root: Path) -> dict[object, object]:
    """Render one fixture consumer through the shipped client's request seam."""
    built = gate_remote_request(repo_root=root, renderer=_RENDERER, runner=_World())
    assert isinstance(built, Success)
    return next(document for document in yaml.safe_load_all(built.unwrap().manifest) if document)


def _registered_test(*, heading: str) -> str:
    """Read the scenario registry exactly as its coverage checker does."""
    rows = json.loads((_REPO_ROOT / "tests" / "heading-coverage.json").read_text(encoding="utf-8"))
    return next(row["test"] for row in rows if row["heading"] == heading)


def test_declared_cpu_and_parallelism_render_into_the_gate_job_and_coverage_worker_count(
    *, tmp_path: Path
) -> None:
    """A consumer's declared resources reach its rendered Job and coverage command."""
    root = _consumer(
        tmp_path=tmp_path,
        declaration="delegated_gate = true\ngate_cpu = 9\ngate_parallelism = 8\n",
    )
    job = _gate_job(root=root)
    gate = next(
        container
        for container in job["spec"]["template"]["spec"]["containers"]
        if container["name"] == "gate"
    )
    env = {entry["name"]: entry["value"] for entry in gate["env"] if "value" in entry}

    assert gate["resources"] == {
        "requests": {"cpu": "9", "memory": "6Gi"},
        "limits": {"memory": "6Gi"},
    }
    assert env["LIVESPEC_TEST_PARALLELISM"] == "8"
    assert 'pytest -n "${test_nprocs}"' in (
        _REPO_ROOT / "scripts" / "just" / "check-per-file-coverage.sh"
    ).read_text(encoding="utf-8")
    assert _registered_test(heading=_CPU_PARALLELISM_HEADING) == (
        "tests.consumer.test_gate_job_resource_scenarios."
        "test_declared_cpu_and_parallelism_render_into_the_gate_job_and_coverage_worker_count"
    )


def test_undeclared_resources_render_the_default_gate_job_size(*, tmp_path: Path) -> None:
    """An opted-in consumer with no resource keys leaves all renderer defaults intact."""
    job = _gate_job(root=_consumer(tmp_path=tmp_path, declaration="delegated_gate = true\n"))
    gate = next(
        container
        for container in job["spec"]["template"]["spec"]["containers"]
        if container["name"] == "gate"
    )
    env = {entry["name"]: entry["value"] for entry in gate["env"] if "value" in entry}

    assert gate["resources"] == {
        "requests": {"cpu": "5", "memory": "6Gi"},
        "limits": {"memory": "6Gi"},
    }
    assert env["LIVESPEC_TEST_PARALLELISM"] == "4"
    assert _registered_test(heading=_DEFAULTS_HEADING).endswith(
        ".test_undeclared_resources_render_the_default_gate_job_size"
    )


def test_non_positive_cpu_refuses_before_the_consumer_submits_a_gate_job(*, tmp_path: Path) -> None:
    """A zero CPU declaration is a refusal, not a rendered or submitted Job."""
    root = _consumer(tmp_path=tmp_path, declaration="delegated_gate = true\ngate_cpu = 0\n")
    verdict = run_delegated_gate(
        repo_root=root,
        renderer=_RENDERER,
        runner=_World(),
        sleeper=lambda **_kwargs: None,
        emit=lambda **_kwargs: None,
    )

    assert verdict.state == GATE_NO_VERDICT
    assert verdict.refuses_push is True
    assert "pyproject.toml" in verdict.detail and "gate_cpu" in verdict.detail
    assert _registered_test(heading=_NON_POSITIVE_HEADING).endswith(
        ".test_non_positive_cpu_refuses_before_the_consumer_submits_a_gate_job"
    )


def test_malformed_memory_refuses_a_delegated_commit_without_local_fallback(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed declaration refuses the commit instead of converting it to a local gate."""
    root = _consumer(
        tmp_path=tmp_path,
        declaration='delegated_pre_commit = true\ngate_memory = "6"\n',
    )
    module = importlib.import_module("livespec_dev_tooling.pre_commit_delegate")
    submitted: list[object] = []
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: _TREE)
    monkeypatch.setattr(module, "_pre_commit_check_suite", lambda **_kwargs: ("check",))
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **kwargs: declared_gate_job_resources(repo_root=kwargs["repo_root"]),
    )
    monkeypatch.setattr(module, "run_gated_push", lambda **kwargs: submitted.append(kwargs))

    verdict = module.run_pre_commit(repo_root=root)

    assert (verdict.local, verdict.exit_status, submitted) == (False, 1, [])
    assert "pyproject.toml" in verdict.reason and "gate_memory" in verdict.reason
    assert _registered_test(heading=_MALFORMED_HEADING).endswith(
        ".test_malformed_memory_refuses_a_delegated_commit_without_local_fallback"
    )


def test_red_leg_replay_uses_the_small_job_size_despite_declared_resources(
    *, tmp_path: Path
) -> None:
    """The replay caller size wins over a consumer's full-suite resource declaration."""
    root = _consumer(
        tmp_path=tmp_path,
        declaration="delegated_commit_tests = true\ngate_cpu = 9\ngate_parallelism = 8\n",
    )
    built = gate_remote_request(
        repo_root=root,
        renderer=_RENDERER,
        runner=_World(),
        resources=("--cpu", "2", "--memory", "3Gi", "--parallelism", "1"),
    )
    assert isinstance(built, Success)
    job = next(document for document in yaml.safe_load_all(built.unwrap().manifest) if document)
    gate = next(
        container
        for container in job["spec"]["template"]["spec"]["containers"]
        if container["name"] == "gate"
    )
    env = {entry["name"]: entry["value"] for entry in gate["env"] if "value" in entry}

    assert gate["resources"] == {
        "requests": {"cpu": "2", "memory": "3Gi"},
        "limits": {"memory": "3Gi"},
    }
    assert env["LIVESPEC_TEST_PARALLELISM"] == "1"
    assert _registered_test(heading=_REPLAY_SIZE_HEADING).endswith(
        ".test_red_leg_replay_uses_the_small_job_size_despite_declared_resources"
    )


class _RecordingLog:
    """A logger double keeping the events the Red leg narrates."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append((event, kwargs))


def _oom_kill_every_gate_job(
    *, module: ModuleType, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make the committing host's gate Job end OOMKilled with no verdict."""
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: _TREE)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: _RENDERER)
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Success(
            importlib.import_module("livespec_dev_tooling.gate_remote_client").GateRunRequest(
                repo_root=root, mirror_url="mirror", manifest="manifest", gate_ref="refs/gates/tree"
            )
        ),
    )
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "commit")
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=GATE_FAILED,
            detail="the gate Job ended Failed",
            token_written=False,
            resource_kill="OOMKilled",
        ),
    )


def test_oom_killed_red_replay_returns_no_verdict_for_a_local_red_leg(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OOM-killed replay supplies no Red verdict, so the Red leg runs locally and records only that."""
    module = importlib.import_module("livespec_dev_tooling.commit_replay_delegate")
    root = _consumer(tmp_path=tmp_path, declaration="delegated_commit_tests = true\n")
    staged_test = root / "tests" / "test_red.py"
    staged_test.parent.mkdir()
    _ = staged_test.write_text("def test_red() -> None:\n    assert False\n", encoding="utf-8")
    monkeypatch.chdir(root)
    _oom_kill_every_gate_job(module=module, root=root, monkeypatch=monkeypatch)
    verdict = module.run_one_test(repo_root=root, pytest_argv=["pytest", "tests/test_red.py"])
    assert (verdict.local, verdict.exit_status) == (False, None)
    assert "OOMKilled" in verdict.reason

    modes = _load_red_green_replay_modes()
    message = root / "COMMIT_EDITMSG"
    _ = message.write_text("feat: red\n", encoding="utf-8")
    log = _RecordingLog()

    status = modes._handle_red_mode(  # noqa: SLF001
        msg_path=message, log=log, tests_paths=["tests/test_red.py"]
    )

    trailers = dict(
        line.split(": ", 1)
        for line in message.read_text(encoding="utf-8").splitlines()
        if line.startswith("TDD-")
    )
    local_events = [
        kwargs for event, kwargs in log.events if event == "commit-time replay gated locally"
    ]
    assert status == 0
    assert len(local_events) == 1 and "OOMKilled" in str(local_events[0]["reason"])
    assert not any(event == "commit-time replay gated by a gate Job" for event, _ in log.events)
    assert trailers["TDD-Red-Test"] == "tests/test_red.py"
    assert trailers["TDD-Red-Failure-Reason"].startswith("F ")
    assert trailers["TDD-Red-Output-Checksum"].startswith("sha256:")
    assert "TDD-Red-Gate-Job" not in trailers and "TDD-Red-Staged-Tree" not in trailers
    assert _registered_test(heading=_REPLAY_OOM_HEADING).endswith(
        ".test_oom_killed_red_replay_returns_no_verdict_for_a_local_red_leg"
    )


def _load_red_green_replay_modes():
    """Load the shipped Red-leg handler module the way the commit hook does."""
    import importlib.util
    import sys

    path = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "_red_green_replay_modes.py"
    spec = importlib.util.spec_from_file_location("_rgr_modes_for_consumer_test", str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
