"""Consumer-tier: the two `SPECIFICATION/scenarios.md` cache read/write-isolation scenarios.

    "a routed job reads the warm cache and cannot write it"
    "a job's compilation-cache writes are refused"

WHAT THIS TREE OWNS OF THEM, STATED PLAINLY. Both scenarios describe a job pod
RUNNING on the pool: a uv generation already seeded into its work volume, a
cargo source replaced onto the host-local crates proxy, and a redis that
refuses the SET the pod could issue. None of that is Python in this repository
and no test here starts a pod. What IS here — and what the pool is rebuilt from
on every boot — is the committed gitops those runtime facts are produced BY:
the local-path provisioner's `setup` script (which MAKES the seed), the ARC
hook pod template (which points the package managers, carries the job's cache
environment, and records the cache spans), the rendered redis ACL (which
refuses the write, server-side), the cache-span emitter (which turns a recorded
row into the scenario's span), and the pool's own isolation suite (which
re-asserts all of it from inside a real routed job every six hours). Every
clause below is asserted against those files, and only where the clause has a
decidable consequence in them.

THE RUNTIME PROOF IS THE ISOLATION SUITE, NOT THIS FILE, and that division is
deliberate: `ci-runner/k3s/phase2/isolation/cache-negative-tests.sh` runs
INSIDE a routed job on this repository's scale set (the schedule in
`.github/workflows/ci-cache-negative-tests.yml` is its timer) and is the only
thing that can observe a real inode, a real redis reply, or a real pod
environment. What a check-runner test adds is the half that suite cannot check
about itself: that the pool is still CONFIGURED to produce the shape the suite
asserts, and that the suite's own cases can still CONVICT. A case that only
ever reports `pass` is green forever and says nothing — so each required case
is asserted to carry both verdicts.

WHY EACH LAYER IS ASSERTED SEPARATELY. The compilation-cache clauses have a
CLIENT half (`SCCACHE_REDIS_RW_MODE=READ_ONLY`, so a job never attempts a
write) and a SERVER half (the `default` user's ACL, so a write that IS
attempted is refused). The spec requires the refusal to be "enforced
server-side" precisely because the client half is good manners a workflow could
undo; asserting only one of them would stay green while the trust argument was
gone. The warm-uv clauses split the same way: the provisioner's
`cp -a --reflink=always` is what makes every inode the job's own, and
`--reflink=always` rather than a plain `cp -a` is what keeps the fallback a
COLD cache rather than the per-start byte copy the pool's README records as the
cost this replaced.

CONTROL ARMS. Every reader here takes TEXT rather than a path, so each test
ends by feeding the SAME reader a synthetic counter-example and asserting it IS
convicted. Without that arm, a reader whose regex quietly stopped matching
would report no violations and the test would pass green while asserting
nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"

# The provisioner whose `setup` script seeds the current uv generation into a
# work volume BEFORE the volume is bound to any pod.
_PROVISIONER = _PHASE2 / "local-path-provisioner" / "local-path-provisioner.yaml"
# The pod template every routed job's container is built from: the job's cache
# environment, the postStart that points cargo at the host-served tier, and the
# warm-copy rows the preStop emitter replays.
_HOOK_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
# The runtime proof, run from inside a routed job on this repository's scale set.
_ISOLATION_SUITE = _PHASE2 / "isolation" / "cache-negative-tests.sh"
# The script that RENDERS the redis ACL file into the `sccache-redis-acl` Secret.
_SCCACHE_CONVERGE = _PHASE2 / "sccache" / "converge-sccache-redis.sh"
# The emitter that turns a recorded warm-copy row into the scenario's span.
_SPAN_EMITTER = _PHASE2 / "cache-telemetry" / "ci-cache-span.sh"

_SEEDED_UV_PATH = "/__w/_warm/uv"
_PROXY_HOST = "crates-proxy.ci-crates-proxy.svc.cluster.local"
_CACHE_TIERS = ("uv", "registry", "target")
# Every redis ACL grant that would let its user PUT an object into the shared
# compilation cache; `+@all` and `+@admin` include the write categories whole.
_WRITE_GRANTS = ("+@write", "+@all", "+@admin", "+@dangerous", "+set", "+@keyspace")

_SETUP_SCRIPT = re.compile(r"^  setup: \|-\n(?P<body>.*?)\n  [a-z]", re.MULTILINE | re.DOTALL)
_CP_INVOCATION = re.compile(r"(?<![\w./-])cp\s+-[^\n]*")
_WORLD_WRITABLE_SEED_DIRS = re.compile(r"-type d -exec chmod 0777")
_UV_CACHE_DIR = re.compile(
    rf"name:[^\S\n]*UV_CACHE_DIR[^\S\n]*\n\s*value:[^\S\n]*{re.escape(_SEEDED_UV_PATH)}[^\S\n]*\n"
)
_RECORDED_ROW = re.compile(r"^\s*rec\s+(?P<tier>[a-z]+)\s+(?P<hit>\S+)", re.MULTILINE)
_REPORTED_CASE = re.compile(r"report\s+(?P<case>[a-z0-9-]+)\s+(?P<result>pass|fail)\b")
_ACL_USER = re.compile(r"^user\s+(?P<name>\S+)\s+(?P<grants>.*)$", re.MULTILINE)
_ENV_NAME = re.compile(r"^\s*-\s*name:\s*(?P<name>[A-Z][A-Z0-9_]*)\s*$", re.MULTILINE)
_CREDENTIAL_NAME = re.compile(r"(PASSWORD|PASSWD|USERNAME|SECRET|TOKEN|WRITER)")
_RW_MODE = re.compile(r"name:\s*SCCACHE_REDIS_RW_MODE\s*\n\s*value:\s*(?P<mode>\S+)")

# The synthetic counter-examples the control arms feed back through the readers:
# a provisioner that hardlinks the generation into the volume (the seed shape
# whose inodes WERE the generation's, retired 2026-09-06), an ACL that resets
# nothing and lets the unauthenticated user write, a pod template that carries a
# writer credential and ships the compile off the job — and, for the readers
# that assert a REQUIRED artifact is present, the empty document.
_CONTROL_PROVISIONER = """\
apiVersion: v1
data:
  setup: |-
    #!/bin/sh
    # A comment mentioning cp -a --reflink=always must not count as a seed.
    mkdir -p "${VOL_DIR}/_warm"
    cp -al "${src}/." "${VOL_DIR}/_warm/uv"
  teardown: |-
    rm -rf "${VOL_DIR}"
