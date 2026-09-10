"""Consumer-tier: two more `SPECIFICATION/scenarios.md` JIT admission scenarios.

    "JIT fleet capacity borrows fairly without exceeding 482 runners"
    "JIT circuit state survives restart without a reburst"

WHAT THIS TREE OWNS OF THEM. As the sibling
`tests/consumer/test_jit_admission_scenarios.py` already states for the other
three JIT scenarios: the controller these describe is ARC's, its source is not
in this repository, and no test here executes it. `ci-runner/k3s/phase2/
README.md` §"What does NOT move to Kueue/ARC" is this repository's own record
of that split. What IS here is the committed gitops the controller runs UNDER —
the one cohort its admissions are apportioned within, the one extended resource
every admission is denominated in, the node profile that declares that
resource's capacity, and the boot-and-timer units that put the capacity back
after a restart. Every clause below is asserted against those files, and only
where the clause has a decidable consequence in them.

The readers here are DELIBERATELY NOT shared with `tests/spec/
test_jit_admission_budget.py`, for the reason the sibling scenario file gives:
that suite registers a `non-functional-requirements.md` heading at unit tier,
and importing from it would make a `scenarios.md` heading's coverage depend on
a unit-tier module, which is the coupling the tier rule exists to prevent.
Neither is this file a restatement of it. That suite asserts the two terms of
the admission `min()` (each repository's ceiling against its own fair share,
and the fair shares against the declared capacity) and scans for a literal 964.
This file asserts the properties those numbers are only MEANINGFUL under: that
the shares denominate ONE borrowable pool rather than several, that nothing
committed forbids the borrowing the scenario permits, that no doubling of the
registered capacity can reach the forbidden figure, and that the bound itself
survives the restart the second scenario is about.
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
_FLAVOR_FILE = _KUEUE_DIR / "resource-flavor.yaml"
_EXTENDED_RESOURCE_DIR = _PHASE2 / "node-extended-resource"
_REAPPLY_SERVICE = _EXTENDED_RESOURCE_DIR / "reapply-node-extended-resource.service"
_REAPPLY_TIMER = _EXTENDED_RESOURCE_DIR / "reapply-node-extended-resource.timer"
_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_INSTALL_NODE = _PHASE2 / "install-node.sh"
_SERVER_PROFILE = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles" / "poweredge-xubuntu.env"
)

# The one cohort every routed scale set's pods are admitted within, the one
# extended resource their quotas are denominated in, and the one flavor that
# resource is offered under.
_COHORT = "fleet-ci-runner-pool"
_CHURN_SLOT = "ci-runner.io/churn-slot"
_FLAVOR = "churn-slot-flavor"

# The section's own two figures: the physical host-wide cap, and the doubling
# no configuration or recovery path may derive.
_PHYSICAL_CAP = 482
_FORBIDDEN_DOUBLING = 964

# Kueue's two knobs that CAP what a cohort member may take from, or give to,
# the shared pool. Both are absent from a queue that borrows and lends without
# limit, which is the posture the scenario's "repositories MAY borrow unused
# fair capacity" requires; a stated `0` is the spelling that forbids it.
_BORROW_KNOBS = ("borrowingLimit", "lendingLimit")

_DOC_SEPARATOR = re.compile(r"^---$", re.MULTILINE)
_KIND = re.compile(r"^kind:\s*(?P<kind>\S+)$", re.MULTILINE)
_NAME = re.compile(r"^  name:\s*(?P<name>\S+)", re.MULTILINE)
_COHORT_NAME = re.compile(r"^  cohortName:\s*(?P<cohort>\S+)", re.MULTILINE)
_COVERED = re.compile(r"^\s*- coveredResources:\s*\[(?P<covered>[^\]]*)\]", re.MULTILINE)
# The flavor a resource group is offered under is the `- name:` DIRECTLY under
# its `flavors:` key. Anchoring on that key matters: the resource entries
# nested below carry `- name:` lines too, and a bare match reads the resource's
# own name as a second flavor.
_FLAVOR_NAME = re.compile(r"^\s*flavors:\s*$\n\s*- name:\s*(?P<flavor>\S+)\s*$", re.MULTILINE)
_NOMINAL_QUOTA = re.compile(r"^\s*nominalQuota:\s*(?P<quota>\d+)\s*$", re.MULTILINE)
_WEIGHT = re.compile(r"^\s*weight:\s*(?P<weight>\S+)\s*$", re.MULTILINE)
_MAX_RUNNERS = re.compile(r"^\s*maxRunners:\s*(?P<max>\d+)\s*$", re.MULTILINE)
_QUEUE_NAME = re.compile(r"^\s*kueue\.x-k8s\.io/queue-name:\s*(?P<lq>\S+)\s*$", re.MULTILINE)
_ADMISSION_CAPACITY = re.compile(r"^ADMISSION_CAPACITY_C=(?P<capacity>\d+)\s*$", re.MULTILINE)


def _active_lines(*, path: Path) -> list[str]:
    """A committed file's ACTIVE lines — blank and comment lines stripped.

    Every file this suite reads carries a long design header and inline
    rationale, and several of those comments quote the very keys and figures
    asserted below. A substring search over the raw bytes would match a key
    that is switched OFF or a number that is merely being explained.
    """
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _cohort_queue_documents() -> dict[str, str]:
    """Each cohort-member ClusterQueue document, keyed by its queue name."""
    documents: dict[str, str] = {}
    for path in sorted(_KUEUE_DIR.glob("cluster-queue-*.yaml")):
        for document in _DOC_SEPARATOR.split(path.read_text(encoding="utf-8")):
            kind = _KIND.search(document)
            cohort = _COHORT_NAME.search(document)
            name = _NAME.search(document)
            if (
                kind is not None
                and kind.group("kind") == "ClusterQueue"
                and cohort is not None
                and cohort.group("cohort") == _COHORT
                and name is not None
            ):
                documents[name.group("name")] = document
    return documents


def _routed_ceilings() -> dict[str, int]:
    """Each queue-routed scale set's values file, mapped to its `maxRunners`.

    A values file naming no LocalQueue, or declaring no ceiling, is not a
    routed scale set: that is how the committed template and the host-unique
    release stay out of the arithmetic.
    """
    ceilings: dict[str, int] = {}
    for path in sorted(_ARC_DIR.glob("values-*.yaml")):
        source = path.read_text(encoding="utf-8")
        queue = _QUEUE_NAME.search(source)
        ceiling = _MAX_RUNNERS.search(source)
        if queue is None or ceiling is None:
            continue
        ceilings[path.name] = int(ceiling.group("max"))
    return ceilings


def _registered_capacity() -> int:
    """The pool node's churn-slot capacity C, from its own committed profile."""
    declared = _ADMISSION_CAPACITY.search(_SERVER_PROFILE.read_text(encoding="utf-8"))
    assert declared is not None, (
        f"the node's admission capacity C must be a value of its committed profile — it is "
        f"the physical term of the section's min() and the bound a restart has to put back; "
        f"profile={_SERVER_PROFILE.relative_to(_REPO_ROOT)}"
    )
    return int(declared.group("capacity"))


