"""_pin_factory_reach_format — the factory-reach env file's sandbox image pin.

The third surface of the `fabro_sandbox_docker_image` format, per
`SPECIFICATION/contracts.md` section "Pin autodiscovery rules": the
`FACTORY_REACH_SANDBOX_IMAGE=ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>`
line of `ci-runner/k3s/phase2/factory/factory-reach-image.env`.

That file is a SECOND copy of the fleet sandbox image pin the workflow
`container:` blocks carry, shipped separately because the CI-pool node's
installed tree has no repository checkout. `fabro_image_pin_lockstep` fails when
the two copies differ, so a release bump that rewrites only the workflow copy is
red by construction — which is what happened to every self-bump from 2026-10-16
(work-item livespec-dev-tooling-7enfyd). Walking the line as the SAME format
makes the fan-out rewrite both in one commit.

Split from `_pin_directory_scan_formats`, which is at its LLOC ceiling; it reads
one well-known file rather than scanning a directory.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.cross_repo._pin_directory_scan_formats import (  # noqa: E402
    FABRO_SANDBOX_IMAGE,
    FABRO_SANDBOX_SOURCE_REPO,
    PIN_FORMAT_FABRO_DOCKER,
    PinFileUnparseable,
    PinWalkResult,
    failed_read,
    read_pin_text,
    record,
)

__all__: list[str] = ["walk_factory_reach_sandbox_image"]


_FACTORY_REACH_ENV: tuple[str, ...] = (
    "ci-runner",
    "k3s",
    "phase2",
    "factory",
    "factory-reach-image.env",
)
# Scoped to the fabro-sandbox image so a line naming any other image yields no
# record; `#` comment lines never match because the key is anchored at the start.
_FACTORY_REACH_LINE_RE = re.compile(
    r"^[ \t]*FACTORY_REACH_SANDBOX_IMAGE="
    + re.escape(FABRO_SANDBOX_IMAGE)
    + r":(?P<tag>\S+)[ \t]*$",
    re.MULTILINE,
)


def walk_factory_reach_sandbox_image(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> PinWalkResult:
    if source_repo_filter is not None and source_repo_filter != FABRO_SANDBOX_SOURCE_REPO:
        return IOSuccess([])
    env_path = root.joinpath(*_FACTORY_REACH_ENV)
    # An ABSENT file is an ANSWER — this consumer ships no factory-reach check.
    if not env_path.is_file():
        return IOSuccess([])
    rel_path = str(env_path.relative_to(root))
    read = read_pin_text(path=env_path, pin_walk="walk_factory_reach_sandbox_image")
    if isinstance(read, IOFailure):
        return failed_read(result=read)
    tags = [
        match.group("tag")
        for match in _FACTORY_REACH_LINE_RE.finditer(unsafe_perform_io(read.unwrap()))
    ]
    # The renderer refuses a file naming two values rather than picking one, so
    # the walk must not pick either: a can't-parse is a FINDING, never a record.
    distinct = sorted(set(tags))
    if len(distinct) > 1:
        detail = f"names {len(distinct)} distinct FACTORY_REACH_SANDBOX_IMAGE values {distinct}"
        log.warning(
            "unparseable pin file",
            pin_walk="walk_factory_reach_sandbox_image",
            file_path=rel_path,
            detail=detail,
        )
        return IOFailure(
            PinFileUnparseable(
                pin_walk="walk_factory_reach_sandbox_image", file_path=rel_path, detail=detail
            )
        )
    return IOSuccess(
        [
            record(
                pin_format=PIN_FORMAT_FABRO_DOCKER,
                file_path=rel_path,
                pin_key=FABRO_SANDBOX_IMAGE,
                current_value=tag,
                source_repo=FABRO_SANDBOX_SOURCE_REPO,
            )
            for tag in tags
        ]
    )
