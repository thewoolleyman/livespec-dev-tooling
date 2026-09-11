"""Consumer-tier: the three `SPECIFICATION/scenarios.md` JIT admission scenarios.

    "JIT replacement is immediate but installation-budgeted"
    "JIT startup batch immediately admits all permitted demand within the
     half-budget point burst"
    "JIT throttle opens one shared circuit"

WHAT THIS TREE OWNS OF THEM, STATED PLAINLY. The controller these scenarios
describe is ARC's, running on the fleet pool; its source is not in this
repository and no test here executes it. What IS here — and what a consumer of
this repository actually gets — is the committed gitops that the controller runs
UNDER: the per-repository scale sets, the Kueue cohort that admits their pods,
the fleet-owned Kueue `Configuration`, and the node profile carrying the pool's
physical capacity. Every clause below is asserted against those files, and only
where a clause has a decidable consequence in them. `ci-runner/k3s/phase2/
README.md` §"What does NOT move to Kueue/ARC" is the record of which half of the
section lands where; this file covers the half that lands here.

Each number is hand-maintained in a DIFFERENT file, so every way they drift
apart is silent: a wrong number is a valid manifest, applies cleanly, and
produces a pool that mints the wrong amount of work. That is the same failure
shape the sibling `tests/spec/test_jit_admission_budget.py` guards for the
section's `min()` terms; these are its three scenario-level clauses.

The scale-set and cohort readers here are DELIBERATELY NOT shared with that
sibling. It registers a `non-functional-requirements.md` heading at unit tier and
lives under `tests/spec/`; this file registers three `scenarios.md` headings and
must live at integration tier or above. Importing one from the other would make
a scenario's coverage depend on a unit-tier module, which is the coupling the
tier rule exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_ARC_DIR = _PHASE2 / "arc"
_KUEUE_DIR = _PHASE2 / "kueue"
_KUEUE_MANAGER_CONFIG = _KUEUE_DIR / "core" / "manager-config-patch.yaml"
_PROFILES_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"

# The one cohort every routed scale set's pods are admitted within.
_COHORT = "fleet-ci-runner-pool"

# The section's own numbers. The installation-token POST and the JIT-config POST
# are the MINT PAIR, "approximately five points each, or ten points per pair",
# and the startup batch may spend at most 450 of GitHub's documented 900 REST
# points per minute — "at most about 45 complete mint pairs".
_PRIMARY_POINTS_PER_MINUTE = 900
_STARTUP_BUDGET_POINTS = 450
_POINTS_PER_MINT_PAIR = 10
_BURST_MINT_PAIRS = _STARTUP_BUDGET_POINTS // _POINTS_PER_MINT_PAIR

# Kueue's ONE knob that makes admission wait on a clock rather than on capacity.
# Upstream ships it commented out and the fleet patch keeps it that way; enabled
# with `blockAdmission`, Kueue holds admission for a timeout per workload, which
# is a fixed positive minimum interval between admissions by another name.
_ADMISSION_TIMER_KEY = "waitForPodsReady"

_DOC_SEPARATOR = re.compile(r"^---$", re.MULTILINE)
_KIND = re.compile(r"^kind:\s*(?P<kind>\S+)$", re.MULTILINE)
_NAME = re.compile(r"^  name:\s*(?P<name>\S+)", re.MULTILINE)
_COHORT_NAME = re.compile(r"^  cohortName:\s*(?P<cohort>\S+)", re.MULTILINE)
_CLUSTER_QUEUE = re.compile(r"^  clusterQueue:\s*(?P<cq>\S+)", re.MULTILINE)
_MAX_RUNNERS = re.compile(r"^\s*maxRunners:\s*(?P<max>\d+)\s*$", re.MULTILINE)
_QUEUE_NAME = re.compile(r"^\s*kueue\.x-k8s\.io/queue-name:\s*(?P<lq>\S+)\s*$", re.MULTILINE)
_CONFIG_SECRET = re.compile(r"^githubConfigSecret:\s*(?P<secret>\S+)", re.MULTILINE)
_ADMISSION_CAPACITY = re.compile(r"^ADMISSION_CAPACITY_C=(?P<capacity>\d+)\s*$", re.MULTILINE)
# A preemption policy Kueue would act on. `Never` is both the fleet's setting and
# Kueue's default, so an ABSENT block is compliant and only a stated non-`Never`
# value convicts.
_PREEMPTION_POLICY = re.compile(
    r"^\s*(?:reclaimWithinCohort|withinClusterQueue|policy):\s*(?P<policy>\S+)\s*$", re.MULTILINE
)


def _cohort_documents() -> list[str]:
    """Every YAML document across the committed ClusterQueue manifests."""
    return [
        document
        for path in sorted(_KUEUE_DIR.glob("cluster-queue-*.yaml"))
        for document in _DOC_SEPARATOR.split(path.read_text(encoding="utf-8"))
    ]


def _local_queues_in_the_cohort() -> set[str]:
    """Each LocalQueue name whose ClusterQueue is a member of the one cohort."""
    cluster_queues = {
        name.group("name")
        for document in _cohort_documents()
        for kind in [_KIND.search(document)]
        for cohort in [_COHORT_NAME.search(document)]
        for name in [_NAME.search(document)]
        if kind is not None
        and kind.group("kind") == "ClusterQueue"
        and cohort is not None
        and cohort.group("cohort") == _COHORT
        and name is not None
    }
    return {
        name.group("name")
        for document in _cohort_documents()
        for kind in [_KIND.search(document)]
        for name in [_NAME.search(document)]
        for target in [_CLUSTER_QUEUE.search(document)]
        if kind is not None
        and kind.group("kind") == "LocalQueue"
        and name is not None
        and target is not None
        and target.group("cq") in cluster_queues
    }


def _routed_scale_sets() -> dict[str, tuple[str, int]]:
    """Each queue-routed scale set's values file, mapped to (LocalQueue, maxRunners).

    A values file that names no LocalQueue, or declares no ceiling, is not a
    routed scale set: that is how the committed template and the host-unique
    release stay out of the arithmetic.
    """
    routed: dict[str, tuple[str, int]] = {}
    for path in sorted(_ARC_DIR.glob("values-*.yaml")):
        source = path.read_text(encoding="utf-8")
        queue = _QUEUE_NAME.search(source)
        ceiling = _MAX_RUNNERS.search(source)
        if queue is None or ceiling is None:
            continue
        routed[path.name] = (queue.group("lq"), int(ceiling.group("max")))
    return routed


def _installation_secrets() -> dict[str, str]:
    """Each routed scale set's values file mapped to the App installation secret it mints with."""
    secrets: dict[str, str] = {}
    for name in _routed_scale_sets():
        secret = _CONFIG_SECRET.search((_ARC_DIR / name).read_text(encoding="utf-8"))
        assert secret is not None, (
            f"a routed scale set must name the App installation secret it mints with — "
            f"minting is what the point budget accounts for; values file={name}"
        )
        secrets[name] = secret.group("secret")
    return secrets


