"""Consumer-tier: a delegated gate finds the tools its members invoke, or it is
not a gate.

`SPECIFICATION/non-functional-requirements.md` requires, of the sandbox image
gate toolchain, that the `python-rust` image this repository builds — and every
layer built atop it — carry `jq` on `PATH`, and generalizes: a non-Python tool a
fleet consumer's gate member invokes, and that the consumer pins in its
`.mise.toml`, MUST be present in the sandbox image that consumer's CI container
pins. The acceptance shape is the `SPECIFICATION/scenarios.md` scenario in which
a consumer's delegated gate finds the mise-pinned tools its gate members invoke.

WHY THIS TIER. The claim spans two artifacts that cannot see each other, and the
defect lived in the seam between them. The gated repository's `ci.yml` names an
image; `render-gate-job.sh` resolves the Job's image from THAT file and
deliberately renders no `mise install`; and the image's own contents are decided
in a Dockerfile in this repository. A unit test on either end passes against a
drifted other end — which is exactly how this shipped. Measured 2026-10-24 on
livespec-console-beads-fabro master 07a224f0 (Job
`gate-livespec-console-beads-fabro-bc28m`): the whole cluster gate ran in about
5m32s and only `check-nextest` failed, with four
`console-ci-parity-check::ci_telemetry_runner_attributes` tests erroring on "jq
is required to run the CI telemetry exporter and is pinned in .mise.toml; run
this test under mise". Console pins `jq` and the image did not carry it.

THE TWO ENDS ARE JOINED BY A VALUE, NOT BY A SHARED EXPECTATION. The fixture
consumer's `ci.yml` pins a `python-rust` image; the REAL renderer runs and
resolves the Job's image from it; and the layer name is then read back OUT of
the image the renderer produced and used to look up which Dockerfile to read. So
a consumer pinning a `python-` image would send this test to a different
Dockerfile rather than silently asserting the one it hoped for, and the
inheritance arm is the same join run against the workflow's own build wiring.

WHY `mise install`'S ABSENCE IS ASSERTED AND NOT ASSUMED. It is the whole reason
the image is the gate's only toolchain source. If the pod did run `mise install`,
every `.mise.toml` pin would arrive at the gate on its own and no image would owe
anything — so the Dockerfile assertions below would be about a requirement that
had quietly stopped existing, while still passing.

WHY THE BUILD-TIME PROOF IS ASSERTED SEPARATELY FROM THE INSTALL. An `apt-get
install` line is a statement of intent; this file and the spec heading it serves
are assertions the delegated gate BELIEVES, and there is no second source to
catch them with. Unless the build itself proves the tool resolves on `PATH`, a
layer that installed it under some other name, or into a directory no login
shell searches, publishes an image that reads exactly like a correct one at every
surface here and is missing the tool at the only surface that matters.

CONTROL ARMS. Every reader here takes TEXT or a rendered manifest, so each is fed
a counter-example and asserted to convict: a layer that installs nothing, one
that installs the tool but never proves it, a leaf wired to the WRONG parent
image, and a leaf that purges the tool back out. The purge arm is the one that
matters most — inheritance is the whole of the second assertion, and a leaf is
free to undo it.
"""

from __future__ import annotations

import re
import subprocess
from itertools import takewhile
from pathlib import Path

import pytest

from livespec_dev_tooling.config import load_gate_check_suite

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SANDBOX = _REPO_ROOT / "docker" / "fabro-sandbox"
_RENDERER = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job.sh"
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "fabro-sandbox-image.yml"

# The empty tree's hash — a real git object name, so the renderer's own argument
# validation is satisfied without a repository having to exist.
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RUN_TIMEOUT_S = 60.0

# The tool the spec names, and the member a fixture consumer invokes it from.
# The recipe is deliberately a name no justfile in this repository carries, so a
# renderer falling back to one of ours could not produce it by accident.
_TOOL = "jq"
_CONSUMER_RECIPE = "check-nextest"

