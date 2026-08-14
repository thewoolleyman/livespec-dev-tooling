"""Contract tests for the shared hosted CI runner router workflow."""

from __future__ import annotations

from pathlib import Path


def _read(relative_path: str) -> str:
    return (Path(__file__).parents[2] / relative_path).read_text(encoding="utf-8")


def test_router_is_hosted_then_probes_twice_before_recovering_to_local() -> None:
    workflow = _read(".github/workflows/reusable-ci-runner-router.yml")

    assert "runs-on: ubuntu-latest" in workflow
    assert workflow.count("ci-runner-health") == 2
    assert "recovery-wait-seconds" in workflow
    assert 'sleep "${{ inputs.recovery-wait-seconds }}"' in workflow
    assert "idle-runner-observed" not in workflow


def test_router_forces_forks_hosted_and_has_only_single_lane_outputs() -> None:
    workflow = _read(".github/workflows/reusable-ci-runner-router.yml")

    assert "if [ \"$TRUSTED\" != 'true' ]" in workflow
    assert "forced-hosted-untrusted-event" in workflow
    assert '["ubuntu-latest"]' in workflow
    assert "local-runner-labels" in workflow
    assert "CI_RUNNER_LABELS" not in workflow


def test_operational_contract_documents_manual_override_and_non_migratable_jobs() -> None:
    documentation = _read("docs/ci-runner-failover.md")

    assert "CI_RUNNER_FAILOVER_MODE" in documentation
    assert "queued" in documentation
    assert "in-progress" in documentation
    assert "golden-master" in documentation
