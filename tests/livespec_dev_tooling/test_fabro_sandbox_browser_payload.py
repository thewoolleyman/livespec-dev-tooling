"""Shape tests for the headless-browser payload in `docker/fabro-sandbox/agent/Dockerfile`.

The agent layer carries Playwright plus the headless Chromium build that Playwright
version pins, so factory-captured proofs in the `livespec-orchestrator-beads-fabro`
reserved workflow have a browser without a per-run download. The payload rides in the
AGENT layer rather than `base` for the reason the agent Dockerfile's own header already
records: CI pulls only the toolchain layers, so browser bytes in `base` would enlarge
every CI job's pull for a capability CI never exercises.

Nothing here builds an image — a container build is not available to the unit suite. What
these tests CAN hold is the Dockerfile's SHAPE, which is where every one of this slice's
regressions would land: a pin that drifts from its ARG, a browser installed somewhere only
an environment variable can find (Fabro spawns ACP nodes under a fail-closed env allowlist,
so such an install is unreachable at runtime), a versions file that hardcodes a second copy
of a number instead of reading the install, or a build-time smoke check quietly weakened
into something that cannot fail the build.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAYER_DIR = _REPO_ROOT / "docker" / "fabro-sandbox"
_DOCKERFILE = _LAYER_DIR / "agent" / "Dockerfile"

_PLAYWRIGHT_VERSION = "1.63.0"
_PLAYWRIGHT_ARG_LINE = re.compile(r"^ARG PLAYWRIGHT_VERSION=(?P<version>\S+)$", re.MULTILINE)

# Playwright's DEFAULT browsers root for uid 0 with `HOME=/root` — the one location that
# needs no `PLAYWRIGHT_BROWSERS_PATH`. Fabro spawns ACP nodes under a fail-closed env
# allowlist, so a browser reachable only through an environment variable is a browser the
# sandbox cannot find at runtime.
_DEFAULT_BROWSERS_ROOT = "/root/.cache/ms-playwright"
_BROWSERS_PATH_ENV = "PLAYWRIGHT_BROWSERS_PATH"
_VERSIONS_FILE = "/etc/livespec/sandbox-browser-versions"

# The Chromium build this Playwright release pins — packages/playwright-core/browsers.json
# at the upstream tag. These belong in the TEST, which is an assertion, and NOT in the
# Dockerfile, which would make them a second copy free to drift from the installed browser.
_PINNED_CHROMIUM_VERSION = "153.0.8010.12"
_PINNED_CHROMIUM_BUILD = "1243"

_SMOKE_MARKER = "playwright screenshot"
_LOOPBACK = "127.0.0.1"
# `\x89PNG\r\n\x1a\n` — the PNG file signature, as the hex the build step compares.
_PNG_SIGNATURE_HEX = "89504e470d0a1a0a"
# A smoke-step scratch artifact together with whatever textually precedes its `/`, so a
# filesystem path can be told apart from a URL path.
_ARTIFACT_REFERENCE = re.compile(r"(?P<prefix>\S*)/(?:page\.html|smoke\.png|serve\.js)")


def _run_steps(*, text: str) -> list[str]:
    """Every `RUN` instruction in `text`, backslash line-continuations kept intact.

    The assertions below are about a STEP, not about the file: "the smoke step removes
    its screenshot" and "some line somewhere in the Dockerfile removes a screenshot" are
    different claims, and only the first is the acceptance condition.
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


def _instruction_lines(*, text: str) -> list[str]:
    """`text`'s lines with comments dropped — what the builder actually executes.

    The comment block is where this Dockerfile records WHY a thing is absent, so a
    prose mention of `PLAYWRIGHT_BROWSERS_PATH` is the opposite of setting one. Only
    instruction lines can carry the violations these tests are about.
    """
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def _step_containing(*, needle: str) -> str:
    """The single `RUN` step carrying `needle` — exactly one, so the step is unambiguous."""
    steps = _run_steps(text=_DOCKERFILE.read_text(encoding="utf-8"))
    matches = [step for step in steps if needle in step]
    assert (
        len(matches) == 1
    ), f"expected exactly one RUN step containing {needle!r}, found {len(matches)}"
    return matches[0]


