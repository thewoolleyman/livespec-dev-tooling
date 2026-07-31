"""pin_autodiscovery — walk a consumer repo and emit pin records as JSON.

Per `SPECIFICATION/contracts.md` §"Pin autodiscovery rules", the walk
inspects the consumer repository for every supported pin format and
yields a normalized record per discovered pin. The walk covers six
formats, split across two cohesive helper modules:

- single-file formats (`_pin_single_file_formats`): `.livespec.jsonc`
  `compat.pinned`, `pyproject.toml` `[tool.uv.sources]`, and
  `.vendor.jsonc` — each reads a single well-known file at the repo root.
- directory-scan formats (`_pin_directory_scan_formats`): the
  `.github/workflows/*.yml` `uses:` ref and the fabro-sandbox docker
  image tag — the latter found at two surfaces walked as ONE format,
  the `docker =` line in `.fabro` `workflow.toml` files and the
  per-job `container:` block's `image:` line in
  `.github/workflows/*.yml`, each matching line yielding its own
  record. Each scans a directory of files. Co-located there: the
  codex-acp Dockerfile `ARG` pin
  (`ARG CODEX_ACP_VERSION=<version>` in
  `docker/fabro-sandbox/agent/Dockerfile`), whose EXTERNAL npm source
  (`zed-industries/codex-acp`) means no fleet fan-out rewrites it and a
  bump is factory-gated (§"codex-acp factory gate"). The shared `record`
  normalizer lives there too.

`.copier-answers.yml` `_commit` is deliberately NOT a pin format: it
is copier render-provenance, not a version pin, so rewriting it would
desync the render-provenance marker and poison future `copier update`s.

Invocation:

    python -m livespec_dev_tooling.cross_repo.pin_autodiscovery \\
        [--root <path>] [--source-repo <name>] [--json]

`--root` defaults to the current working directory. `--source-repo`
filters records to a single source; omit it to emit every discovered
pin. `--json` is the default (and currently only) output mode and is
accepted for forward-compat with any future text mode.

Tolerance, and its ONE limit:

- Missing pin files yield no records (no error).
- An unrecognized pin format on a file we DID find but cannot parse
  yields one record with `pin_format: "unrecognized"` and the file
  path for human inspection.
- A file the walk FOUND and could not READ is NOT tolerated. It is the
  third input, distinct from both of the above, and the only one
  `SPECIFICATION/contracts.md` §"Pin autodiscovery rules" does not
  make normative tolerance for. It lands on `discover`'s failure track
  naming the file. Before livespec-dev-tooling-9sl0 it propagated as an
  uncaught `OSError` / `UnicodeDecodeError` out of a function whose
  contract is tolerance — which in the central fleet sweep killed the
  whole nine-member run partway through one member's walk.

Output discipline mirrors the check modules: structured stderr via
structlog when diagnostics are emitted; the result JSON array is
written to stdout. No `print()`, no `sys.stderr.write` direct.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.cross_repo._pin_directory_scan_formats import (  # noqa: E402
    PinFileUnparseable,
    PinFileUnreadable,
    PinWalkFailure,
    walk_codex_acp_docker_arg,
    walk_fabro_workflow_docker,
    walk_github_workflow_container_image,
    walk_github_workflow_uses,
)
from livespec_dev_tooling.cross_repo._pin_single_file_formats import (  # noqa: E402
    walk_livespec_jsonc,
    walk_pyproject_toml,
    walk_vendor_jsonc,
)

__all__: list[str] = []


# Every supported pin format's walker, in the order the records are
# emitted. A tuple rather than seven `records.extend(...)` lines because
# the walk now has to name WHICH walker hit an unreadable file, and a
# walker's identity is not recoverable from the exception.
_WALKS = (
    walk_livespec_jsonc,
    walk_pyproject_toml,
    walk_vendor_jsonc,
    walk_github_workflow_uses,
    walk_fabro_workflow_docker,
    walk_github_workflow_container_image,
    walk_codex_acp_docker_arg,
)


# `PinFileUnreadable` and `PinFileUnparseable` are DEFINED in
# `_pin_directory_scan_formats` (beside `read_pin_text`, which constructs the
# first) and RE-EXPORTED here. They cannot live in this module: it imports the
# walkers, so a walker naming a type defined here would close an import cycle.
# The re-export keeps `from ...pin_autodiscovery import PinFileUnreadable`
# resolving for existing consumers — `fleet/_rows_pin_currency.py` imports it
# from here.
__all__ += ["PinFileUnparseable", "PinFileUnreadable", "PinWalkFailure"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pin-autodiscovery",
        description=(
            "Walk a consumer repo and emit a JSON array of pin records per "
            'SPECIFICATION/contracts.md §"Pin autodiscovery rules". Covers '
            ".livespec.jsonc, pyproject.toml [tool.uv.sources], .vendor.jsonc, "
            ".github/workflows/*.yml uses: refs, the fabro-sandbox docker "
            "image tag in .fabro workflow.toml files, and the codex-acp "
            "Dockerfile ARG CODEX_ACP_VERSION pin."
        ),
    )
    _ = parser.add_argument(
        "--root",
        type=Path,
        default=None,
        metavar="PATH",
        help="consumer repo root to walk (default: current working directory)",
    )
    _ = parser.add_argument(
        "--source-repo",
        type=str,
        default=None,
        metavar="NAME",
        help="restrict output to pins of this source repo (omit to emit all)",
    )
    _ = parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="emit JSON to stdout (default; accepted for forward-compat)",
    )
    return parser


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("pin_autodiscovery")


def discover(
    *, root: Path, source_repo: str | None
) -> IOResult[list[dict[str, str]], PinWalkFailure]:
    """Walk `root` for pin records, or name the file the walk could not use.

    Importable for embedded use (e.g., from a future Python-driven
    workflow); equivalent to invoking the CLI with `--root=<root>` and
    optionally `--source-repo=<source_repo>`.

    `IOResult` rather than `Result`: the seven walkers reach the filesystem
    DIRECTLY, through `path.read_text()` and `Path.glob`, with no injected
    seam between them and the disk. That is what livespec v179 member 1
    clause (d) — the callee fixpoint — sees, and it is the honest type.

    NO `try` here any more. Each walker returns its own `IOResult`, so the
    railway sits at the seam that actually touches the disk rather than one
    level up — and a walker that bypassed the shared reader can no longer
    fail quietly into a weaker root-named diagnostic, because there is no
    catch to land in.

    The walk STOPS at the first failure, and that is unchanged for BOTH
    failure arms. A partial record list would be worse than a failure: it
    is shaped exactly like a complete walk of a repo that happens to carry
    fewer pins, so a caller filtering it by pin format cannot tell the two
    apart. That argument applied to an unreadable file before
    livespec-dev-tooling-9sl0 and applies identically to an UNPARSEABLE one
    now — which is livespec-dev-tooling-2j2l, previously one level down and
    now closed here.
    """
    log = _configure_logger()
    records: list[dict[str, str]] = []
    for walk in _WALKS:
        walked = walk(root=root, source_repo_filter=source_repo, log=log)
        if isinstance(walked, IOFailure):
            return walked
        records.extend(unsafe_perform_io(walked.unwrap()))
    return IOSuccess(records)


def main() -> int:
    args = _build_parser().parse_args()
    root: Path = args.root if args.root is not None else Path.cwd()
    source_repo: str | None = args.source_repo
    walked = discover(root=root, source_repo=source_repo)
    if isinstance(walked, IOFailure):
        # FAIL LOUD, never an empty array. Emitting `[]` here would be
        # indistinguishable from a repo that genuinely carries no pins, and
        # every consumer of this stdout treats "no records" as "nothing to
        # bump" — so a single unreadable file would silently skip a
        # consumer in a release fan-out.
        failure = unsafe_perform_io(walked.failure())
        # Name WHICH failure: an operator's next action differs. A can't-read
        # may be environmental and worth retrying; a can't-parse is a
        # definitive property of the committed bytes and needs an edit.
        _configure_logger().error(
            (
                "pin autodiscovery could not PARSE a pin file"
                if isinstance(failure, PinFileUnparseable)
                else "pin autodiscovery could not READ a pin file"
            ),
            pin_walk=failure.pin_walk,
            file_path=failure.file_path,
            detail=failure.detail,
        )
        return 1
    # `unsafe_perform_io` is NOT ceremony: `IOResult.unwrap()` returns an
    # `IO[T]`, not a `T`, and `json.dumps(IO([...]))` raises rather than
    # silently emitting the wrong thing — but the sibling spellings of this
    # mistake do not (see `required_role_keys_declared`), so the correct
    # form is used here rather than the one that happens to fail loudly.
    _ = sys.stdout.write(json.dumps(unsafe_perform_io(walked.unwrap()), indent=2, sort_keys=True))
    _ = sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