# The image the fixture consumer's CI container pins. The TAG is what carries the
# layer name, and the layer name is what this test joins the two ends on.
_CONSUMER_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-v1.126.1"

# Which Dockerfile builds each layer of the python-rust chain. `python-rust-agent`
# is the shared `agent` Dockerfile built with the python-rust digest as its
# parent, which is why the two names map to one file.
_LAYER_DOCKERFILES = {
    "python-rust": _SANDBOX / "python-rust" / "Dockerfile",
    "python-rust-agent": _SANDBOX / "agent" / "Dockerfile",
    "python-rust-fuzz": _SANDBOX / "python-rust-fuzz" / "Dockerfile",
}
# The layer every other layer of the chain is built FROM, and so the one that
# discharges the obligation for all of them.
_ROOT_LAYER = "python-rust"
# Each leaf built atop it: its workflow build-step id, and the build-arg that
# step wires its parent image through. Read as a pair because an arm that knew
# only the step would accept a step wiring the wrong arg, and an arm that knew
# only the arg would accept the right arg wired in some other step.
_LEAF_WIRING = {
    "python-rust-agent": ("build_python_rust_agent", "PARENT_IMAGE"),
    "python-rust-fuzz": ("build_python_rust_fuzz", "PYTHON_RUST_IMAGE"),
}
# The workflow step whose digest every leaf's parent arg must name.
_ROOT_BUILD_STEP = "build_python_rust"

# An image tag of this chain: `<layer>-sha-<short>` per master build, or
# `<layer>-v<X.Y.Z>` per release. Both suffixes are matched so the join below
# works on whichever form a consumer happens to pin.
_IMAGE_TAG = re.compile(r"^(?P<layer>.+?)-(?:sha-[0-9a-f]+|v\d+\.\d+\.\d+)$")
# An `apt-get install` package list: everything after the flags, up to the line
# continuation that ends the invocation.
_APT_INSTALL = re.compile(r"apt-get[^\n]*install(?P<rest>(?:[^\n]|\\\n)*)")
_APT_FLAG = re.compile(r"^-")
# The ways a layer takes a package back out again. `apt-get remove`/`purge` and a
# bare `rm` of the binary are the three a leaf would plausibly reach for.
_REMOVALS = ("apt-get remove", "apt-get purge", "apt-get -y remove", "dpkg --purge")

# The counter-examples the control arms feed back through the readers.
_CONTROL_INSTALLS_NOTHING = """\
FROM scratch
RUN echo "no toolchain here" > /dev/null
"""
_CONTROL_INSTALLS_WITHOUT_PROVING = """\
FROM scratch
RUN apt-get update \\
    && apt-get install -y --no-install-recommends jq \\
    && rm -rf /var/lib/apt/lists/*
"""
_CONTROL_PURGES_THE_TOOL = """\
ARG PYTHON_RUST_IMAGE=livespec-fabro-sandbox:python-rust-dev
FROM ${PYTHON_RUST_IMAGE}
RUN apt-get purge -y jq
"""
# A leaf that HARDCODES its base image instead of taking the build-arg the
# workflow wires, so correct wiring in the workflow reaches nothing — and that
# MENTIONS the tool in a comment. The mention is the false-positive direction of
# the removal reader: prose explaining that the tool is inherited must never read
# as a line that removes it, or every correctly-documented leaf is convicted.
_CONTROL_IGNORES_ITS_PARENT_ARG = """\
ARG PYTHON_RUST_IMAGE=livespec-fabro-sandbox:python-rust-dev
FROM livespec-fabro-sandbox:python-dev
# jq is inherited from the parent layer; this leaf installs nothing itself.
RUN echo "leaf payload" > /dev/null
"""
# A leaf wired to the PYTHON digest rather than the python-rust one: the most
# plausible way inheritance breaks, since the sibling `python-agent` step in the
# same workflow wires exactly that.
_CONTROL_WRONG_PARENT = """\
      - name: Build + push python-rust-fuzz
        id: build_python_rust_fuzz
        uses: docker/build-push-action@v7
        with:
          build-args: |
            PYTHON_RUST_IMAGE=${{ steps.target.outputs.image }}@${{ \
steps.build_python.outputs.digest }}
      - name: Something else
"""


