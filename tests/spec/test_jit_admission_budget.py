"""§"Adaptive JIT runner admission budget" — the three static terms of the min(), held together.

The section's admission formula is `min(queued jobs, doubled repository logical
ceiling, fair share of remaining host-wide capacity)` under a physical invariant:
"The physical host-wide cap remains exactly 482 active runners; no configuration
or recovery path may derive or admit 964 runners."

`DERIVATION.md` beside the manifests records where each term lives, and the
mapping is what makes the formula real: the first term is dynamic (ARC's
listener counts assigned jobs and needs no configuration), and the other THREE
are static files that bound it —

- `doubled repository logical ceiling` is a scale set's `maxRunners`, bounded
  since 2026-09-06 to `max(2 x nominalQuota, 6)`;
- `fair share of remaining host-wide capacity` is that repository's ClusterQueue
  `nominalQuota` inside the one cohort;
- the physical cap is the node's `ci-runner.io/churn-slot` capacity, which the
  node's own profile carries as `ADMISSION_CAPACITY_C`.

Each term is a hand-maintained number in a DIFFERENT file, and the relations
between them are what the section states rather than what any one file says. So
every way they can drift apart is silent, and each drift breaks a named clause:

- **A `maxRunners` that outgrows its quota** breaks "never so large that a
  backlog is materialized as pending admission objects the host's control plane
  must keep reconciling". The scale set still admits; the surplus becomes
  pending pods the scheduler re-reconciles forever, which is precisely the cost
  the clause says must be paid at the forge instead.
- **A `maxRunners` that shrinks to its quota** breaks the opposite clause,
  "Repositories MAY fairly borrow unused capacity": with the ceiling equal to
  the fair share, idle capacity elsewhere in the cohort is unreachable. The
  bound is two-sided for that reason, and this is the direction `DERIVATION.md`
  records the earlier "one number" reading getting wrong.
- **Quotas that no longer sum to the node's capacity** break the fair-share term
  itself: over-subscribed, the guaranteed floors are not guaranteed;
  under-subscribed, capacity the host has is unreachable by anyone.

None of the three raises an error. A wrong number is a valid manifest, applies
cleanly, and produces a pool that admits the wrong amount of work.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KUEUE_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "kueue"
_ARC_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "arc"
_SERVER_PROFILE = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles" / "poweredge-xubuntu.env"
)

# The one cohort the fair-share term is apportioned within.
_COHORT = "fleet-ci-runner-pool"
_CHURN_SLOT = "ci-runner.io/churn-slot"

# The bound the section's "small multiple ... and any floor" clause resolves to
# for this pool, recorded with the pool's admission derivation as the section
# requires: `max(MULTIPLE x nominalQuota, FLOOR)`.
_CEILING_MULTIPLE = 2
_CEILING_FLOOR = 6

# The physical invariant, stated in the section itself.
_PHYSICAL_CAP = 482
_FORBIDDEN_DOUBLING = _PHYSICAL_CAP * 2

_DOC_SEPARATOR = re.compile(r"^---$", re.MULTILINE)
_KIND = re.compile(r"^kind:\s*(?P<kind>\S+)$", re.MULTILINE)
_NAME = re.compile(r"^  name:\s*(?P<name>\S+)", re.MULTILINE)
_COHORT_NAME = re.compile(r"^  cohortName:\s*(?P<cohort>\S+)", re.MULTILINE)
_CLUSTER_QUEUE = re.compile(r"^  clusterQueue:\s*(?P<cq>\S+)", re.MULTILINE)
_NOMINAL_QUOTA = re.compile(r"^\s+nominalQuota:\s*(?P<quota>\d+)\s*$", re.MULTILINE)
_MAX_RUNNERS = re.compile(r"^\s*maxRunners:\s*(?P<max>\d+)\s*$", re.MULTILINE)
_QUEUE_NAME = re.compile(r"^\s*kueue\.x-k8s\.io/queue-name:\s*(?P<lq>\S+)\s*$", re.MULTILINE)
_ADMISSION_CAPACITY = re.compile(r"^ADMISSION_CAPACITY_C=(?P<capacity>\d+)\s*$", re.MULTILINE)


def _documents() -> list[str]:
    """Every YAML document across the committed ClusterQueue manifests."""
    return [
        document
        for path in sorted(_KUEUE_DIR.glob("cluster-queue-*.yaml"))
        for document in _DOC_SEPARATOR.split(path.read_text(encoding="utf-8"))
    ]


def _cohort_quotas() -> dict[str, int]:
    """Each cohort-member ClusterQueue's churn-slot `nominalQuota`."""
    quotas: dict[str, int] = {}
    for document in _documents():
        kind = _KIND.search(document)
        cohort = _COHORT_NAME.search(document)
        name = _NAME.search(document)
        quota = _NOMINAL_QUOTA.search(document)
        if kind is None or kind.group("kind") != "ClusterQueue":
            continue
        if cohort is None or cohort.group("cohort") != _COHORT:
            continue
        assert name is not None and quota is not None and _CHURN_SLOT in document, (
            f"a `{_COHORT}` member must carry a name and one `{_CHURN_SLOT}` "
            f"nominalQuota; document={document!r}"
        )
        quotas[name.group("name")] = int(quota.group("quota"))
    return quotas


