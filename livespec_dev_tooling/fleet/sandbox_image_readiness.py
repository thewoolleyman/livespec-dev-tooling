"""Hold a livespec-dev-tooling release fan-out until ghcr.io serves its sandbox image.

Authority: `SPECIFICATION/contracts.md` section "`reusable-release-dispatch.yml`"
(v087) — "when source_repo is livespec-dev-tooling, the fan-out MUST NOT fire
any sibling-released dispatch until ghcr.io serves a manifest for each of the
release's semver-tagged livespec-fabro-sandbox layers ... It MUST poll for them
for at most 90 minutes. When any is still absent at that bound, the run MUST
fail with an annotation naming each missing tag and MUST dispatch to no
sibling". A release of any other source_repo MUST NOT wait.

THE RACE THIS CLOSES. `release-dispatch.yml` and `fabro-sandbox-image.yml` both
trigger on `release: published`, so the bump PRs open while the image is still
building. Measured 2026-10-22 (coordinator R612): v1.125.0 published at
10:38:18Z and consumer bump PRs opened at 10:43Z, but ghcr.io did not serve
`python-rust-agent-v1.125.0` until 11:08Z to 11:19Z. One consumer's `check-arch`
took a 404 and needed a rerun; livespec-orchestrator-beads-fabro's bump PR
MERGED at 10:52:20Z, putting a sandbox tag on that repo's master which no pull
could resolve for another 27 minutes. A bump to a tag that does not exist is
not a usable bump — it is a clean-looking, auto-merged diff pointing at
nothing, which is the same failure shape `fabro_image_pin_rewrite` refuses a
bare rewrite for.

WAITING IS THE WHOLE REMEDY, and the bound is what keeps it from becoming a
hang. The scheduled pin-freshness sweep remains the safety net once the image
publishes, so a run that times out costs a delay rather than a missed bump;
what it must never do is dispatch. THE BOUND IS A RATIFIED CONSTANT — there is
no flag, environment variable or per-release exemption that lengthens or
shortens it, for the same reason the settle window carries none: a settable
bound is a severity lever wearing a different name. `probe` and `clock` are
injected as TEST SEAMS, reachable only from `main`'s keyword arguments and
never from argv.

FAIL-CLOSED READING OF THE REGISTRY. `default_tag_probe` answers True only on a
`200`. A 404, a refused anonymous token, a timeout, or a `curl` that will not
start all answer False — "not yet" — so an unreadable registry delays the
fan-out instead of releasing it against a tag nobody confirmed exists.

Output discipline matches the sibling fan-out helper: structlog JSON to stderr,
with the `::error::` / `::notice::` workflow-command lines on stdout because
the Actions runner parses them from there.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "POLL_SECONDS",
    "SANDBOX_IMAGE_LAYERS",
    "SANDBOX_IMAGE_REPOSITORY",
    "WAITING_SOURCE_REPO",
    "WAIT_BOUND_SECONDS",
    "Clock",
    "TagProbe",
    "await_sandbox_image",
    "default_tag_probe",
    "main",
    "missing_sandbox_tags",
    "sandbox_image_tags",
    "system_clock",
]

# The repository `fabro-sandbox-image.yml` pushes to, and the SIX layers it
# publishes a `<layer>-v<X.Y.Z>` tag for on every release. The set is the whole
# obligation: a layer omitted here is a layer nothing waits for, and a bump
# rewrites a consumer's pin to whichever layer that consumer runs — so a
# five-of-six wait reopens the race for exactly the consumers that pin the
# missing one. `python-rust-agent` is the layer ghcr served 27 minutes late on
# 2026-10-22, and `python-rust-fuzz` is the CI-only leaf that has no agent atop
# it; neither is optional.
SANDBOX_IMAGE_REPOSITORY = "thewoolleyman/livespec-fabro-sandbox"
SANDBOX_IMAGE_LAYERS: tuple[str, ...] = (
    "base",
    "python",
    "python-agent",
    "python-rust",
    "python-rust-agent",
    "python-rust-fuzz",
)
# The ONE publishing repository whose release writes those tags. Every other
# repo's release fans out unheld — it writes no sandbox tag, so waiting for one
# would delay a dispatch for a condition that can never change.
WAITING_SOURCE_REPO = "livespec-dev-tooling"
WAIT_BOUND_SECONDS = 90 * 60
POLL_SECONDS = 30

_TOKEN_URL = (
    f"https://ghcr.io/token?service=ghcr.io&scope=repository:{SANDBOX_IMAGE_REPOSITORY}:pull"
)
_MANIFEST_URL = "https://ghcr.io/v2/{repository}/manifests/{tag}"
# Both OCI and Docker media types, index and manifest alike: the layered build
# pushes a multi-arch index, and a probe that accepted only one spelling would
# read a served tag as absent and wait out the whole bound.
_MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
_CURL_TIMEOUT_SECONDS = "30"
_SERVED_STATUS = "200"


class TagProbe(Protocol):
    """Whether ghcr.io currently serves a manifest for one tag."""

    def __call__(self, *, tag: str) -> bool: ...


@dataclass(frozen=True, kw_only=True)
class Clock:
    """The two time operations the bounded poll needs, as an injectable pair.

    A dataclass of callables rather than a Protocol with methods, because the
    test double is a stub of two functions and the production value is two
    stdlib functions; neither wants a class.
    """

    monotonic: Callable[[], float]
    sleep: Callable[[float], None]


def system_clock() -> Clock:
    """The real clock — monotonic so a wall-clock adjustment cannot shorten the bound."""
    return Clock(monotonic=time.monotonic, sleep=time.sleep)


def sandbox_image_tags(*, tag: str) -> tuple[str, ...]:
    """Every layered sandbox tag a bump to release `tag` rewrites a pin to."""
    return tuple(f"{layer}-{tag}" for layer in SANDBOX_IMAGE_LAYERS)


def missing_sandbox_tags(*, tag: str, probe: TagProbe) -> tuple[str, ...]:
    """The layered tags ghcr.io does not serve right now, in layer order."""
    return tuple(one for one in sandbox_image_tags(tag=tag) if not probe(tag=one))


def await_sandbox_image(
    *,
    tag: str,
    probe: TagProbe,
    clock: Clock,
    bound_seconds: int = WAIT_BOUND_SECONDS,
    poll_seconds: int = POLL_SECONDS,
) -> tuple[str, ...]:
    """Poll until every layered tag is served; return the tags still missing at the bound.

    An EMPTY result means the fan-out may proceed. A non-empty one is the
    failure the caller renders — never an exception, because the missing TAGS
    are the whole diagnostic and an exception type cannot carry them.

    The deadline is taken once, before the first read, so a slow registry
    cannot extend the bound by making each round take longer.
    """
    deadline = clock.monotonic() + bound_seconds
    while True:
        missing = missing_sandbox_tags(tag=tag, probe=probe)
        if not missing:
            return ()
        if clock.monotonic() >= deadline:
            return missing
        clock.sleep(poll_seconds)


def default_tag_probe(*, tag: str) -> bool:
    """True only when ghcr.io SERVES a manifest for `tag`; every other answer is "not yet"."""
    token = _anonymous_pull_token()
    if token is None:
        return False
    status = _curl(
        argv=[
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            f"Accept: {_MANIFEST_ACCEPT}",
            _MANIFEST_URL.format(repository=SANDBOX_IMAGE_REPOSITORY, tag=tag),
        ]
    )
    return status == _SERVED_STATUS


def _anonymous_pull_token() -> str | None:
    """The anonymous pull token ghcr.io issues for this PUBLIC repository, or None.

    Not a secret — it authorizes exactly the read any unauthenticated client
    may already make — but it is still the registry's required dance: the
    manifest endpoint answers `401` without one, which a probe would otherwise
    read as "not served" for every tag forever.
    """
    payload = _curl(argv=[_TOKEN_URL])
    if payload is None:
        return None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    token = cast("dict[str, object]", decoded).get("token") if isinstance(decoded, dict) else None
    return token if isinstance(token, str) and token else None


def _curl(*, argv: list[str]) -> str | None:
    """One bounded `curl` read's stdout, or None when it did not answer."""
    try:
        done = subprocess.run(
            ["curl", "-sS", "--max-time", _CURL_TIMEOUT_SECONDS, *argv],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sandbox_image_readiness",
        description=(
            "Hold a livespec-dev-tooling release fan-out until ghcr.io serves every "
            "layered livespec-fabro-sandbox tag the release writes."
        ),
    )
    _ = parser.add_argument("--source-repo", required=True)
    _ = parser.add_argument("--tag", required=True)
    return parser


