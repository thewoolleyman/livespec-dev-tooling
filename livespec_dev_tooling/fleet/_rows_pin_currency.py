"""Pin-currency obligation rows for fleet members.

These rows evaluate freshness for pin formats whose PRESENCE is either
checked elsewhere or intentionally optional by member shape. The inventory
comes from `cross_repo.pin_autodiscovery`, so the central fleet sweep and
the release fan-out keep one shared understanding of supported pin
formats.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from livespec_dev_tooling.cross_repo.pin_autodiscovery import discover
from livespec_dev_tooling.cross_repo.pin_staleness import denotes_same_release
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
)

__all__: list[str] = [
    "assert_fabro_sandbox_image_pin_currency",
    "assert_github_workflow_uses_pin_currency",
    "assert_livespec_compat_pin_currency",
]


PinFormat = Literal[
    "fabro_sandbox_docker_image",
    "github_workflow_uses_ref",
    "livespec_jsonc_compat_pinned",
]


@dataclass(frozen=True, kw_only=True)
class PinCurrencySpec:
    """One supported fleet pin format plus the files autodiscovery reads."""

    pin_format: PinFormat
    candidate_paths: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class PinRecord:
    """Normalized pin record from autodiscovery, narrowed for currency checks."""

    pin_format: str
    file_path: str
    pin_key: str
    current_value: str
    source_repo: str


@dataclass(frozen=True, kw_only=True)
class StalePin:
    """One pin whose current value does not denote the latest release."""

    record: PinRecord
    latest: str


_LIVESPEC_COMPAT_SPEC = PinCurrencySpec(
    pin_format="livespec_jsonc_compat_pinned",
    candidate_paths=(".livespec.jsonc",),
)
_GITHUB_WORKFLOW_USES_SPEC = PinCurrencySpec(
    pin_format="github_workflow_uses_ref",
    candidate_paths=(),
)
_FABRO_SANDBOX_IMAGE_SPEC = PinCurrencySpec(
    pin_format="fabro_sandbox_docker_image",
    candidate_paths=(),
)


_FABRO_WORKFLOW_PREFIXES: tuple[str, ...] = (
    ".claude-plugin/.fabro/workflows/",
    ".fabro/workflows/",
)
_WORKFLOW_PREFIX = ".github/workflows/"
_WORKFLOW_SUFFIXES = (".yml", ".yaml")


def _workflow_path(*, path: str) -> bool:
    return path.startswith(_WORKFLOW_PREFIX) and path.endswith(_WORKFLOW_SUFFIXES)


def _fabro_workflow_path(*, path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _FABRO_WORKFLOW_PREFIXES) and path.endswith(
        "/workflow.toml"
    )


def _candidate_paths_for(*, tree_paths: Iterable[str], spec: PinCurrencySpec) -> tuple[str, ...]:
    if spec.candidate_paths:
        return spec.candidate_paths
    if spec.pin_format == "github_workflow_uses_ref":
        return tuple(sorted(path for path in tree_paths if _workflow_path(path=path)))
    return tuple(
        sorted(
            path
            for path in tree_paths
            if _workflow_path(path=path) or _fabro_workflow_path(path=path)
        )
    )


def _materialize_files(
    *, ctx: FleetContext, member: FleetMember, root: Path, candidate_paths: tuple[str, ...]
) -> None:
    for rel_path in candidate_paths:
        text = ctx.file_text(repo=member.repo, path=rel_path)
        if text is not None:
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = path.write_text(text, encoding="utf-8")


def _record_from_raw(*, raw: dict[str, str]) -> PinRecord:
    return PinRecord(
        pin_format=raw["pin_format"],
        file_path=raw["file_path"],
        pin_key=raw["pin_key"],
        current_value=raw["current_value"],
        source_repo=raw["source_repo"],
    )


def _latest_release_tag(*, ctx: FleetContext, source_repo: str) -> str | None:
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{source_repo}/releases/latest")
    if not isinstance(payload, dict):
        return None
    tag = cast("dict[str, object]", payload).get("tag_name")
    return tag if isinstance(tag, str) else None


def _stale_pins(
    *, ctx: FleetContext, records: tuple[PinRecord, ...]
) -> tuple[StalePin, ...] | None:
    stale: list[StalePin] = []
    latest_cache: dict[str, str | None] = {}
    for record in records:
        if record.source_repo not in latest_cache:
            latest_cache[record.source_repo] = _latest_release_tag(
                ctx=ctx, source_repo=record.source_repo
            )
        latest = latest_cache[record.source_repo]
        if latest is None:
            return None
        if not denotes_same_release(pinned_tag=record.current_value, release_tag=latest):
            stale.append(StalePin(record=record, latest=latest))
    return tuple(stale)


def _stale_pin_summary(*, pin: StalePin) -> str:
    return " ".join(
        (
            pin.record.file_path,
            pin.record.pin_key,
            "current",
            pin.record.current_value,
            "latest release",
            pin.latest,
        )
    )


def _finding_message(
    *, member: FleetMember, spec: PinCurrencySpec, stale: tuple[StalePin, ...]
) -> str:
    findings = "; ".join(_stale_pin_summary(pin=pin) for pin in stale)
    return f"{member.repo}: {spec.pin_format} pin stale: {findings}"


def _records_for(
    *, ctx: FleetContext, member: FleetMember, spec: PinCurrencySpec
) -> tuple[PinRecord, ...]:
    candidate_paths = _candidate_paths_for(tree_paths=ctx.tree(repo=member.repo).paths, spec=spec)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _materialize_files(ctx=ctx, member=member, root=root, candidate_paths=candidate_paths)
        return tuple(
            _record_from_raw(raw=raw)
            for raw in discover(root=root, source_repo=None)
            if raw["pin_format"] == spec.pin_format
        )


def _pin_currency_outcome(
    *, ctx: FleetContext, member: FleetMember, spec: PinCurrencySpec
) -> RowOutcome:
    records = _records_for(ctx=ctx, member=member, spec=spec)
    stale = _stale_pins(ctx=ctx, records=records)
    if stale is None:
        return RowPass(note="pin records present; freshness unverified (latest release unreadable)")
    return (
        RowFinding(
            message=_finding_message(member=member, spec=spec, stale=stale),
            severity="warning",
        )
        if stale
        else RowPass()
    )


def assert_livespec_compat_pin_currency(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """`.livespec.jsonc` `compat.pinned` records are current; stale records warn."""
    return _pin_currency_outcome(ctx=ctx, member=member, spec=_LIVESPEC_COMPAT_SPEC)


def assert_github_workflow_uses_pin_currency(
    *, ctx: FleetContext, member: FleetMember
) -> RowOutcome:
    """GitHub Actions `uses: owner/repo/path@ref` records are current; stale records warn."""
    return _pin_currency_outcome(ctx=ctx, member=member, spec=_GITHUB_WORKFLOW_USES_SPEC)


def assert_fabro_sandbox_image_pin_currency(
    *, ctx: FleetContext, member: FleetMember
) -> RowOutcome:
    """Fabro sandbox image tags are current; stale records warn."""
    return _pin_currency_outcome(ctx=ctx, member=member, spec=_FABRO_SANDBOX_IMAGE_SPEC)
