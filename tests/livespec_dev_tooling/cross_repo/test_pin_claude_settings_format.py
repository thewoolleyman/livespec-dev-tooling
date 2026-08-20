"""Tests for the `.claude/settings.json` extra-known-marketplace pin format."""

from __future__ import annotations

import json
from pathlib import Path

from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo import pin_autodiscovery

__all__: list[str] = []


def _walk(*, root: Path, source_repo: str | None = None) -> list[dict[str, str]]:
    """The walk's records, failing loud if a pin file could not be READ."""
    return unsafe_perform_io(
        pin_autodiscovery.discover(root=root, source_repo=source_repo).unwrap()
    )


def _write_claude_settings(*, root: Path, extra_known_marketplaces: object) -> None:
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"extraKnownMarketplaces": extra_known_marketplaces}, indent=2),
        encoding="utf-8",
    )


def test_discover_claude_settings_extra_known_marketplace_pin_emits_record(
    *, tmp_path: Path
) -> None:
    """A concrete marketplace source ref emits one normalized pin record."""
    _write_claude_settings(
        root=tmp_path,
        extra_known_marketplaces={
            "livespec": {
                "source": {
                    "source": "github",
                    "repo": "thewoolleyman/livespec",
                    "ref": "v0.7.3",
                }
            }
        },
    )

    result = _walk(root=tmp_path, source_repo=None)

    assert result == [
        {
            "pin_format": "claude_settings_extra_known_marketplace_source_ref",
            "file_path": ".claude/settings.json",
            "pin_key": "livespec",
            "current_value": "v0.7.3",
            "source_repo": "livespec",
        }
    ]


def test_discover_claude_settings_absent_file_yields_nothing(*, tmp_path: Path) -> None:
    """A repo without `.claude/settings.json` yields no records for this format."""
    assert _walk(root=tmp_path, source_repo=None) == []


def test_discover_claude_settings_without_marketplace_pins_yields_nothing(
    *, tmp_path: Path
) -> None:
    """A settings file without pinned marketplace source refs yields no records."""
    _write_claude_settings(root=tmp_path, extra_known_marketplaces={})

    assert _walk(root=tmp_path, source_repo=None) == []


def test_discover_claude_settings_release_ref_is_moving_alias_not_pin(*, tmp_path: Path) -> None:
    """The literal `release` branch alias is not a pin and must not be bumped."""
    _write_claude_settings(
        root=tmp_path,
        extra_known_marketplaces={
            "livespec": {
                "source": {
                    "source": "github",
                    "repo": "thewoolleyman/livespec",
                    "ref": "release",
                }
            }
        },
    )

    assert _walk(root=tmp_path, source_repo=None) == []


def test_discover_claude_settings_source_repo_filter(*, tmp_path: Path) -> None:
    """The source-repo filter matches the GitHub repo short name."""
    _write_claude_settings(
        root=tmp_path,
        extra_known_marketplaces={
            "livespec": {
                "source": {
                    "source": "github",
                    "repo": "thewoolleyman/livespec",
                    "ref": "v0.7.3",
                }
            },
            "livespec-driver-claude": {
                "source": {
                    "source": "github",
                    "repo": "thewoolleyman/livespec-driver-claude",
                    "ref": "v0.2.1",
                }
            },
        },
    )

    result = _walk(root=tmp_path, source_repo="livespec-driver-claude")

    assert result == [
        {
            "pin_format": "claude_settings_extra_known_marketplace_source_ref",
            "file_path": ".claude/settings.json",
            "pin_key": "livespec-driver-claude",
            "current_value": "v0.2.1",
            "source_repo": "livespec-driver-claude",
        }
    ]


def test_discover_claude_settings_unparseable_fails_the_walk(*, tmp_path: Path) -> None:
    """Invalid `.claude/settings.json` lands on the can't-PARSE failure track."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not-json", encoding="utf-8")

    walked = pin_autodiscovery.discover(root=tmp_path, source_repo=None)

    assert isinstance(walked, IOFailure)
    failure = unsafe_perform_io(walked.failure())
    assert isinstance(failure, pin_autodiscovery.PinFileUnparseable)
    assert failure.file_path == ".claude/settings.json"
    assert failure.pin_walk == "walk_claude_settings_extra_known_marketplaces"
