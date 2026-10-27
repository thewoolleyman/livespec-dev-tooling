"""fabro_image_pin_lockstep — Fabro sandbox image pins match this repo's pins.

The fleet Fabro sandbox image is built as a LAYER TREE
(`docker/fabro-sandbox/<layer>/Dockerfile`): `base → python →
{python-agent, python-rust → {python-rust-agent, python-rust-fuzz}}`, where
the `agent` leaf Dockerfile is built twice, once atop each of `python` and
`python-rust`, and `python-rust-fuzz` is a CI-only leaf (g++ + nightly +
cargo-fuzz for fuzzing consumers) with no agent atop it.
The versions each layer bakes are declared as greppable `ARG NAME=value`
lines, and the obligated ones MUST stay in lockstep with this repo's own
pin sources:

- EVERY `.mise.toml` `[tools]` pin ↔ a same-named `ARG <TOOL>_VERSION`
  that some layer must both declare AND install via `mise use -g`. The
  obligation is DERIVED from the table, not listed here, so a newly
  declared tool cannot slip through unbaked — an unbaked tool is
  re-fetched over the network by every containerized job, which is how
  a `shellcheck` CDN hiccup came to kill unrelated checks.
- `ARG PYTHON_VERSION` ↔ `.python-version`.
- `ARG GH_VERSION` ↔ the supported GitHub CLI pin required by the
  Fabro PR orchestration surface.

ONE OBLIGATION HERE IS NOT AN IMAGE-BAKED ARG AT ALL, and it belongs in
this module for the same reason the others do — it asks whether a copy of
a Fabro sandbox image pin still equals the pin it was copied from.
`ci-runner/k3s/phase2/factory/factory-reach-image.env` SHIPS the sandbox
image reference to a CI-pool node, because the factory reach check is a
converge artifact and the installed tree it runs from carries no
repository checkout (work-item `livespec-dev-tooling-jvnqwv`, freeze
ruling R70). The reference it ships is the same one the release fan-out
rewrites in `.github/workflows/ci.yml`'s job `container:` blocks — so the
shipped file must name exactly one image, the workflow must declare
exactly one distinct container image, and the two must be EQUAL. Both
files are REQUIRED inputs: treating either absence as "nothing to
compare" would make the obligation vanish on a rename, which is the
laxer-by-accident shape every arm here is written to avoid. Nothing on
the node can notice the drift by itself — the check renders a Job, the
Job pulls a superseded image, and it reports green for a toolchain no
dispatch runs.

These ARGs live in DIFFERENT layer files (`JUST_VERSION` /
`LEFTHOOK_VERSION` / `SHELLCHECK_VERSION` in `base`;
`UV_VERSION` / `PYTHON_VERSION` in `python`;
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
has an EXTERNAL npm source (`@agentclientprotocol/codex-acp`) and IS
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
# The factory reach check's shipped copy of the fleet sandbox image pin, and
# the workflow surface the release fan-out rewrites that same reference at.
_FACTORY_REACH_PIN_PATH = (
    Path("ci-runner") / "k3s" / "phase2" / "factory" / "factory-reach-image.env"
)
_CI_WORKFLOW_PATH = Path(".github") / "workflows" / "ci.yml"
_FACTORY_REACH_PIN_KEY = "FACTORY_REACH_SANDBOX_IMAGE"

_ARG_LINE = re.compile(r"^ARG\s+([A-Z0-9_]+)=(\S+)\s*$")
_FACTORY_REACH_PIN_LINE = re.compile(rf"^[ \t]*{_FACTORY_REACH_PIN_KEY}=(\S+)[ \t]*$", re.MULTILINE)
# An `image:` that is the FIRST field of a job's `container:` block — the one
# surface the release fan-out's `fabro_sandbox_docker_image` rewrite touches in
# a workflow, and the shape every containerized job in this repo's ci.yml uses.
# Matched as a two-line pattern so a stray `image:` elsewhere in the workflow
# (a service container, a step input) contributes nothing.
_WORKFLOW_CONTAINER_IMAGE = re.compile(
    r"^[ \t]*container:[ \t]*\n[ \t]*image:[ \t]*(\S+)[ \t]*$", re.MULTILINE
)
_TOOLS_TABLE_HEADER = re.compile(r"^\[tools\]\s*$")
_TOOL_LINE = re.compile(r'^\s*([\w-]+)\s*=\s*"([^"]+)"\s*$')

# Lockstep obligations are DERIVED from the `.mise.toml` `[tools]` table
# rather than listed here: every declared tool obligates a same-named ARG
# pin (`<TOOL>_VERSION`) that the image must both carry and install. A
# hardcoded list made a newly declared tool carry NO obligation, so it
# silently stayed out of the image and became a per-job network fetch on
# every containerized CI job — the state `shellcheck` reached. Deriving
# the set means the check fails until the tool is genuinely baked.
# PYTHON_VERSION is handled separately (its repo-side pin source is
# `.python-version`, not the mise table).
#
# Derivation covers only the tools a repo DOES declare, so it cannot
# notice one silently dropped from the table. `_REQUIRED_MISE_TOOLS` is
# the complementary direction: the toolchain every fleet repo must keep
# declared, checked independently of what the image happens to bake.
_REQUIRED_MISE_TOOLS = ("just", "lefthook", "shellcheck", "uv")
_PYTHON_LOCKSTEP_ARG = "PYTHON_VERSION"
_GH_SUPPORTED_ARG = "GH_VERSION"
_SUPPORTED_GH_VERSION = "2.102.0"
_GH_SHA256_ARG = "GH_SHA256"
_GH_RELEASE_URL = "https://github.com/cli/cli/releases/download/v${GH_VERSION}/"
_GH_CHECKSUM_VERIFY = '"${GH_SHA256}  /tmp/gh.tgz" | sha256sum -c -'
_GH_MISE_PIN = "gh@${GH_VERSION}"
_CHAIN_DEFAULT_ARGS = (
    ("BASE_IMAGE", "livespec-fabro-sandbox:base-dev"),
    ("PYTHON_IMAGE", "livespec-fabro-sandbox:python-dev"),
    ("PARENT_IMAGE", "livespec-fabro-sandbox:python-dev"),
    ("PYTHON_RUST_IMAGE", "livespec-fabro-sandbox:python-rust-dev"),
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


def _mise_lockstep_arg(*, tool_name: str) -> str:
    """Derive a tool's obligated Dockerfile ARG name from its `[tools]` key.

    The image names each baked tool pin `<TOOL>_VERSION`, upper-cased with
    `-` folded to `_` so the name is a legal ARG identifier (`shellcheck`
    -> `SHELLCHECK_VERSION`).
    """
    return tool_name.upper().replace("-", "_") + "_VERSION"


def _mise_install_pin(*, tool_name: str, arg_name: str) -> str:
    """The `mise use -g` fragment that proves the tool is baked, not just pinned."""
    return tool_name + "@${" + arg_name + "}"


def _mise_tool_issues(
    *,
    dockerfile_args: dict[str, str],
    mise_tools: dict[str, str],
    dockerfile_source: str,
) -> list[str]:
    """Check both mise-tool directions: required-and-declared, and declared-and-baked."""
    issues: list[str] = []
    for tool_name in _REQUIRED_MISE_TOOLS:
        if tool_name not in mise_tools:
            issues.append(f"{tool_name}: pin missing from {_MISE_PATH} [tools]")
    for tool_name, repo_value in sorted(mise_tools.items()):
        arg_name = _mise_lockstep_arg(tool_name=tool_name)
        image_value = dockerfile_args.get(arg_name)
        if image_value is None:
            issues.append(
                f"{arg_name}: obligated ARG pin missing from the {_LAYER_DIR} layers "
                f"({_MISE_PATH} declares {tool_name}, so the image must bake it — "
                f"an unbaked tool is re-fetched over the network by every job)"
            )
            continue
        if image_value != repo_value:
            issues.append(
                f"{arg_name}: image bakes {image_value!r} but "
                f"{_MISE_PATH} pins {tool_name} = {repo_value!r}"
            )
            continue
        install_pin = _mise_install_pin(tool_name=tool_name, arg_name=arg_name)
        if install_pin not in dockerfile_source:
            issues.append(
                f"{tool_name}: ARG {arg_name} is pinned but no layer installs it — "
                f"the image must carry `mise use -g {install_pin}` so the tool is "
                f"baked rather than fetched per job"
            )
    return issues


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
    issues.extend(
        _mise_tool_issues(
            dockerfile_args=dockerfile_args,
            mise_tools=mise_tools,
            dockerfile_source=dockerfile_source,
        )
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
    issues.extend(
        _gh_install_issues(dockerfile_source=dockerfile_source, dockerfile_args=dockerfile_args)
    )
    return issues


def _factory_reach_pin_issues(*, shipped_source: str, workflow_source: str) -> list[str]:
    """Compare the SHIPPED factory-reach image pin against the workflow's pin.

    Three findings, and the two refusals come before the comparison because
    neither has an answer to compare: a shipped file naming no image (or two)
    leaves the reach check unable to render a Job at all, and a workflow
    declaring two distinct container images makes "which one must the shipped
    pin equal" a real question that picking would silently answer wrong.
    """
    shipped = set(_FACTORY_REACH_PIN_LINE.findall(shipped_source))
    workflow = set(_WORKFLOW_CONTAINER_IMAGE.findall(workflow_source))
    if len(shipped) != 1:
        return [
            f"{_FACTORY_REACH_PIN_KEY}: {_FACTORY_REACH_PIN_PATH} names {len(shipped)} "
            f"distinct image references {sorted(shipped)}; it must name exactly one — it "
            f"is the ONLY sandbox image pin present on a CI-pool node"
        ]
    if len(workflow) != 1:
        return [
            f"{_FACTORY_REACH_PIN_KEY}: {_CI_WORKFLOW_PATH} declares {len(workflow)} "
            f"distinct job `container:` images {sorted(workflow)}; refusing to guess which "
            f"one {_FACTORY_REACH_PIN_PATH} must equal"
        ]
    shipped_image = shipped.pop()
    workflow_image = workflow.pop()
    if shipped_image != workflow_image:
        return [
            f"{_FACTORY_REACH_PIN_KEY}: {_FACTORY_REACH_PIN_PATH} ships "
            f"{shipped_image!r} but {_CI_WORKFLOW_PATH} pins {workflow_image!r} — the "
            f"shipped copy is what a pool node pulls, so bump BOTH in the same change"
        ]
    return []


def _gh_install_issues(*, dockerfile_source: str, dockerfile_args: dict[str, str]) -> list[str]:
    issues: list[str] = []
    if _GH_RELEASE_URL not in dockerfile_source:
        issues.append(
            "GH_VERSION: gh must be downloaded from its pinned GitHub release "
            f"{_GH_RELEASE_URL!r} (cli.github.com's apt repo only serves the "
            "current version, so an exact apt pin rots)"
        )
    if not dockerfile_args.get(_GH_SHA256_ARG):
        issues.append(f"GH_VERSION: the image must pin {_GH_SHA256_ARG} for the gh release tarball")
    if _GH_CHECKSUM_VERIFY not in dockerfile_source:
        issues.append(f"GH_VERSION: the gh install must verify {_GH_CHECKSUM_VERIFY!r}")
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
    pin_sources = (
        cwd / _MISE_PATH,
        cwd / _PYTHON_VERSION_PATH,
        cwd / _FACTORY_REACH_PIN_PATH,
        cwd / _CI_WORKFLOW_PATH,
    )
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
    issues.extend(
        _factory_reach_pin_issues(
            shipped_source=(cwd / _FACTORY_REACH_PIN_PATH).read_text(encoding="utf-8"),
            workflow_source=(cwd / _CI_WORKFLOW_PATH).read_text(encoding="utf-8"),
        )
    )
    if issues:
        for issue in issues:
            log.error("fabro sandbox image pin out of lockstep", issue=issue)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
