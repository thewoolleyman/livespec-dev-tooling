"""_pin_directory_scan_formats — directory-scanning pin-format walks.

Extracted verbatim from `pin_autodiscovery` (cohesive seam: the two pin
formats that scan a DIRECTORY of files rather than reading a single
well-known file). Per `SPECIFICATION/contracts.md` §"Pin autodiscovery
rules", these two formats are:

- `.github/workflows/*.yml` / `*.yaml` `uses:` ref — every line of the
  form `uses: <owner>/<repo>/<path>@<ref>` in any GitHub Actions
  workflow file.
- fabro-sandbox docker image tag — the
  `docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>"` line in
  every Fabro `workflow.toml` under either `.claude-plugin/.fabro/workflows/`
  or the root `.fabro/workflows/`.

The shared `record` normalizer lives here (imported by
`_pin_single_file_formats`) — every discovered pin, single-file or
directory-scan, is emitted through it so the record shape is defined in
exactly one place.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "record",
    "walk_fabro_workflow_docker",
    "walk_github_workflow_uses",
]


_PIN_FORMAT_WORKFLOW_USES = "github_workflow_uses_ref"
_PIN_FORMAT_FABRO_DOCKER = "fabro_sandbox_docker_image"

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
) -> list[dict[str, str]]:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []
    out: list[dict[str, str]] = []
    yml_paths = sorted(list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml")))
    for yml_path in yml_paths:
        rel_path = str(yml_path.relative_to(root))
        text = yml_path.read_text(encoding="utf-8")
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
    return out


_FABRO_DOCKER_RE = re.compile(
    r'^\s*docker\s*=\s*"' + re.escape(_FABRO_SANDBOX_IMAGE) + r':(?P<tag>[^"]+)"',
    re.MULTILINE,
)


def walk_fabro_workflow_docker(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> list[dict[str, str]]:
    # The source repo is fixed at the literal "livespec-dev-tooling" (the image
    # is released by this repo; its tag tracks the dev-tooling release version),
    # so honor the filter up front — nothing here can match another source.
    source_repo = _FABRO_SANDBOX_SOURCE_REPO
    if source_repo_filter is not None and source_repo_filter != source_repo:
        return []
    out: list[dict[str, str]] = []
    for parts in _FABRO_WORKFLOW_DIRS:
        workflows_dir = root.joinpath(*parts)
        if not workflows_dir.is_dir():
            continue
        for toml_path in sorted(workflows_dir.glob("*/workflow.toml")):
            rel_path = str(toml_path.relative_to(root))
            text = toml_path.read_text(encoding="utf-8")
            match = _FABRO_DOCKER_RE.search(text)
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
    return out