def test_playwright_is_pinned_by_one_agent_layer_arg_the_npm_install_reads() -> None:
    """One `ARG PLAYWRIGHT_VERSION`, in the agent layer only, and the install reads it.

    `fabro_image_pin_lockstep` parses `ARG NAME=value` across every layer Dockerfile and
    MERGES them, so a duplicated ARG does not fail that check — it silently lets the two
    copies drift. The ARG therefore has to be unique across the whole layer tree, and the
    npm spec has to interpolate it rather than repeat the literal.
    """
    text = _DOCKERFILE.read_text(encoding="utf-8")
    versions = _PLAYWRIGHT_ARG_LINE.findall(text)
    assert versions == [
        _PLAYWRIGHT_VERSION
    ], f"expected exactly one ARG PLAYWRIGHT_VERSION={_PLAYWRIGHT_VERSION}, found {versions}"
    siblings = sorted(p for p in _LAYER_DIR.glob("*/Dockerfile") if p != _DOCKERFILE)
    assert (
        siblings
    ), "the layer tree must contain sibling Dockerfiles for this check to mean anything"
    for sibling in siblings:
        assert "PLAYWRIGHT_VERSION" not in sibling.read_text(encoding="utf-8"), (
            f"{sibling.relative_to(_REPO_ROOT)} also declares PLAYWRIGHT_VERSION; the merged "
            "pin parse would hide the drift between the two copies"
        )
    assert (
        "playwright@${PLAYWRIGHT_VERSION}" in text
    ), "the playwright npm install must take its version from the ARG, never a repeated literal"
    assert _PLAYWRIGHT_VERSION not in text.replace(
        f"ARG PLAYWRIGHT_VERSION={_PLAYWRIGHT_VERSION}", ""
    ), "the pinned version must appear exactly once, on the ARG line"


def test_chromium_lands_with_its_deps_in_playwrights_default_root_home_location() -> None:
    """`playwright install --with-deps chromium`, apt retried and cleaned, no path env.

    `--with-deps` is the apt-based dependency route for the Ubuntu 24.04 root of this
    chain, and it shells out to apt, so the retry posture and the list cleanup have to
    ride in the SAME step — exactly as the bubblewrap step above does. The install is
    left at Playwright's default destination on purpose: naming a
    `PLAYWRIGHT_BROWSERS_PATH` would move the browser somewhere only an environment
    variable can find, and the Fabro env allowlist does not carry one.
    """
    instructions = _instruction_lines(text=_DOCKERFILE.read_text(encoding="utf-8"))
    step = _step_containing(needle="playwright install")
    assert (
        "playwright install --with-deps chromium" in step
    ), "the browser and its system dependencies install together, via the apt-based route"
    assert (
        'Acquire::Retries "5"' in step
    ), "apt fetches in this step retry like every other dependency fetch in this layer"
    assert (
        "apt-get clean" in step and "rm -rf /var/lib/apt/lists/*" in step
    ), "the apt lists are cleaned in the same layer that populated them"
    setters = [line for line in instructions if _BROWSERS_PATH_ENV in line]
    assert not setters, f"{_BROWSERS_PATH_ENV} must never be set: the sandbox cannot rely on env reaching it {setters}"
    assert f"test -d {_DEFAULT_BROWSERS_ROOT}" in step, (
        "the install step must PROVE the bytes landed in Playwright's default root-home "
        f"location {_DEFAULT_BROWSERS_ROOT} rather than leave it to assumption"
    )
    other_roots = [
        line
        for line in instructions
        if "ms-playwright" in line and _DEFAULT_BROWSERS_ROOT not in line
    ]
    assert not other_roots, f"a second browsers root would shadow the default one: {other_roots}"


def test_versions_file_records_what_was_installed_and_the_build_prints_it() -> None:
    """Two lines in `/etc/livespec/sandbox-browser-versions`, both READ from the install.

    The Chromium number is deliberately NOT written down here. Playwright's pin is the
    single source of truth for which build lands, so a literal in the Dockerfile would
    be a second copy free to drift from the browser that is actually present — the
    versions file would then confidently report a version nothing in the image has.
    Reading it out of the installed binary cannot drift by construction.
    """
    instructions = _instruction_lines(text=_DOCKERFILE.read_text(encoding="utf-8"))
    step = _step_containing(needle=_VERSIONS_FILE)
    assert (
        r"printf 'playwright %s\nchromium %s\n'" in step
    ), f"{_VERSIONS_FILE} carries the Playwright version and the Chromium version, one per line"
    assert (
        "playwright --version" in step
    ), "the recorded Playwright version is read from the installed CLI"
    assert (
        '"${chromium_bin}" --version' in step
    ), "the recorded Chromium version is read from the installed browser binary"
    assert (
        f"{_DEFAULT_BROWSERS_ROOT}/chromium-*/chrome-linux*/chrome" in step
    ), "the binary is located by globbing Playwright's default browsers root"
    assert (
        f"cat {_VERSIONS_FILE}" in step
    ), "both versions are printed during the build, not merely written to a file"
    for literal in (_PINNED_CHROMIUM_VERSION, _PINNED_CHROMIUM_BUILD):
        copies = [line for line in instructions if literal in line]
        assert not copies, (
            f"{literal!r} is hardcoded at {copies}; Playwright's pin already determines it, "
            "so a second copy can drift from the browser the image actually carries"
        )