"""
_CONTROL_TEMPLATE = """\
containers:
  - name: $job
    env:
      - name: SCCACHE_REDIS_WRITER_PASSWORD
        value: hunter2
      - name: SCCACHE_DIST_SCHEDULER_URL
        value: http://elsewhere:10600
"""
_CONTROL_ACL = """\
user default on nopass ~* &* +@all
user sccache-writer on >secret ~* &* -@all +@read +@write
"""
_CONTROL_SUITE = """\
report warm-seed-private pass "looked and found nothing wrong"
report redis-set-refused pass "looked and found nothing wrong"
"""


def _provisioner_setup_script(*, manifest: str) -> str:
    """The script the provisioner runs while it provisions a job's work volume."""
    block = _SETUP_SCRIPT.search(manifest)
    return "" if block is None else block.group("body")


def _seed_copies(*, setup: str) -> list[str]:
    """Every `cp` the setup script RUNS to populate a volume — comment lines excluded."""
    runnable = "\n".join(line for line in setup.splitlines() if not line.lstrip().startswith("#"))
    return [match.group(0).rstrip("\\ ").strip() for match in _CP_INVOCATION.finditer(runnable)]


def _seeds_a_job_could_share_or_pay_for(*, setup: str) -> list[str]:
    """Each seeding copy that is not a reflink clone — a shared inode, or a byte copy."""
    return [copy for copy in _seed_copies(setup=setup) if "--reflink=always" not in copy]


