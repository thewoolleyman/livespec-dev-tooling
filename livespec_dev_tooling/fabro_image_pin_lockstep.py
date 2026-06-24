"""fabro_image_pin_lockstep — Fabro sandbox image pins match this repo's pins.

The fleet Fabro sandbox image (docker/fabro-sandbox/Dockerfile) bakes
the fleet toolchain as a container; the versions it bakes are
declared as greppable `ARG NAME=value` lines, and they MUST stay in
lockstep with this repo's own pin sources:

- `ARG UV_VERSION` / `ARG JUST_VERSION` / `ARG LEFTHOOK_VERSION`
  ↔ the `.mise.toml` `[tools]` pins (`uv` / `just` / `lefthook`).
- `ARG PYTHON_VERSION` ↔ `.python-version`.

The image's remaining ARG pins (mise itself, node, gh, the ACP
adapter) have no repo-side pin source — they mirror the host
toolchain and are tracked only in the Dockerfile — so they carry no
lockstep obligation. The uv package-cache pre-warm carries no drift
risk by construction: the image build COPYs this repo's own
`pyproject.toml` + `uv.lock` from the build context, so it cannot
reference a stale lockfile.

Repo-private check: this repo OWNS the image, so siblings have
nothing to wire — the module deliberately lives OUTSIDE
`livespec_dev_tooling/checks/` to stay out of the canonical
(fleet-universal) slug set discovered by `canonical_checks`. Wired
in this repo's justfile `check:` aggregate (repo-private block) and
the CI check-metadata matrix.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at
module import time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_DOCKERFILE_PATH = Path("docker") / "fabro-sandbox" / "Dockerfile"
_MISE_PATH = Path(".mise.toml")
_PYTHON_VERSION_PATH = Path(".python-version")

_ARG_LINE = re.compile(r"^ARG\s+([A-Z0-9_]+)=(\S+)\s*$")
_TOOLS_TABLE_HEADER = re.compile(r"^\[tools\]\s*$")
_TOOL_LINE = re.compile(r'^\s*([\w-]+)\s*=\s*"([^"]+)"\s*$')

# Lockstep obligations: Dockerfile ARG name ↔ `.mise.toml` `[tools]`
# pin name. PYTHON_VERSION is handled separately (its repo-side pin
# source is `.python-version`, not the mise table).
_MISE_LOCKSTEP_ARGS = (
    ("UV_VERSION", "uv"),
    ("JUST_VERSION", "just"),
    ("LEFTHOOK_VERSION", "lefthook"),
)
_PYTHON_LOCKSTEP_ARG = "PYTHON_VERSION"


def _parse_dockerfile_args(*, source: str) -> dict[str, str]:
    """Parse the Dockerfile's `ARG NAME=value` pin lines into a dict."""
    args: dict[str, str] = {}
    for raw in source.splitlines():
        match = _ARG_LINE.match(raw)
        if match is not None:
            args[match.group(1)] = match.group(2)
    return args


def _parse_mise_tools(*, source: str) -> dict[str, str]:
    """Parse `.mise.toml`'s `[tools]` table into a name->version dict."""
    tools: dict[str, str] = {}
    in_tools_section = False
    for raw in source.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if line.startswith("["):
            in_tools_section = bool(_TOOLS_TABLE_HEADER.match(line))
            continue
        if not in_tools_section:
            continue
        match = _TOOL_LINE.match(raw)
        if match is not None:
            tools[match.group(1)] = match.group(2)
    return tools


def _lockstep_issues(
    *,
    dockerfile_args: dict[str, str],
    mise_tools: dict[str, str],
    python_version: str,
) -> list[str]:
    """Compare the image-baked pins against the repo pins; return drift findings."""
    issues: list[str] = []
    for arg_name, tool_name in _MISE_LOCKSTEP_ARGS:
        image_value = dockerfile_args.get(arg_name)
        repo_value = mise_tools.get(tool_name)
        if image_value is None:
            issues.append(f"{arg_name}: obligated ARG pin missing from {_DOCKERFILE_PATH}")
            continue
        if repo_value is None:
            issues.append(f"{tool_name}: pin missing from {_MISE_PATH} [tools]")
            continue
        if image_value != repo_value:
            issues.append(
                f"{arg_name}: image bakes {image_value!r} but "
                f"{_MISE_PATH} pins {tool_name} = {repo_value!r}"
            )
    image_python = dockerfile_args.get(_PYTHON_LOCKSTEP_ARG)
    if image_python is None:
        issues.append(f"{_PYTHON_LOCKSTEP_ARG}: obligated ARG pin missing from {_DOCKERFILE_PATH}")
    elif image_python != python_version:
        issues.append(
            f"{_PYTHON_LOCKSTEP_ARG}: image bakes {image_python!r} but "
            f"{_PYTHON_VERSION_PATH} pins {python_version!r}"
        )
    return issues


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("fabro_image_pin_lockstep")
    cwd = Path.cwd()
    inputs = (
        cwd / _DOCKERFILE_PATH,
        cwd / _MISE_PATH,
        cwd / _PYTHON_VERSION_PATH,
    )
    missing = [path for path in inputs if not path.is_file()]
    if missing:
        for path in missing:
            log.error(
                "pin-lockstep input file missing",
                file=str(path.relative_to(cwd)),
            )
        return 1
    dockerfile_source, mise_source, python_source = (
        path.read_text(encoding="utf-8") for path in inputs
    )
    issues = _lockstep_issues(
        dockerfile_args=_parse_dockerfile_args(source=dockerfile_source),
        mise_tools=_parse_mise_tools(source=mise_source),
        python_version=python_source.strip(),
    )
    if issues:
        for issue in issues:
            log.error("fabro sandbox image pin out of lockstep", issue=issue)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
