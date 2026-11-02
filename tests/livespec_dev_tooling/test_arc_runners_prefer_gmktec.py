"""ARC runner pods prefer gmktec-xubuntu over the k3s server node.

Orchestrator plan `bd-ib-nmuyjc` (scope event 2026-11-02T17:10:45Z), accepted
by coordinator `legacy-coordinator-agent`. A runner pod requests only
`ci-runner.io/churn-slot` and no cpu or memory, so the default scheduler's
least-allocated scoring placed every runner on poweredge-xubuntu: measured
2026-11-02 at about 17:30Z, 28 runner pods used 59.5 of its 72 cores while
gmktec held 0 runners with 12 free churn slots.

These static tests grade the committed Helm values (no YAML library is
importable here):

- every Kueue-gated scale set the converge applies, and the EXAMPLE template a
  new one is copied from, carries a PREFERRED node affinity naming
  gmktec-xubuntu inside its runner pod template;
- the affinity is never REQUIRED, so the churn-slot budget, not this
  preference, decides when runners overflow to poweredge;
- the phase-1 poweredge proof scale set is left as captured.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ARC = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "arc"
_CONVERGE = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "reconstruct" / "converge-ci-stack.sh"
_PHASE_ONE = "values-poweredge-xubuntu-k3s.yaml"


def _converged_values_files() -> list[str]:
    text = _CONVERGE.read_text(encoding="utf-8")
    block = text[text.index("declare -A SCALE_SETS=(") :]
    block = block[: block.index("\n)")]
    return re.findall(r'\]="(values-[^"]+\.yaml)"', block)


def _gated_files() -> list[str]:
    return [name for name in _converged_values_files() if name != _PHASE_ONE] + [
        "values-EXAMPLE-repo.yaml"
    ]


def _runner_pod_spec(*, name: str) -> str:
    text = (_ARC / name).read_text(encoding="utf-8")
    template = text[text.index("\ntemplate:\n") :]
    spec_start = template.index("\n  spec:\n") + len("\n  spec:\n")
    following = re.search(r"\n\S", template[spec_start:])
    end = spec_start + following.start() if following else len(template)
    return template[spec_start:end]


def test_ten_gated_scale_sets_and_the_template_are_graded() -> None:
    assert len(_gated_files()) == 11


@pytest.mark.parametrize("name", _gated_files())
def test_runner_pods_prefer_gmktec(name: str) -> None:
    spec = _runner_pod_spec(name=name)
    assert re.search(
        r"\n    affinity:\n"
        r"      nodeAffinity:\n"
        r"        preferredDuringSchedulingIgnoredDuringExecution:\n"
        r"          - weight: 100\n"
        r"            preference:\n"
        r"              matchExpressions:\n"
        r"                - key: kubernetes\.io/hostname\n"
        r"                  operator: In\n"
        r'                  values: \["gmktec-xubuntu"\]\n',
        "\n" + spec,
    ), f"{name}: runner pod template does not prefer gmktec-xubuntu"


@pytest.mark.parametrize("name", _gated_files())
def test_the_preference_is_never_required(name: str) -> None:
    assert "requiredDuringScheduling" not in _runner_pod_spec(name=name)


def test_the_phase_one_proof_set_is_left_as_captured() -> None:
    assert "affinity:" not in (_ARC / _PHASE_ONE).read_text(encoding="utf-8")