def _registered_capacity() -> int:
    """The pool's total `ci-runner.io/churn-slot` capacity, summed across node profiles.

    Churn-slot capacity is PER-NODE since the two-node opening (DERIVATION.md
    "The derivation at C = 44 — the two-node pool (2026-09-11)"); the section's
    remaining-physical-capacity term is the whole pool, so it is the sum of every
    node's own `ADMISSION_CAPACITY_C`.
    """
    total = 0
    seen = False
    for profile in sorted(_PROFILES_DIR.glob("*.env")):
        declared = _ADMISSION_CAPACITY.search(profile.read_text(encoding="utf-8"))
        assert declared is not None, (
            f"every pool node's admission capacity C must be a value of its committed "
            f"profile — the section's remaining-physical-capacity term lives there; "
            f"profile={profile.relative_to(_REPO_ROOT)}"
        )
        total += int(declared.group("capacity"))
        seen = True
    assert seen, "at least one pool node profile must declare an ADMISSION_CAPACITY_C"
    return total


def _active_config_lines() -> list[str]:
    """The fleet-owned Kueue `Configuration`'s ACTIVE lines — comments stripped.

    Upstream's body is carried verbatim including its large commented-out
    reference block, so a substring search over the raw file matches keys that
    are switched OFF. Only the uncommented lines are configuration.
    """
    return [
        line
        for line in _KUEUE_MANAGER_CONFIG.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_replacement_admission_is_neither_clock_serialized_nor_billed_to_a_private_budget() -> None:
    """§"JIT replacement is immediate but installation-budgeted", both halves.

    IMMEDIATE: "A fixed positive minimum interval between all runner admissions
    is prohibited; rate protection comes from the installation-wide budget and
    from an actual GitHub response, not from serializing healthy replenishment."
    The one committed knob that could impose such an interval is Kueue's
    `waitForPodsReady`, and the fleet's `Configuration` must leave it off.

    BUDGETED: "it MUST account for the mint pair against the SHARED installation
    budget." A budget can only be shared if there is ONE installation to share:
    give a scale set its own `githubConfigSecret` and it mints against a second
    App installation with its own 900 points, at which point the accounting is
    silently wrong in the direction of over-spending — nothing errors, the pool
    simply mints past a budget it believes it is inside.
    """
    timer_lines = [line for line in _active_config_lines() if _ADMISSION_TIMER_KEY in line]
    assert not timer_lines, (
        f"`{_ADMISSION_TIMER_KEY}` gates admission on a per-workload timeout rather than "
        f"on capacity, which serializes healthy replenishment — the one thing the section "
        f"names as prohibited, and the one thing rate protection must NOT come from; "
        f"active lines={timer_lines!r} in "
        f"{_KUEUE_MANAGER_CONFIG.relative_to(_REPO_ROOT)}"
    )

    secrets = _installation_secrets()
    assert secrets, "the routed scale sets must be committed for their minting to be readable"
    assert len(set(secrets.values())) == 1, (
        f"every routed scale set must mint against ONE App installation, or there is no "
        f"shared budget for the mint pair to be accounted against — each installation "
        f"carries its own point ceiling, so a second secret splits the budget in two "
        f"while every consumer keeps reading it as one; got {secrets!r}"
    )


def test_the_startup_batch_admits_all_permitted_demand_inside_the_half_budget_burst() -> None:
    """§"JIT startup batch immediately admits all permitted demand within the half-budget point burst".

    The startup batch admits "every demand item permitted by the repository
    desired-admission formula, remaining physical host capacity, and the
    remaining 450-point startup budget" — a `min()` whose second term is the
    pool's registered churn-slot capacity. The heading is the claim that ALL of
    that permitted demand fits inside the burst, so the committed capacity must
    convert to no more than the burst's mint pairs. Raised past it — as C was to
    64 for about two hours on 2026-09-06 — a cold start can no longer reach
    capacity in the startup batch at all, and nothing anywhere reports that the
    guarantee lapsed.

    The second assertion keeps the first from being vacuous. It is only a real
    bound while demand can EXCEED it, which is exactly the section's "even when
    more demand remains": the fleet's summed ceilings are what that demand can
    reach, and they must outrun the burst for the clause to govern anything.
    """
    capacity = _registered_capacity()
    assert 0 < capacity <= _BURST_MINT_PAIRS, (
        f"the pool's registered physical capacity bounds the startup batch, so admitting "
        f"all of it costs {capacity} mint pairs at {_POINTS_PER_MINT_PAIR} points each — "
        f"which must stay inside the {_STARTUP_BUDGET_POINTS}-point burst, i.e. "
        f"{_BURST_MINT_PAIRS} pairs, half of GitHub's documented "
        f"{_PRIMARY_POINTS_PER_MINUTE} REST points per minute; capacity={capacity}"
    )

    ceilings = sum(ceiling for _, ceiling in _routed_scale_sets().values())
    assert ceilings > _BURST_MINT_PAIRS, (
        f"the summed per-repository ceilings are the demand the batch can face, and they "
        f"must exceed the burst for 'MUST NOT exceed the 450-point startup budget EVEN "
        f"WHEN MORE DEMAND REMAINS' to govern a state the pool can actually be in — "
        f"otherwise the bound above is asserted against demand that can never reach it; "
        f"ceilings={ceilings} burst={_BURST_MINT_PAIRS}"
    )


def test_a_throttle_opens_one_circuit_that_evicts_no_healthy_runner() -> None:
    """§"JIT throttle opens one shared circuit".

    ONE: the circuit is installation-wide, and the committed pool gives it
    exactly one installation and exactly one admission cohort to be wide over.
    A routed scale set outside `fleet-ci-runner-pool` would be admitted against
    its own quota, so one repository's throttle boundary would not be the
    others' — two circuits wearing one name.

    NO EVICTION: "it MUST retain queued demand and healthy registered runners",
    which the section restates as "Healthy registered runners remain available
    and queued demand remains pending while the circuit is open". Preemption is
    the committed mechanism that would break it: a repository whose demand sits
    queued behind an open circuit must not reclaim a peer's already-admitted,
    healthy runner. `Never` is both the pool's setting and Kueue's default, so
    an absent block is compliant here and only a stated policy convicts.
    """
    routed = _routed_scale_sets()
    in_cohort = _local_queues_in_the_cohort()
    outside = sorted(
        f"{name} -> {local_queue}"
        for name, (local_queue, _) in routed.items()
        if local_queue not in in_cohort
    )
    assert routed and not outside, (
        f"every routed scale set's pods must be admitted inside the one `{_COHORT}` "
        f"cohort, or the circuit the throttle opens is not one shared boundary but "
        f"several that happen to share a name; outside={outside}"
    )

    stated = sorted(
        f"{path.name}: {match.group('policy')}"
        for path in sorted(_KUEUE_DIR.glob("cluster-queue-*.yaml"))
        for match in _PREEMPTION_POLICY.finditer(path.read_text(encoding="utf-8"))
        if _COHORT in path.read_text(encoding="utf-8") and match.group("policy") != "Never"
    )
    assert not stated, (
        f"no cohort member may enable preemption: with the circuit open, queued demand "
        f"stays pending BY DESIGN, and a preempting queue would spend that wait evicting "
        f"the healthy registered runners the section requires to remain available — "
        f"turning a throttle into a fleet-wide loss of in-flight work; stated={stated}"
    )
