"""Shape tests for `docker/fabro-sandbox/agent/Dockerfile` during the codex-acp package succession.

Per `SPECIFICATION/contracts.md` section "Pin autodiscovery rules", `ARG CODEX_ACP_VERSION`
pins exactly ONE package — `@agentclientprotocol/codex-acp` — baked under the dedicated
npm prefix `/opt/livespec/codex-acp` and invoked at `/opt/livespec/codex-acp/bin/codex-acp`,
never as a global: both it and the deprecated predecessor `@zed-industries/codex-acp`
export the bin `codex-acp`, and `npx --no-install <package>` runs whichever package owns
the shared global bin link, so package-name resolution cannot keep them apart. The
predecessor MAY ride along for one release on a TRANSITIONAL global line that carries a
literal version, declares no ARG, and states its own removal condition.

These tests read the REAL Dockerfile so the transitional line cannot silently outlive
its removal condition and the successor cannot regress into a colliding global install.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE = _REPO_ROOT / "docker" / "fabro-sandbox" / "agent" / "Dockerfile"

_SUCCESSOR = "@agentclientprotocol/codex-acp"
_PREDECESSOR = "@zed-industries/codex-acp"
_SUCCESSOR_PREFIX = "/opt/livespec/codex-acp"
_ARG_LINE = re.compile(r"^ARG CODEX_ACP_VERSION=(?P<version>\S+)$", re.MULTILINE)
_INSTALL_LINE = re.compile(
    r"^RUN npm install -g (?P<flags>[^\n]*?)\\\n\s+(?P<spec>\S+)$", re.MULTILINE
)


def _installs() -> list[tuple[str, str]]:
    """Every `RUN npm install -g <flags> \\ <package@version>` pair in the agent layer."""
    text = _DOCKERFILE.read_text(encoding="utf-8")
    return [(m.group("flags"), m.group("spec")) for m in _INSTALL_LINE.finditer(text)]


def test_codex_acp_arg_pins_the_successor_exactly_once_under_its_dedicated_prefix() -> None:
    """One ARG line; one successor install, from the ARG, under the dedicated prefix, never global."""
    text = _DOCKERFILE.read_text(encoding="utf-8")
    args = _ARG_LINE.findall(text)
    assert len(args) == 1, f"expected exactly one ARG CODEX_ACP_VERSION line, found {len(args)}"
    assert re.fullmatch(r"\d+\.\d+\.\d+", args[0]), f"bare npm semver expected, got {args[0]!r}"
    successor = [(flags, spec) for flags, spec in _installs() if spec.startswith(_SUCCESSOR + "@")]
    assert len(successor) == 1, "the successor must be installed exactly once"
    flags, spec = successor[0]
    assert (
        spec == f"{_SUCCESSOR}@${{CODEX_ACP_VERSION}}"
    ), "the successor version must come from the ARG"
    assert (
        f"--prefix {_SUCCESSOR_PREFIX}" in flags
    ), "the successor must live under its dedicated prefix"
    assert (
        "--force" not in flags
    ), "no bin-link override: the dedicated prefix owns no global bin link"


def test_predecessor_rides_only_on_a_transitional_literal_global_line() -> None:
    """The transitional predecessor line: literal terminal version, ARG-less, global, removal stated."""
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert not any(
        line.startswith("ARG") and _PREDECESSOR in line for line in text.splitlines()
    ), "the predecessor must never be pinned by an ARG (it is not autodiscovered)"
    predecessor = [
        (flags, spec) for flags, spec in _installs() if spec.startswith(_PREDECESSOR + "@")
    ]
    # This is the TRANSITIONAL release: exactly one predecessor line. The N+1 removal
    # PR (equivalent proof part 3) deletes that line and retires this test with it.
    assert (
        len(predecessor) == 1
    ), "exactly one transitional predecessor install line on the cutover release"
    flags, spec = predecessor[0]
    assert spec == f"{_PREDECESSOR}@0.16.0", "the predecessor is frozen at its terminal release"
    assert (
        "--prefix" not in flags and "--force" not in flags
    ), "the predecessor keeps its plain global install"
    preamble = text[: text.index(spec)].rsplit("\n\n", 1)[-1]
    assert (
        "REMOVE THIS LINE" in preamble
    ), "the transitional line must state its own removal condition in the comment block above it"
