"""`verify-factory-reach.sh` resolves its sandbox image from the pin it SHIPS WITH.

WHY THIS FILE EXISTS (work-item livespec-dev-tooling-jvnqwv, livespec plan
`factory-worker-nodes-gitops`, epic `livespec-sqvj7p`). The check landed reading
the sandbox image out of this repository's own `.github/workflows/ci.yml`
`container:` block. That is correct for `../gates/render-gate-job.sh`, which runs
from a checkout on the control node — and WRONG for this check, which freeze
ruling R70 (2026-10-16) made a converge artifact: the installed tree on a pool
node carries no checkout, so the workflow it read is not there. The image pin
therefore ships BESIDE the script, as `factory-reach-image.env`, and
`livespec_dev_tooling/fabro_image_pin_lockstep.py` is what keeps that shipped pin
equal to the fleet pin the release fan-out rewrites in `ci.yml`.

HOW THE ASSERTION IS MADE UNFORGEABLE. The script is run from a SCRATCH INSTALLED
LAYOUT holding the four shipped files and nothing else — the layout
`ansible/roles/factory_reach_check` installs — with a DECOY `ci.yml` planted at
the exact relative path the retired resolution computed
(`${SCRIPT_DIR}/../../../../.github/workflows/ci.yml`), naming an image the fleet
never publishes. A script that still read the workflow would render the decoy and
fail here, so this cannot pass by the committed pin and the committed workflow
happening to agree.

A dry run contacts nothing — no cluster, no endpoint, no registry — which
`test_ci_runner_k3s_factory_reach_verifier.py` proves against a tripwire PATH.
This file asserts the image the manifest NAMES, so it runs on the ambient PATH.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "factory"
_SCRIPT_NAME = "verify-factory-reach.sh"
_IMAGE_PIN_NAME = "factory-reach-image.env"

# Everything the installed layout carries, and the whole of it: the renderer, the
# probe it embeds, the endpoints it probes and the image pin it renders. Stated
# here rather than globbed, because the point of the scratch layout is that a
# file the install forgot is a file this test does not supply either.
_SHIPPED = (
    _SCRIPT_NAME,
    "factory-reach-probe.sh",
    "factory-reach-endpoints.env",
    _IMAGE_PIN_NAME,
)

# The key the shipped pin file carries the image reference under.
_IMAGE_KEY = "FACTORY_REACH_SANDBOX_IMAGE"
_IMAGE_LINE = re.compile(rf"^\s*{_IMAGE_KEY}=(?P<image>\S+)\s*$", re.MULTILINE)

# An image the fleet's own build never publishes, so its presence in a rendered
# manifest can only mean the script read the decoy workflow.
_DECOY_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:decoy-never-published"
_DECOY_WORKFLOW = (
    "jobs:\n  check:\n    runs-on: ubuntu-latest\n    container:\n" f"      image: {_DECOY_IMAGE}\n"
)

# The node the Definition of Done's host-captured leg names first. Which node is
# irrelevant to the image, and naming a real one keeps the rendered manifest the
# one an operator reads.
_NODE = "hp-xubuntu"


def _shipped_image() -> str:
    """The image reference the committed pin file names, read out of it."""
    pin = _FACTORY_DIR / _IMAGE_PIN_NAME
    assert pin.is_file(), (
        f"{pin.relative_to(_REPO_ROOT)} must be committed: the check runs from an installed "
        f"tree on a pool node, where this repository's .github/workflows/ci.yml does not "
        f"exist, so the image it renders has to ship beside it"
    )
    matches = _IMAGE_LINE.findall(pin.read_text(encoding="utf-8"))
    assert len(matches) == 1, (
        f"{pin.relative_to(_REPO_ROOT)} must name exactly one {_IMAGE_KEY}; found {matches}. "
        f"Two values is two answers to which toolchain the probe runs, and guessing wrong "
        f"proves a pull nobody performs"
    )
    return matches[0]


@pytest.fixture
def installed_layout(*, tmp_path: Path) -> Path:
    """The four shipped files under a scratch installed tree, plus a decoy workflow.

    The directory mirrors the converge's installed layout
    (`/usr/local/lib/ci-runner-k3s/factory`) so the decoy lands where the
    retired `${SCRIPT_DIR}/../../../../.github/workflows/ci.yml` resolution
    would have looked for it.
    """
    install = tmp_path / "usr" / "local" / "lib" / "ci-runner-k3s" / "factory"
    install.mkdir(parents=True)
    for name in _SHIPPED:
        _ = shutil.copy(_FACTORY_DIR / name, install / name)
    decoy = install.parents[3] / ".github" / "workflows" / "ci.yml"
    decoy.parent.mkdir(parents=True)
    _ = decoy.write_text(_DECOY_WORKFLOW, encoding="utf-8")
    return install


def _run(*, argv: list[str]) -> tuple[int, str]:
    """One script run, returning its code and merged output."""
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        stdin=subprocess.DEVNULL,
        env={**os.environ},
    )
    return completed.returncode, completed.stdout + completed.stderr


def test_the_installed_layout_dry_run_renders_the_shipped_image_pin(
    *, installed_layout: Path
) -> None:
    """The manifest's image is the pin file's image, with no checkout in reach."""
    code, output = _run(
        argv=["bash", str(installed_layout / _SCRIPT_NAME), "--dry-run", "--node", _NODE]
    )
    assert code == 0, (
        f"`{_SCRIPT_NAME} --dry-run --node {_NODE}` must exit 0 from the INSTALLED layout: "
        f"a converge artifact that needs a repository checkout beside it is one the node "
        f"cannot run;\n{output}"
    )
    assert f"image: {_shipped_image()}" in output, (
        f"the rendered Job must name the image the shipped {_IMAGE_PIN_NAME} carries "
        f"({_shipped_image()}), because that file is the only pin present on a pool node;"
        f"\nmanifest={output}"
    )
    assert _DECOY_IMAGE not in output, (
        f"the rendered Job must NOT name {_DECOY_IMAGE}: a decoy ci.yml sits at the exact "
        f"path the retired workflow resolution computed, so reading it renders an image the "
        f"fleet never publishes while still printing green;\nmanifest={output}"
    )


def test_an_installed_layout_with_no_shipped_pin_is_refused_rather_than_guessed(
    *, installed_layout: Path
) -> None:
    """A missing pin file is a configuration refusal, naming the file.

    Exit 2 and nothing submitted, on the script's own usage-error rail. The
    alternative is the shape this change exists to remove: falling back to a
    workflow that is not on the node, or to a literal nobody rewrites, and
    proving a pull of an image no dispatch uses.
    """
    (installed_layout / _IMAGE_PIN_NAME).unlink(missing_ok=True)

    code, output = _run(
        argv=["bash", str(installed_layout / _SCRIPT_NAME), "--dry-run", "--node", _NODE]
    )

    assert code == 2, (
        f"an installed layout with no {_IMAGE_PIN_NAME} must exit 2 — the configuration-error "
        f"rail — rather than render a guessed image; got {code}\n{output}"
    )
    assert _IMAGE_PIN_NAME in output, (
        f"the refusal must NAME the missing file, so an operator fixes the install rather "
        f"than the script;\n{output}"
    )
