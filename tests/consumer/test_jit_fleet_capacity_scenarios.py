"""Consumer-tier: the two `SPECIFICATION/scenarios.md` JIT fleet-capacity scenarios.

    "JIT fleet capacity borrows fairly without exceeding 482 runners"
    "JIT circuit state survives restart without a reburst"

WHAT THIS TREE OWNS OF THEM, STATED PLAINLY. Both scenarios describe ARC's
controller and the host's service manager. Neither is source in this repository
and no test here executes either. What IS here — and what a consumer of this
repository actually gets — is the committed gitops and unit files they run
UNDER: the per-repository scale sets, the Kueue cohort that admits their pods,
and the systemd units that restore the pool's shared state and restart its
supervisors. Every clause below is asserted against those files, and only where
a clause has a decidable consequence in them. `ci-runner/k3s/phase2/README.md`
§"What does NOT move to Kueue/ARC" is the record of which half of the section
lands where: the installation-wide REST point budget and the circuit breaker
itself are ARC's OWN controller's concern and a confirmed GAP rather than
anything committed here. So the restart scenario is asserted as what a restart
of a supervisor can and cannot do TO THE POOL — not as the circuit's internal
bookkeeping, which this repository does not hold.

Every number and directive below is hand-maintained in a DIFFERENT file, so
every way they drift apart is silent: a wrong one is a valid manifest or a valid
unit, applies cleanly, and produces a pool that borrows less than it may, or
bursts on a restart that should have been quiet.

WHY THE 482 CLAUSE IS ASSERTED AGAINST THE NODE'S FINITE SLOT RATHER THAN
AGAINST KUEUE. `VALIDATION_CHECKLIST.md` item 7 measured it live on 2026-08-16:
with two synthetic queues whose combined `nominalQuota` equalled the node's
capacity, Kueue marked ALL six submitted workloads `Admitted` while exactly four
pods ran and two stayed `Pending`. Kueue's own admission is therefore NECESSARY
BUT NOT SUFFICIENT; the finite `ci-runner.io/churn-slot` extended resource,
enforced by the Kubernetes scheduler, is the real and final gate. A scale set
whose runner does not REQUEST that slot is invisible to it and borrows without
any bound at all.

CONTROL ARMS. Every reader here takes TEXT rather than a path, so each test ends
by feeding the SAME reader a synthetic counter-example and asserting it IS
convicted. Without that arm, a reader whose regex quietly stopped matching would
report no violations and the test would pass green while asserting nothing.

The readers are DELIBERATELY NOT shared with the sibling
`tests/spec/test_jit_admission_budget.py`, which registers a
`non-functional-requirements.md` heading at unit tier: importing one from the
other would make a scenario's coverage depend on a unit-tier module, which is
the coupling the tier rule exists to prevent. They are not shared with
`tests/consumer/test_jit_admission_scenarios.py` either — a cross-module import
of another test's private names is what `private_calls` and pyright's
`reportPrivateUsage` both forbid.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_RUNNER = _REPO_ROOT / "ci-runner"
_PHASE2 = _CI_RUNNER / "k3s" / "phase2"
_ARC_DIR = _PHASE2 / "arc"
_KUEUE_DIR = _PHASE2 / "kueue"

# The unit that applies the queues, the ARC controller and every scale set — the
# moment the pool becomes able to admit demand again after a restart.
_CONVERGE_UNIT = _PHASE2 / "reconstruct" / "converge-ci-stack.service"
_CONVERGE_UNIT_NAME = "converge-ci-stack.service"
# The two units that restore shared state the k3s datastore does not keep across
# a boot (it is tmpfs): the node's churn-slot capacity, and the App installation
# secret every mint pair is drawn against.
_STATE_RESTORING_UNITS = (
    _PHASE2 / "node-extended-resource" / "reapply-node-extended-resource.service",
    _CI_RUNNER / "k3s" / "secret-reinjection" / "inject-github-app-secret.service",
)
# The long-lived JIT supervisor its service manager may restart, and the
# single-use ephemeral runner it mints.
_SUPERVISOR_UNIT = _CI_RUNNER / "gate-runner" / "gate-runner-supervisor.service"
_EPHEMERAL_RUNNER_UNIT = _CI_RUNNER / "gate-runner" / "gate-runner@.service"

_COHORT = "fleet-ci-runner-pool"
_CHURN_SLOT = "ci-runner.io/churn-slot"
_PHYSICAL_CAP = 482

_DOC_SEPARATOR = re.compile(r"^---$", re.MULTILINE)
_KIND = re.compile(r"^kind:\s*(?P<kind>\S+)$", re.MULTILINE)
_NAME = re.compile(r"^  name:\s*(?P<name>\S+)", re.MULTILINE)
_COHORT_NAME = re.compile(r"^  cohortName:\s*(?P<cohort>\S+)", re.MULTILINE)
_CLUSTER_QUEUE = re.compile(r"^  clusterQueue:\s*(?P<cq>\S+)", re.MULTILINE)
_NOMINAL_QUOTA = re.compile(r"^\s+nominalQuota:\s*(?P<quota>\d+)\s*$", re.MULTILINE)
_BORROWING_LIMIT = re.compile(r"^\s+borrowingLimit:\s*(?P<limit>\S+)\s*$", re.MULTILINE)
_MAX_RUNNERS = re.compile(r"^\s*maxRunners:\s*(?P<max>\d+)\s*$", re.MULTILINE)
_MIN_RUNNERS = re.compile(r"^\s*minRunners:\s*(?P<min>\d+)\s*$", re.MULTILINE)
_QUEUE_NAME = re.compile(r"^\s*kueue\.x-k8s\.io/queue-name:\s*(?P<lq>\S+)\s*$", re.MULTILINE)
_SLOT_QUANTITY = re.compile(rf'^{re.escape(_CHURN_SLOT)}:\s*"?(?P<slots>\d+)"?$')

# The synthetic counter-examples the control arms feed back through the readers.
_CONTROL_QUEUE_DOCUMENT = """
apiVersion: kueue.x-k8s.io/v1beta2
kind: ClusterQueue
metadata:
  name: control-cq
