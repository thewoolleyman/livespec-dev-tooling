"""A detached run refused for host authority leaves no green token behind.

Work item livespec-dev-tooling-l7puic, the detached-runner half of
livespec-dev-tooling-d2fm3g (livespec-orchestrator-git-jsonl#1225, 2026-11-17).
The pre-push client already runs the authority half BEFORE the Job and withholds
the token when a member refused. The detached runner (`gate_runner_delegate`) ran
the Job first, so a green Job wrote the token and the authority half only
refused afterwards; the retry of the same tree matched the token and skipped the
full aggregate. The runner must read the authority half first and pass that
reading to the Job's verdict as `mint_token`.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests.livespec_dev_tooling.test_gate_runner_delegate import _init_repo


def _stub_cluster(
    *, module: object, monkeypatch: pytest.MonkeyPatch, root: Path, returncode: int
) -> list[object]:
    """Wire a canned cluster and return the ordered log of what the run issued."""
    from returns.result import Success

    from livespec_dev_tooling._gate_host_authority import HostAuthorityRun
    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    issued: list[object] = []
    request = GateRunRequest(
        repo_root=root, mirror_url="mirror", manifest="manifest", gate_ref="ref"
    )

    def authority(**_kwargs: object) -> tuple[HostAuthorityRun, ...]:
        issued.append("authority")
        return (
            HostAuthorityRun(
                member="check-widget-approval",
                tree_hash="tree",
                returncode=returncode,
                detail="approval label is absent",
            ),
        )

    def job(**kwargs: object) -> GateVerdict:
        issued.append(("job", kwargs.get("mint_token", True)))
        return GateVerdict(
            state=GATE_PASSED,
            detail="the Job passed",
            token_written=kwargs.get("mint_token", True) is True,
            job_name="gate-widget-1",
        )

    monkeypatch.setattr(module, "_working_tree_source", lambda **_kwargs: ("tree", "commit"))
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "gate_remote_request", lambda **_kwargs: Success(request))
    monkeypatch.setattr(module, "run_host_authority_members", authority)
    monkeypatch.setattr(module, "run_gated_push", job)
    return issued


def test_a_refused_authority_member_leaves_the_detached_run_no_green_token(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    root, _ = _init_repo(tmp_path=tmp_path)
    issued = _stub_cluster(module=module, monkeypatch=monkeypatch, root=root, returncode=1)

    outcome = module.run_cluster_gate(repo_root=root, command=("just", "check"))

    assert all(
        [
            outcome.exit_status == 1,
            "check-widget-approval" in outcome.detail,
            issued == ["authority", ("job", False)],
        ]
    )


def test_a_passing_authority_half_lets_the_detached_job_mint_its_token(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("livespec_dev_tooling.gate_runner_delegate")
    root, _ = _init_repo(tmp_path=tmp_path)
    issued = _stub_cluster(module=module, monkeypatch=monkeypatch, root=root, returncode=0)

    outcome = module.run_cluster_gate(repo_root=root, command=("just", "check"))

    assert all([outcome.exit_status == 0, issued == ["authority", ("job", True)]])
