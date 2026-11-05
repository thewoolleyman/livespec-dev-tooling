"""The adaptive JIT runner admission budget of `SPECIFICATION/non-functional-requirements.md`
— the three static terms of the min(), held together.

The section's admission formula is `min(queued jobs, doubled repository logical
ceiling, fair share of remaining host-wide capacity)` under a physical invariant:
"The physical host-wide cap remains exactly 482 active runners; no configuration
or recovery path may derive or admit 964 runners."

`DERIVATION.md` beside the manifests records where each term lives, and the
mapping is what makes the formula real: the first term is dynamic (ARC's
listener counts assigned jobs and needs no configuration), and the other THREE
are static files that bound it —

- `doubled repository logical ceiling` is a scale set's `maxRunners`, bounded
  since 2026-09-06 to `max(2 x nominalQuota, 6)` except where DERIVATION.md
  records an exception;
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
- **Quotas that no longer sum to the pool's total capacity** break the
  fair-share term itself: over-subscribed, the guaranteed floors are not
  guaranteed; under-subscribed, capacity the pool has is unreachable by anyone.
  Since the two-node opening (DERIVATION.md "The derivation at C = 44 — the
  two-node pool") churn-slot capacity is per-node while the cohort quota is
  cluster-wide, so the sum is taken across every node's `ADMISSION_CAPACITY_C`.

None of the three raises an error. A wrong number is a valid manifest, applies
cleanly, and produces a pool that admits the wrong amount of work.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KUEUE_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "kueue"
_DERIVATION = _KUEUE_DIR / "DERIVATION.md"
_ARC_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "arc"
_PROFILES_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"

# The one cohort the fair-share term is apportioned within.
_COHORT = "fleet-ci-runner-pool"
_CHURN_SLOT = "ci-runner.io/churn-slot"

# The bound the section's "small multiple ... and any floor" clause resolves to
# for this pool, recorded with the pool's admission derivation as the section
# requires: `max(MULTIPLE x nominalQuota, FLOOR)`.
_CEILING_MULTIPLE = 2
_CEILING_FLOOR = 6

# The recorded exceptions to that bound, keyed by ClusterQueue. Each one is a row
# in DERIVATION.md "Recorded exceptions to the rule", carrying the measurement
# that justifies it and the acceptance check that confirms or reverts it. A
# ceiling matches its row here or the bound above, never anything else.
_RECORDED_CEILING_EXCEPTIONS: dict[str, int] = {
    # The rule's 2x multiple with its floor of 6 waived: a ~100 GiB work volume
    # per job (DERIVATION.md "The fabro fork scale set (2026-11-05)").
    "fabro-cq": 2,
}

# Each exception's row in DERIVATION.md "Recorded exceptions to the rule":
# `| `<repository>` | <nominalQuota> | <rule value> | **<maxRunners>** | <date> |`.
_EXCEPTION_ROW = re.compile(
    (
        r"^\| `(?P<repo>[^`]+)` \| (?P<quota>\d+) \| (?P<rule>\d+) \| "
        r"\*\*(?P<max>\d+)\*\* \| \d{4}-\d{2}-\d{2} \|"
    ),
    re.MULTILINE,
)
_EXCEPTIONS_HEADING = "### Recorded exceptions to the rule"
_EXCEPTION_QUEUES = {"fabro": "fabro-cq"}

# The physical invariant, stated in the section itself.
_PHYSICAL_CAP = 482
_FORBIDDEN_DOUBLING = _PHYSICAL_CAP * 2

_DOC_SEPARATOR = re.compile(r"^---$", re.MULTILINE)
_KIND = re.compile(r"^kind:\s*(?P<kind>\S+)$", re.MULTILINE)
_NAME = re.compile(r"^  name:\s*(?P<name>\S+)", re.MULTILINE)
_COHORT_NAME = re.compile(r"^  cohortName:\s*(?P<cohort>\S+)", re.MULTILINE)
_CLUSTER_QUEUE = re.compile(r"^  clusterQueue:\s*(?P<cq>\S+)", re.MULTILINE)
_NOMINAL_QUOTA = re.compile(r"^\s+nominalQuota:\s*(?P<quota>\d+)\s*$", re.MULTILINE)
_LENDING_LIMIT = re.compile(r"^\s+lendingLimit:\s*(?P<limit>\S+)\s*$", re.MULTILINE)
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
    """`maxRunners == max(2 x nominalQuota, 6)`, or its recorded exception, in both directions."""
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
    expected = {
        cq: _RECORDED_CEILING_EXCEPTIONS.get(cq, max(_CEILING_MULTIPLE * quota, _CEILING_FLOOR))
        for cq, quota in quotas.items()
    }
    wrong = sorted(
        f"{ceilings[cq][0]}: maxRunners={ceilings[cq][1]} quota={quota} " f"expected={expected[cq]}"
        for cq, quota in quotas.items()
        if ceilings[cq][1] != expected[cq]
    )
    assert not wrong, (
        f"each repository's ceiling must be the bounded multiple of its fair share. Too "
        f"HIGH and queued work beyond the bound materializes as pending admission objects "
        f"the host's control plane keeps reconciling, which the section says must wait at "
        f"the forge instead; too LOW — down at the quota — and 'Repositories MAY fairly "
        f"borrow unused capacity' becomes unreachable, because the ceiling IS the "
        f"guaranteed share. Both apply cleanly and neither reports anything; wrong={wrong}"
    )


def _pool_capacity() -> dict[str, int]:
    """Each pool node's `ADMISSION_CAPACITY_C`, keyed by profile name.

    Churn-slot capacity is PER-NODE since the two-node opening (DERIVATION.md
    "The derivation at C = 44 — the two-node pool (2026-09-11)"), while the Kueue
    cohort quota is a single CLUSTER-WIDE number. So the term the fair shares sum
    to is the TOTAL across every node's own profile, not any one node's value.
    """
    capacities: dict[str, int] = {}
    for profile in sorted(_PROFILES_DIR.glob("*.env")):
        declared = _ADMISSION_CAPACITY.search(profile.read_text(encoding="utf-8"))
        assert declared is not None, (
            f"every pool node's admission capacity C must be a value of its committed "
            f"profile — the per-node profile is where the section's host-capacity term "
            f"lives; profile={profile.relative_to(_REPO_ROOT)}"
        )
        capacities[profile.name] = int(declared.group("capacity"))
    return capacities


def test_the_fair_shares_sum_to_the_capacity_the_node_profiles_declare() -> None:
    """The apportionment is exact: the floors add up to the pool's total C across nodes."""
    quotas = _cohort_quotas()
    capacities = _pool_capacity()
    assert capacities, "at least one pool node profile must declare an ADMISSION_CAPACITY_C"
    capacity = sum(capacities.values())
    assert sum(quotas.values()) == capacity, (
        f"the cohort's guaranteed floors must sum to exactly the pool's TOTAL registered "
        f"capacity across every node — the cohort quota is cluster-wide while churn-slot "
        f"capacity is per-node, so it sums to both. Over-subscribed, a floor is not a floor "
        f"— two repositories at their guaranteed share cannot both be admitted; "
        f"under-subscribed, capacity the pool has is unreachable by anyone. Kueue applies "
        f"either without complaint; sum={sum(quotas.values())} capacity={capacity} "
        f"per_node={capacities} quotas={quotas}"
    )


