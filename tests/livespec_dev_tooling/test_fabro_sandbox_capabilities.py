"""Shape tests for `/etc/livespec/sandbox-capabilities` across the Fabro sandbox layers.

ITS CONSUMER is the Definition-of-Done gate in `livespec-orchestrator-beads-fabro`,
which checks each factory-captured assertion against the capabilities the sandbox
image PUBLISHES in this file. That makes the file an ASSERTION the gate believes:
a name listed here that the image does not actually carry is worse than no file at
all, because the gate has no second source to catch it with.

Each layer therefore states what IT carries. `base` writes the file; `python` and
`python-rust` add toolchain and inherit it unchanged; the `agent` layer REWRITES it
with its own longer list. Nothing here builds an image — a container build is not
available to the unit suite — so what these tests hold is the Dockerfile SHAPE:
the exact name lists, their lowercase one-per-line form, and the proof that each
declared capability is present before it is declared.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAYER_DIR = _REPO_ROOT / "docker" / "fabro-sandbox"
_BASE_DOCKERFILE = _LAYER_DIR / "base" / "Dockerfile"
_AGENT_DOCKERFILE = _LAYER_DIR / "agent" / "Dockerfile"

_CAPABILITIES_FILE = "/etc/livespec/sandbox-capabilities"
_BASE_CAPABILITIES = ["terminal", "tmux"]
_AGENT_CAPABILITIES = ["terminal", "tmux", "headless_browser", "herdr"]

# `printf '%s\n' a b c > <file>` — the one-name-per-line form, with the names
# captured so the test reads the LIST the image publishes rather than merely
# confirming that some write happened.
_PUBLISH = re.compile(
    r"printf '%s\\n' (?P<names>[^>]+?) > " + re.escape(_CAPABILITIES_FILE),
)
_CAPABILITY_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _run_steps(*, text: str) -> list[str]:
    """Every `RUN` instruction in `text`, backslash line-continuations kept intact.

    The assertions below are about a STEP: "the step that publishes the capability
    file also proves the capabilities are present" and "the Dockerfile mentions tmux
    somewhere" are different claims, and only the first is the acceptance condition.
    """
    steps: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        if not current and not raw.startswith("RUN "):
            continue
        current.append(raw)
        if not raw.rstrip().endswith("\\"):
            steps.append("\n".join(current))
            current = []
    return steps


def _publishing_step(*, dockerfile: Path) -> str:
    """The single `RUN` step in `dockerfile` that writes the capability file."""
    matches = [
        step
        for step in _run_steps(text=dockerfile.read_text(encoding="utf-8"))
        if _PUBLISH.search(step)
    ]
    assert len(matches) == 1, (
        f"expected exactly one RUN step publishing {_CAPABILITIES_FILE} in "
        f"{dockerfile.relative_to(_REPO_ROOT)}, found {len(matches)}"
    )
    return matches[0]


def _published_names(*, dockerfile: Path) -> list[str]:
    """The capability names the publishing step in `dockerfile` writes, in order."""
    match = _PUBLISH.search(_publishing_step(dockerfile=dockerfile))
    assert match is not None, f"no capability list parsed from {dockerfile.relative_to(_REPO_ROOT)}"
    return match.group("names").split()


def test_base_image_publishes_the_terminal_capabilities_it_carries() -> None:
    """`base` writes `terminal` and `tmux`, and proves tmux is really there first.

    tmux was added to `base` for factory-tier acceptance tests that drive real tmux
    sockets, so the base chain genuinely carries it and every image stacked on `base`
    inherits the claim. Declaring it without probing the installed binary would let an
    apt step that silently dropped the package publish a capability the image lacks,
    and the Definition-of-Done gate would believe it.
    """
    step = _publishing_step(dockerfile=_BASE_DOCKERFILE)
    assert step.startswith("RUN set -eux;"), (
        "the publishing step must abort on the first non-zero command — a probe that "
        "cannot fail does not establish the capability it precedes"
    )
    assert _published_names(dockerfile=_BASE_DOCKERFILE) == _BASE_CAPABILITIES, (
        f"{_CAPABILITIES_FILE} in base must list exactly {_BASE_CAPABILITIES}, in that "
        "order, one per line"
    )
    assert "tmux -V" in step, "the declared tmux must be probed — a version call runs the binary"
    assert (
        f"cat {_CAPABILITIES_FILE}" in step
    ), "the published list belongs in the build log too, not only in the filesystem"


def test_agent_image_republishes_the_full_list_of_what_it_carries() -> None:
    """The `agent` layer REWRITES the file with its own payload added, each one probed.

    It rewrites rather than appends because an append would make the file a record of
    which layers ran, not of what the published image carries — and a half-written
    append is indistinguishable from a complete one. The agent-only names are the two
    payloads this layer installs: the headless browser and herdr.
    """
    step = _publishing_step(dockerfile=_AGENT_DOCKERFILE)
    assert step.startswith("RUN set -eux;"), (
        "the publishing step must abort on the first non-zero command — a probe that "
        "cannot fail does not establish the capability it precedes"
    )
    assert _published_names(dockerfile=_AGENT_DOCKERFILE) == _AGENT_CAPABILITIES, (
        f"{_CAPABILITIES_FILE} in the agent layer must list exactly {_AGENT_CAPABILITIES}, "
        "in that order, one per line"
    )
    assert "tmux -V" in step, "the inherited tmux is re-probed in the layer that re-declares it"
    assert "herdr --version" in step, "the declared herdr must be probed in this layer too"
    assert (
        "test -d /root/.cache/ms-playwright" in step
    ), "the declared headless browser must be probed where Playwright's default root put it"
    assert (
        f"cat {_CAPABILITIES_FILE}" in step
    ), "the published list belongs in the build log too, not only in the filesystem"


def test_every_published_capability_name_is_lowercase_snake_case() -> None:
    """One lowercase snake_case name per line — the file is parsed, never prose.

    The gate matches these names against the capabilities an assertion requires, so a
    stray capital, a hyphen or an inline comment is a capability the gate silently
    fails to recognise rather than a formatting nit.
    """
    for dockerfile in (_BASE_DOCKERFILE, _AGENT_DOCKERFILE):
        names = _published_names(dockerfile=dockerfile)
        assert names, f"{dockerfile.relative_to(_REPO_ROOT)} publishes an empty capability list"
        for name in names:
            assert _CAPABILITY_NAME.fullmatch(name), (
                f"{name!r} in {dockerfile.relative_to(_REPO_ROOT)} is not a lowercase "
                "snake_case capability name"
            )
        assert len(set(names)) == len(names), f"duplicate capability in {names}"
    base_names = _published_names(dockerfile=_BASE_DOCKERFILE)
    agent_names = _published_names(dockerfile=_AGENT_DOCKERFILE)
    assert agent_names[: len(base_names)] == base_names, (
        "the agent list must RESTATE the inherited base capabilities before its own; "
        "dropping one would retract a capability the image still carries"
    )


def test_no_intermediate_layer_rewrites_the_capability_file() -> None:
    """Only `base` and `agent` write it, so each published image states its own truth.

    `python` and `python-rust` add toolchain, not capabilities, and are published as
    their own images. A third writer between the two ends would mean the file a given
    image carries depends on which layer happened to run last rather than on what that
    image contains.
    """
    writers = sorted(
        path
        for path in _LAYER_DIR.glob("*/Dockerfile")
        if _CAPABILITIES_FILE in path.read_text(encoding="utf-8")
    )
    assert writers == sorted(
        (_BASE_DOCKERFILE, _AGENT_DOCKERFILE)
    ), f"only base and agent may mention {_CAPABILITIES_FILE}; found {writers}"