def main(
    *,
    argv: list[str] | None = None,
    probe: TagProbe = default_tag_probe,
    clock: Clock | None = None,
) -> int:
    """Clear the fan-out, or fail naming every tag ghcr.io still does not serve."""
    log = structlog.get_logger("sandbox_image_readiness")
    args = _build_parser().parse_args(argv)
    source_repo = cast("str", args.source_repo)
    tag = cast("str", args.tag)
    if source_repo != WAITING_SOURCE_REPO:
        log.info(
            "release writes no livespec-fabro-sandbox tag; fan-out is not held",
            source_repo=source_repo,
            tag=tag,
        )
        return 0
    missing = await_sandbox_image(
        tag=tag, probe=probe, clock=system_clock() if clock is None else clock
    )
    if missing:
        # stdout on purpose: the Actions runner parses workflow commands from
        # stdout, so this is what makes the withheld fan-out visible on the run
        # rather than a bare non-zero exit nobody can diagnose.
        print(  # noqa: T201
            f"::error::release fan-out withheld: ghcr.io still serves no manifest for "
            f"{', '.join(missing)} after {WAIT_BOUND_SECONDS // 60} minutes; no "
            f"sibling-released dispatch was sent, because a bump to a tag that does not "
            f"exist is not a usable bump. The scheduled pin-freshness sweep will bump "
            f"these pins once the image publishes."
        )
        log.error(
            "sandbox image tags still absent at the ratified bound",
            tag=tag,
            missing_tags=list(missing),
            bound_seconds=WAIT_BOUND_SECONDS,
        )
        return 1
    print(f"::notice::ghcr.io serves every livespec-fabro-sandbox tag for {tag}")  # noqa: T201
    log.info("every sandbox image tag is served; releasing the fan-out", tag=tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