def _unwritable_seed_gaps(*, setup: str) -> list[str]:
    """Each missing thing that would leave a job unable to create an entry beside its seed."""
    return [
        missing
        for missing, present in (
            (
                "the seed root is not created world-writable",
                'mkdir -m 0777 "${VOL_DIR}/_warm"' in setup,
            ),
            (
                "seeded directories are never chmod'd for a non-root writer",
                _WORLD_WRITABLE_SEED_DIRS.search(setup) is not None,
            ),
        )
        if not present
    ]


def _index_contact_gaps(*, template: str) -> list[str]:
    """Each tier whose job-visible configuration would still reach the public package index."""
    gaps: list[str] = []
    if _UV_CACHE_DIR.search(template) is None:
        gaps.append(f"uv: UV_CACHE_DIR is not pinned to the seeded {_SEEDED_UV_PATH}")
    if "replace-with" not in template or _PROXY_HOST not in template:
        gaps.append("cargo: no crates-io source replacement onto the host-served proxy")
    return gaps


def _tiers_without_a_recordable_hit(*, template: str) -> list[str]:
    """Each cache tier the postStart never records a warm-copy row for whose hit can be true."""
    recorded: dict[str, set[str]] = {}
    for row in _RECORDED_ROW.finditer(template):
        recorded.setdefault(row.group("tier"), set()).add(row.group("hit"))
    return [
        f"{tier}: recorded hits={sorted(recorded.get(tier, set()))}"
        for tier in _CACHE_TIERS
        if not recorded.get(tier, set()) - {"false"}
    ]


def _span_emission_gaps(*, emitter: str) -> list[str]:
    """Each missing thing that would stop a recorded row becoming the scenario's span."""
    return [
        missing
        for missing, present in (
            ("the `cache.warm-copy` span name", 'span("cache.warm-copy"' in emitter),
            ("the `build.cache.hit` attribute", 'attr("build.cache.hit"' in emitter),
            ("a replay of the recorded rows", 'os.path.join(STATE, "warm-copy.tsv")' in emitter),
        )
        if not present
    ]


def _cases_that_cannot_convict(*, suite: str, required: tuple[str, ...]) -> list[str]:
    """Each required isolation case that never reports a failing verdict."""
    verdicts: dict[str, set[str]] = {}
    for reported in _REPORTED_CASE.finditer(suite):
        verdicts.setdefault(reported.group("case"), set()).add(reported.group("result"))
    return [
        f"{case}: verdicts={sorted(verdicts.get(case, set()))}"
        for case in required
        if verdicts.get(case, set()) != {"pass", "fail"}
    ]


def _acl_users_granted_write(*, converge: str) -> list[str]:
    """Each redis user the rendered ACL grants a capability that could write the cache."""
    return sorted(
        f"{user.group('name')}: {grant}"
        for user in _ACL_USER.finditer(converge)
        for grant in _WRITE_GRANTS
        if grant in user.group("grants").split()
    )


def _acl_users_without_a_reset(*, converge: str) -> list[str]:
    """Each redis user whose grants are not built up from an explicit `-@all` reset."""
    return sorted(
        user.group("name")
        for user in _ACL_USER.finditer(converge)
        if "-@all" not in user.group("grants").split()
    )


def _job_visible_writer_credentials(*, template: str) -> list[str]:
    """Each env name a job pod would carry that could authenticate a write to a shared cache."""
    return sorted(
        name
        for name in (env.group("name") for env in _ENV_NAME.finditer(template))
        if _CREDENTIAL_NAME.search(name) is not None
    )


def _job_client_write_posture(*, template: str) -> str | None:
    """The read/write mode a job's compilation-cache client runs under; None when unstated."""
    stated = _RW_MODE.search(template)
    return None if stated is None else stated.group("mode")


