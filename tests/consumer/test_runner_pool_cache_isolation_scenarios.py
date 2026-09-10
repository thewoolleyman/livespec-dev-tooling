"""Consumer-tier: the two `SPECIFICATION/scenarios.md` cache-ISOLATION scenarios.

    "a routed job reads the warm cache and cannot write it"
    "a job's compilation-cache writes are refused"

Both scenarios are about what a job CANNOT do, and the pool already ships the
artifact that decides it: `ci-runner/k3s/phase2/isolation/cache-negative-tests.sh`
is run from inside a routed job on a schedule, and its own header states the
rule these tests hold it to — "EVERY CASE MUST BE ABLE TO FAIL. A case is a
violation when the forbidden thing SUCCEEDS, and ALSO when the precondition
that makes the assertion meaningful is absent". A suite that cannot convict is
a green light wired to nothing, and it would be green on exactly the pool that
had lost the isolation.

So the suite is DRIVEN here, over synthetic warm-seed fixtures under
`tmp_path`, through the four environment seams it already exposes for that
purpose (`CACHE_NEG_WARM_SEED`, `CACHE_NEG_REDIS_HOST`, `CACHE_NEG_REDIS_PORT`,
`CACHE_NEG_PROXY_URL`). No pod, no node and no redis is involved: the fixtures
are ordinary directories, and each arm differs from its control in exactly the
one property the scenario names.

What the drive CANNOT settle is asserted against the committed gitops beside
it — the redis ACL the converge renders, and the environment the hook pod
template hands a job — because the refusal the second scenario requires is the
BACKEND's, and no fixture in this repository can stand in for a server-side
ACL. The two halves are marked in each test's own docstring.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_SUITE = _PHASE2 / "isolation" / "cache-negative-tests.sh"
_HOOK_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
_ACL_CONVERGE = _PHASE2 / "sccache" / "converge-sccache-redis.sh"

# The four case names the suite reports under. Only the first two are this
# file's subject; the others are named so an unexpected report shape is caught
# rather than silently read as an absent case.
_SEED_CASE = "warm-seed-private"
_CREDENTIAL_CASE = "no-writer-credential"
_REDIS_CASE = "redis-set-refused"

# The redis category tokens that decide the second scenario. `+@write` is what
# a writing identity carries; a reader carries the read and connection
# categories after `-@all` has taken everything away.
_WRITE_CATEGORY = "+@write"
_DENY_ALL = "-@all"

# The reader-side declaration the hook pod template hands every job, and the
# credential-shaped names the suite refuses to find in a job's environment.
_RW_MODE_ENV = "SCCACHE_REDIS_RW_MODE"
_READ_ONLY = "READ_ONLY"
_WRITER_PASSWORD_ENV = "SCCACHE_REDIS_WRITER_PASSWORD"

# A closed port on loopback, so the suite's redis and proxy cases fail their
# PRECONDITION immediately instead of waiting on a timeout. Reaching a real
# backend is not this file's subject and would make the verdict depend on
# whatever happens to be listening on the machine running the suite.
_CLOSED_ENDPOINT_HOST = "127.0.0.1"
_CLOSED_ENDPOINT_PORT = "1"

_CASE_LINE = re.compile(r"^case=(?P<case>\S+) result=(?P<result>\S+) (?P<detail>.*)$", re.MULTILINE)
_ACL_USER = re.compile(r"^user (?P<user>\S+) (?P<rules>.+)$", re.MULTILINE)


def _run_suite(*, seed: Path, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run the committed isolation suite against one fixture; return (rc, stdout).

    `COVERAGE_PROCESS_START` and `COV_CORE_*` are scrubbed from the child
    environment: the suite's redis case runs a short python3 heredoc, and a
    coverage-instrumented grandchild writes `.coverage.*` files that race the
    parallel check dispatcher (the failure mode `tests_no_subprocess_spawn`
    exists to prevent, and the discipline its allowlist imposes on any test
    that genuinely needs a real subprocess).
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env["CACHE_NEG_WARM_SEED"] = str(seed)
    env["CACHE_NEG_REDIS_HOST"] = _CLOSED_ENDPOINT_HOST
    env["CACHE_NEG_REDIS_PORT"] = _CLOSED_ENDPOINT_PORT
    env["CACHE_NEG_PROXY_URL"] = f"http://{_CLOSED_ENDPOINT_HOST}:{_CLOSED_ENDPOINT_PORT}"
    env.update(extra_env or {})
    completed = subprocess.run(
        ["bash", str(_SUITE)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    return completed.returncode, completed.stdout


def _verdict(*, output: str, case: str) -> tuple[str, str]:
    """The `(result, detail)` the suite reported for one case."""
    for match in _CASE_LINE.finditer(output):
        if match.group("case") == case:
            return match.group("result"), match.group("detail")
    # Unreached while the suite reports every case this file asks about, which
    # is what the assertions below establish. It stays as the guard that keeps a
    # RENAMED or dropped case a loud failure rather than a silently skipped
    # assertion — the shape that would let the suite stop testing and stay green.
    pytest.fail(  # pragma: no cover
        f"the suite reported no `case={case}` line at all; output={output!r}"
    )


def _seed_with(*, root: Path, name: str, size: int = 128 * 1024) -> Path:
    """A seeded file of `size` bytes under a fresh seed directory."""
    root.mkdir(parents=True, exist_ok=True)
    seeded = root / name
    _ = seeded.write_bytes(b"\0" * size)
    return seeded


def test_the_isolation_suite_convicts_a_seeded_inode_shared_outside_the_job_volume(
    *, tmp_path: Path
) -> None:
    """§"a routed job reads the warm cache and cannot write it".

    The clause with teeth is the middle one: "a path the job can reach MUST NOT
    resolve to a SHARED INODE of a warm tree, so a write from inside the job to
    a seeded file MUST land in the job's own volume and MUST leave the shared
    generation unchanged". That is a property of the SEED, and the pool decides
    it with the suite driven here rather than with a claim in a manifest — the
    hardlink seed that shipped from 2026-09-04 to 2026-09-06 had exactly this
    defect, and the suite reported it on every run until the reflink seed
    replaced it.

    Three fixtures, differing in one property each:

    SHARED (the violation): a seeded file with a second link OUTSIDE the seed —
    the shape a hardlink seed of a warm generation has. Must be convicted, and
    the conviction must NAME the shared inode.

    PRIVATE-BUT-LINKED (the control that stops the conviction from being
    trivial): a seeded file with a second link INSIDE the seed. uv hardlinks
    entries to each other within a cache and `cp -a` preserves those, so this
    is what a HEALTHY seed looks like, and a check that merely flagged
    multi-link inodes would convict it too. It must NOT be convicted for a link
    outside the tree — whatever else the fixture's own filesystem makes the
    suite say about reflink extents, which is not this repository's property.

    ABSENT (the vacuity guard): no seed at all. The suite's own header makes
    this a violation rather than a pass, and it matters more than it looks: an
    unseeded volume is exactly what a broken provisioner produces, and a suite
    that scored it green would go on reporting an isolation it never tested.
    """
    shared_seed = tmp_path / "shared" / "uv"
    seeded = _seed_with(root=shared_seed, name="pkg.bin")
    outside = tmp_path / "shared" / "generation-copy.bin"
    os.link(seeded, outside)
    rc, output = _run_suite(seed=shared_seed)
    result, detail = _verdict(output=output, case=_SEED_CASE)
    assert result == "fail" and "link outside this tree" in detail, (
        f"a seeded file carrying a link OUTSIDE the seed is the shared inode the scenario "
        f"forbids a job from reaching, and the suite must convict it by name — this is the "
        f"defect the hardlink seed actually had; result={result!r} detail={detail!r}"
    )
    assert rc != 0, (
        f"a convicted case must carry the suite's exit code: the scheduled job's conclusion "
        f"IS the report, so a violation that exits 0 is invisible; rc={rc} output={output!r}"
    )

    private_seed = tmp_path / "private" / "uv"
    first = _seed_with(root=private_seed, name="archive.bin")
    os.link(first, private_seed / "wheels.bin")
    _, private_detail = _verdict(output=_run_suite(seed=private_seed)[1], case=_SEED_CASE)
    assert "link outside this tree" not in private_detail, (
        f"a seeded file linked only to another file INSIDE the seed is what a healthy uv "
        f"cache looks like after `cp -a`, and convicting it would make the case fire on link "
        f"COUNT rather than on the shared-inode property the scenario names; "
        f"detail={private_detail!r}"
    )

    absent_result, absent_detail = _verdict(
        output=_run_suite(seed=tmp_path / "never-seeded" / "uv")[1], case=_SEED_CASE
    )
    assert absent_result == "fail" and "precondition" in absent_detail, (
        f"an unseeded volume must be reported as a precondition failure, never scored as "
        f"passing isolation: nothing was tested, and a green report there is a pool that has "
        f"stopped checking; result={absent_result!r} detail={absent_detail!r}"
    )


def test_a_job_carries_no_writer_credential_and_only_one_acl_identity_may_write(
    *, tmp_path: Path
) -> None:
    """§"a job's compilation-cache writes are refused".

    "a write issued with the pod's credentials MUST be REFUSED BY THE BACKEND"
    — by the backend, so the refusal cannot be asserted against a client
    setting. It has two committed halves and neither is sufficient alone.

    THE JOB HOLDS NOTHING THAT COULD WRITE, driven: the suite's
    `no-writer-credential` case, over a clean environment and over one carrying
    the writer password. This is the file's only pass/fail PAIR from the same
    fixture, and it is what proves the suite discriminates at all rather than
    reporting whatever its fixtures happen to make easy.

    THE BACKEND WOULD REFUSE ANYWAY, read: the ACL the converge renders gives
    the unauthenticated `default` user — the identity every job pod connects as
    — `-@all` and then only read and connection categories, while exactly ONE
    user carries `+@write`. That is the "trust by construction, server-side"
    the sccache manifest's header claims, held to the file that renders it.
    The hook template's `SCCACHE_REDIS_RW_MODE=READ_ONLY` is the job's good
    manners on top, and is asserted as exactly that: a declaration, beside a
    backend that does not depend on it.

    AND THE SUITE WILL NOT SCORE AN UNREACHABLE BACKEND AS A REFUSAL: with
    nothing listening, `redis-set-refused` must report a precondition failure.
    A cache that is merely DOWN produces no `-NOPERM`, and reading that silence
    as a refusal is how a pool with an open ACL would keep reporting green.
    """
    # One seed, reused by every arm below: the credential and redis cases do
    # not read it, and holding it fixed is what leaves the environment as the
    # only thing that differs between the pass and the fail.
    seed = tmp_path / "seed"
    _ = _seed_with(root=seed, name="pkg.bin")
    clean_result, clean_detail = _verdict(output=_run_suite(seed=seed)[1], case=_CREDENTIAL_CASE)
    assert clean_result == "pass", (
        f"a job environment carrying no writer credential must pass the case that looks for "
        f"one, or the assertion below proves nothing; detail={clean_detail!r}"
    )

    leaked_result, leaked_detail = _verdict(
        output=_run_suite(seed=seed, extra_env={_WRITER_PASSWORD_ENV: "not-a-real-secret"})[1],
        case=_CREDENTIAL_CASE,
    )
    assert leaked_result == "fail" and _WRITER_PASSWORD_ENV in leaked_detail, (
        f"a writer credential reachable from inside a job is the one thing that would let a "
        f"job's own compilation output into the shared cache, and the case must convict it "
        f"BY NAME; result={leaked_result!r} detail={leaked_detail!r}"
    )

    unreachable_result, unreachable_detail = _verdict(
        output=_run_suite(seed=seed)[1], case=_REDIS_CASE
    )
    assert unreachable_result == "fail" and "precondition" in unreachable_detail, (
        f"a backend nothing can reach issues no refusal, so the case must report a "
        f"precondition failure rather than read the silence as one — a cache that is merely "
        f"down would otherwise certify an ACL nobody tested; result={unreachable_result!r} "
        f"detail={unreachable_detail!r}"
    )

    rules = {
        match.group("user"): match.group("rules").split()
        for match in _ACL_USER.finditer(_ACL_CONVERGE.read_text(encoding="utf-8"))
    }
    assert "default" in rules, (
        f"the rendered ACL must state the `default` user explicitly: it is the identity an "
        f"unauthenticated job pod connects as, and redis's own default for it is permissive; "
        f"users={sorted(rules)}"
    )
    assert _DENY_ALL in rules["default"] and _WRITE_CATEGORY not in rules["default"], (
        f"the identity a job connects as must have everything taken away and only reads "
        f"given back — this is the refusal the scenario requires to come from the BACKEND; "
        f"default rules={rules['default']}"
    )
    writers = sorted(user for user, stated in rules.items() if _WRITE_CATEGORY in stated)
    assert len(writers) == 1 and writers != ["default"], (
        f"exactly one ACL identity may write the shared cache — the populator's — or a job's "
        f"own compilation output can reach entries every other repository then reads; "
        f"writers={writers}"
    )

    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")
    assert f"value: {_READ_ONLY}" in template and _RW_MODE_ENV in template, (
        f"the template must still hand every job `{_RW_MODE_ENV}={_READ_ONLY}` — the client "
        f"never attempting a write is worth having beside a backend that would refuse it, "
        f"and it is what the emitter reports as the job's declared mode; "
        f"template={_HOOK_TEMPLATE.relative_to(_REPO_ROOT)}"
    )
    assert _WRITER_PASSWORD_ENV not in template, (
        f"and the template must hand a job no writer credential of any kind, or the ACL "
        f"above is a lock beside its own key; template={_HOOK_TEMPLATE.relative_to(_REPO_ROOT)}"
    )