spec:
  cohortName: fleet-ci-runner-pool
  resourceGroups:
    - coveredResources: ["ci-runner.io/churn-slot"]
      flavors:
        - name: churn-slot-flavor
          resources:
            - name: "ci-runner.io/churn-slot"
              nominalQuota: 1
              borrowingLimit: 0
"""
_CONTROL_VALUES = """\
runnerScaleSetName: "control"
template:
  metadata:
    labels:
      kueue.x-k8s.io/queue-name: control-lq
minRunners: 3
maxRunners: 6
"""
_CONTROL_UNIT = """\
[Service]
Restart=always
ExecStart=/bin/true
"""


def _cohort_documents() -> list[str]:
    """Every YAML document across the committed ClusterQueue manifests."""
    return [
        document
        for path in sorted(_KUEUE_DIR.glob("cluster-queue-*.yaml"))
        for document in _DOC_SEPARATOR.split(path.read_text(encoding="utf-8"))
    ]


def _cohort_members(*, documents: list[str]) -> dict[str, tuple[int, str | None]]:
    """Each cohort-member ClusterQueue mapped to (churn-slot `nominalQuota`, stated limit)."""
    members: dict[str, tuple[int, str | None]] = {}
    for document in documents:
        kind = _KIND.search(document)
        cohort = _COHORT_NAME.search(document)
        if kind is None or kind.group("kind") != "ClusterQueue":
            continue
        if cohort is None or cohort.group("cohort") != _COHORT:
            continue
        name = _NAME.search(document)
        quota = _NOMINAL_QUOTA.search(document)
        assert name is not None and quota is not None and _CHURN_SLOT in document, (
            f"a `{_COHORT}` member must carry a name and one `{_CHURN_SLOT}` nominalQuota — "
            f"that quota IS the repository's fair share; document={document!r}"
        )
        limit = _BORROWING_LIMIT.search(document)
        members[name.group("name")] = (
            int(quota.group("quota")),
            None if limit is None else limit.group("limit"),
        )
    return members


def _local_queue_targets(*, documents: list[str]) -> dict[str, str]:
    """Each committed LocalQueue name mapped to the ClusterQueue it feeds."""
    targets: dict[str, str] = {}
    for document in documents:
        kind = _KIND.search(document)
        name = _NAME.search(document)
        cluster_queue = _CLUSTER_QUEUE.search(document)
        if kind is None or kind.group("kind") != "LocalQueue":
            continue
        assert name is not None and cluster_queue is not None, (
            f"a LocalQueue must name itself and the ClusterQueue whose fair share it draws "
            f"on; document={document!r}"
        )
        targets[name.group("name")] = cluster_queue.group("cq")
    return targets


def _routed_scale_sets() -> dict[str, tuple[str, int, str]]:
    """Each queue-routed scale set: values file -> (LocalQueue, `maxRunners`, source).

    A values file that names no LocalQueue, or declares no ceiling, is not a
    routed scale set: that is how the committed template and the host-unique
    release stay out of the arithmetic.
    """
    routed: dict[str, tuple[str, int, str]] = {}
    for path in sorted(_ARC_DIR.glob("values-*.yaml")):
        source = path.read_text(encoding="utf-8")
        queue = _QUEUE_NAME.search(source)
        ceiling = _MAX_RUNNERS.search(source)
        if queue is None or ceiling is None:
            continue
        routed[path.name] = (queue.group("lq"), int(ceiling.group("max")), source)
    return routed


def _borrowing_limited(*, members: dict[str, tuple[int, str | None]]) -> list[str]:
    """Each cohort member that narrows Kueue's default, unlimited within-cohort borrowing."""
    return sorted(
        f"{name}: borrowingLimit={limit}"
        for name, (_, limit) in members.items()
        if limit is not None
    )


