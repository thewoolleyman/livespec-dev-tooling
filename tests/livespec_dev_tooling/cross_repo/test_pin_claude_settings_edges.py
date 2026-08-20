"""Edge coverage for the Claude settings pin walker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import structlog
from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo import _pin_claude_settings_format as claude_settings
from livespec_dev_tooling.cross_repo import pin_autodiscovery

__all__: list[str] = []


def _walk(*, root: Path, source_repo: str | None = None) -> list[dict[str, str]]:
    """The walk's records, failing loud if a pin file could not be READ."""
    return unsafe_perform_io(
        pin_autodiscovery.discover(root=root, source_repo=source_repo).unwrap()
    )


def _write_settings_text(*, root: Path, text: str) -> None:
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(text, encoding="utf-8")


def test_claude_settings_non_object_or_missing_marketplaces_yields_nothing(
    *, tmp_path: Path
) -> None:
    """Well-formed settings without a marketplace object is absence, not failure."""
    _write_settings_text(root=tmp_path, text="[]")
    assert _walk(root=tmp_path) == []

    _write_settings_text(root=tmp_path, text=json.dumps({"extraKnownMarketplaces": []}))
    assert _walk(root=tmp_path) == []


def test_claude_settings_skips_malformed_or_non_github_marketplace_entries(
    *, tmp_path: Path
) -> None:
    """Malformed entries and non-GitHub sources are not marketplace source-ref pins."""
    _write_settings_text(
        root=tmp_path,
        text=json.dumps(
            {
                "extraKnownMarketplaces": {
                    "not-an-object": "bad",
                    "missing-source": {},
                    "source-not-object": {"source": "bad"},
                    "not-github": {
                        "source": {
                            "source": "local",
                            "repo": "thewoolleyman/livespec",
                            "ref": "v0.7.3",
                        }
                    },
                    "missing-repo": {"source": {"source": "github", "ref": "v0.7.3"}},
                    "missing-ref": {
                        "source": {
                            "source": "github",
                            "repo": "thewoolleyman/livespec",
                        }
                    },
                    "non-tag-ref": {
                        "source": {
                            "source": "github",
                            "repo": "thewoolleyman/livespec",
                            "ref": "main",
                        }
                    },
                }
            }
        ),
    )

    assert _walk(root=tmp_path) == []


def test_claude_settings_read_failure_lands_on_failure_track(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A found-but-unreadable settings file is surfaced as can't-READ."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}", encoding="utf-8")
    failure = pin_autodiscovery.PinFileUnreadable(
        pin_walk="walk_claude_settings_extra_known_marketplaces",
        file_path=".claude/settings.json",
        detail="synthetic read failure",
    )

    def fail_read(*, path: Path, pin_walk: str) -> IOFailure[object, object]:
        _ = path
        _ = pin_walk
        return IOFailure(failure)

    monkeypatch.setattr(claude_settings, "read_pin_text", fail_read)

    walked = claude_settings.walk_claude_settings_extra_known_marketplaces(
        root=tmp_path,
        source_repo_filter=None,
        log=structlog.get_logger("test"),
    )

    assert isinstance(walked, IOFailure)
    assert unsafe_perform_io(walked.failure()) == failure