def _local_compile_gaps(*, template: str) -> list[str]:
    """Each way the pod template would stop a cache MISS being compiled inside the job."""
    offloaded = sorted(
        {
            env.group("name")
            for env in _ENV_NAME.finditer(template)
            if env.group("name").startswith("SCCACHE_DIST")
        }
    )
    wrapped = "rustc-wrapper" in template
    gaps = [] if wrapped else ["no `rustc-wrapper`: nothing wraps a local compile"]
    if offloaded:
        gaps.append(f"the compile is shipped off the job: {offloaded}")
    if "/dev/tcp/$redis_host/6379" not in template:
        gaps.append("the wrapper stanza is not gated on the backend answering a probe")
    return gaps


def test_a_routed_job_reads_the_warm_cache_and_cannot_write_it() -> None:
    """§"a routed job reads the warm cache and cannot write it", clause by clause.

    RESOLVE FROM THE CACHE WITHOUT CONTACTING THE PACKAGE INDEX: two tiers, two
    committed mechanisms, each silent when wrong. uv reads whatever
    `UV_CACHE_DIR` names, so the env must name the path the provisioner seeded
    — point it anywhere else and uv creates a cold cache there and resolves
    from PyPI, with no error anywhere. cargo is host-SERVED rather than seeded,
    so the postStart's `[source.crates-io] replace-with` stanza onto the
    node-local crates proxy is the whole of "without contacting the index"; a
    template that writes no stanza leaves cargo talking to crates.io exactly as
    before, which is a slow job rather than a failing one.

    MUST NOT RESOLVE TO A SHARED INODE, AND A WRITE MUST LEAVE THE GENERATION
    UNCHANGED: the seed is made by the provisioner's `setup` script, and the
    flag on that one `cp` IS the clause. `cp -al` (the hardlink seed of
    2026-09-04) gives the job the GENERATION'S inodes, so a write from inside
    the job lands in the shared tree — the trust hazard this scenario was
    re-based onto closing. A plain `cp -a` is private but pays a per-start byte
    copy, which the pool's README records as the cost the reflink replaced.
    Only `cp -a --reflink=always` is both: every file a new inode of this
    volume, and a filesystem without reflink FAILS the copy into a cold cache
    rather than falling back to bytes.

    MUST STILL BE ABLE TO CREATE A NEW ENTRY BESIDE THE SEED: the seeded files
    keep the generation's root ownership, so a non-root job can only add
    entries where the setup script widened the directory modes. A protected but
    unusable cache satisfies the isolation half of this scenario and breaks the
    tier.

    A `cache.warm-copy` SPAN WITH `build.cache.hit` TRUE FOR EACH TIER: the
    postStart RECORDS one row per tier and the preStop emitter replays them, so
    the clause needs both halves. A tier recorded only with a literal `false`
    (the kill-switch and canary arms record exactly that on purpose) can never
    carry the hit this scenario requires.

    THE RUNTIME HALF is the pool's isolation suite, and what this asserts about
    it is that its `warm-seed-private` case can still CONVICT: a case with only
    a passing verdict is green forever.
    """
    setup = _provisioner_setup_script(manifest=_PROVISIONER.read_text(encoding="utf-8"))
    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")
    copies = _seed_copies(setup=setup)
    unsafe = _seeds_a_job_could_share_or_pay_for(setup=setup)
    assert copies and not unsafe, (
        f"every copy the provisioner makes into a work volume must be "
        f"`cp -a --reflink=always`: `-l` hands the job the GENERATION'S inodes, so a write "
        f"from inside the job reaches the shared tree, and a plain `cp -a` is private but "
        f"pays the per-start byte copy the reflink seed replaced. `--reflink=always` also "
        f"makes a filesystem without reflink leave NO seed (cold) rather than silently "
        f"copying bytes; copies={copies} unsafe={unsafe}"
    )

    unwritable = _unwritable_seed_gaps(setup=setup)
    assert not unwritable, (
        f"the seeded tree keeps the generation's root ownership, so a non-root job can add "
        f"an entry beside the seed only where the setup script widened the directory modes "
        f"— without that the cache is isolated and useless, which fails this scenario's "
        f"third Then as surely as a shared inode fails its second; gaps={unwritable}"
    )

    contacting = _index_contact_gaps(template=template)
    assert not contacting, (
        f"the job's dependency sync must resolve from the pool: uv reads `UV_CACHE_DIR` and "
        f"nothing else, so it must name the seeded {_SEEDED_UV_PATH}, and cargo reaches the "
        f"host only through the postStart's crates-io source replacement. Either one wrong "
        f"is a job that quietly fetches from the public index; gaps={contacting}"
    )

    coldest = _tiers_without_a_recordable_hit(template=template)
    emission = _span_emission_gaps(emitter=_SPAN_EMITTER.read_text(encoding="utf-8"))
    assert not coldest and not emission, (
        f"each tier must record a `cache.warm-copy` row whose hit CAN be true, and the "
        f"emitter must replay those rows as `cache.warm-copy` spans carrying "
        f"`build.cache.hit` — the kill-switch and canary arms record a literal false on "
        f"purpose, so a tier recorded only that way can never report the hit this scenario "
        f"requires; tiers={coldest} emitter={emission}"
    )

    toothless = _cases_that_cannot_convict(
        suite=_ISOLATION_SUITE.read_text(encoding="utf-8"), required=("warm-seed-private",)
    )
    assert not toothless, (
        f"the runtime proof of this scenario is the pool's isolation suite running inside a "
        f"routed job; a case that reports only `pass` is green forever and observes nothing "
        f"— each required case must carry a failing verdict too; cases={toothless}"
    )

    control_setup = _provisioner_setup_script(manifest=_CONTROL_PROVISIONER)
    assert _seeds_a_job_could_share_or_pay_for(setup=control_setup) == [
        'cp -al "${src}/." "${VOL_DIR}/_warm/uv"'
    ], "the seed reader must still convict a hardlink seed, and must still ignore comments"
    assert _provisioner_setup_script(manifest="") == "", (
        "the setup reader must return nothing rather than a stale body when the "
        "provisioner manifest carries no `setup` script at all"
    )
    assert (
        len(_unwritable_seed_gaps(setup=control_setup)) == 2
    ), "the writability reader must still convict a seed left at the generation's modes"
    assert (
        len(_index_contact_gaps(template=_CONTROL_TEMPLATE)) == 2
    ), "the index reader must still convict a template that points neither tier at the pool"
    assert _tiers_without_a_recordable_hit(template=_CONTROL_TEMPLATE) == [
        f"{tier}: recorded hits=[]" for tier in _CACHE_TIERS
    ], "the warm-copy reader must still convict tiers that record no row at all"
    assert (
        len(_span_emission_gaps(emitter="")) == 3
    ), "the emitter reader must still convict an emitter that builds no warm-copy span"
    assert _cases_that_cannot_convict(suite=_CONTROL_SUITE, required=("warm-seed-private",)) == [
        "warm-seed-private: verdicts=['pass']"
    ], "the isolation-case reader must still convict a case that only ever reports pass"


