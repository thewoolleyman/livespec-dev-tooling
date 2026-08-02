"""fabro_image_pin_lockstep — Fabro sandbox image pins match this repo's pins.

The fleet Fabro sandbox image is built as a LAYER TREE
(`docker/fabro-sandbox/<layer>/Dockerfile`): `base → python →
{python-agent, python-rust → python-rust-agent}`, where the `agent` leaf
Dockerfile is built twice, once atop each of `python` and `python-rust`.
The versions each layer bakes are declared as greppable `ARG NAME=value`
lines, and the obligated ones MUST stay in lockstep with this repo's own
pin sources:

- `ARG UV_VERSION` / `ARG JUST_VERSION` / `ARG LEFTHOOK_VERSION`
  ↔ the `.mise.toml` `[tools]` pins (`uv` / `just` / `lefthook`).
- `ARG PYTHON_VERSION` ↔ `.python-version`.
- `ARG GH_VERSION` ↔ the supported GitHub CLI pin required by the
  Fabro PR orchestration surface.

These ARGs live in DIFFERENT layer files (`JUST_VERSION` /
`LEFTHOOK_VERSION` in `base`; `UV_VERSION` / `PYTHON_VERSION` in `python`;
the two ACP adapter pins in `agent`), so the parser reads the ARG lines
from the whole SET of layer Dockerfiles and merges them. Keep each ARG in
exactly one layer — the merge means a duplicated ARG would NOT fail this
check, it would silently let the two copies drift.

The image's remaining ARG pins (mise itself, node, the Claude ACP
adapter `CLAUDE_AGENT_ACP_VERSION`, `RUST_VERSION`) have no repo-side pin
source — they mirror the host toolchain (or, for Rust, the console's
`rust-toolchain.toml`, checked on the CONSUMER side per the
No-Circular-Dependency Directive) — so they carry no lockstep obligation
here. `CODEX_ACP_VERSION` is the exception among the ACP adapters: it now
has an EXTERNAL npm source (`@zed-industries/codex-acp`) and IS
autodiscovered and bumpable — the pin-autodiscovery walk emits it
(pin_format `codex_acp_docker_arg`) and the pin-freshness surface opens a
bump PR on any npm `latest` difference under a live Codex-provider factory
gate (see `SPECIFICATION/contracts.md` section "codex-acp factory gate"). That
external source is verified cross-repo by the factory gate, NOT by this
in-repo lockstep check, so `CODEX_ACP_VERSION` still carries no
`.mise.toml` / `.python-version` lockstep obligation here. No image layer
pre-warms the uv cache, so there is no lockfile to drift.

Repo-private check: this repo OWNS the image, so siblings have nothing to
wire — the module deliberately lives OUTSIDE `livespec_dev_tooling/checks/`
to stay out of the canonical (fleet-universal) slug set discovered by
`canonical_checks`. Wired in this repo's justfile `check:` aggregate
(repo-private block) and the CI check-metadata matrix.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned. Diagnostics flow through structlog
(JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at module
import time.
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


_LAYER_DIR = Path("docker") / "fabro-sandbox"
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
_GH_SUPPORTED_ARG = "GH_VERSION"
_SUPPORTED_GH_VERSION = "2.96.0"
_GH_KEYRING_PATH = "/etc/apt/keyrings/githubcli-archive-keyring.gpg"
_GH_KEYRING_URL = "https://cli.github.com/packages/githubcli-archive-keyring.gpg"
_GH_APT_SOURCE = (
    "deb [arch=$(dpkg --print-architecture) signed-by="
    + _GH_KEYRING_PATH
    + "] https://cli.github.com/packages stable main"
)
_GH_PACKAGE_PIN = "gh=${GH_VERSION}"
_GH_MISE_PIN = "gh@${GH_VERSION}"
_CHAIN_DEFAULT_ARGS = (
    ("BASE_IMAGE", "livespec-fabro-sandbox:base-dev"),
    ("PYTHON_IMAGE", "livespec-fabro-sandbox:python-dev"),
    ("PARENT_IMAGE", "livespec-fabro-sandbox:python-dev"),
)


def _discover_layer_dockerfiles(*, cwd: Path) -> list[Path]:
    """Discover the layer Dockerfiles at `docker/fabro-sandbox/<layer>/Dockerfile`.

    Globs one directory level so a new layer (a new `<name>/Dockerfile`)
    is picked up automatically. Returns the matches sorted for stable
    diagnostics; empty when the layer tree is absent.
    """
    return sorted((cwd / _LAYER_DIR).glob("*/Dockerfile"))


def _parse_dockerfile_args(*, sources: list[str]) -> dict[str, str]:
    """Parse and merge `ARG NAME=value` pin lines across the layer Dockerfiles."""
    args: dict[str, str] = {}
    for source in sources:
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
    dockerfile_source: str,
) -> list[str]:
    """Compare the image-baked pins against the repo pins; return drift findings."""
    issues: list[str] = []
    for arg_name, expected in _CHAIN_DEFAULT_ARGS:
        actual = dockerfile_args.get(arg_name)
        if actual != expected:
            issues.append(
                f"{arg_name}: local FROM-chain default is {actual!r}; expected {expected!r}"
            )
    for arg_name, tool_name in _MISE_LOCKSTEP_ARGS:
        image_value = dockerfile_args.get(arg_name)
        repo_value = mise_tools.get(tool_name)
        if image_value is None:
            issues.append(f"{arg_name}: obligated ARG pin missing from the {_LAYER_DIR} layers")
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
        issues.append(
            f"{_PYTHON_LOCKSTEP_ARG}: obligated ARG pin missing from the {_LAYER_DIR} layers"
        )
    elif image_python != python_version:
        issues.append(
            f"{_PYTHON_LOCKSTEP_ARG}: image bakes {image_python!r} but "
            f"{_PYTHON_VERSION_PATH} pins {python_version!r}"
        )
    image_gh = dockerfile_args.get(_GH_SUPPORTED_ARG, "")
    if image_gh != _SUPPORTED_GH_VERSION:
        issues.append(
            f"{_GH_SUPPORTED_ARG}: image bakes {image_gh!r} but "
            f"the supported GitHub CLI pin is {_SUPPORTED_GH_VERSION!r}"
        )
    issues.extend(_gh_install_issues(dockerfile_source=dockerfile_source))
    return issues


def _gh_install_issues(*, dockerfile_source: str) -> list[str]:
    issues: list[str] = []
    if (
        _GH_KEYRING_URL not in dockerfile_source
        or _GH_KEYRING_PATH not in dockerfile_source
        or _GH_APT_SOURCE not in dockerfile_source
    ):
        issues.append(
            "GH_VERSION: gh apt source must be the signed cli.github.com repository "
            f"{_GH_APT_SOURCE!r}"
        )
    if _GH_PACKAGE_PIN not in dockerfile_source:
        issues.append(f"GH_VERSION: apt install must use the exact package pin {_GH_PACKAGE_PIN!r}")
    if _GH_MISE_PIN in dockerfile_source:
        issues.append("GH_VERSION: gh must not be installed by mise")
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
    layer_dockerfiles = _discover_layer_dockerfiles(cwd=cwd)
    if not layer_dockerfiles:
        log.error(
            "no fabro-sandbox layer Dockerfiles found",
            glob=str(_LAYER_DIR / "*" / "Dockerfile"),
        )
        return 1
    pin_sources = (cwd / _MISE_PATH, cwd / _PYTHON_VERSION_PATH)
    missing = [path for path in pin_sources if not path.is_file()]
    if missing:
        for path in missing:
            log.error(
                "pin-lockstep input file missing",
                file=str(path.relative_to(cwd)),
            )
        return 1
    mise_source = (cwd / _MISE_PATH).read_text(encoding="utf-8")
    python_source = (cwd / _PYTHON_VERSION_PATH).read_text(encoding="utf-8")
    dockerfile_sources = [path.read_text(encoding="utf-8") for path in layer_dockerfiles]
    dockerfile_args = _parse_dockerfile_args(sources=dockerfile_sources)
    issues = _lockstep_issues(
        dockerfile_args=dockerfile_args,
        mise_tools=_parse_mise_tools(source=mise_source),
        python_version=python_source.strip(),
        dockerfile_source="\n".join(dockerfile_sources),
    )
    if issues:
        for issue in issues:
            log.error("fabro sandbox image pin out of lockstep", issue=issue)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
