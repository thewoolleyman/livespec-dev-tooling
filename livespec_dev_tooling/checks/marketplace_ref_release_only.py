"""marketplace_ref_release_only - pin shared livespec marketplaces to `release`.

The Claude plugin marketplace registry `~/.claude/plugins/known_marketplaces.json`
is HOST-GLOBAL: it holds exactly one `source` — including exactly one `ref` — per
marketplace NAME, shared by every checkout on the host. There is no per-checkout
marketplace ref. So when one repo's committed `.claude/settings.json` pins a
shared `thewoolleyman/livespec*` marketplace to a version tag, that repo's
SessionStart `ensure-plugins` rewrites the shared slot, and every OTHER repo
still declaring `release` then fails `ensure-plugins` with "network source
differs". The consequence is silent — the plugins stay enabled-but-not-installed
and skills simply stop resolving, with no error anywhere — which is how a
transient orchestrator pin to a tag took `plan`-skill loading down across the
release cohort on 2026-09-08.

This check reads the consumer's committed `.claude/settings.json` and fails any
livespec-family marketplace whose `ref` is not `release`, making such a pin a
merge-blocking, deliberate edit rather than an accident. Marketplaces outside the
family (for example `anthropics/*`) own their own registry slots and are exempt.
A checkout with no `.claude/settings.json` is outside this check's role and
passes; settings that cannot be read or parsed FAIL CLOSED, because a guard that
cannot see the pin cannot certify it. Diagnostics flow through structlog JSON to
stderr.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  - vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_CHECK_ID = "marketplace_ref_release_only"
_SETTINGS_RELPATH = (".claude", "settings.json")
_MARKETPLACES_KEY = "extraKnownMarketplaces"
_FAMILY_REPO_PREFIX = "thewoolleyman/livespec"
_REQUIRED_REF = "release"
_FAIL_EXIT = 1
_HINT = (
    "the plugin marketplace registry ~/.claude/plugins/known_marketplaces.json is "
    "host-global and holds one ref per marketplace name, so pinning a shared "
    "livespec marketplace to a tag rewrites the slot every other checkout on the "
    "host shares and breaks their ensure-plugins with 'network source differs'; "
    "declare ref 'release' and pin plugin versions through the release branch"
)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def _read_settings(*, path: Path) -> dict[str, object] | None:
    """Parse the settings document, or None when it is unreadable or not an object."""
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)


def _entry_offender(*, name: str, entry: object) -> tuple[str, str, object] | None:
    """Return `(name, repo, ref)` when this marketplace pins a family repo off `release`.

    Only a github-style object `source` carrying a family `repo` can rewrite a
    shared registry slot; every other shape (a relative-path source string, an
    entry that is not an object, a source without a string `repo`, a non-family
    repo) owns no shared livespec slot and is not this check's business.
    """
    if not isinstance(entry, dict):
        return None
    source_obj = cast("dict[str, object]", entry).get("source")
    if not isinstance(source_obj, dict):
        return None
    source = cast("dict[str, object]", source_obj)
    repo = source.get("repo")
    if not isinstance(repo, str) or not repo.startswith(_FAMILY_REPO_PREFIX):
        return None
    ref = source.get("ref")
    if ref == _REQUIRED_REF:
        return None
    return (name, repo, ref)


def _offenders(*, settings: dict[str, object]) -> tuple[tuple[str, str, object], ...]:
    marketplaces_obj = settings.get(_MARKETPLACES_KEY, {})
    if not isinstance(marketplaces_obj, dict):
        return ()
    marketplaces = cast("dict[str, object]", marketplaces_obj)
    return tuple(
        offender
        for offender in (
            _entry_offender(name=name, entry=entry) for name, entry in sorted(marketplaces.items())
        )
        if offender is not None
    )


def main() -> int:
    log = _configure_logger()
    path = Path.cwd().joinpath(*_SETTINGS_RELPATH)
    if not path.is_file():
        log.info(
            "marketplace ref release only: skipped",
            check_id=_CHECK_ID,
            reason="no .claude/settings.json in this checkout",
        )
        return 0

    settings = _read_settings(path=path)
    if settings is None:
        log.error(
            "settings.json is unreadable, so the marketplace refs cannot be certified",
            check_id=_CHECK_ID,
            status="fail",
            path="/".join(_SETTINGS_RELPATH),
            line=0,
            hint="repair the JSON document; this guard fails closed rather than assuming a pin",
        )
        return _FAIL_EXIT

    offenders = _offenders(settings=settings)
    for name, repo, ref in offenders:
        log.error(
            "livespec-family marketplace must declare ref 'release'",
            check_id=_CHECK_ID,
            status="fail",
            path="/".join(_SETTINGS_RELPATH),
            line=0,
            marketplace=name,
            repo=repo,
            ref=ref,
            hint=_HINT,
        )
    if offenders:
        return _FAIL_EXIT

    log.info(
        "marketplace ref release only: pass",
        check_id=_CHECK_ID,
        reason="every livespec-family marketplace declares ref 'release'",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
