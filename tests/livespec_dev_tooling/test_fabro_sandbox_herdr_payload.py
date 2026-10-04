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

# The one fragment that appears in the smoke step and nowhere else, so
# `_step_containing` resolves that step unambiguously.
_SMOKE_MARKER = "pane wait-output"
_SESSION = '"${smoke_session}"'
_HERDR = "herdr --session " + _SESSION


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


def test_smoke_step_drives_a_headless_herdr_server_through_a_whole_pane_round_trip() -> None:
    """The capture is END-TO-END: start a server with no terminal, then pane in, pane out.

    `herdr --version` and a present binary prove nothing about whether this image can
    drive panes. The ways a headless terminal workspace fails inside a container — a
    server that cannot allocate a pty, a socket it cannot bind, a pane whose shell never
    starts — all pass a version probe and then fail on the first real pane. So the step
    has to BE the round trip: a server in its own named session, a pane, a split of that
    pane, one line of literal text in, and the same line read back out.

    Nothing attaches a terminal to that server. A docker build has no tty, which is
    exactly the shape a dispatched run runs in, so the headless `server` subcommand is
    the only correct way in; an `attach` here would both hang the build and prove the
    wrong thing.
    """
    step = _step_containing(needle=_SMOKE_MARKER)
    assert (
        f'{_HERDR} server > "${{smoke_dir}}/server.log" 2>&1 &' in step
    ), "the server runs headless, in its own named session, with its log kept for the build"
    assert (
        "session attach" not in step
    ), "nothing may attach a terminal to the smoke server — the build has no tty to attach"
    assert f"{_HERDR} pane list >/dev/null 2>&1" in step, (
        "readiness is POLLED on a real socket call rather than slept for: a fixed sleep "
        "is either a slower build or a flake, depending on the host"
    )
    assert (
        'test -S "${smoke_state}/herdr.sock"' in step
    ), "the step must prove the server's socket exists before it drives anything over it"
    assert (
        f'root_pane="$({_HERDR} workspace create --cwd /tmp' in step
    ), "the first pane comes from a real workspace the server creates"
    assert (
        f'split_pane="$({_HERDR} pane split "${{root_pane}}" --direction right' in step
    ), "the split is a real split of the pane the server just reported"
    assert step.count('["pane_id"]') == 2, (
        "both pane ids are READ from the server's own JSON replies; assuming them would "
        "address the wrong pane in silence the day the layout changes"
    )
    assert (
        'test "${root_pane}" != "${split_pane}"' in step
    ), "a split that returned the pane it split would pass every other assertion here"
    assert (
        f'{_HERDR} pane send-text "${{split_pane}}" "${{smoke_text}}"' in step
    ), "one line of literal text goes into the split pane"
    assert (
        f'{_HERDR} pane read --source visible --format text "${{split_pane}}"'
        ' | grep -F "${smoke_text}"' in step
    ), "and the SAME line is read back out of that pane — the read is the assertion"


def test_herdr_smoke_step_fails_the_build_on_any_failed_step() -> None:
    """A smoke check that cannot fail the build is decoration, so hold the failure path.

    Two ways this degrades silently. The step could stop aborting on a non-zero command
    (`set -e` dropped, or a failure swallowed by `|| true`), leaving a green build on a
    herdr that never rendered a pane. Or the wait for the pane echo could become
    unbounded — `pane wait-output` without `--timeout` waits INDEFINITELY, which turns a
    broken pane from a build failure into a build that never ends, and a hung build
    reports no verdict at all.
    """
    step = _step_containing(needle=_SMOKE_MARKER)
    assert step.startswith("RUN set -eux;"), (
        "the smoke step must abort on the first non-zero command — without `set -e` a "
        "failed pane operation or a failed read-back leaves the build green"
    )
    assert (
        f'{_HERDR} pane wait-output --match "${{smoke_text}}" --timeout ' in step
    ), "the wait on the pane echo must be BOUNDED, so a dead pane fails instead of hanging"
    assert (
        'test -n "${smoke_ready}"' in step
    ), "a server that never answered must fail the build, not fall through to the panes"
    swallowed = [token for token in ("|| true", "; true", "set +e", "|| :") if token in step]
    assert not swallowed, (
        f"{swallowed} would swallow a failure in the smoke step, which is the one step "
        "whose whole purpose is to fail"
    )


def test_smoke_step_leaves_no_server_and_no_session_state_in_the_committed_layer() -> None:
    """The published layer carries the binary — not a live server, a socket or a session.

    Three distinct residues, and each is its own problem. A server still running when
    the step ends is a process the builder reaps at an unspecified moment, so whether
    its state lands in the layer is a race. A session directory baked into the image
    is state every container then starts from, which makes a stale snapshot look like
    a live one to the next reader. And the socket inside it is a dead file with a live
    name: a run that found it would address a server that does not exist.

    Order is part of the assertion. `session delete` operates on a STOPPED session, so
    stopping has to come first; and the step must PROVE the directory is gone rather
    than trust the delete, because a silent no-op there is indistinguishable from a
    successful removal.
    """
    step = _step_containing(needle=_SMOKE_MARKER)
    stop = f"{_HERDR} server stop"
    delete = 'herdr session delete "${smoke_session}"'
    assert stop in step, "the smoke server must be stopped by the step that started it"
    assert delete in step, "the session's state directory and socket must be removed with it"
    assert step.index(stop) < step.index(delete), (
        "`session delete` removes a STOPPED session, so the stop has to come first — "
        "deleting a live session is the ordering that silently leaves state behind"
    )
    assert 'test -S "${smoke_state}/herdr.sock"' in step and step.index(
        'test -S "${smoke_state}/herdr.sock"'
    ) < step.index(
        stop
    ), "the socket is asserted PRESENT while the server runs, so its absence later means something"
    assert (
        'test ! -e "${smoke_state}"' in step
    ), "the step must PROVE the session directory is gone, not trust `session delete` to say so"
    assert step.index(delete) < step.index(
        'test ! -e "${smoke_state}"'
    ), "the proof belongs after the removal it is about"
    assert step.rstrip().endswith('rm -rf "${smoke_dir}"'), (
        "the step must END by removing its temporary directory, so the server log is "
        "gone before the layer is committed — a later `RUN rm` cannot help, the bytes "
        "are already committed into the layer this step produced"
    )
    stray = [
        line
        for line in step.splitlines()
        if "/tmp/" in line and "${smoke_dir}" not in line and "--cwd /tmp" not in line
    ]
    assert not stray, f"a scratch file outside the temporary directory survives the layer: {stray}"


def test_header_names_the_consumers_of_the_herdr_payload_and_of_the_capability_file() -> None:
    """The header answers "who asked for this" for BOTH of this slice's additions.

    A payload with no recorded consumer is a payload nobody can safely delete, and the
    capability file is worse than that: it is read by a gate in ANOTHER repository, so
    the only place a reader of this Dockerfile can learn that deleting a line there
    breaks a Definition-of-Done check over here is this header. The browser payload
    already set the precedent of naming its consumer in the same block.
    """
    header = _DOCKERFILE.read_text(encoding="utf-8").split("\nARG ", 1)[0]
    for phrase in ("herdr", "livespec-overseer", "herdr panes alongside tmux"):
        assert phrase in header, f"the header must name the herdr payload's consumer: {phrase!r}"
    for phrase in (
        "/etc/livespec/sandbox-capabilities",
        "Definition-of-Done gate",
        "livespec-orchestrator-beads-fabro",
    ):
        assert phrase in header, f"the header must name the capability file's consumer: {phrase!r}"
