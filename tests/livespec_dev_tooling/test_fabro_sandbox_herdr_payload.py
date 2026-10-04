"""Shape tests for the herdr payload in `docker/fabro-sandbox/agent/Dockerfile`.

The agent layer bakes a pinned `herdr` so a dispatched run can drive real terminal
panes. ITS CONSUMER is the `livespec-overseer` plan `overseer-uzvcbn` ("herdr panes
alongside tmux"), whose Proof of Done cannot be factory-captured until the sandbox
can actually run herdr. The payload rides in the AGENT layer for the reason the
browser payload already rides there: CI pulls only the toolchain layers, so bytes
only Fabro sandboxes execute must not land in `base`.

Nothing here builds an image — a container build is not available to the unit suite,
exactly as `test_fabro_sandbox_browser_payload` records. What these tests CAN hold is
the Dockerfile's SHAPE, which is where this slice's regressions would land: a binary
made executable before its checksum is verified, a download pinned by a repeated
literal instead of the ARG, a smoke step quietly weakened into something that cannot
fail the build, or a server left running with its socket baked into the layer.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAYER_DIR = _REPO_ROOT / "docker" / "fabro-sandbox"
_DOCKERFILE = _LAYER_DIR / "agent" / "Dockerfile"

# Measured against the upstream release on 2026-10-04: github.com/herdrdev/herdr
# release v0.9.3 (published 2026-09-29, not a prerelease), asset
# `herdr-linux-x86_64`, 29,962,088 bytes. The digest belongs in the TEST as well as
# the Dockerfile ARG because the ARG is the thing under test: a silent edit to it
# would otherwise re-pin the payload to whatever the editor pleased.
_HERDR_VERSION = "0.9.3"
_HERDR_SHA256 = "18a8dc65f1c2fa485884344356dea1cfd911c6f06cf46fa78e193f4087f4dba7"
_HERDR_ASSET = "herdr-linux-x86_64"
_HERDR_RELEASE_URL = (
    "https://github.com/herdrdev/herdr/releases/download/v${HERDR_VERSION}/" + _HERDR_ASSET
)
# `/usr/local/bin` is on the default PATH of a non-root shell, which is the
# requirement: a sandbox user has to find the binary without sourcing anything.
_HERDR_BIN = "/usr/local/bin/herdr"

_VERSION_ARG_LINE = re.compile(r"^ARG HERDR_VERSION=(?P<version>\S+)$", re.MULTILINE)
_SHA256_ARG_LINE = re.compile(r"^ARG HERDR_SHA256=(?P<digest>\S+)$", re.MULTILINE)


def _run_steps(*, text: str) -> list[str]:
    """Every `RUN` instruction in `text`, backslash line-continuations kept intact.

    The assertions below are about a STEP, not about the file: "the install step
    verifies the checksum before it installs" and "some line somewhere verifies a
    checksum" are different claims, and only the first is the acceptance condition.
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


def _step_containing(*, needle: str) -> str:
    """The single `RUN` step carrying `needle` — exactly one, so the step is unambiguous."""
    steps = _run_steps(text=_DOCKERFILE.read_text(encoding="utf-8"))
    matches = [step for step in steps if needle in step]
    assert (
        len(matches) == 1
    ), f"expected exactly one RUN step containing {needle!r}, found {len(matches)}"
    return matches[0]


def test_herdr_is_pinned_by_agent_layer_args_and_verified_before_it_becomes_executable() -> None:
    """One version ARG, one digest ARG, and the checksum is checked BEFORE the chmod.

    Order is the whole point of this test. `curl -o` writes a non-executable file, so
    the moment the payload becomes runnable is the `install -m 0755`; putting the
    `sha256sum -c` after it would leave a window in which an unverified binary is
    executable in the layer. `fabro_image_pin_lockstep` MERGES `ARG NAME=value` across
    the layer Dockerfiles, so a duplicated ARG would not fail that check — it would
    silently let two copies drift — which is why uniqueness across the tree is asserted
    here instead.
    """
    text = _DOCKERFILE.read_text(encoding="utf-8")
    versions = _VERSION_ARG_LINE.findall(text)
    assert versions == [
        _HERDR_VERSION
    ], f"expected exactly one ARG HERDR_VERSION={_HERDR_VERSION}, found {versions}"
    digests = _SHA256_ARG_LINE.findall(text)
    assert digests == [
        _HERDR_SHA256
    ], f"expected exactly one ARG HERDR_SHA256={_HERDR_SHA256}, found {digests}"
    siblings = sorted(p for p in _LAYER_DIR.glob("*/Dockerfile") if p != _DOCKERFILE)
    assert (
        siblings
    ), "the layer tree must contain sibling Dockerfiles for this check to mean anything"
    for sibling in siblings:
        sibling_text = sibling.read_text(encoding="utf-8")
        assert "HERDR_VERSION" not in sibling_text and "HERDR_SHA256" not in sibling_text, (
            f"{sibling.relative_to(_REPO_ROOT)} also declares a herdr pin; the merged pin "
            "parse would hide the drift between the two copies"
        )
    step = _step_containing(needle=_HERDR_RELEASE_URL)
    assert step.startswith("RUN set -eux;"), (
        "the install step must abort on the first non-zero command — without `set -e` a "
        "failed checksum leaves the build green"
    )
    assert (
        "--retry 5 --retry-all-errors --retry-connrefused" in step
    ), "the herdr download retries a transient CDN failure like every other fetch in this layer"
    verify = 'echo "${HERDR_SHA256}  /tmp/' + _HERDR_ASSET + '" | sha256sum -c -'
    make_executable = f"install -m 0755 /tmp/{_HERDR_ASSET} {_HERDR_BIN}"
    assert verify in step, "the download must be checked against the pinned digest ARG"
    assert (
        make_executable in step
    ), f"the verified binary must land at {_HERDR_BIN}, on a non-root shell's default PATH"
    assert step.index(verify) < step.index(make_executable), (
        "the pinned SHA-256 must be verified BEFORE `install -m 0755` makes the payload "
        "executable; `curl -o` leaves it non-executable until then"
    )
    assert (
        'test "$(herdr --version | awk \'{print $NF}\')" = "${HERDR_VERSION}"' in step
    ), "the build must READ the version back from the installed binary and hold it to the ARG"
    assert _HERDR_VERSION not in text.replace(
        f"ARG HERDR_VERSION={_HERDR_VERSION}", ""
    ), "the pinned version must appear exactly once, on the ARG line"