def test_the_fair_shares_denominate_one_borrowable_pool_no_doubling_of_which_reaches_the_cap() -> (
    None
):
    """§"JIT fleet capacity borrows fairly without exceeding 482 runners".

    BORROWS: "repositories MAY borrow unused fair capacity", and the term they
    borrow against is a "fair share of REMAINING HOST-WIDE capacity". Both
    words are load-bearing and both are decidable here. Host-wide requires the
    shares to be denominated in ONE resource offered under ONE flavor: give a
    queue a second covered resource or a second flavor and its share is
    apportioned out of a pool the others cannot see, so unused capacity is
    unreachable — the queues still admit, the manifests still apply, and the
    borrowing the section permits silently stops happening. And borrowing
    requires that nothing committed CAPS it: Kueue's `borrowingLimit` and
    `lendingLimit` are the two knobs that do, and a queue that borrows and
    lends freely states neither.

    FAIRLY: the specification states no per-repository priority
    differentiation, so no cohort member may weigh itself above another. The
    weighting that IS intended lives in the nominal quotas.

    WITHOUT EXCEEDING 482: the fleet's active runners are bounded by the pool
    they are admitted out of, so the assertion is against that pool rather than
    against any paper ceiling — the shares must sum to exactly the capacity the
    node registers (a sum below it strands capacity; a sum above it admits work
    the scheduler cannot place), and no single repository's ceiling may exceed
    the whole pool, or the `min()`'s doubled-ceiling term would never bind and
    one repository could hold every slot. "or imply 964 capacity" is the
    section's warning about a DOUBLING, so the bound is asserted doubled: even
    a path that counted the registered capacity twice — the shape that had two
    pools jointly implying 964 during the podman side-by-side window — must
    stay under the cap.
    """
    queues = _cohort_queue_documents()
    assert queues, (
        f"the cohort's ClusterQueues must be committed for any of this to be readable; "
        f"none found under {_KUEUE_DIR.relative_to(_REPO_ROOT)}"
    )

    misdenominated = sorted(
        f"{name}: covered={sorted(covered)} flavors={sorted(flavors)}"
        for name, document in queues.items()
        for covered in [
            {
                entry.strip().strip('"')
                for entry in _COVERED.search(document).group("covered").split(",")
            }
            if _COVERED.search(document) is not None
            else set[str]()
        ]
        for flavors in [{match.group("flavor") for match in _FLAVOR_NAME.finditer(document)}]
        if covered != {_CHURN_SLOT} or flavors != {_FLAVOR}
    )
    assert not misdenominated, (
        f"every cohort member must quota exactly `{_CHURN_SLOT}` under exactly the one "
        f"`{_FLAVOR}` flavor, or the shares are apportioned out of pools that cannot see "
        f"each other and unused fair capacity is not borrowable at all; wrong={misdenominated}"
    )
    flavor_source = _FLAVOR_FILE.read_text(encoding="utf-8")
    flavor_kind = _KIND.search(flavor_source)
    flavor_declared = _NAME.search(flavor_source)
    assert (
        flavor_kind is not None
        and flavor_kind.group("kind") == "ResourceFlavor"
        and flavor_declared is not None
        and flavor_declared.group("name") == _FLAVOR
    ), (
        f"the one flavor every cohort member requests from must itself be committed, or the "
        f"queues resolve against a flavor that exists only on whichever cluster last had it "
        f"applied by hand; flavor file={_FLAVOR_FILE.relative_to(_REPO_ROOT)}"
    )

    capped = sorted(
        f"{name}: {line.strip()}"
        for name, document in queues.items()
        for line in document.splitlines()
        if line.strip() and not line.strip().startswith("#")
        for knob in _BORROW_KNOBS
        if line.strip().startswith(f"{knob}:")
    )
    assert not capped, (
        f"no cohort member may cap what it takes from or gives to the shared pool: the "
        f"section says repositories MAY borrow unused fair capacity, and {_BORROW_KNOBS} are "
        f"the two committed knobs that forbid it; stated={capped}"
    )

    weights = {
        name: [match.group("weight") for match in _WEIGHT.finditer(document)]
        for name, document in queues.items()
    }
    distinct = {weight for stated in weights.values() for weight in stated}
    assert len(distinct) <= 1, (
        f"borrowing is FAIR only while no member weighs itself above another — the "
        f"specification states no per-repository priority differentiation, and the intended "
        f"weighting lives in the nominal quotas; weights={weights}"
    )

    shares = {
        name: sum(int(match.group("quota")) for match in _NOMINAL_QUOTA.finditer(document))
        for name, document in queues.items()
    }
    capacity = _registered_capacity()
    assert sum(shares.values()) == capacity, (
        f"the cohort's fair shares must sum to exactly the churn-slot capacity the node "
        f"registers: below it the pool strands capacity nobody can borrow, above it Kueue "
        f"admits pods the scheduler then cannot place, and both look like a healthy pool; "
        f"shares={shares} sum={sum(shares.values())} capacity={capacity}"
    )

    ceilings = _routed_ceilings()
    assert ceilings, "the routed scale sets must be committed for their ceilings to be readable"
    over_pool = sorted(
        f"{name}: {ceiling}" for name, ceiling in ceilings.items() if ceiling > capacity
    )
    assert not over_pool, (
        f"no repository's logical ceiling may exceed the whole churn-slot pool ({capacity}): "
        f"the doubled-ceiling term of the section's min() would then never bind, and one "
        f"repository's backlog could hold every slot in the fleet; over={over_pool}"
    )

    # Both terms below are DERIVED from the committed tree — the capacity from
    # the node profile, the ceilings from the routed scale sets — so each can
    # fail. A comparison between this section's own two figures could not: 964
    # is two 482s by construction, and asserting that relation would restate
    # the constants rather than judge the pool.
    assert 0 < capacity * 2 < _PHYSICAL_CAP, (
        f"the section forbids any configuration or recovery path DERIVING "
        f"{_FORBIDDEN_DOUBLING} — the shape that produced it was two pools each near the "
        f"{_PHYSICAL_CAP} cap counted together — so even a path that counted the registered "
        f"capacity twice must stay under the cap, which is what keeps the doubling "
        f"unreachable rather than merely unstated; capacity={capacity}"
    )
    demanded = sum(ceilings.values())
    assert 0 < demanded <= _PHYSICAL_CAP, (
        f"and the fleet's active runners must never exceed {_PHYSICAL_CAP}: every routed "
        f"repository asking for its whole logical ceiling at once is the most the forge can "
        f"admit, so that total is the fleet figure the section bounds; "
        f"ceilings={ceilings} demanded={demanded}"
    )


