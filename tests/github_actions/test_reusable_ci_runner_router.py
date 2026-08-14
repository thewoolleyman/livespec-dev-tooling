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


def test_router_exposes_a_saturation_grace_window_defaulting_to_five_minutes() -> None:
    workflow = _read(".github/workflows/reusable-ci-runner-router.yml")

    assert "saturation-grace-seconds" in workflow
    assert "default: 300" in workflow
    assert "saturation-poll-interval-seconds" in workflow
    assert "max-wait-seconds: ${{ inputs.saturation-grace-seconds }}" in workflow
    assert "poll-interval-seconds: ${{ inputs.saturation-poll-interval-seconds }}" in workflow


def test_router_only_grants_the_grace_window_to_the_first_probe() -> None:
    """The existing 30s recovery hysteresis on the second probe is unchanged."""
    workflow = _read(".github/workflows/reusable-ci-runner-router.yml")

    assert workflow.count("max-wait-seconds: ${{") == 1
    assert workflow.count("poll-interval-seconds: ${{") == 1


def test_documentation_explains_the_outage_vs_saturation_distinction() -> None:
    documentation = _read("docs/ci-runner-failover.md")

    assert "saturation" in documentation.lower()
    assert "saturated-timeout" in documentation
    assert "no-online-matching-runner" in documentation
    assert "300 seconds" in documentation or "5 minutes" in documentation
    assert "homelab" in documentation
    assert "Nix" in documentation