def _ceilings_without_borrow_headroom(
    *,
    routed: dict[str, tuple[str, int, str]],
    targets: dict[str, str],
    members: dict[str, tuple[int, str | None]],
) -> list[str]:
    """Each routed scale set whose ceiling cannot borrow, or reaches past what the cohort holds."""
    borrowable = sum(quota for quota, _ in members.values())
    wrong: list[str] = []
    for name, (local_queue, ceiling, _) in sorted(routed.items()):
        member = members.get(targets.get(local_queue, local_queue))
        floor = None if member is None else member[0]
        if floor is not None and floor < ceiling <= borrowable:
            continue
        wrong.append(f"{name}: maxRunners={ceiling} floor={floor} borrowable={borrowable}")
    return wrong


def _slot_quantities(*, source: str) -> dict[str, list[str]]:
    """Each `requests:` / `limits:` block mapped to the churn-slot quantities it declares."""
    quantities: dict[str, list[str]] = {}
    block = ""
    for line in source.splitlines():
        stripped = line.strip()
        if stripped in ("requests:", "limits:"):
            block = stripped.rstrip(":")
        quantity = _SLOT_QUANTITY.match(stripped)
        if quantity is not None:
            quantities.setdefault(block, []).append(quantity.group("slots"))
    return quantities


def _scale_sets_outside_the_finite_slot(*, values: dict[str, str]) -> list[str]:
    """Each scale set whose runner does not request AND limit exactly one churn-slot."""
    outside: list[str] = []
    for name, source in sorted(values.items()):
        declared = _slot_quantities(source=source)
        if declared.get("requests") == ["1"] and declared.get("limits") == ["1"]:
            continue
        outside.append(
            f"{name}: requests={declared.get('requests')} limits={declared.get('limits')}"
        )
    return outside


def _baseline_bursts(*, values: dict[str, str]) -> list[str]:
    """Each scale set declaring a non-zero `minRunners` — a burst its listener mints on start."""
    return sorted(
        f"{name}: minRunners={baseline.group('min')}"
        for name, source in values.items()
        for baseline in [_MIN_RUNNERS.search(source)]
        if baseline is not None and baseline.group("min") != "0"
    )


def _directive(*, unit: str, key: str) -> str | None:
    """A systemd unit directive's value, or None when the unit does not state it."""
    stated = re.search(rf"^{re.escape(key)}=(?P<value>.*)$", unit, re.MULTILINE)
    return None if stated is None else stated.group("value").strip()


def _ordering_gaps(*, converge: str, restorers: dict[str, str]) -> list[str]:
    """Each state-restoring unit not ordered strictly before the converge, in BOTH directions."""
    after = (_directive(unit=converge, key="After") or "").split()
    gaps: list[str] = []
    for name, body in sorted(restorers.items()):
        before = (_directive(unit=body, key="Before") or "").split()
        if name in after and _CONVERGE_UNIT_NAME in before:
            continue
        gaps.append(f"{name}: converge After={after} unit Before={before}")
    return gaps


def _restart_pacing_seconds(*, unit: str) -> int:
    """The seconds the service manager waits before restarting this unit; 0 when unstated."""
    stated = _directive(unit=unit, key="RestartSec")
    digits = "" if stated is None else stated.rstrip("s")
    return int(digits) if digits.isdigit() else 0


