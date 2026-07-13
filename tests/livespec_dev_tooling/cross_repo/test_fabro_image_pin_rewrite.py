"""Behavioral tests for `fabro_image_pin_rewrite` — prefix-preserving docker-pin rewrite.

Per `SPECIFICATION/contracts.md` §"Pin autodiscovery rules", the fabro-sandbox
image pin is `docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>"`.
Since the layer split (livespec-3lev.4) that `<tag>` carries a `<layer>-` prefix
(`python-v<X.Y.Z>` / `python-rust-v<X.Y.Z>`) over the bare release version, so a
release fan-out MUST rewrite only the trailing `vX.Y.Z` and preserve the prefix
— the pre-extraction inline heredoc dropped it, breaking the pin on every
release. These tests give the extracted module the behavioral coverage the
heredoc never had.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.cross_repo.fabro_image_pin_rewrite import (
    main,
    rewrite_layered_docker_tag,
    rewrite_pin_in_text,
)

__all__: list[str] = []


_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox"


# ---------------------------------------------------------------------------
# rewrite_layered_docker_tag — pure prefix-preserving version bump
# ---------------------------------------------------------------------------


def test_preserves_python_rust_prefix() -> None:
    """A `python-rust-` layer prefix survives; only the version is bumped."""
    assert (
        rewrite_layered_docker_tag(current_tag="python-rust-v0.43.0", release_tag="v0.44.0")
        == "python-rust-v0.44.0"
    )


def test_preserves_python_prefix() -> None:
    """A `python-` layer prefix survives; only the version is bumped."""
    assert (
        rewrite_layered_docker_tag(current_tag="python-v0.43.0", release_tag="v0.44.0")
        == "python-v0.44.0"
    )


def test_preserves_base_prefix() -> None:
    """A `base-` layer prefix survives; only the version is bumped."""
    assert (
        rewrite_layered_docker_tag(current_tag="base-v0.43.0", release_tag="v0.44.0")
        == "base-v0.44.0"
    )


def test_bare_version_rewrites_to_bare_release() -> None:
    """A bare `vX.Y.Z` tag (no layer prefix) rewrites to the bare release tag."""
    assert rewrite_layered_docker_tag(current_tag="v0.43.0", release_tag="v0.44.0") == "v0.44.0"


def test_prefixed_non_semver_tag_falls_back_to_bare() -> None:
    """A tag with no `vX.Y.Z` anchor (a pre-layer `sha-` tag) rewrites bare.

    Such a tag carries no version to anchor a prefix against, so there is
    nothing to preserve — the rewrite yields the bare release tag. This case
    does not recur once consumers pin `<layer>-v<X.Y.Z>`, but the fallback is
    total rather than raising.
    """
    assert rewrite_layered_docker_tag(current_tag="sha-ea684ad", release_tag="v0.44.0") == "v0.44.0"


# ---------------------------------------------------------------------------
# rewrite_pin_in_text — file-text rewrite + single-match count
# ---------------------------------------------------------------------------


def test_rewrite_pin_in_text_rewrites_single_pin() -> None:
    """The `docker = "<image>:<tag>"` line is rewritten once, prefix preserved."""
    text = f'[image]\ndocker = "{_IMAGE}:python-rust-v0.43.0"\n'
    new_text, count = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-rust-v0.43.0",
        release_tag="v0.44.0",
    )
    assert count == 1
    assert new_text == f'[image]\ndocker = "{_IMAGE}:python-rust-v0.44.0"\n'


def test_rewrite_pin_in_text_reports_zero_when_absent() -> None:
    """When the pin line is not present, the count is zero and text is unchanged."""
    text = "no docker pin here\n"
    new_text, count = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-rust-v0.43.0",
        release_tag="v0.44.0",
    )
    assert count == 0
    assert new_text == text


# ---------------------------------------------------------------------------
# main — env-driven in-place file rewrite
# ---------------------------------------------------------------------------


def test_main_rewrites_file_in_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`main()` reads the pin coordinates from env and rewrites the file in place."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "workflow.toml"
    _ = pin_file.write_text(f'docker = "{_IMAGE}:python-rust-v0.43.0"\n', encoding="utf-8")
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", _IMAGE)
    monkeypatch.setenv("PIN_CURRENT", "python-rust-v0.43.0")
    monkeypatch.setenv("PIN_TAG", "v0.44.0")
    assert main() == 0
    assert pin_file.read_text(encoding="utf-8") == f'docker = "{_IMAGE}:python-rust-v0.44.0"\n'


def test_main_returns_nonzero_when_pin_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` reports a non-zero exit and leaves the file untouched when the pin is absent."""
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "workflow.toml"
    _ = pin_file.write_text("no docker pin here\n", encoding="utf-8")
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", _IMAGE)
    monkeypatch.setenv("PIN_CURRENT", "python-rust-v0.43.0")
    monkeypatch.setenv("PIN_TAG", "v0.44.0")
    assert main() == 1
    assert pin_file.read_text(encoding="utf-8") == "no docker pin here\n"
