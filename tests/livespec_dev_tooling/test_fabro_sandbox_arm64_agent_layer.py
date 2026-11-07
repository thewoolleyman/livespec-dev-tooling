"""The python-agent layer also builds natively for an arm64 homelab worker.

WHAT WAS MEASURED. On 2026-11-07 every published `python-agent-*` tag was
amd64-only while `python` was a two-platform index, so an arm64 factory sandbox
had no image carrying the ACP adapters and bubblewrap that a dispatch's implement,
fix and review nodes need. The agent Dockerfile also fetched x86_64-only sccache
and herdr assets, so it could not have built on arm64 at all.

These tests read the workflow as parsed YAML and the Dockerfile as text. What they
cannot show is that the layer BUILDS on arm64: the `build-arm64` job proves that on
every pull request touching this tree.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "fabro-sandbox-image.yml"
_DOCKERFILE = _REPO_ROOT / "docker" / "fabro-sandbox" / "agent" / "Dockerfile"
# github.com/mozilla/sccache release v0.17.0, the aarch64-unknown-linux-musl
# tarball's digest as the release reports it, read 2026-11-07.
_SCCACHE_SHA256_ARM64 = "821a86343191aa1cbab74bd42f9e93c9a63bf85e4742945f40d3ae84193c1c77"


def _jobs() -> dict[str, Any]:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]


def _step(*, job: str, name: str) -> dict[str, Any]:
    steps = [step for step in _jobs()[job]["steps"] if step.get("name") == name]
    assert len(steps) == 1, f"{job} must carry exactly one step named {name!r}"
    return steps[0]


def test_the_arm64_job_builds_the_agent_layer_on_the_arm64_python_digest() -> None:
    step = _step(job="build-arm64", name="Build + push python-agent (arm64)")
    settings = step["with"]
    assert settings["file"] == "docker/fabro-sandbox/agent/Dockerfile"
    assert settings["platforms"] == "linux/arm64"
    assert "@${{ steps.build_python.outputs.digest }}" in settings["build-args"], (
        "the agent layer must sit FROM the arm64 python digest this job just built, or it "
        "would carry another architecture's toolchain"
    )


def test_the_arm64_agent_layer_publishes_only_suffixed_tags() -> None:
    settings = _step(job="build-arm64", name="Compute python-agent tags")["with"]
    assert "suffix=-arm64" in settings["flavor"]
    assert "prefix=python-agent-sha-" in settings["tags"]
    assert "prefix=python-agent-" in settings["tags"]


def test_no_amd64_python_agent_tag_becomes_a_multi_platform_index() -> None:
    settings = _step(job="multiarch", name="Compute the layer tags to merge")["with"]
    assert "python-agent" not in settings["tags"], (
        "merging python-agent tags would change what every amd64 factory instance pinned to "
        "those tags resolves"
    )


def test_sccache_selects_its_asset_and_digest_by_target_architecture() -> None:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG TARGETARCH" in text
    assert re.findall(r"^ARG SCCACHE_SHA256_arm64=(\S+)$", text, re.MULTILINE) == [
        _SCCACHE_SHA256_ARM64
    ]
    # `:-` because these steps run under `set -u`, and TARGETARCH is unset outside BuildKit.
    assert 'if [ "${TARGETARCH}" =' not in text
    assert 'if [ "${TARGETARCH:-}" = "arm64" ]; then' in text
    assert 'asset="sccache-v${SCCACHE_VERSION}-aarch64-unknown-linux-musl";' in text
    assert 'asset_sha256="${SCCACHE_SHA256_arm64}";' in text
    assert 'echo "${asset_sha256}  /tmp/sccache.tgz" | sha256sum -c -;' in text