def _layer_of(*, image: str) -> str:
    """The chain layer an image reference names, or `""` when its tag names none.

    Read off the TAG rather than taken as given, because this is the join: the
    renderer resolves an image from the consumer's own workflow, and which
    Dockerfile owes the tool follows from which layer that image is.
    """
    _, _, tag = image.rpartition(":")
    found = _IMAGE_TAG.match(tag)
    return "" if found is None else found.group("layer")


def _apt_installed(*, dockerfile: str) -> set[str]:
    """Every package the Dockerfile's `apt-get install` steps name.

    The flags are dropped rather than enumerated, so a step that grows a new
    `-o Acquire::Retries=5` or `--no-install-recommends` does not read as
    installing a package called that.
    """
    named: set[str] = set()
    for invocation in _APT_INSTALL.finditer(dockerfile):
        body = invocation.group("rest").replace("\\\n", " ")
        words = takewhile(lambda word: word != "&&", body.split())
        named.update(word for word in words if not _APT_FLAG.match(word))
    return named


def _gate_tool_gaps(*, dockerfile: str, tool: str) -> list[str]:
    """Each way a layer would leave a delegated gate without `tool`.

    Both gaps are silent at every other surface. An absent install publishes an
    image the spec says carries the tool; an install nobody proved publishes one
    that merely tried to.
    """
    gaps: list[str] = []
    if tool not in _apt_installed(dockerfile=dockerfile):
        gaps.append(f"{tool} is never installed by this layer")
    if f"command -v {tool}" not in dockerfile:
        gaps.append(
            f"the build never proves {tool} resolves on PATH, so a failed install publishes"
        )
    return gaps


def _removal_of(*, dockerfile: str, tool: str) -> list[str]:
    """Each way this layer takes `tool` back out of the image it inherited."""
    found: list[str] = []
    for line in dockerfile.splitlines():
        if tool not in line:
            continue
        if any(removal in line for removal in _REMOVALS) or f"rm /usr/bin/{tool}" in line:
            found.append(line.strip())
    return found


def _build_step(*, workflow: str, step_id: str) -> str:
    """One workflow build step's own text, sliced at the next step's `- name:`.

    Scoped to the step because the wiring claim is about which digest THIS leaf's
    parent arg names: the workflow carries six build steps whose arg lines differ
    only in the step they reference, so an unscoped search would be satisfied by
    any one of them.
    """
    lines = workflow.splitlines()
    opener = next(index for index, line in enumerate(lines) if line.strip() == f"id: {step_id}")
    body = takewhile(lambda line: not line.startswith("      - name:"), lines[opener + 1 :])
    return "\n".join(body)


def _inheritance_gaps(*, workflow: str, dockerfile: str, layer: str, tool: str) -> list[str]:
    """Each way a leaf layer would NOT carry what `python-rust` provisioned.

    Inheritance is the whole of the second assertion, so both halves are read:
    the leaf must really be built FROM the python-rust image the workflow just
    built, and it must not undo the install afterwards.
    """
    gaps: list[str] = []
    step_id, parent_arg = _LEAF_WIRING[layer]
    step = _build_step(workflow=workflow, step_id=step_id)
    wiring = f"{parent_arg}=${{{{ steps.target.outputs.image }}}}@${{{{ "
    if f"{wiring}steps.{_ROOT_BUILD_STEP}.outputs.digest }}}}" not in " ".join(step.split()):
        gaps.append(f"{layer} does not wire {parent_arg} to the {_ROOT_LAYER} digest")
    if f"FROM ${{{parent_arg}}}" not in dockerfile:
        gaps.append(f"{layer}'s Dockerfile does not build FROM ${parent_arg}")
    gaps.extend(
        f"{layer} removes {tool} again: {line}"
        for line in _removal_of(dockerfile=dockerfile, tool=tool)
    )
    return gaps