def _restarts_without_pacing(*, units: dict[str, str]) -> list[str]:
    """Each restartable unit the service manager would respawn with no interval between tries."""
    unpaced: list[str] = []
    for name, body in sorted(units.items()):
        policy = _directive(unit=body, key="Restart")
        if policy in (None, "no"):
            continue
        if _restart_pacing_seconds(unit=body) > 0:
            continue
        unpaced.append(f"{name}: Restart={policy} RestartSec={_restart_pacing_seconds(unit=body)}")
    return unpaced


def test_fleet_capacity_borrows_fairly_and_the_finite_slot_holds_the_physical_cap() -> None:
    """§"JIT fleet capacity borrows fairly without exceeding 482 runners", both halves.

    BORROWS FAIRLY: "Repositories MAY borrow unused fair capacity." Two committed
    preconditions make that reachable, and each fails silently. On the Kueue side,
    a member that states a `borrowingLimit` narrows the default — which is to
    borrow the cohort's whole unused nominal quota — and `borrowingLimit: 0`
    removes borrowing outright, pinning every repository at its guaranteed floor
    while the pool sits idle. On the ARC side, a repository can only USE borrowed
    capacity below its own `maxRunners`, so a ceiling at or under its fair share
    makes the clause unreachable no matter what the cohort permits; a ceiling
    above what the whole cohort holds is the opposite error, authorizing runners
    no borrowing can ever admit, which is exactly the backlog the Given says must
    wait at the forge rather than exist as pending objects on the host.

    WITHOUT EXCEEDING 482: the bound on all that borrowing is the cohort's summed
    nominal quota, and the thing that ENFORCES it is not Kueue — measured live,
    Kueue admitted six workloads onto four slots (`VALIDATION_CHECKLIST.md` item
    7). It is the node's finite `ci-runner.io/churn-slot` extended resource, so a
    routed scale set that does not request and limit exactly one slot is outside
    the only authoritative gate and its borrowing is bounded by nothing.
    """
    documents = _cohort_documents()
    members = _cohort_members(documents=documents)
    routed = _routed_scale_sets()
    values = {name: source for name, (_, _, source) in routed.items()}
    assert members and routed, (
        f"the cohort and its routed scale sets must both be committed for either half of "
        f"this scenario to be readable; members={sorted(members)} routed={sorted(routed)}"
    )

    limited = _borrowing_limited(members=members)
    assert not limited, (
        f"no cohort member may state a `borrowingLimit`: Kueue's default is to lend the "
        f"cohort's whole unused nominal quota, and any stated limit narrows that — `0` "
        f"removes 'Repositories MAY borrow unused fair capacity' entirely, pinning every "
        f"repository to its guaranteed floor while the pool idles; limited={limited}"
    )

    unborrowable = _ceilings_without_borrow_headroom(
        routed=routed, targets=_local_queue_targets(documents=documents), members=members
    )
    assert not unborrowable, (
        f"each routed scale set's ceiling must sit strictly ABOVE its own fair share and no "
        f"higher than the cohort's total borrowable capacity. At or under the share, the "
        f"repository can never spend capacity a peer lends it; above the cohort total, the "
        f"surplus is a backlog materialized as pending admission objects the host must keep "
        f"reconciling, which the Given says must wait at the forge; wrong={unborrowable}"
    )

    outside = _scale_sets_outside_the_finite_slot(values=values)
    borrowable = sum(quota for quota, _ in members.values())
    assert not outside and 0 < borrowable <= _PHYSICAL_CAP, (
        f"borrowing is bounded by the cohort's summed fair shares, and that bound is "
        f"enforced by the node's finite `{_CHURN_SLOT}` — Kueue's own Admitted condition is "
        f"necessary but NOT sufficient, measured six admitted onto four slots. A scale set "
        f"that does not request AND limit exactly one slot is invisible to the only real "
        f"gate on the {_PHYSICAL_CAP}-runner cap; outside={outside} borrowable={borrowable}"
    )

    control_members = _cohort_members(documents=[_CONTROL_QUEUE_DOCUMENT])
    assert _borrowing_limited(members=control_members) == [
        "control-cq: borrowingLimit=0"
    ], "the borrowing reader must still convict a stated limit"
    assert _ceilings_without_borrow_headroom(
        routed={"control.yaml": ("control-lq", 1, _CONTROL_VALUES)},
        targets={"control-lq": "control-cq"},
        members=control_members,
    ) == [
        "control.yaml: maxRunners=1 floor=1 borrowable=1"
    ], "the headroom reader must still convict a ceiling collapsed onto its own fair share"
    assert _scale_sets_outside_the_finite_slot(values={"control.yaml": _CONTROL_VALUES}) == [
        "control.yaml: requests=None limits=None"
    ], "the finite-slot reader must still convict a scale set that requests no slot"


