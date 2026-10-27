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


def test_base_image_pins_terminal_size_env_for_the_zero_by_zero_hook_pty() -> None:
    """COLUMNS/LINES must be ENV so Python 3.10 never sees a 0-column terminal."""
    text = _DOCKERFILE.read_text(encoding="utf-8")
    env_values: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("ENV "):
            for pair in line.removeprefix("ENV ").split():
                key, _, value = pair.partition("=")
                env_values[key] = value

    assert int(env_values["COLUMNS"]) >= 80
    assert int(env_values["LINES"]) > 0


def test_python_layer_probes_terminal_width_under_a_zero_by_zero_pty() -> None:
    """The python layer build must prove the pinned CPython sees a usable width."""
    text = (_DOCKERFILE.parents[1] / "python" / "Dockerfile").read_text(encoding="utf-8")

    assert "stty cols 0 rows 0" in text
    assert "shutil.get_terminal_size().columns" in text
    assert "uv python find ${PYTHON_VERSION}" in text