def _a_consumer_pinning(*, root: Path, image: str, tool: str, recipe: str) -> Path:
    """A fixture consuming repository that pins `tool` and gates with `recipe`.

    The `.mise.toml` pin is the scenario's Given and is written even though
    nothing here reads it: it is the fact that makes the tool's absence from the
    image a DEFECT rather than a consumer that forgot to ask for it, and a
    fixture that omitted it would be asserting a different scenario.
    """
    root.mkdir(parents=True, exist_ok=True)
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(
        f"jobs:\n  one:\n    runs-on: self-hosted\n    container:\n      image: {image}\n",
        encoding="utf-8",
    )
    _ = (root / ".mise.toml").write_text(f'[tools]\n{tool} = "1.7.1"\n', encoding="utf-8")
    _ = (root / "pyproject.toml").write_text(
        f'[tool.livespec_dev_tooling]\ndelegated_gate = true\ngate_check_suite = ["{recipe}"]\n',
        encoding="utf-8",
    )
    return root


def _render(*, repo_root: Path) -> str:
    """Run the REAL renderer for one fixture consumer; return its manifest.

    The renderer is the subject of the When, so a canned manifest would assert
    the fixture. It contacts nothing by construction and applies nothing.

    The suite is read out of the consumer's own `pyproject.toml` by the SAME
    public reader the delegating client uses, and handed on as the `--check-suite`
    flags that client passes — so the member in the rendered Job traces back to
    the fixture's declaration rather than to a constant invented at the renderer's
    boundary. That the client is the thing which reads it is owned by
    `test_delegated_gate_declared_recipe_scenarios`; what matters here is that the
    member this gate runs and the image it runs in come from ONE repository.
    """
    declared = load_gate_check_suite(repo_root=repo_root) or ()
    suite = [flag for recipe in declared for flag in ("--check-suite", recipe)]
    completed = subprocess.run(
        [str(_RENDERER), "--repo-root", str(repo_root), "--tree-hash", _TREE, *suite],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_S,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def _rendered_images(*, manifest: str) -> set[str]:
    """Every container image the rendered Job runs, as the Job itself names them."""
    return {
        line.split("image:", 1)[1].strip()
        for line in manifest.splitlines()
        if line.strip().startswith("image:")
    }


def _executed_lines(*, manifest: str) -> list[str]:
    """The rendered manifest's lines with its comment lines dropped.

    The template explains at length why a gate pod does not run `just bootstrap`,
    and prose ABOUT a step must never read as the step: the absence asserted
    below is made of these lines only.
    """
    return [
        stripped
        for stripped in (line.strip() for line in manifest.splitlines())
        if stripped and not stripped.startswith("#")
    ]


def test_a_consumers_delegated_gate_finds_the_mise_pinned_tools_its_gate_members_invoke(
    *, tmp_path: Path
) -> None:
    """The scenario, clause by clause, joined on the image the renderer resolved.

    GIVEN A CONSUMER THAT PINS `jq` AND HAS A GATE MEMBER THAT INVOKES IT, AND A
    CI CONTAINER THAT PINS A `python-rust` IMAGE: a fixture repository under
    `tmp_path`, whose `ci.yml` container is the only place an image is named.

    WHEN A DELEGATED GATE JOB RUNS THAT GATE IN THAT IMAGE WITHOUT `mise
    install`: the REAL renderer runs, and both halves of that When are asserted
    on what it produced. The Job's image must be the consumer's pinned one, since
    an image the gate does not run in owes the gate nothing; and no executed line
    may run `mise install`, which is the whole reason the image is the gate's
    only toolchain source — a pod that did install the consumer's pins would make
    every Dockerfile assertion below moot while leaving them green.

    THEN `jq` MUST BE FOUND ON `PATH`: read off the layer the resolved image
    names, which is the join. The install is asserted AND the build-time PATH
    proof with it: without the proof a layer that installed the tool under
    another name, or somewhere no login shell searches, publishes an image that
    reads correct here and is empty there.

    AND THE GATE MEMBER MUST RUN ITS VERIFICATION: the consumer's own declared
    recipe must appear in the Job, because a gate that drops the member needs no
    tool at all — narrowing the gate on the delegated path is the one remedy the
    spec forbids.

    CONTROL ARMS, each the same reader under the opposite condition: a layer that
    installs nothing is convicted on both counts, and one that installs the tool
    without proving it is convicted on exactly the proof — which is what
    separates asserting a PROVEN install from asserting that some apt line
    mentioned the package.
    """
    consumer = _a_consumer_pinning(
        root=tmp_path / "console", image=_CONSUMER_IMAGE, tool=_TOOL, recipe=_CONSUMER_RECIPE
    )

    manifest = _render(repo_root=consumer)

    assert _rendered_images(manifest=manifest) == {_CONSUMER_IMAGE}, (
        f"the Job must run in the image the CONSUMER pins — the gate's toolchain is whatever "
        f"that image carries, and an image resolved from anywhere else owes this gate nothing; "
        f"rendered={sorted(_rendered_images(manifest=manifest))}"
    )
    installs = [line for line in _executed_lines(manifest=manifest) if "mise install" in line]
    assert not installs, (
        f"the Job must run no `mise install`: if it did, the consumer's `.mise.toml` pins would "
        f"arrive at the gate on their own and no image would owe the gate anything, so every "
        f"assertion below would be about a requirement that had quietly stopped existing; "
        f"found={installs}"
    )
    assert f"just {_CONSUMER_RECIPE}" in manifest, (
        f"the consumer's own declared gate member `{_CONSUMER_RECIPE}` must run — a gate that "
        f"drops the member needs no tool at all, and narrowing the gate on the delegated path is "
        f"the one remedy the spec forbids"
    )

    layer = _layer_of(image=_CONSUMER_IMAGE)
    assert layer == _ROOT_LAYER, (
        f"the scenario's Given is a CI container pinning a `{_ROOT_LAYER}` image, so the fixture "
        f"must resolve to that layer rather than to whichever Dockerfile this test hoped to "
        f"read; resolved={layer!r}"
    )
    gaps = _gate_tool_gaps(
        dockerfile=_LAYER_DOCKERFILES[layer].read_text(encoding="utf-8"), tool=_TOOL
    )
    assert not gaps, (
        f"the {layer} image must carry {_TOOL} on PATH, and must PROVE it at build time: this "
        f"Dockerfile is an assertion the delegated gate believes with no second source to catch "
        f"it, so a layer that failed to install what it declares must fail the build rather than "
        f"publish an image missing the tool. Measured 2026-10-24: four console "
        f"`ci_telemetry_runner_attributes` tests errored on {_TOOL}'s absence in Job "
        f"gate-livespec-console-beads-fabro-bc28m; gaps={gaps}"
    )

    assert _gate_tool_gaps(dockerfile=_CONTROL_INSTALLS_NOTHING, tool=_TOOL) == [
        f"{_TOOL} is never installed by this layer",
        f"the build never proves {_TOOL} resolves on PATH, so a failed install publishes",
    ], "the reader must still convict a layer that provisions no gate toolchain at all"
    assert _gate_tool_gaps(dockerfile=_CONTROL_INSTALLS_WITHOUT_PROVING, tool=_TOOL) == [
        f"the build never proves {_TOOL} resolves on PATH, so a failed install publishes"
    ], (
        "and must convict an unproven install on exactly the proof — that is the difference "
        "between asserting a PROVEN install and asserting that some apt line named the package"
    )


def test_every_layer_atop_the_python_rust_image_carries_the_gate_toolchain() -> None:
    """The heading's two sentences: the root layer carries it, the leaves inherit it.

    THE ROOT LAYER: `python-rust` installs the tool and proves it on `PATH`, read
    by the same gaps reader the scenario uses.

    THE LEAVES: `python-rust-agent` and `python-rust-fuzz` are asserted to carry
    the tool by INHERITANCE, which is the only way they can — neither installs it
    and neither should, since a second install would drift from the first. So
    both halves of inheritance are read: the workflow must wire each leaf's
    parent build-arg to the digest of the `python-rust` build step, and the
    leaf's own Dockerfile must build FROM that arg and must not purge the tool
    back out afterwards.

    CONTROL ARMS. A leaf wired to the PYTHON digest instead is convicted — the
    most plausible break, since the sibling `python-agent` step in the same
    workflow wires exactly that — and so is a leaf that inherits the tool and
    then purges it. Without the purge arm, "inherits" would be an assertion about
    a `FROM` line rather than about the image's contents.
    """
    workflow = _WORKFLOW.read_text(encoding="utf-8")

    root_gaps = _gate_tool_gaps(
        dockerfile=_LAYER_DOCKERFILES[_ROOT_LAYER].read_text(encoding="utf-8"), tool=_TOOL
    )
    assert not root_gaps, (
        f"the {_ROOT_LAYER} layer is where the whole chain's obligation is discharged, so it "
        f"must install {_TOOL} and prove it on PATH; gaps={root_gaps}"
    )

    for layer in _LEAF_WIRING:
        gaps = _inheritance_gaps(
            workflow=workflow,
            dockerfile=_LAYER_DOCKERFILES[layer].read_text(encoding="utf-8"),
            layer=layer,
            tool=_TOOL,
        )
        assert not gaps, (
            f"{layer} must carry {_TOOL} by inheriting it from {_ROOT_LAYER}: it must be built "
            f"FROM the {_ROOT_LAYER} image the workflow just built, and must not take the tool "
            f"back out; gaps={gaps}"
        )
        installs = _apt_installed(dockerfile=_LAYER_DOCKERFILES[layer].read_text(encoding="utf-8"))
        assert _TOOL not in installs or layer == _ROOT_LAYER, (
            f"{layer} must not install {_TOOL} a second time: a per-leaf install drifts from the "
            f"root layer's, and the whole point of the chain is that one provisioning serves "
            f"every image built atop it; installed={sorted(installs)}"
        )

    assert _inheritance_gaps(
        workflow=_CONTROL_WRONG_PARENT,
        dockerfile=_LAYER_DOCKERFILES["python-rust-fuzz"].read_text(encoding="utf-8"),
        layer="python-rust-fuzz",
        tool=_TOOL,
    ) == [f"python-rust-fuzz does not wire PYTHON_RUST_IMAGE to the {_ROOT_LAYER} digest"], (
        "the wiring reader must still convict a leaf built FROM the python digest — the sibling "
        "`python-agent` step in the same workflow wires exactly that, so it is the break that "
        "would really happen"
    )
    assert _inheritance_gaps(
        workflow=workflow,
        dockerfile=_CONTROL_PURGES_THE_TOOL,
        layer="python-rust-fuzz",
        tool=_TOOL,
    ) == [f"python-rust-fuzz removes {_TOOL} again: RUN apt-get purge -y {_TOOL}"], (
        "and must convict a leaf that inherits the tool and then purges it, or 'inherits' is an "
        "assertion about a FROM line rather than about what the image contains"
    )
    assert _inheritance_gaps(
        workflow=workflow,
        dockerfile=_CONTROL_IGNORES_ITS_PARENT_ARG,
        layer="python-rust-fuzz",
        tool=_TOOL,
    ) == ["python-rust-fuzz's Dockerfile does not build FROM $PYTHON_RUST_IMAGE"], (
        "and a leaf that HARDCODES its base image, since the workflow's wiring then reaches "
        "nothing — while a comment merely MENTIONING the tool must NOT be read as removing it, "
        "which is the false-positive direction that would convict every documented leaf"
    )