def test_a_restarted_jit_supervisor_recovers_shared_state_without_a_reburst() -> None:
    """§"JIT circuit state survives restart without a reburst", clause by clause.

    RECOVER THAT SHARED STATE BEFORE ADMITTING DEMAND: this pool's k3s datastore
    is tmpfs, so the shared state a restart must recover lives in two units —
    the node's churn-slot capacity (the host-capacity term itself) and the App
    installation secret every mint pair is drawn against. Both must be ordered
    strictly before `converge-ci-stack.service`, the unit that applies the
    queues, the controller and every scale set and so makes the pool able to
    admit again. The ordering is asserted in BOTH directions, because systemd
    takes either edge alone: drop one and the converge still runs, just against
    a node whose capacity is not yet registered — admitting demand against a
    state it never recovered, with nothing reporting it.

    MUST NOT CREATE A NEW STARTUP BURST: `minRunners` is the one committed knob
    that mints unconditionally. A non-zero baseline is minted by the listener the
    moment it starts, BEFORE any recovered circuit or budget state can gate it —
    and again on every subsequent restart, which is the reburst by construction.

    NOR AN INFINITE RESTART LOOP: the minted ephemeral runner's JIT config is
    single-use, so `Restart=no` is load-bearing — a service manager that respawns
    it replays a consumed registration that can never succeed, forever. The
    long-lived supervisor may restart, but its `RestartSec` must be non-zero:
    systemd's default is 100 ms, which turns a crash-on-start into a tight loop
    re-polling and re-minting as fast as the host allows.
    """
    restorers = {path.name: path.read_text(encoding="utf-8") for path in _STATE_RESTORING_UNITS}
    gaps = _ordering_gaps(converge=_CONVERGE_UNIT.read_text(encoding="utf-8"), restorers=restorers)
    assert len(restorers) == len(_STATE_RESTORING_UNITS) and not gaps, (
        f"every unit that restores the pool's shared state must be ordered strictly before "
        f"`{_CONVERGE_UNIT_NAME}`, the unit that makes the pool able to admit demand again. "
        f"Without both edges the converge still runs — against a node whose churn-slot "
        f"capacity or whose installation secret is not back yet, which is admission before "
        f"recovery and reports nothing; gaps={gaps}"
    )

    values = {name: source for name, (_, _, source) in _routed_scale_sets().items()}
    bursting = _baseline_bursts(values=values)
    assert values and not bursting, (
        f"every routed scale set must declare `minRunners: 0`: a non-zero baseline is minted "
        f"by the listener the moment it starts, ahead of any recovered circuit or budget "
        f"state, and again on every restart — a new startup burst by construction; "
        f"bursting={bursting}"
    )

    ephemeral = _EPHEMERAL_RUNNER_UNIT.read_text(encoding="utf-8")
    supervisor = _SUPERVISOR_UNIT.read_text(encoding="utf-8")
    unpaced = _restarts_without_pacing(
        units={_EPHEMERAL_RUNNER_UNIT.name: ephemeral, _SUPERVISOR_UNIT.name: supervisor}
    )
    assert _directive(unit=ephemeral, key="Restart") == "no" and not unpaced, (
        f"the ephemeral runner's JIT config is single-use, so restarting it replays a "
        f"consumed registration that can never succeed — `Restart=no` is what keeps that "
        f"from being an infinite loop. A supervisor that DOES restart must state a non-zero "
        f"`RestartSec`; systemd's default is 100 ms, which re-polls and re-mints as fast as "
        f"the host allows; unpaced={unpaced}"
    )

    assert _ordering_gaps(converge=_CONTROL_UNIT, restorers={"control.service": _CONTROL_UNIT}) == [
        "control.service: converge After=[] unit Before=[]"
    ], "the ordering reader must still convict units carrying no ordering at all"
    assert _baseline_bursts(values={"control.yaml": _CONTROL_VALUES}) == [
        "control.yaml: minRunners=3"
    ], "the baseline-burst reader must still convict a non-zero minRunners"
    assert _restarts_without_pacing(units={"control.service": _CONTROL_UNIT}) == [
        "control.service: Restart=always RestartSec=0"
    ], "the restart-pacing reader must still convict an unpaced Restart=always"
