"""Shape tests for fail-closed Git authorship in the Fabro base image."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE = _REPO_ROOT / "docker" / "fabro-sandbox" / "base" / "Dockerfile"
_OPERATOR = "Chad Woolley <thewoolleyman@gmail.com>"


def test_base_image_has_no_fallback_author_and_disables_identity_inference() -> None:
    """The reusable image must fail closed until a workflow injects its author."""
    text = _DOCKERFILE.read_text(encoding="utf-8")

    assert "git config --system user.useConfigOnly true" in text
    assert "git config --system user.name" not in text
    assert "git config --system user.email" not in text
    assert "E2E Test" not in text
    assert "e2e-test@example.com" not in text


def test_image_build_exercises_missing_and_injected_author_paths() -> None:
    """The image build itself must prove both sides with real Git commits."""
    text = _DOCKERFILE.read_text(encoding="utf-8")

    assert 'git commit -m "identity-negative-control"' in text
    assert "Author identity unknown" in text
    assert 'git config --local user.name "Chad Woolley"' in text
    assert 'git config --local user.email "thewoolleyman@gmail.com"' in text
    assert "git var GIT_AUTHOR_IDENT" in text
    assert 'git log -1 --format="%an <%ae>"' in text
    assert _OPERATOR in text