def test_measured_job_hours_derive_the_committed_fair_shares() -> None:
    """Seven-day pool job-hours are the dated, auditable source of every quota."""
    expected = {
        "livespec-orchestrator-beads-fabro-cq": 25,
        "livespec-dev-tooling-cq": 6,
        "livespec-dev-tooling-master-cq": 3,
        "livespec-cq": 2,
        "livespec-overseer-cq": 1,
        "livespec-orchestrator-git-jsonl-cq": 1,
        "livespec-driver-claude-cq": 1,
        "livespec-driver-pi-cq": 1,
        "livespec-console-beads-fabro-cq": 1,
        "livespec-driver-codex-cq": 1,
        "livespec-runtime-cq": 1,
        "fabro-cq": 1,
    }
    assert _cohort_quotas() == expected

    derivation = _DERIVATION.read_text(encoding="utf-8")
    assert "## Measured job-hours re-derivation at C = 44 (2026-10-22)" in derivation
    assert "SUM(duration_ms) / 3,600,000" in derivation
    assert "deducts one from `livespec-orchestrator-beads-fabro` (30 → 29)" in derivation
    assert "## The master-push slice for livespec-dev-tooling (2026-11-03)" in derivation
    assert "## The fabro fork scale set (2026-11-05)" in derivation