def test_smoke_step_screenshots_a_page_it_serves_itself_over_loopback() -> None:
    """The capture is END-TO-END: this step is the origin server AND the browser client.

    Screenshotting a `file://` URL or a public page would each prove something weaker.
    A `file://` capture never exercises the network stack the reserved workflow's proofs
    use, and a public URL makes the image build depend on the internet being up and on
    a third party's page not changing. Serving a page this step just wrote, on the
    loopback interface, is hermetic and still exercises the real HTTP path.
    """
    step = _step_containing(needle=_SMOKE_MARKER)
    assert '> "${smoke_dir}/page.html"' in step, "the step must write the page it is about to serve"
    assert (
        f'.listen(Number(process.argv[3]), "{_LOOPBACK}")' in step
    ), f"the origin server binds {_LOOPBACK} only — never a routable interface"
    assert (
        f'"http://{_LOOPBACK}:${{smoke_port}}/page.html" "${{smoke_dir}}/smoke.png"' in step
    ), "the capture targets the locally served page and writes a PNG beside it"
    assert (
        "playwright screenshot --browser chromium" in step
    ), "the capture runs through Playwright against the Chromium this layer installed"


def test_smoke_step_fails_the_build_on_a_bad_capture_or_a_failed_assertion() -> None:
    """A smoke check that cannot fail the build is decoration, so hold the failure path.

    Two ways this degrades silently, and both are checked here. The step could stop
    aborting on a non-zero command (`set -e` dropped, or a failure swallowed by
    `|| true`), leaving a build that goes green on a Chromium that never rendered. Or an
    assertion could be loosened into one anything satisfies — a truncated or
    zero-length file still opens, so the PNG signature and a floor well above an empty
    file are what separate "a capture happened" from "a file exists".
    """
    step = _step_containing(needle=_SMOKE_MARKER)
    assert step.startswith("RUN set -eux;"), (
        "the smoke step must abort on the first non-zero command — without `set -e` a "
        "failed capture or a failed assertion leaves the build green"
    )
    assert (
        f'test "${{smoke_signature}}" = "{_PNG_SIGNATURE_HEX}"' in step
    ), "the captured bytes must be asserted to carry the PNG file signature"
    assert (
        'test "${smoke_bytes}" -gt 1024' in step
    ), "the capture must be asserted larger than one kilobyte, above any empty-file artifact"
    swallowed = [token for token in ("|| true", "; true", "set +e", "|| :") if token in step]
    assert not swallowed, (
        f"{swallowed} would swallow a failure in the smoke step, which is the one step "
        "whose whole purpose is to fail"
    )


def test_smoke_step_leaves_nothing_of_itself_in_the_committed_layer() -> None:
    """The published layer carries the browser, the Playwright install and the versions file.

    A scratch page and a screenshot baked into a published image are worse than
    wasteful: the next reader finds a stale PNG in the filesystem and has no way to
    tell it from a live artifact. Every scratch file therefore lives under one
    `mktemp -d` directory and that directory is removed by the same step, in the same
    layer — a later `RUN rm` would not help, because the bytes are already committed
    into the layer this step produced.
    """
    step = _step_containing(needle=_SMOKE_MARKER)
    assert 'smoke_dir="$(mktemp -d)"' in step, "the scratch files belong in one temporary directory"
    # Each artifact name may appear as a FILESYSTEM path under the temporary directory,
    # or as the URL path the loopback server answers on — nowhere else. Matching the bare
    # name would conflate the two: `path:"/page.html"` in the readiness probe is a request
    # target, not a file that could survive the layer.
    stray = [
        match.group(0)
        for match in _ARTIFACT_REFERENCE.finditer(step)
        if not match.group("prefix").endswith("${smoke_dir}")
        and "http://" not in match.group("prefix")
        and not match.group("prefix").endswith('path:"')
    ]
    assert not stray, f"a scratch file outside the temporary directory survives the layer: {stray}"
    assert step.rstrip().endswith('rm -rf "${smoke_dir}"'), (
        "the step must END by removing its temporary directory, so the page and the "
        "screenshot are gone before the layer is committed"
    )


def test_header_names_the_browser_payloads_consumer_and_defends_its_layer() -> None:
    """The header answers "who asked for this" and "why is it not in `base`".

    This layer's existing header already argues the agent-vs-base split for bubblewrap
    and the ACP adapters, and a headless browser is a much larger instance of the same
    class of payload — so the same argument has to be made for it explicitly, or the
    next person weighing an image-size complaint has no record of the trade and the
    obvious "move it down to base" looks free. Naming the consumer matters for the
    mirror case: a payload with no recorded consumer is a payload nobody can safely
    delete.
    """
    header = _DOCKERFILE.read_text(encoding="utf-8").split("\nARG ", 1)[0]
    for phrase in (
        "livespec-orchestrator-beads-fabro",
        "factory-captured proofs",
        "reserved workflow",
    ):
        assert phrase in header, f"the header must name the browser payload's consumer: {phrase!r}"
    for phrase in ("agent layer", "CI image pulls are unchanged"):
        assert phrase in header, (
            "the header must record that the browser rides in the agent layer rather than "
            f"base, leaving CI's pull unchanged: {phrase!r}"
        )
