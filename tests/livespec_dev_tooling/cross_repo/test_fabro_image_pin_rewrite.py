"""Behavioral tests for `fabro_image_pin_rewrite` — prefix-preserving docker-pin rewrite.

Per `SPECIFICATION/contracts.md` §"Pin autodiscovery rules", the fabro-sandbox
image pin is `docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>"`.
Since the layer split (livespec-3lev.4) that `<tag>` carries a `<layer>-` prefix
(`python-v<X.Y.Z>` / `python-rust-v<X.Y.Z>`) over the bare release version, so a
release fan-out MUST rewrite only the trailing `vX.Y.Z` and preserve the prefix
— the pre-extraction inline heredoc dropped it, breaking the pin on every
release. These tests give the extracted module the behavioral coverage the
heredoc never had.

They also pin the UNREWRITABLE-SHAPE guard. `.github/workflows/fabro-sandbox-image.yml`
publishes five layers (`base-`, `python-`, `python-agent-`, `python-rust-`,
`python-rust-agent-`) and every published tag carries its layer prefix, so a
rewrite yielding a BARE `vX.Y.Z` names an image that will never exist. A tag with
no prefix to preserve is therefore refused (`None`) rather than silently rewritten
bare — the silent rewrite produced a clean-looking diff and a green auto-merge
bump PR pointing at nothing.
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
#
# One case per layer the image build publishes, so the rewrite is proven over
# the whole published prefix set rather than over a sample of it.
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


def test_preserves_python_agent_prefix() -> None:
    """A `python-agent-` layer prefix survives; only the version is bumped."""
    assert (
        rewrite_layered_docker_tag(current_tag="python-agent-v0.43.0", release_tag="v0.44.0")
        == "python-agent-v0.44.0"
    )


def test_preserves_python_rust_agent_prefix() -> None:
    """A `python-rust-agent-` layer prefix survives; only the version is bumped."""
    assert (
        rewrite_layered_docker_tag(current_tag="python-rust-agent-v0.43.0", release_tag="v0.44.0")
        == "python-rust-agent-v0.44.0"
    )


# ---------------------------------------------------------------------------
# rewrite_layered_docker_tag — the unrewritable shapes
#
# Both shapes below would have yielded a BARE `release_tag` before the guard.
# The image build publishes no bare tag, so that result named an image that
# never exists — a green bump PR pointing at nothing. Refusing is the only
# honest answer; the pin must be migrated to a prefixed tag by hand.
# ---------------------------------------------------------------------------


def test_bare_version_is_unrewritable() -> None:
    """A bare `vX.Y.Z` tag has no prefix to preserve, so the rewrite is refused."""
    assert rewrite_layered_docker_tag(current_tag="v0.38.1", release_tag="v0.44.0") is None


def test_sha_tag_without_layer_prefix_is_unrewritable() -> None:
    """A pre-layer `sha-<short>` tag carries no `vX.Y.Z` anchor, so it is refused."""
    assert rewrite_layered_docker_tag(current_tag="sha-ea684ad", release_tag="v0.44.0") is None


def test_layer_prefixed_sha_tag_is_unrewritable() -> None:
    """A published `<layer>-sha-<short>` tag has no version anchor either.

    The build publishes `python-sha-<short>` alongside `python-v<X.Y.Z>`, but a
    sha-pinned tag names one commit's image — there is no version in it to bump,
    so the fan-out cannot maintain it and must say so rather than invent one.
    """
    assert (
        rewrite_layered_docker_tag(current_tag="python-sha-ea684ad", release_tag="v0.44.0") is None
    )


# ---------------------------------------------------------------------------
# rewrite_pin_in_text — file-text rewrite + single-match count
# ---------------------------------------------------------------------------


def test_rewrite_pin_in_text_rewrites_single_pin() -> None:
    """The `docker = "<image>:<tag>"` line is rewritten once, prefix preserved."""
    text = f'[image]\ndocker = "{_IMAGE}:python-rust-v0.43.0"\n'
    result = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-rust-v0.43.0",
        release_tag="v0.44.0",
    )
    assert result is not None
    new_text, count = result
    assert count == 1
    assert new_text == f'[image]\ndocker = "{_IMAGE}:python-rust-v0.44.0"\n'


def test_rewrite_pin_in_text_reports_zero_when_absent() -> None:
    """When the pin line is not present, the count is zero and text is unchanged."""
    text = "no docker pin here\n"
    result = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-rust-v0.43.0",
        release_tag="v0.44.0",
    )
    assert result is not None
    new_text, count = result
    assert count == 0
    assert new_text == text


def test_rewrite_pin_in_text_refuses_unrewritable_tag() -> None:
    """An unrewritable `current_tag` short-circuits to `None` — the text is never touched.

    The refusal happens BEFORE the pattern is built, so a matching pin line is
    left alone rather than rewritten to a bare tag. `None` is distinct from the
    `(text, 0)` "pin absent" answer: the pin is present, it simply cannot be
    maintained by the fan-out.
    """
    text = f'[image]\ndocker = "{_IMAGE}:sha-ea684ad"\n'
    assert (
        rewrite_pin_in_text(
            text=text,
            image_key=_IMAGE,
            current_tag="sha-ea684ad",
            release_tag="v0.44.0",
        )
        is None
    )


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
    result = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-v0.43.2",
        release_tag="v0.44.0",
    )
    assert result is not None
    new_text, count = result
    assert count == 1
    assert new_text == "jobs:\n" + _container_job(job="check-python", tag="python-v0.44.0")


def test_rewrite_pin_in_text_rewrites_container_shorthand() -> None:
    """The one-line `container: <image>` shorthand is rewritten too."""
    text = f"jobs:\n  check:\n    container: {_IMAGE}:python-rust-v0.48.2\n"
    result = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-rust-v0.48.2",
        release_tag="v0.49.0",
    )
    assert result is not None
    new_text, count = result
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
        result = rewrite_pin_in_text(
            text=text,
            image_key=_IMAGE,
            current_tag="python-v0.43.2",
            release_tag="v0.44.0",
        )
        assert result is not None
        text, count = result
        assert count == 1
    assert text == (
        "jobs:\n"
        + _container_job(job="check-python", tag="python-v0.44.0")
        + _container_job(job="check-docs", tag="python-v0.44.0")
        + _container_job(job="check-shell", tag="python-v0.44.0")
    )
    # A fourth invocation finds nothing left to rewrite.
    fourth = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-v0.43.2",
        release_tag="v0.44.0",
    )
    assert fourth is not None
    _, count = fourth
    assert count == 0


def test_rewrite_pin_in_text_leaves_unrelated_container_image_untouched() -> None:
    """An unrelated `container:` / `image:` line is not a match — the rewrite is scoped."""
    text = (
        "jobs:\n"
        "  build:\n"
        "    container:\n"
        "      image: ghcr.io/thewoolleyman/some-other-image:python-v0.43.2\n"
    )
    result = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-v0.43.2",
        release_tag="v0.44.0",
    )
    assert result is not None
    new_text, count = result
    assert count == 0
    assert new_text == text


def test_rewrite_pin_in_text_does_not_truncate_a_longer_tag() -> None:
    """A tag that merely STARTS with `current_tag` is not a match.

    `python-v0.43.2` must not match the `python-v0.43.20` line and leave a
    stray `0` behind; the tag has to end where the record says it ends.
    """
    text = "jobs:\n" + _container_job(job="check-python", tag="python-v0.43.20")
    result = rewrite_pin_in_text(
        text=text,
        image_key=_IMAGE,
        current_tag="python-v0.43.2",
        release_tag="v0.44.0",
    )
    assert result is not None
    new_text, count = result
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
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
    assert "::error::failed to rewrite docker image tag" in capsys.readouterr().err


def test_main_returns_nonzero_with_migration_error_for_unrewritable_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` refuses an unprefixed pin with its OWN error, not the pin-absent one.

    The two failures need different operator actions — a missing pin means the
    autodiscovery record went stale, while an unprefixed pin means the pin must
    be MIGRATED to a layer-prefixed tag by hand — so the annotations must be
    distinguishable. The file is left byte-identical either way.
    """
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "workflow.toml"
    original = f'docker = "{_IMAGE}:sha-ea684ad"\n'
    _ = pin_file.write_text(original, encoding="utf-8")
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", _IMAGE)
    monkeypatch.setenv("PIN_CURRENT", "sha-ea684ad")
    monkeypatch.setenv("PIN_TAG", "v0.44.0")
    assert main() == 1
    assert pin_file.read_text(encoding="utf-8") == original
    err = capsys.readouterr().err
    assert err.startswith("::error::")
    # Names the offending tag and the required operator action.
    assert "sha-ea684ad" in err
    assert "no layer prefix" in err
    assert "migrate" in err.lower()
    # Distinct from the pin-absent annotation.
    assert "failed to rewrite docker image tag" not in err


