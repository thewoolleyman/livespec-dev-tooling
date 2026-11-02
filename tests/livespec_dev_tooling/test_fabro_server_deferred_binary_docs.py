"""The Fabro host-variable guide documents safe deferred binary promotion."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_DOC = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "fabro_server" / "HOST_VARS.md"
_BINARY_SECTION = "### How the binary install actually behaves"


def _section(*, heading: str) -> str:
    """Return a document section, including its heading and excluding the next one."""
    text = _DOC.read_text(encoding="utf-8")
    start = text.find(f"{heading}\n")
    assert start >= 0, f"{_DOC} must retain the `{heading}` operator guide"
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_the_binary_guide_explains_why_deferred_promotion_preserves_binary_path() -> None:
    """Operators learn that the server's executable path is also its worker-launch path."""
    section = _section(heading=_BINARY_SECTION)

    assert "spawns each run's worker from its own executable path" in section, (
        "the binary-install guide must explain that a running Fabro server launches "
        "workers from its own executable path"
    )
    assert "`binary_path` is never replaced while its server will not restart" in section, (
        "the deferred-restart guide must say that binary_path stays linked until the run "
        "that restarts the server promotes the staged candidate"
    )