def test_master_push_slice_reserves_its_quota_and_lends_none_of_it() -> None:
    """The master slice's floor is reserved: `lendingLimit: 0`, no preemption.

    Reclaim is Never across the cohort, so a lent master slot would only come
    back when the pull-request job borrowing it finished — the wait the slice
    exists to remove. Every OTHER member must keep lending its whole floor.
    """
    lending = {
        document_name.group("name"): limit.group("limit")
        for document in _documents()
        if (document_name := _NAME.search(document)) is not None
        and (limit := _LENDING_LIMIT.search(document)) is not None
    }
    assert lending == {"livespec-dev-tooling-master-cq": "0"}
    master = next(
        document
        for document in _documents()
        if (found := _NAME.search(document)) is not None
        and found.group("name") == "livespec-dev-tooling-master-cq"
    )
    for setting in ("reclaimWithinCohort: Never", "policy: Never", "withinClusterQueue: Never"):
        assert setting in master


def test_rederived_orchestrator_ceiling_removes_its_recorded_exception() -> None:
    """The former 12-runner exception cannot outlive a rule value at or above 12."""
    orchestrator = "livespec-orchestrator-beads-fabro-cq"
    quota = _cohort_quotas()[orchestrator]
    rule_value = max(_CEILING_MULTIPLE * quota, _CEILING_FLOOR)
    derivation = _DERIVATION.read_text(encoding="utf-8")

    assert rule_value == 50
    assert rule_value >= 12
    # Its DERIVATION.md row is gone with it: every row there must match an
    # exception here (test_every_recorded_exception_is_a_derivation_row_...).
    assert orchestrator not in _RECORDED_CEILING_EXCEPTIONS
    assert (
        "The Recorded exceptions to the rule table remains absent because 52 is not below 12."
        in " ".join(derivation.split())
    )


def test_every_recorded_exception_is_a_derivation_row_that_still_permits_borrowing() -> None:
    """Each exception is a DERIVATION.md row, matches the manifests, and keeps maxRunners > quota.

    The row is where the measurement and the acceptance check live, so an
    exception in this file without one is a number nobody can audit. And an
    exception may move a ceiling off the rule but never down to the share: the
    section requires the ceiling to be "large enough that a repository can
    borrow unused capacity beyond its guaranteed share".
    """
    derivation = _DERIVATION.read_text(encoding="utf-8")
    assert _EXCEPTIONS_HEADING in derivation
    # Only the exceptions subsection: other tables in the file share the shape.
    section = derivation.split(_EXCEPTIONS_HEADING, 1)[1].split("\n#", 1)[0]
    rows = {
        _EXCEPTION_QUEUES.get(row.group("repo"), row.group("repo")): row
        for row in _EXCEPTION_ROW.finditer(section)
    }
    assert set(rows) == set(_RECORDED_CEILING_EXCEPTIONS), (
        f"every recorded exception needs exactly one DERIVATION.md row and no row may "
        f"outlive its exception; rows={sorted(rows)} "
        f"exceptions={sorted(_RECORDED_CEILING_EXCEPTIONS)}"
    )
    quotas = _cohort_quotas()
    ceilings = _scale_set_ceilings()
    for cq, ceiling in _RECORDED_CEILING_EXCEPTIONS.items():
        row = rows[cq]
        assert int(row.group("quota")) == quotas[cq], (cq, row.group(0))
        assert int(row.group("rule")) == max(_CEILING_MULTIPLE * quotas[cq], _CEILING_FLOOR)
        assert int(row.group("max")) == ceiling == ceilings[cq][1], (cq, row.group(0))
        assert ceiling > quotas[cq], (
            f"{cq}: an exception may waive the rule but not the borrowing clause; "
            f"maxRunners={ceiling} nominalQuota={quotas[cq]}"
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