def test_unrewritable_tag_error_names_the_layer_choice_by_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal names BOTH candidate roles and never offers the build-internal `base-` layer.

    The guidance IS the feature here: this guard exists to tell an operator what
    to do, and the choice it has to disambiguate is CI-job-container vs Fabro
    sandbox. Naming only one form — or presenting the layers as a flat menu —
    reproduces the mistake the guard exists to prevent, because the slim
    `python-` / `python-rust-` layers carry no ACP adapters and a sandbox pinned
    to one is broken in a way the tag itself does not reveal.

    `base-` is deliberately absent: it is build-internal, no consumer in the
    fleet pins it, and offering it can only invite a wrong choice.
    """
    monkeypatch.chdir(tmp_path)
    pin_file = tmp_path / "workflow.toml"
    _ = pin_file.write_text(f'docker = "{_IMAGE}:sha-ea684ad"\n', encoding="utf-8")
    monkeypatch.setenv("PIN_FILE", str(pin_file))
    monkeypatch.setenv("PIN_KEY", _IMAGE)
    monkeypatch.setenv("PIN_CURRENT", "sha-ea684ad")
    monkeypatch.setenv("PIN_TAG", "v0.44.0")
    assert main() == 1
    err = capsys.readouterr().err
    # Both slim CI-container forms, at the release tag being rewritten to.
    assert "python-v0.44.0" in err
    assert "python-rust-v0.44.0" in err
    # Both adapter-carrying sandbox forms.
    assert "python-agent-v0.44.0" in err
    assert "python-rust-agent-v0.44.0" in err
    # The roles are named, so the choice is decidable rather than a flat menu.
    assert "container" in err.lower()
    assert "sandbox" in err.lower()
    assert "adapter" in err.lower()
    # The build-internal layer is never offered.
    assert "base-" not in err
