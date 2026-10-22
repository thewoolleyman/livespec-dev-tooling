"""The PRIVATE cross-repo sibling's token — minted on the host, carried by one Job.

`SPECIFICATION/contracts.md` in livespec-dev-tooling states, of the delegated
pre-push gate and its cross-repository siblings, that the gate Job clones every
sibling a consumer's `.livespec.jsonc` `cross_repo_targets` names, a PUBLIC one
anonymously and a PRIVATE one with a GitHub App installation token the PUSHING
HOST mints at submission. The token must be scoped to exactly the private
siblings that gate run names and to read-only repository contents, must not
appear in the rendered manifest's text, in a log or in a termination message,
and must not be stored as a long-lived Secret or under any new standing
credential name. A host that cannot mint it refuses the push as a missing
verdict. Work-item livespec-dev-tooling-7kvh2d.

WHY THIS IS ONE MODULE RATHER THAN TWO HALVES. The concern has two ends that sit
in different callers — `gate_remote_delegate` asks the host which siblings are
private and gets the token, `gate_remote_client` hands that token to the one Job
that may read it — and the single thing that must stay true spans both: the
credential exists in exactly two places, this process's memory and one
owner-referenced Secret, and in neither of the artifacts anybody can read back.
Split across the two callers, that invariant is stated nowhere and is checked by
nothing.

THE `GateRunRequest` ANNOTATION IS A TYPE-CHECKING IMPORT, and that is not a
dodge. The type lives in `gate_remote_client`, which calls into here, so a
runtime import would close a cycle; under `from __future__ import annotations`
the annotation is a string and the import is needed only by the type checker.
The alternative — restating the request's fields as seven parameters — would put
this module's idea of a gate run beside the real one, free to drift.

The CLUSTER COMMAND PREFIX, by contrast, is passed in rather than built here:
`gate_remote_client._kubectl` is the one place a cluster command is built, so
every command carries the credential wrapper and no step can be spelled without
it. Rebuilding the prefix here would be a second place that could forget.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandRunner,
    GateStepFailed,
    StepOutcome,
    require_success,
)

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

if TYPE_CHECKING:
    from livespec_dev_tooling.gate_remote_client import GateRunRequest

__all__: list[str] = [
    "DELIVER_STEP",
    "MINT_STEP",
    "create_private_sibling_token_secret",
    "private_sibling_credential",
]

# The two step names a failure here reports — the MINT on the pushing host and
# the DELIVERY of what it minted to the one Job that may read it. PUBLIC, because the verdict a
# refused push carries names the step that did not complete and the tests that
# assert the refusal read the name off this module rather than restating it.
MINT_STEP = "mint-private-sibling-token"
DELIVER_STEP = "create-private-sibling-token-secret"

# The minter, in the two places it exists — and BOTH MOVE WITH THIS CODE, which
# is the whole point. A checkout of THIS repository carries it in-tree, so a
# change to it is gated by the same push that makes it; every OTHER repository
# reaches the copy the wheel ships INSIDE this package (`pyproject.toml`'s
# `[tool.hatch.build.targets.wheel.force-include]` table carries the committed
# file in). The renderer beside it resolves the same two ways for the same
# reason — stop-the-line R283, 2026-10-20, where a client and the script it
# drove moved on different schedules and every delegated push in the fleet was
# refused until an operator ran a playbook by hand.
_MINTER_IN_REPO = Path("ci-runner/k3s/phase2/gates/mint-private-sibling-token.sh")
_MINTER_PACKAGED = Path(__file__).resolve().parent / "gates" / "mint-private-sibling-token.sh"

# The one `.livespec.jsonc` key that can make a push need a token at all. Read as
# TEXT rather than parsed: the question here is only whether to ask the host, and
# the authoritative parse of the block — which siblings, at which urls — belongs
# to the minter and to the renderer, each of which reads the file itself.
_CROSS_REPO_TARGETS = '"cross_repo_targets"'

# What the minter is told, and all it is told. It reads the repository's own
# declaration, so the repository root is the whole argument list.
_REPO_ROOT_FLAG = "--repo-root"


def private_sibling_credential(
    *, repo_root: Path, runner: GateCommandRunner, helper: Path
) -> Result[tuple[tuple[str, ...], str], GateStepFailed]:
    """Which of this repository's siblings are private, and the token for them.

    NOT ASKED AT ALL when the repository registers no `cross_repo_targets`,
    which is the state of every repository that cites no sibling. That skip is
    not an optimisation: the minter reads the fleet GitHub App's credentials
    through `helper`, the environment wrapper that projects them, so asking
    unconditionally would make a host holding no App credential unable to
    delegate a push that needs no token — a cost paid by every repository to
    serve the two that cite private siblings.

    THE WRAPPER IS THE PROGRAM RUN, not the minter. `with-livespec-env.sh`
    projects the credentials from 1Password and SCRUBS the caller's environment,
    so a minter invoked directly would see neither — and the gate pod never sees
    them at all, which is the property the whole design rests on. It arrives as
    an argument rather than being named here so the caller that owns the host
    story owns the path.

    THE MINTER CLASSIFIES, NOT THIS PROCESS. Telling a private sibling from a
    public one takes an anonymous probe of each url or an authenticated API
    read, and the answer is what the mint is SCOPED BY — so a second classifier
    here would be a second answer to the question the token's scope rests on,
    and the two could disagree while both looked right.

    A FAILURE IS A STEP THAT DID NOT COMPLETE, so it reaches `GATE_NO_VERDICT`
    and REFUSES the push — the contract's "a pushing host that cannot mint the
    token refuses the push as a missing verdict". It must never degrade to an
    anonymous clone: that hands the recipe an EMPTY tree for a sibling it cites,
    and an absent citation target reads as green.
    """
    config = repo_root / ".livespec.jsonc"
    if not config.is_file() or _CROSS_REPO_TARGETS not in config.read_text(encoding="utf-8"):
        return Success(((), ""))
    in_repo = repo_root / _MINTER_IN_REPO
    argv = [
        str(helper),
        "--",
        str(in_repo if in_repo.is_file() else _MINTER_PACKAGED),
        _REPO_ROOT_FLAG,
        str(repo_root),
    ]
    minted = require_success(step=MINT_STEP, argv=argv, outcome=runner(argv=argv, cwd=repo_root))
    if isinstance(minted, Failure):
        return Failure(minted.failure())
    return _minted_credential(argv=argv, answer=minted.unwrap().stdout)


def _minted_credential(
    *, argv: Sequence[str], answer: str
) -> Result[tuple[tuple[str, ...], str], GateStepFailed]:
    """The minter's answer, or ONE refusal that quotes none of it.

    Every unusable shape is the SAME fault — the host did not say which siblings
    are private and hand over a token for exactly those — so they share one
    refusal rather than each earning a message that distinguishes nothing a
    reader could act on differently.

    `bool(names) != bool(token)` is the half worth stating. Names without a
    token would render a Secret mount nothing fills, and a token without names
    would be a credential minted for no sibling; both are answers this process
    must not carry forward, and neither is caught by type checks alone.

    THE ANSWER IS NEVER QUOTED INTO THE DETAIL. A malformed answer can still
    carry a real token, and this detail is printed to the pushing operator's
    terminal — the contract forbids the token reaching a log, so the refusal
    names the step and the argv it ran and stops there.
    """
    try:
        decoded: object = json.loads(answer)
    except json.JSONDecodeError:
        decoded = None
    payload: Mapping[str, object] = (
        cast("Mapping[str, object]", decoded) if isinstance(decoded, dict) else {}
    )
    named = payload.get("private_siblings")
    names = cast("list[object]", named) if isinstance(named, list) else None
    token = payload.get("token", "")
    if (
        names is None
        or not all(isinstance(name, str) for name in names)
        or not isinstance(token, str)
        or bool(names) != bool(token)
    ):
        return Failure(
            GateStepFailed(
                step=MINT_STEP,
                argv=tuple(argv),
                returncode=None,
                detail=(
                    "the private sibling token minter did not answer with a private_siblings "
                    "list and one installation token scoped to exactly those siblings"
                ),
            )
        )
    return Success((tuple(cast("list[str]", names)), token))


def create_private_sibling_token_secret(
    *,
    request: GateRunRequest,
    kubectl: Sequence[str],
    runner: GateCommandRunner,
    job_name: str,
    job_payload: str,
) -> StepOutcome:
    """Hand ONE Job's clone its token, and nothing else a chance to read it.

    CREATED AFTER THE JOB, DELIBERATELY, because the ownerReference needs the
    UID the API server assigns at create time — and the ownerReference is the
    whole reason this is not a long-lived Secret: garbage collection removes it
    when the Job goes, so the gate credential needs no `delete` verb and nothing
    is left behind for the next reader. A Secret created first would either have
    no owner, and so outlive every run, or need a second write to acquire one.

    THE POD DOES NOT RACE IT. The Secret volume is not optional, so the kubelet
    retries the mount until it exists rather than starting the container without
    it; and the Job waits on Kueue admission before any pod is scheduled, which
    is orders of magnitude longer than this one API call.

    A FAILED CREATE IS A MISSING VERDICT, not a red tree: the Job is already
    submitted and will sit unmountable until its TTL, so there is a Job and no
    verdict — exactly the state `GATE_NO_VERDICT` names.

    `kubectl` arrives already prefixed with the credential wrapper, built by the
    one place in `gate_remote_client` that builds a cluster command, so no step
    can be spelled here that escapes it.
    """
    uid = _owning_uid(payload=job_payload)
    if uid is None:
        return Failure(
            GateStepFailed(
                step=DELIVER_STEP,
                argv=(),
                returncode=None,
                detail=(
                    "the created Job carries no metadata.uid to own the private sibling token "
                    "Secret, and an unowned Secret holding an installation token outlives "
                    "every run"
                ),
            )
        )
    document = json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": request.private_sibling_secret,
                "namespace": request.namespace,
                "ownerReferences": [
                    {
                        "apiVersion": "batch/v1",
                        "kind": "Job",
                        "name": job_name,
                        "uid": uid,
                        "controller": True,
                    }
                ],
            },
            "type": "Opaque",
            "stringData": {"token": request.private_sibling_token},
        }
    )
    # THE TOKEN TRAVELS ON STDIN, never in the argv: an argv is readable in `ps`
    # on the pushing host for as long as the call lasts, and the contract
    # confines this credential to the one Job that consumes it.
    argv = [*kubectl, "create", "--filename", "-"]
    return require_success(
        step=DELIVER_STEP,
        argv=argv,
        outcome=runner(argv=argv, cwd=request.repo_root, stdin=document),
    )


def _owning_uid(*, payload: str) -> str | None:
    """The UID the API server assigned the Job, or `None`.

    `json.loads` is UNGUARDED on purpose: the caller has already parsed this
    same payload to learn the Job's NAME and refused the run when it could not,
    so a decode error here is a bug in the caller rather than a state the
    cluster can put us in.
    """
    decoded: object = json.loads(payload)
    metadata = (
        cast("Mapping[str, object]", decoded).get("metadata") if isinstance(decoded, dict) else None
    )
    uid = cast("Mapping[str, object]", metadata).get("uid") if isinstance(metadata, dict) else None
    return uid if isinstance(uid, str) and uid else None