def _local_queue_targets() -> dict[str, str]:
    """Each committed LocalQueue name mapped to the ClusterQueue it feeds."""
    targets: dict[str, str] = {}
    for document in _documents():
        kind = _KIND.search(document)
        name = _NAME.search(document)
        cluster_queue = _CLUSTER_QUEUE.search(document)
        if kind is not None and kind.group("kind") == "LocalQueue":
            assert (
                name is not None and cluster_queue is not None
            ), f"a LocalQueue must name itself and its ClusterQueue; document={document!r}"
            targets[name.group("name")] = cluster_queue.group("cq")
    return targets


def _scale_set_ceilings() -> dict[str, tuple[str, int]]:
    """Each queue-routed scale set's ClusterQueue mapped to (values file, maxRunners).

    A values file that names no LocalQueue, or declares no ceiling, is not a
    routed scale set and contributes nothing — that is how the committed
    template and the host-unique release stay out of the arithmetic.
    """
    targets = _local_queue_targets()
    ceilings: dict[str, tuple[str, int]] = {}
    for path in sorted(_ARC_DIR.glob("values-*.yaml")):
        source = path.read_text(encoding="utf-8")
        queue = _QUEUE_NAME.search(source)
        ceiling = _MAX_RUNNERS.search(source)
        if queue is None or ceiling is None:
            continue
        local_queue = queue.group("lq")
        ceilings[targets.get(local_queue, local_queue)] = (path.name, int(ceiling.group("max")))
    return ceilings


def test_every_repository_ceiling_is_the_bounded_multiple_of_its_fair_share() -> None:
    """`maxRunners == max(2 x nominalQuota, 6)`, asserted in both directions at once."""
    quotas = _cohort_quotas()
    ceilings = _scale_set_ceilings()
    assert quotas and ceilings, (
        f"the cohort and its scale sets must both be committed; quotas={sorted(quotas)} "
        f"ceilings={sorted(ceilings)}"
    )
    unrouted = sorted(set(quotas) - set(ceilings))
    assert not unrouted, (
        f"every cohort member's fair share must belong to a scale set that can spend it; "
        f"a quota with no scale set routed to it is capacity reserved for nobody; "
        f"unrouted={unrouted}"
    )
    wrong = sorted(
        f"{ceilings[cq][0]}: maxRunners={ceilings[cq][1]} quota={quota} "
        f"expected={max(_CEILING_MULTIPLE * quota, _CEILING_FLOOR)}"
        for cq, quota in quotas.items()
        if ceilings[cq][1] != max(_CEILING_MULTIPLE * quota, _CEILING_FLOOR)
    )
    assert not wrong, (
        f"each repository's ceiling must be the bounded multiple of its fair share. Too "
        f"HIGH and queued work beyond the bound materializes as pending admission objects "
        f"the host's control plane keeps reconciling, which the section says must wait at "
        f"the forge instead; too LOW — down at the quota — and 'Repositories MAY fairly "
        f"borrow unused capacity' becomes unreachable, because the ceiling IS the "
        f"guaranteed share. Both apply cleanly and neither reports anything; wrong={wrong}"
    )


def test_the_fair_shares_sum_to_the_capacity_the_node_profile_declares() -> None:
    """The apportionment is exact: the floors add up to C, over- nor under-subscribed."""
    quotas = _cohort_quotas()
    declared = _ADMISSION_CAPACITY.search(_SERVER_PROFILE.read_text(encoding="utf-8"))
    assert declared is not None, (
        f"the node's admission capacity C must be a value of its committed profile — the "
        f"per-node profile is where the section's host-capacity term lives; "
        f"profile={_SERVER_PROFILE.relative_to(_REPO_ROOT)}"
    )
    capacity = int(declared.group("capacity"))
    assert sum(quotas.values()) == capacity, (
        f"the cohort's guaranteed floors must sum to exactly the capacity the node "
        f"registers. Over-subscribed, a floor is not a floor — two repositories at their "
        f"guaranteed share cannot both be admitted; under-subscribed, capacity the host "
        f"has is unreachable by anyone. Kueue applies either without complaint; "
        f"sum={sum(quotas.values())} capacity={capacity} quotas={quotas}"
    )


def test_no_committed_admission_path_reaches_or_doubles_the_physical_cap() -> None:
    """ "no configuration or recovery path may derive or admit 964 runners"."""
    ceilings = _scale_set_ceilings()
    admissible = sum(ceiling for _, ceiling in ceilings.values())
    assert admissible <= _PHYSICAL_CAP, (
        f"every scale set at its ceiling simultaneously must stay within the physical "
        f"host-wide cap of {_PHYSICAL_CAP} active runners; admissible={admissible}"
    )
    doubling = sorted(
        f"{path.relative_to(_REPO_ROOT)}"
        for path in (*sorted(_KUEUE_DIR.glob("*.yaml")), *sorted(_ARC_DIR.glob("values-*.yaml")))
        if re.search(
            rf"^\s*\w+:\s*{_FORBIDDEN_DOUBLING}\s*$", path.read_text(encoding="utf-8"), re.MULTILINE
        )
    )
    assert not doubling, (
        f"the section forbids any configuration or recovery path DERIVING or admitting "
        f"{_FORBIDDEN_DOUBLING} runners — the doubling of the physical cap that the "
        f"'doubled repository logical ceiling' term invites when it is read as applying "
        f"to the host rather than to a repository; doubling={doubling}"
    )