def test_a_jobs_compilation_cache_writes_are_refused() -> None:
    """§"a job's compilation-cache writes are refused", clause by clause.

    REACHABLE THROUGH ITS READ-ONLY ENDPOINT: a job pod connects to the shared
    redis as the UNAUTHENTICATED `default` user, because the pod carries no
    credential — so "read-only endpoint" is exactly the ACL that
    `converge-sccache-redis.sh` renders into the `sccache-redis-acl` Secret.
    Every user in that file must build its grants up from an explicit `-@all`
    reset, since redis ACL rules are applied in order and a grant added without
    one inherits whatever the default user already had.

    THE CRATE MUST COMPILE LOCALLY IN THE JOB: sccache is configured as a
    `rustc-wrapper`, which on a miss invokes the real compiler in this job.
    Two committed facts keep that true and both fail silently. A
    `SCCACHE_DIST_*` scheduler in the pod's environment would ship the compile
    to a build farm — still a green job, and no longer this job. And the
    wrapper stanza is written only when the backend answers a TCP probe, so an
    unreachable cache leaves a plain local compile rather than a wrapper
    pointing at nothing.

    THE RESULTING OBJECT MUST NOT APPEAR IN THE SHARED CACHE, AND A WRITE WITH
    THE POD'S CREDENTIALS MUST BE REFUSED BY THE BACKEND: two layers, asserted
    separately on purpose. The CLIENT layer is `SCCACHE_REDIS_RW_MODE`, which
    must be `READ_ONLY` so a job never attempts the write at all. The SERVER
    layer is the ACL: the `default` user may hold no write capability, so a
    write that IS attempted returns NOPERM. The spec says the refusal is
    "enforced server-side" precisely because the client layer is good manners a
    workflow could undo — and the ACL alone is not enough either, since a pod
    that carried the writer credential would authenticate past it, which is why
    no job-visible env name may look like one.

    THE RUNTIME HALF is again the pool's isolation suite: its
    `redis-set-refused` and `no-writer-credential` cases must each still be
    able to convict.
    """
    converge = _SCCACHE_CONVERGE.read_text(encoding="utf-8")
    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")
    writers = _acl_users_granted_write(converge=converge)
    unreset = _acl_users_without_a_reset(converge=converge)
    assert writers and not any(entry.startswith("default:") for entry in writers) and not unreset, (
        f"a job pod carries no credential, so it connects as the unauthenticated `default` "
        f"user — that user may hold no write capability, or the refusal this scenario "
        f"requires never happens. Exactly one writer must exist (an ACL granting nobody a "
        f"write is an unreadable or unrendered file, not a safe one), and every user must "
        f"build up from an explicit `-@all` reset because redis applies rules in order; "
        f"writers={writers} unreset={unreset}"
    )

    posture = _job_client_write_posture(template=template)
    leaked = _job_visible_writer_credentials(template=template)
    assert posture == "READ_ONLY" and not leaked, (
        f"the job's own client must run READ_ONLY so it never attempts a write, and the pod "
        f"must carry no name that could authenticate one — a pod holding the writer "
        f"credential authenticates straight past the ACL, which is why the two layers are "
        f"asserted separately; rw_mode={posture} credentials={leaked}"
    )

    offloaded = _local_compile_gaps(template=template)
    assert not offloaded, (
        f"a miss must be compiled IN THIS JOB: sccache is a `rustc-wrapper` around the real "
        f"compiler, a `SCCACHE_DIST_*` scheduler would ship the compile to a build farm, and "
        f"the wrapper stanza must be gated on the backend answering a probe so an "
        f"unreachable cache leaves a plain local compile; gaps={offloaded}"
    )

    toothless = _cases_that_cannot_convict(
        suite=_ISOLATION_SUITE.read_text(encoding="utf-8"),
        required=("redis-set-refused", "no-writer-credential"),
    )
    assert not toothless, (
        f"the runtime proof that the backend refuses the write is the isolation suite's own "
        f"SET from inside a routed job; a case that reports only `pass` is green forever; "
        f"cases={toothless}"
    )

    assert _acl_users_granted_write(converge=_CONTROL_ACL) == [
        "default: +@all",
        "sccache-writer: +@write",
    ], "the ACL reader must still convict an unauthenticated user granted the write categories"
    assert _acl_users_without_a_reset(converge=_CONTROL_ACL) == [
        "default"
    ], "the reset reader must still convict a user whose grants inherit rather than reset"
    assert _job_visible_writer_credentials(template=_CONTROL_TEMPLATE) == [
        "SCCACHE_REDIS_WRITER_PASSWORD"
    ], "the credential reader must still convict a writer credential handed to a job pod"
    assert (
        _job_client_write_posture(template=_CONTROL_TEMPLATE) is None
    ), "the posture reader must report an unstated rw_mode rather than assuming READ_ONLY"
    assert _local_compile_gaps(template=_CONTROL_TEMPLATE) == [
        "no `rustc-wrapper`: nothing wraps a local compile",
        "the compile is shipped off the job: ['SCCACHE_DIST_SCHEDULER_URL']",
        "the wrapper stanza is not gated on the backend answering a probe",
    ], "the local-compile reader must still convict a template that ships the compile away"
