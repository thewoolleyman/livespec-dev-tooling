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
  `docker/fabro-sandbox/base/Dockerfile`), whose EXTERNAL npm source
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

Tolerance:

- Missing pin files yield no records (no error).
- An unrecognized pin format on a file we DID find but cannot parse
  yields one record with `pin_format: "unrecognized"` and the file
  path for human inspection.

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

from livespec_dev_tooling.cross_repo._pin_directory_scan_formats import (  # noqa: E402
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


def discover(*, root: Path, source_repo: str | None) -> list[dict[str, str]]:
    """Pure entry point — walk `root` and return discovered pin records.

    Importable for embedded use (e.g., from a future Python-driven
    workflow); equivalent to invoking the CLI with `--root=<root>` and
    optionally `--source-repo=<source_repo>`.
    """
    log = _configure_logger()
    records: list[dict[str, str]] = []
    records.extend(walk_livespec_jsonc(root=root, source_repo_filter=source_repo, log=log))
    records.extend(walk_pyproject_toml(root=root, source_repo_filter=source_repo, log=log))
    records.extend(walk_vendor_jsonc(root=root, source_repo_filter=source_repo, log=log))
    records.extend(walk_github_workflow_uses(root=root, source_repo_filter=source_repo, log=log))
    records.extend(walk_fabro_workflow_docker(root=root, source_repo_filter=source_repo, log=log))
    records.extend(
        walk_github_workflow_container_image(root=root, source_repo_filter=source_repo, log=log)
    )
    records.extend(walk_codex_acp_docker_arg(root=root, source_repo_filter=source_repo, log=log))
    return records


def main() -> int:
    args = _build_parser().parse_args()
    root: Path = args.root if args.root is not None else Path.cwd()
    source_repo: str | None = args.source_repo
    records = discover(root=root, source_repo=source_repo)
    _ = sys.stdout.write(json.dumps(records, indent=2, sort_keys=True))
    _ = sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
