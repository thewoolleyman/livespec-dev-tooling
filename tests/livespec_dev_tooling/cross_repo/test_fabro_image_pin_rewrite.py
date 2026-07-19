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
# rewrite_pin_in_text — the `.github/workflows/` container-image surface
#
# The same pin, at the second surface the autodiscovery walk now covers: a
# cut-over consumer runs its CI jobs inside the baked sandbox image, so the
# reference appears as a job `container:` block's `image:` line. Without these
# the walk's new records would hit a rewriter that cannot match them — and
# `main()` treats a zero match count as fatal, so the fan-out would FAIL rather
# than silently no-op.
# ---------------------------------------------------------------------------


def _container_job(*, job: str, tag: str) -> str:
    """Render one CI job whose `container:` block pins the fabro-sandbox image."""
    return (
        f"  {job}:\n"
        "    runs-on: ubuntu-latest\n"
        "    container:\n"
        f"      image: {_IMAGE}:{tag}\n"
    )


def test_rewrite_pin_in_text_rewrites_workflow_container_image() -> None:
    """A job `container:` block's `image:` line is rewritten, layer prefix preserved."""
    text = "jobs:\n" + _container_job(job="check-python", tag="python-v0.43.2")
    new_text, count = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-v0.43.2",
        release_tag="v0.44.0",
    )
    assert count == 1
    assert new_text == "jobs:\n" + _container_job(job="check-python", tag="python-v0.44.0")


def test_rewrite_pin_in_text_rewrites_container_shorthand() -> None:
    """The one-line `container: <image>` shorthand is rewritten too."""
    text = f"jobs:\n  check:\n    container: {_IMAGE}:python-rust-v0.48.2\n"
    new_text, count = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-rust-v0.48.2",
        release_tag="v0.49.0",
    )
    assert count == 1
    assert new_text == f"jobs:\n  check:\n    container: {_IMAGE}:python-rust-v0.49.0\n"


def test_repeated_invocations_converge_every_matching_line() -> None:
    """N invocations rewrite N identical `image:` lines — one per walk record.

    The walk yields ONE RECORD PER MATCHING LINE and each record drives one
    `rewrite_pin_in_text` invocation with `count=1`, so each invocation consumes
    the next still-unrewritten occurrence. A single-pass rewriter would leave
    jobs 2..N pinned to the stale tag — exactly the in-file drift the per-line
    rule exists to eliminate.
    """
    text = (
        "jobs:\n"
        + _container_job(job="check-python", tag="python-v0.43.2")
        + _container_job(job="check-docs", tag="python-v0.43.2")
        + _container_job(job="check-shell", tag="python-v0.43.2")
    )
    for _ in range(3):
        text, count = rewrite_pin_in_text(
            text=text,
            image_key=_IMAGE,
            current_tag="python-v0.43.2",
            release_tag="v0.44.0",
        )
        assert count == 1
    assert text == (
        "jobs:\n"
        + _container_job(job="check-python", tag="python-v0.44.0")
        + _container_job(job="check-docs", tag="python-v0.44.0")
        + _container_job(job="check-shell", tag="python-v0.44.0")
    )
    # A fourth invocation finds nothing left to rewrite.
    _, count = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-v0.43.2",
        release_tag="v0.44.0",
    )
    assert count == 0


def test_rewrite_pin_in_text_leaves_unrelated_container_image_untouched() -> None:
    """An unrelated `container:` / `image:` line is not a match — the rewrite is scoped."""
    text = (
        "jobs:\n"
        "  build:\n"
        "    container:\n"
        "      image: ghcr.io/thewoolleyman/some-other-image:python-v0.43.2\n"
    )
    new_text, count = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-v0.43.2",
        release_tag="v0.44.0",
    )
    assert count == 0
    assert new_text == text


def test_rewrite_pin_in_text_does_not_truncate_a_longer_tag() -> None:
    """A tag that merely STARTS with `current_tag` is not a match.

    `python-v0.43.2` must not match the `python-v0.43.20` line and leave a
    stray `0` behind; the tag has to end where the record says it ends.
    """
    text = "jobs:\n" + _container_job(job="check-python", tag="python-v0.43.20")
    new_text, count = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-v0.43.2",
        release_tag="v0.44.0",
    )
    assert count == 0
    assert new_text == text


def test_main_rewrites_workflow_container_image_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` rewrites a `.github/workflows/` CI image pin, prefix preserved.

    The end-to-end shape of the record the walk now emits: a `.yml` `PIN_FILE`
    carrying a `python-rust-` layered tag, which must bump to
    `python-rust-v<new>` and NOT to a bare `v<new>` — the layer prefix is what
    selects the image layer the consumer's CI actually needs.
    """
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "ci.yml"
    _ = pin_file.write_text(
        "jobs:\n" + _container_job(job="check-python", tag="python-rust-v0.48.2"),
        encoding="utf-8",
    )
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", _IMAGE)
    monkeypatch.setenv("PIN_CURRENT", "python-rust-v0.48.2")
    monkeypatch.setenv("PIN_TAG", "v0.49.0")
    assert main() == 0
    assert pin_file.read_text(encoding="utf-8") == "jobs:\n" + _container_job(
        job="check-python", tag="python-rust-v0.49.0"
    )


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