def test_the_bound_a_restart_must_recover_is_durable_reapplied_first_and_cannot_loop() -> None:
    """§"JIT circuit state survives restart without a reburst".

    The shared state this tree owns is not the circuit itself — that is ARC's,
    and `ci-runner/k3s/phase2/README.md` §"What does NOT move to Kueue/ARC"
    says so — it is the BOUND every admission passes through: the node's
    registered `ci-runner.io/churn-slot` capacity. Lose it across a restart and
    the scenario's two prohibited outcomes are exactly what happens: a
    `kubectl patch node --subresource=status` is not a device-plugin
    registration, so a kubelet restart can drop it silently, and the queues
    then advertise a capacity the node no longer carries.

    RECOVERED BEFORE ADMITTING: the unit must be pulled in at boot and ordered
    BEFORE the converge that applies the queues, not merely timed — the first
    real reboot showed the timer firing after the converge had already begun
    applying queues denominated in a resource that was not yet there.

    RECOVERY THAT DOES NOT DEPEND ON ITSELF: `OnUnitActiveSec` re-arms only
    from a SUCCESSFUL activation, so a boot in which the unit failed by
    dependency leaves that trigger with no next elapse at all — measured on
    2026-09-04, when the node carried no capacity for eighty minutes behind an
    armed and silent timer. A wall-clock `OnCalendar` trigger is the one that
    fires regardless of the service's own history, and it is also what makes
    `Persistent=true` effective, since that setting applies to `OnCalendar`
    timers alone.

    NO NEW BURST, NO RESTART LOOP: the capacity restored is the one already
    decided, never a freshly derived (larger) one — the unit ships a
    deliberately un-defaulted placeholder so an un-edited copy fails loudly
    instead of quietly reapplying the wrong number, the node runbook reads the
    value from the profile's `ADMISSION_CAPACITY_C`, and the converge's own
    assertion reads it back off the INSTALLED unit rather than re-deriving it.
    And the recovery path cannot become the infinite restart loop the scenario
    forbids: a `oneshot` driven by a timer has no restart policy to run away
    with, which a `Restart=always` service would.
    """
    service = _active_lines(path=_REAPPLY_SERVICE)
    timer = _active_lines(path=_REAPPLY_TIMER)

    assert "Type=oneshot" in service, (
        f"the reapply service must be a oneshot: it is driven by a timer and by boot, and a "
        f"long-running service with a restart policy is precisely the infinite restart loop "
        f"the scenario forbids; active lines={service}"
    )
    restart_policies = [line for line in service if line.startswith("Restart=")]
    assert not restart_policies, (
        f"the reapply service must state no restart policy — a `Restart=always` on a unit "
        f"that exits, ordered behind a dependency that can fail at boot, is a restart loop "
        f"wearing a reconciliation's name; stated={restart_policies}"
    )
    assert "Before=converge-ci-stack.service" in service and "After=k3s.service" in service, (
        f"the capacity must be back BEFORE the converge applies the queues that are "
        f"denominated in it, and after the API server it patches is up — otherwise recovery "
        f"races the very admission it is supposed to bound; active lines={service}"
    )
    assert "WantedBy=multi-user.target" in service, (
        f"the unit must be pulled in at boot in its own right: leaving recovery to the timer "
        f"alone is what let a converge start applying queues before the resource existed; "
        f"active lines={service}"
    )

    triggers = [
        line for line in timer if line.startswith(("OnBootSec=", "OnUnitActiveSec=", "OnCalendar="))
    ]
    assert len(triggers) == 3 and any(line.startswith("OnCalendar=") for line in triggers), (
        f"the timer must carry a WALL-CLOCK trigger beside the boot and activation ones: "
        f"`OnUnitActiveSec` re-arms only from a successful activation, so a dependency-failed "
        f"boot leaves it with no next elapse and the node runs unbounded behind an armed, "
        f"silent timer; triggers={triggers}"
    )
    assert "Persistent=true" in timer, (
        f"a missed run must be caught up at the next activation rather than skipped — the "
        f"catch-up applies to OnCalendar timers, which is the trigger above; "
        f"active lines={timer}"
    )

    exec_starts = [line for line in service if line.startswith("ExecStart=")]
    assert len(exec_starts) == 1 and exec_starts[0].endswith("CAPACITY_PLACEHOLDER"), (
        f"the shipped unit must carry an un-defaulted placeholder for the capacity: a "
        f"defaulted number would let an un-edited copy silently reapply a bound that is not "
        f"this node's, which is a reburst by another name; ExecStart={exec_starts}"
    )

    runbook = _INSTALL_NODE.read_text(encoding="utf-8")
    assert "ADMISSION_CAPACITY_C" in runbook, (
        f"the node runbook must READ the capacity from the profile rather than take it on "
        f"the command line, or the number the recovery path restores is whatever the last "
        f"operator typed; runbook={_INSTALL_NODE.relative_to(_REPO_ROOT)}"
    )
    converge = _CONVERGE.read_text(encoding="utf-8")
    assert "CONVERGE_CHURN_CAPACITY" in converge and "systemctl show" in converge, (
        f"the converge must learn the intended capacity by READING IT BACK off the installed "
        f"reapply unit, not by re-deriving it: a second derivation is a second place for the "
        f"bound to drift, and drift upward is the reburst; converge="
        f"{_CONVERGE.relative_to(_REPO_ROOT)}"
    )
