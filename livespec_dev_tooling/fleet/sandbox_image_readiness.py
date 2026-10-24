"""Hold the release fan-out until ghcr.io serves the release's sandbox image.

`SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", subsection "`reusable-release-dispatch.yml`" (v087): when
`source_repo` is livespec-dev-tooling, the fan-out MUST NOT fire any
`sibling-released` dispatch until ghcr.io serves a manifest for each of the
release's semver-tagged `livespec-fabro-sandbox` layers; it MUST poll for them
for at most 90 minutes; and when any is still absent at that bound the run MUST
fail with an annotation naming each missing tag and dispatch to no sibling,
"because a bump to a tag that does not exist is not a usable bump". A release of
any other `source_repo` MUST NOT wait.

WHY THE WAIT GOES BEFORE THE DISPATCH RATHER THAN AFTER IT. Both
`release-dispatch.yml` and `fabro-sandbox-image.yml` trigger on
`release: published`, so they race, and the consumer side of that race does not
fail loudly — it SUCCEEDS wrongly. Measured 2026-10-22 (coordinator R612):
v1.125.0 published at 10:38:18Z, consumer bump PRs opened at 10:43Z, and
`python-rust-agent-v1.125.0` was not served until 11:19Z. Console PR #1266's
`check-arch` took a 404 for that tag and needed a rerun; livespec-orchestrator
PR #3507 MERGED at 10:52:20Z, putting a sandbox tag on that repo's master that
ghcr did not serve for another 27 minutes, so any factory dispatch from
orchestrator inside that window would have pulled a missing image. The bump
diff looked clean in both cases, which is exactly why the race has to be closed
upstream of the dispatch.

THE PROBE'S CAN'T-READ IS "NOT SERVED YET", DELIBERATELY. A registry that
refuses the pull token, answers HTML, or times out has told us nothing about the
tag — and the only fail-closed reading of nothing is that the image is not
there. That keeps the fan-out waiting and, at the bound, fails naming the tags;
the opposite reading would dispatch bumps onto a tag no one has seen. The
scheduled pin-freshness sweep remains the safety net once the image publishes,
which is what makes failing here cheap rather than terminal.

The six layers are the ones `.github/workflows/fabro-sandbox-image.yml`
publishes, and every tag it pushes carries its layer prefix in the `-v<X.Y.Z>`
form — a BARE `v<X.Y.Z>` is never published, the same fact
`cross_repo.fabro_image_pin_rewrite` refuses a bare rewrite over.

Output discipline: structlog JSON to stderr for the narrative, and the one
deliberate stdout emission is the `::error::` workflow command the Actions
runner parses from stdout, which is what makes the missing tags an annotation on
the run rather than a line in a log nobody opens.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.cross_repo.pin_autodiscovery import (  # noqa: E402
    FABRO_SANDBOX_IMAGE,
)

__all__: list[str] = [
    "FABRO_SANDBOX_IMAGE",
    "POLL_BOUND_SECONDS",
    "SANDBOX_IMAGE_LAYERS",
    "SOURCE_REPO_THAT_WAITS",
    "SandboxTagsUnserved",
    "await_sandbox_tags",
    "ghcr_missing_tags",
    "main",
    "run_curl",
    "sandbox_image_tags",
]


# The publishing repository whose releases carry sandbox tags at all. The
# fabro-sandbox image is built and released BY livespec-dev-tooling and its tag
# tracks that release version, so no other member's release has anything to
# wait for — and waiting anyway would delay every sibling's fan-out behind a
# tag that will never appear.
SOURCE_REPO_THAT_WAITS = "livespec-dev-tooling"

# The six layers `fabro-sandbox-image.yml` publishes, leaf-last. The whole set
# is required rather than the one layer a given consumer pins: the fan-out
# rewrites EVERY matching pin across every member in one round, so a bump is
# usable only when all six are served.
SANDBOX_IMAGE_LAYERS = (
    "base",
    "python",
    "python-agent",
    "python-rust",
    "python-rust-agent",
    "python-rust-fuzz",
)

# The ratified bound: 90 minutes. A RATIFIED CONSTANT, not a tunable — the
# clause fixes it, and a settable bound is a severity lever wearing a different
# name, exactly as the settle window's is.
POLL_BOUND_SECONDS = 90 * 60

# Far enough apart that a 90-minute wait costs the registry a few dozen reads
# rather than thousands, close enough that a healthy publish (measured at
# 30 to 41 minutes behind the release) is noticed promptly.
_POLL_INTERVAL_SECONDS = 30.0

_GHCR_HOST = "ghcr.io"
_MANIFEST_ACCEPT = ",".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
_CURL_TIMEOUT_SECONDS = "30"


@dataclass(frozen=True, kw_only=True)
class SandboxTagsUnserved:
    """The bound elapsed with tags still absent, and WHICH ones.

    `missing` is every tag still unserved at the bound rather than the first
    one found absent: the operator's next question is which layer's build
    failed, and a single name sends them looking at the wrong one when two
    layers are late.
    """

    missing: tuple[str, ...]
    waited_seconds: float


class CurlRunner(Protocol):
    """Callable seam for one registry read; injected so tests reach no network.

    Named for the tool rather than generically because `CommandRunner` is
    already a DIFFERENT protocol in this package (`_local_context`), and the
    fleet package requires each type name to be declared exactly once — two
    unrelated protocols sharing a name is how a call site ends up satisfying
    the wrong one.
    """

    def __call__(self, argv: Sequence[str], /) -> tuple[int, str]: ...


class TagProbe(Protocol):
    """Callable seam answering WHICH of `tags` the registry does not serve."""

    def __call__(self, *, image: str, tags: tuple[str, ...]) -> tuple[str, ...]: ...


class PollSleeper(Protocol):
    """Callable seam for the poll delay; injected so tests never really sleep.

    Distinct from `_credential_preflight.Sleeper`, whose delay is a credential
    BACKOFF rather than a registry poll, for the one-name-one-type reason
    recorded on `CurlRunner` above.
    """

    def __call__(self, seconds: float, /) -> None: ...


class Clock(Protocol):
    """Callable seam for elapsed-time readings; monotonic in production."""

    def __call__(self) -> float: ...


def sandbox_image_tags(*, tag: str) -> tuple[str, ...]:
    """The six layered image tags a bump to release `tag` writes.

    The leading `v` is normalized off the release tag before it is put back,
    because the build pushes `<layer>-v<X.Y.Z>` and the fan-out is handed the
    release TAG: composing naively yields `base-vv1.125.0`, which names an
    image that will never exist and would therefore wait out the whole bound on
    a healthy release.
    """
    version = tag.removeprefix("v")
    return tuple(f"{layer}-v{version}" for layer in SANDBOX_IMAGE_LAYERS)


def run_curl(argv: Sequence[str], /) -> tuple[int, str]:
    """Run one `curl` read and return its (exit status, stdout).

    The exit STATUS is returned rather than raised on: a registry that 404s a
    tag not yet published, or times out, is the ordinary condition this module
    exists to poll through, and an exception would make the first unserved
    probe the end of the wait.
    """
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout


def _registry_path(*, image: str) -> str:
    """The `<owner>/<name>` path inside the registry, from the full image ref."""
    return image.removeprefix(f"{_GHCR_HOST}/")


def _pull_token(*, image: str, run: CurlRunner) -> str | None:
    """An anonymous pull token for `image`, or None when the registry did not give one.

    None is the can't-read, and every one of its three shapes — a refused
    request, bytes that are not JSON, a JSON body carrying no `token` — reads
    the same downstream: nothing was learned, so no tag counts as served.
    """
    path = _registry_path(image=image)
    status, body = run(
        (
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--max-time",
            _CURL_TIMEOUT_SECONDS,
            f"https://{_GHCR_HOST}/token?scope=repository:{path}:pull&service={_GHCR_HOST}",
        )
    )
    if status != 0:
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    token = cast("dict[str, object]", payload).get("token")
    return token if isinstance(token, str) and token else None


def _manifest_served(*, image: str, tag: str, token: str, run: CurlRunner) -> bool:
    """Whether the registry serves a manifest for one tag."""
    path = _registry_path(image=image)
    status, _ = run(
        (
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--head",
            "--max-time",
            _CURL_TIMEOUT_SECONDS,
            "--header",
            f"Authorization: Bearer {token}",
            "--header",
            f"Accept: {_MANIFEST_ACCEPT}",
            f"https://{_GHCR_HOST}/v2/{path}/manifests/{tag}",
        )
    )
    return status == 0


def ghcr_missing_tags(
    *, image: str, tags: tuple[str, ...], run: CurlRunner = run_curl
) -> tuple[str, ...]:
    """Which of `tags` ghcr.io does not serve a manifest for.

    One pull token is fetched and reused across the whole set, so a six-layer
    probe costs the registry one token read rather than six. A token the
    registry would not give makes EVERY tag unserved — the fail-closed reading
    of a read that answered nothing.
    """
    token = _pull_token(image=image, run=run)
    if token is None:
        return tags
    return tuple(
        tag for tag in tags if not _manifest_served(image=image, tag=tag, token=token, run=run)
    )


def await_sandbox_tags(
    *,
    tag: str,
    probe: TagProbe,
    image: str = FABRO_SANDBOX_IMAGE,
    sleep: PollSleeper = time.sleep,
    now: Clock = time.monotonic,
    bound_seconds: float = POLL_BOUND_SECONDS,
) -> Result[tuple[str, ...], SandboxTagsUnserved]:
    """Poll until every layered tag for `tag` is served, or until the bound elapses.

    The success value is the tags that are now served, which is the whole set —
    carried so a caller can log WHAT it waited for rather than re-deriving it.

    The bound is checked AFTER a probe and BEFORE the next sleep, so the last
    probe of a timed-out wait happens at the bound rather than one interval
    past it, and a wait whose first probe already exceeds the bound still
    probes exactly once. A loop that slept first would make the minimum wait
    one interval even for an image that was ready before the fan-out started.
    """
    started = now()
    tags = sandbox_image_tags(tag=tag)
    while True:
        missing = probe(image=image, tags=tags)
        if not missing:
            return Success(tags)
        waited = now() - started
        if waited >= bound_seconds:
            return Failure(SandboxTagsUnserved(missing=missing, waited_seconds=waited))
        sleep(_POLL_INTERVAL_SECONDS)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sandbox_image_readiness",
        description=(
            "Hold a livespec-dev-tooling release fan-out until ghcr.io serves "
            "every layered livespec-fabro-sandbox tag that release's bump writes."
        ),
    )
    _ = parser.add_argument("--source-repo", required=True)
    _ = parser.add_argument("--tag", required=True)
    return parser


def main(
    *,
    argv: list[str] | None = None,
    probe: TagProbe = ghcr_missing_tags,
    sleep: PollSleeper = time.sleep,
    now: Clock = time.monotonic,
) -> int:
    """Gate the fan-out on sandbox-image readiness; 0 to dispatch, 1 to refuse."""
    log = structlog.get_logger("sandbox_image_readiness")
    args = _build_parser().parse_args(argv)
    source_repo = cast("str", args.source_repo)
    tag = cast("str", args.tag)
    if source_repo != SOURCE_REPO_THAT_WAITS:
        log.info(
            "release carries no sandbox image tags; dispatching without waiting",
            source_repo=source_repo,
            tag=tag,
        )
        return 0
    waited = await_sandbox_tags(tag=tag, probe=probe, sleep=sleep, now=now)
    if isinstance(waited, Failure):
        unserved = waited.failure()
        # stdout on purpose: the Actions runner parses workflow commands from
        # stdout, which is what makes the missing tags an annotation on the run.
        print(  # noqa: T201
            f"::error::livespec-fabro-sandbox tags for {tag} are still unserved after "
            f"{int(unserved.waited_seconds)}s; dispatching to no sibling. Missing: "
            f"{', '.join(unserved.missing)}"
        )
        log.error(
            "sandbox image tags unserved at the ratified bound; no sibling dispatched",
            tag=tag,
            missing=list(unserved.missing),
            waited_seconds=unserved.waited_seconds,
            bound_seconds=POLL_BOUND_SECONDS,
        )
        return 1
    log.info(
        "every sandbox image tag is served; the fan-out may dispatch",
        tag=tag,
        tags=list(waited.unwrap()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
