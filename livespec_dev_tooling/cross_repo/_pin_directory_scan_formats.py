"""_pin_directory_scan_formats — directory-scanning pin-format walks.

Extracted verbatim from `pin_autodiscovery` (cohesive seam: the pin
formats that scan a DIRECTORY of files rather than reading a single
well-known file). Per `SPECIFICATION/contracts.md` section "Pin autodiscovery
rules", the directory-scan formats are:

- `.github/workflows/*.yml` / `*.yaml` `uses:` ref — every line of the
  form `uses: <owner>/<repo>/<path>@<ref>` in any GitHub Actions
  workflow file.
- fabro-sandbox docker image tag — the
  `docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>"` line in
  every Fabro `workflow.toml` under either `.claude-plugin/.fabro/workflows/`
  or the root `.fabro/workflows/`, AND the same image reference as the
  `image:` line under a job's `container:` block in every
  `.github/workflows/*.yml` (where a cut-over consumer runs its CI inside
  the baked sandbox image). Both surfaces are the one format, walked by a
  function each; every matching line yields its own record, so one release
  fan-out reconciles a consumer's CI image and its Fabro sandbox image
  together instead of leaving CI behind.

Co-located here (it is the sibling docker-image adapter pin, though it
reads one well-known file rather than scanning a directory):

- codex-acp Dockerfile `ARG` — the `ARG CODEX_ACP_VERSION=<version>` line
  in `docker/fabro-sandbox/agent/Dockerfile`. Unlike every other format
  its source is EXTERNAL to the fleet (the npm package
  `agentclientprotocol/codex-acp`), so no fleet release fan-out ever rewrites
  it and it is factory-gated on bump (section "codex-acp factory gate").

The shared `record` normalizer lives here (imported by
`_pin_single_file_formats`) — every discovered pin, single-file or
directory-scan, is emitted through it so the record shape is defined in
exactly one place.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "PinFileUnparseable",
    "PinFileUnreadable",
    "PinWalkFailure",
    "PinWalkResult",
    "failed_read",
    "read_pin_text",
    "record",
    "walk_codex_acp_docker_arg",
    "walk_fabro_workflow_docker",
    "walk_github_workflow_container_image",
    "walk_github_workflow_uses",
]


@dataclass(frozen=True, kw_only=True)
class PinFileUnreadable:
    """The walk FOUND a pin file and could not read its BYTES.

    A transport failure — absent permissions, a vanished file, bytes that
    are not UTF-8. It is not attributable to the member's committed
    content and may not reproduce on the next run, which is why
    `SPECIFICATION/contracts.md` section "Pin-currency severity policy" keeps it
    at the row's lower severity: "a can't-read is not a violation"
    (livespec-dev-tooling-6ge). The consuming row renders it as a SKIP.

    `file_path` names the file rather than leaving the operator to guess.
    The reader is typically walking a materialized copy of ANOTHER repo's
    tree — the central fleet sweep writes member files into a temp
    directory before walking them — so "a pin file could not be read"
    without the path is a diagnostic they cannot act on. `pin_walk` names
    the walker for the same reason, since one repo can carry files of
    several formats.
    """

    pin_walk: str
    file_path: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class PinFileUnparseable:
    """The walk READ a pin file's bytes and could not make sense of them.

    NOT a `PinFileUnreadable`, and the distinction is load-bearing rather
    than taxonomic. A can't-parse is a DEFINITIVE, REPRODUCIBLE property
    of the member's committed bytes: it will fail identically on every
    future run until someone edits the file. `SPECIFICATION/contracts.md`
    section "Pin-currency severity policy" therefore requires the consuming row
    to render it as a FINDING — never a pass, and never the skip a
    can't-read earns.

    Two types rather than one flag because the two have DIFFERENT
    RENDERINGS at the row (`RowSkip` vs `RowFinding`), and a single type
    carrying a boolean invites a caller to handle one arm and forget the
    other. That forgetting is exactly livespec-dev-tooling-2j2l: the
    predecessor of this type was an in-band record with
    `pin_format="unrecognized"`, which `_rows_pin_currency._records_for`
    silently dropped through its `pin_format` equality filter, turning an
    unparseable pin file into a PASSING row. A record is the one carrier
    a record-filtering consumer discards without ever making a decision;
    a failure-track value of its own type is not.
    """

    pin_walk: str
    file_path: str
    detail: str


# The walk's failure track. Both arms name the file and the walker; they
# differ in what the row must DO about them, which is why they are
# distinct types rather than one type with a discriminator field.
PinWalkFailure = PinFileUnreadable | PinFileUnparseable
PinWalkResult = IOResult[list[dict[str, str]], PinWalkFailure]


_PIN_FORMAT_WORKFLOW_USES = "github_workflow_uses_ref"
_PIN_FORMAT_FABRO_DOCKER = "fabro_sandbox_docker_image"
_PIN_FORMAT_CODEX_ACP = "codex_acp_docker_arg"

# The fabro-sandbox image is BUILT + RELEASED by livespec-dev-tooling and its
# tag tracks the dev-tooling release version, so this pin's source repo is
# HARDCODED (unlike pyproject, whose source repo derives from the git URL).
_FABRO_SANDBOX_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"
_FABRO_SANDBOX_SOURCE_REPO = "livespec-dev-tooling"
# Fleet consumers carry the Fabro workflow config at one of two roots: the
# orchestrator under `.claude-plugin/.fabro/workflows/`, the console under the
# top-level `.fabro/workflows/`. Both are walked so neither consumer is missed.
_FABRO_WORKFLOW_DIRS: tuple[tuple[str, ...], ...] = (
    (".claude-plugin", ".fabro", "workflows"),
    (".fabro", "workflows"),
)


def read_pin_text(*, path: Path, pin_walk: str) -> IOResult[str, PinFileUnreadable]:
    """`path`'s UTF-8 text, or the failure-track value naming the file.

    THE ONE READER every walker uses, in both walker modules. Both flavors
    of read failure — `OSError` (absent permissions, a vanished file) and
    `UnicodeDecodeError` (bytes that are not UTF-8) — become one
    `PinFileUnreadable` carrying the path, so the caller handles a single
    shape.

    `UnicodeDecodeError` is why this function exists at all: it carries the
    offending BYTES and NO filename, so a decode failure escaping a walk
    could only ever be reported against the walk ROOT. The operator reading
    that is looking at a materialized copy of ANOTHER repo's tree, where
    "some pin file did not decode" is not something they can act on.

    `pin_walk` is a PARAMETER rather than something the caller patches in
    afterwards. Before the conversion, `pin_autodiscovery.discover` filled
    it from its own loop variable (`walk.__name__`) while catching the
    raise. Once the failure is a VALUE returned from here, that loop can no
    longer supply it — and a walker's identity is not recoverable from a
    `Path`. Taking it as an argument keeps ONE failure type with ONE
    construction site; the alternative (each walker re-mapping the failure
    through `.alt()`) adds a rewrite at every call site that can be
    silently forgotten, which is the class of omission this epic exists to
    remove.

    A NEW `read_text` added to a walker without going through here would
    reopen the hole silently — it would raise past the walk's `IOResult`
    boundary instead of landing on the failure track.
    """
    try:
        return IOSuccess(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as unreadable:
        return IOFailure(
            PinFileUnreadable(pin_walk=pin_walk, file_path=str(path), detail=str(unreadable))
        )


def failed_read(*, result: IOResult[str, PinFileUnreadable]) -> PinWalkResult:
    """Re-wrap a `read_pin_text` failure as the WALK's failure, preserving it.

    `read_pin_text` fails with `IOResult[str, ...]`; a walker returns
    `IOResult[list[...], ...]`. The success types differ, so a walker
    cannot return the reader's value directly. This lifts it without
    inspecting or rewriting the failure, so the file path and walker name
    the reader recorded reach the row unchanged.

    Call it ONLY on a value already known to be an `IOFailure`.
    """
    return IOFailure(unsafe_perform_io(result.failure()))


def record(
    *,
    pin_format: str,
    file_path: str,
    pin_key: str,
    current_value: str,
    source_repo: str,
) -> dict[str, str]:
    return {
        "pin_format": pin_format,
        "file_path": file_path,
        "pin_key": pin_key,
        "current_value": current_value,
        "source_repo": source_repo,
    }


_WORKFLOW_USES_RE = re.compile(
    r"""
    ^\s+uses:\s+
    (?P<owner>[A-Za-z0-9_.-]+)/
    (?P<repo>[A-Za-z0-9_.-]+)/
    (?P<path>[^@\s]+)@
    (?P<ref>[^\s#]+)
    """,
    re.VERBOSE,
)


def walk_github_workflow_uses(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> PinWalkResult:
    workflows_dir = root / ".github" / "workflows"
    # An ABSENT directory is an ANSWER, not a failure: a consumer with no
    # `.github/workflows/` simply carries no pins of this format, which
    # section "Pin autodiscovery rules" makes normative tolerance for. The same
    # reading applies to a `glob` yielding nothing below.
    if not workflows_dir.is_dir():
        return IOSuccess([])
    out: list[dict[str, str]] = []
    yml_paths = sorted(list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml")))
    for yml_path in yml_paths:
        rel_path = str(yml_path.relative_to(root))
        read = read_pin_text(path=yml_path, pin_walk="walk_github_workflow_uses")
        if isinstance(read, IOFailure):
            return failed_read(result=read)
        text = unsafe_perform_io(read.unwrap())
        for line in text.splitlines():
            match = _WORKFLOW_USES_RE.match(line)
            if match is None:
                continue
            owner = match.group("owner")
            repo = match.group("repo")
            path = match.group("path")
            ref = match.group("ref")
            if source_repo_filter is not None and source_repo_filter != repo:
                continue
            out.append(
                record(
                    pin_format=_PIN_FORMAT_WORKFLOW_USES,
                    file_path=rel_path,
                    pin_key=f"{owner}/{repo}/{path}",
                    current_value=ref,
                    source_repo=repo,
                )
            )
    _ = log
    return IOSuccess(out)


_FABRO_DOCKER_RE = re.compile(
    r'^\s*docker\s*=\s*"' + re.escape(_FABRO_SANDBOX_IMAGE) + r':(?P<tag>[^"]+)"',
    re.MULTILINE,
)


def walk_fabro_workflow_docker(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> PinWalkResult:
    # The source repo is fixed at the literal "livespec-dev-tooling" (the image
    # is released by this repo; its tag tracks the dev-tooling release version),
    # so honor the filter up front — nothing here can match another source.
    source_repo = _FABRO_SANDBOX_SOURCE_REPO
    if source_repo_filter is not None and source_repo_filter != source_repo:
        return IOSuccess([])
    out: list[dict[str, str]] = []
    for parts in _FABRO_WORKFLOW_DIRS:
        workflows_dir = root.joinpath(*parts)
        if not workflows_dir.is_dir():
            continue
        for toml_path in sorted(workflows_dir.glob("*/workflow.toml")):
            rel_path = str(toml_path.relative_to(root))
            read = read_pin_text(path=toml_path, pin_walk="walk_fabro_workflow_docker")
            if isinstance(read, IOFailure):
                return failed_read(result=read)
            text = unsafe_perform_io(read.unwrap())
            # Find-ALL, not first-match-per-file: the contract's one-record-per-
            # matching-line rule binds the whole `fabro_sandbox_docker_image`
            # format, not only its `.github/workflows/` surface.
            for match in _FABRO_DOCKER_RE.finditer(text):
                out.append(
                    record(
                        pin_format=_PIN_FORMAT_FABRO_DOCKER,
                        file_path=rel_path,
                        pin_key=_FABRO_SANDBOX_IMAGE,
                        current_value=match.group("tag"),
                        source_repo=source_repo,
                    )
                )
    _ = log
    return IOSuccess(out)


# The SAME fabro-sandbox image, pinned at a SECOND surface: a cut-over consumer
# runs its CI jobs inside the baked sandbox image, so the reference appears in
# `.github/workflows/*.yml` as the `image:` line nested under a job's
# `container:` block. GitHub Actions has no workflow-level `container:`, so a
# consumer repeats that block PER JOB — hence one record per matching line, both
# across files and within one file. The one-line `container: <image>` shorthand
# is covered by the same scoped match. The match is scoped to the fabro-sandbox
# image itself so an unrelated `container:` / `image:` line yields no record.
_WORKFLOW_CONTAINER_IMAGE_RE = re.compile(
    r"""
    ^\s*(?:image|container):\s+
    ["']?
    """
    + re.escape(_FABRO_SANDBOX_IMAGE)
    + r""":
    (?P<tag>[^\s"'#]+)
    """,
    re.VERBOSE,
)


def walk_github_workflow_container_image(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> PinWalkResult:
    # Same hardcoded source repo as the `workflow.toml` surface (the image is
    # released by livespec-dev-tooling and its tag tracks the dev-tooling release
    # version), which is what lets a dev-tooling release fan-out rewrite a
    # consumer's CI image in the SAME bump commit as its pyproject/compat pins.
    source_repo = _FABRO_SANDBOX_SOURCE_REPO
    if source_repo_filter is not None and source_repo_filter != source_repo:
        return IOSuccess([])
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return IOSuccess([])
    out: list[dict[str, str]] = []
    yml_paths = sorted(list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml")))
    for yml_path in yml_paths:
        rel_path = str(yml_path.relative_to(root))
        read = read_pin_text(path=yml_path, pin_walk="walk_github_workflow_container_image")
        if isinstance(read, IOFailure):
            return failed_read(result=read)
        text = unsafe_perform_io(read.unwrap())
        for line in text.splitlines():
            match = _WORKFLOW_CONTAINER_IMAGE_RE.match(line)
            if match is None:
                continue
            out.append(
                record(
                    pin_format=_PIN_FORMAT_FABRO_DOCKER,
                    file_path=rel_path,
                    pin_key=_FABRO_SANDBOX_IMAGE,
                    current_value=match.group("tag"),
                    source_repo=source_repo,
                )
            )
    _ = log
    return IOSuccess(out)


# The codex-acp adapter version is baked into the fabro-sandbox AGENT-layer
# Dockerfile as a bare-semver `ARG`. Its source is the EXTERNAL npm package
# `@agentclientprotocol/codex-acp` (the Codex ACP adapter the orchestrator's
# implementer nodes run), so — unlike the fabro image tag, released BY this
# fleet — the source repo is HARDCODED to the external GitHub repository and no
# fleet release fan-out ever rewrites it. `current_value` is the bare npm semver
# (no `v` prefix).
# Package succession (livespec-dev-tooling-opdc, 2026-08-26): the predecessor
# `@zed-industries/codex-acp` is npm-deprecated at its terminal 0.16.0 and MUST
# NOT be the autodiscovered source (contracts.md section "Pin autodiscovery
# rules"). Changing WHICH package this pins is a succession, never a bump.
_CODEX_ACP_SOURCE_REPO = "agentclientprotocol/codex-acp"
_CODEX_ACP_ARG_NAME = "CODEX_ACP_VERSION"
_CODEX_ACP_DOCKERFILE: tuple[str, ...] = ("docker", "fabro-sandbox", "agent", "Dockerfile")
_CODEX_ACP_ARG_RE = re.compile(
    r"^ARG\s+" + re.escape(_CODEX_ACP_ARG_NAME) + r"=(?P<version>\S+)\s*$",
    re.MULTILINE,
)


def walk_codex_acp_docker_arg(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> PinWalkResult:
    # The source is the EXTERNAL npm package agentclientprotocol/codex-acp, not a
    # fleet repo, so honor the filter up front: a fleet-release fan-out
    # (`--source-repo <fleet-repo>`) must NEVER match this pin — that would let a
    # sibling release rewrite the baked Codex adapter version. The record is
    # emitted only when the filter is absent (the freshness scan) or equals the
    # external source `agentclientprotocol/codex-acp`.
    source_repo = _CODEX_ACP_SOURCE_REPO
    if source_repo_filter is not None and source_repo_filter != source_repo:
        return IOSuccess([])
    dockerfile = root.joinpath(*_CODEX_ACP_DOCKERFILE)
    # An ABSENT Dockerfile is an ANSWER — this consumer bakes no codex-acp
    # adapter — exactly as an absent `.vendor.jsonc` is.
    if not dockerfile.is_file():
        return IOSuccess([])
    read = read_pin_text(path=dockerfile, pin_walk="walk_codex_acp_docker_arg")
    if isinstance(read, IOFailure):
        return failed_read(result=read)
    match = _CODEX_ACP_ARG_RE.search(unsafe_perform_io(read.unwrap()))
    # A Dockerfile carrying no `ARG CODEX_ACP_VERSION=` line is ALSO an
    # answer, not a parse failure: the file is a Dockerfile, not a
    # dedicated pin manifest, so its shape is not this format's to
    # adjudicate. Contrast `walk_pyproject_toml`, where a
    # `[tool.uv.sources]` block that yields no entry IS unparseable —
    # there the block exists solely to hold pins.
    if match is None:
        return IOSuccess([])
    _ = log
    return IOSuccess(
        [
            record(
                pin_format=_PIN_FORMAT_CODEX_ACP,
                file_path=str(dockerfile.relative_to(root)),
                pin_key=_CODEX_ACP_ARG_NAME,
                current_value=match.group("version"),
                source_repo=source_repo,
            )
        ]
    )
