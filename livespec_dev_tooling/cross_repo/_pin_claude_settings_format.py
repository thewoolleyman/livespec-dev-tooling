"""_pin_claude_settings_format — Claude settings marketplace pin walk.

Per `SPECIFICATION/contracts.md` section "Pin autodiscovery rules", the
`.claude/settings.json` `extraKnownMarketplaces` entries can pin a Claude
plugin marketplace source by its nested `source.ref` value. Only concrete
release-tag refs are pins. The literal `release` ref is a moving branch alias
and is deliberately skipped so a bump fan-out does not freeze an intentional
follow-the-latest posture into a concrete tag.

This format reads one well-known file but stays separate from
`_pin_single_file_formats`: that module already owns three root-file formats,
and the Claude settings shape has its own pin-vs-moving-alias discriminator.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.cross_repo._pin_directory_scan_formats import (  # noqa: E402
    PinFileUnparseable,
    PinWalkFailure,
    PinWalkResult,
    failed_read,
    read_pin_text,
    record,
)

__all__: list[str] = ["walk_claude_settings_extra_known_marketplaces"]


_CLAUDE_SETTINGS = ".claude/settings.json"
_PIN_FORMAT_CLAUDE_SETTINGS = "claude_settings_extra_known_marketplace_source_ref"
_PINNED_RELEASE_TAG_RE = re.compile(r"^v\d+(?:\.\d+)+[A-Za-z0-9_.+-]*$")


def _is_pinned_ref(*, ref: str) -> bool:
    """Return whether `ref` is a concrete pin rather than a moving alias."""
    return _PINNED_RELEASE_TAG_RE.fullmatch(ref) is not None


def _source_repo_from_github_repo(*, repo: str) -> str:
    """Return the source repo short name from an `owner/repo` GitHub path."""
    return repo.rstrip("/").rsplit("/", 1)[-1]


def _unparseable(
    *, pin_walk: str, file_path: str, detail: str, log: structlog.stdlib.BoundLogger
) -> PinWalkResult:
    """Log the unparseable file and put it on the walk's failure track."""
    log.warning("unparseable pin file", pin_walk=pin_walk, file_path=file_path, detail=detail)
    return IOFailure(PinFileUnparseable(pin_walk=pin_walk, file_path=file_path, detail=detail))


def _extra_known_marketplaces_from_settings(*, parsed: object) -> dict[str, object] | None:
    """Return the `extraKnownMarketplaces` object, or None when absent/malformed."""
    if not isinstance(parsed, dict):
        return None
    settings = cast("dict[str, object]", parsed)
    extra_known_marketplaces = settings.get("extraKnownMarketplaces")
    if not isinstance(extra_known_marketplaces, dict):
        return None
    return cast("dict[str, object]", extra_known_marketplaces)


def _record_for_marketplace(
    *, marketplace_name: str, entry: object, source_repo_filter: str | None
) -> dict[str, str] | None:
    """Return one pin record for a concrete marketplace source ref, or None."""
    if not isinstance(entry, dict):
        return None
    entry_dict = cast("dict[str, object]", entry)
    source = entry_dict.get("source")
    if not isinstance(source, dict):
        return None
    source_dict = cast("dict[str, object]", source)
    if source_dict.get("source") != "github":
        return None
    repo = source_dict.get("repo")
    ref = source_dict.get("ref")
    if not isinstance(repo, str) or not isinstance(ref, str) or not _is_pinned_ref(ref=ref):
        return None
    source_repo = _source_repo_from_github_repo(repo=repo)
    if source_repo_filter is not None and source_repo_filter != source_repo:
        return None
    return record(
        pin_format=_PIN_FORMAT_CLAUDE_SETTINGS,
        file_path=_CLAUDE_SETTINGS,
        pin_key=marketplace_name,
        current_value=ref,
        source_repo=source_repo,
    )


def walk_claude_settings_extra_known_marketplaces(
    *, root: Path, source_repo_filter: str | None, log: structlog.stdlib.BoundLogger
) -> IOResult[list[dict[str, str]], PinWalkFailure]:
    path = root / _CLAUDE_SETTINGS
    if not path.is_file():
        return IOSuccess([])
    read = read_pin_text(path=path, pin_walk="walk_claude_settings_extra_known_marketplaces")
    if isinstance(read, IOFailure):
        return failed_read(result=read)
    try:
        parsed = json.loads(unsafe_perform_io(read.unwrap()))
    except json.JSONDecodeError as undecodable:
        return _unparseable(
            pin_walk="walk_claude_settings_extra_known_marketplaces",
            file_path=_CLAUDE_SETTINGS,
            detail=str(undecodable),
            log=log,
        )
    marketplaces = _extra_known_marketplaces_from_settings(parsed=parsed)
    if marketplaces is None:
        return IOSuccess([])
    out: list[dict[str, str]] = []
    for marketplace_name, entry in marketplaces.items():
        discovered = _record_for_marketplace(
            marketplace_name=marketplace_name,
            entry=entry,
            source_repo_filter=source_repo_filter,
        )
        if discovered is not None:
            out.append(discovered)
    return IOSuccess(out)
