"""The committed, ordered maintainer radar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

__all__: list[str] = ["RADAR", "RadarEntry", "validate_structure"]


@dataclass(frozen=True, kw_only=True, slots=True)
class RadarEntry:
    """One target the maintainer has placed on the ordered radar."""

    kind: Literal["plan", "item"]
    tenant: str
    id: str
    words: str
    said_at: date
    blocked_by: tuple[str, ...]


class _StructuralValidator:
    """Validate radar defects knowable from committed data alone."""

    def __call__(self, entries: tuple[RadarEntry, ...]) -> tuple[str, ...]:
        errors: list[str] = []
        indexes_by_target: dict[tuple[str, str], int] = {}
        for index, entry in enumerate(entries):
            target = (entry.tenant, entry.id)
            target_description = f"{entry.tenant}:{entry.id}"
            prior_index = indexes_by_target.get(target)
            if prior_index is None:
                indexes_by_target[target] = index
            else:
                duplicate_description = f"duplicate radar entry {target_description}"
                errors.append(f"{duplicate_description} at indexes {prior_index} and {index}")
            entry_description = f"radar entry {index} {target_description}"
            for reference in entry.blocked_by:
                if reference.count(":") != 1:
                    errors.append(
                        f"{entry_description} has malformed blocked_by reference {reference!r}"
                    )
                    continue
                tenant, identifier = reference.split(":")
                if not tenant or not identifier:
                    errors.append(
                        f"{entry_description} has malformed blocked_by reference {reference!r}"
                    )
        return tuple(errors)

    def ensure(self, *, entries: tuple[RadarEntry, ...]) -> None:
        """Reject committed entries carrying an offline structural defect."""
        if errors := self(entries):
            raise ValueError("\n".join(errors))


validate_structure: _StructuralValidator = _StructuralValidator()


RADAR: tuple[RadarEntry, ...] = (
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-w7ley3",
        words=(
            "radar-and-deterministic-admission: single ordered radar list + Honeycomb "
            "input contract + pure admission function + dispatcher cutover. NEW at #1 per "
            "the maintainer."
        ),
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-6vuiwe",
        words="VPS load: dev-host-test-gate-load",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-sv6m5p",
        words="VPS load: implement-test-performance",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-nmuyjc",
        words="Fleet capacity balancing: kubernetes-sandbox-backend",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-me5aqz",
        words="Fleet capacity balancing: gmktec-factory-placement",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-opbzv3",
        words="Fleet capacity balancing: factory-idle-with-ready-work",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-overseer",
        id="overseer-uzvcbn",
        words="herdr-overseer",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-b2jzxw",
        words="anthropic-burn-mitigation",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-vspttc",
        words="codex-implement-cost-per-run",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-qy5wol",
        words="sandbox-commit-gate-ceiling",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-qgwxo4",
        words="dev-host-disk-retention",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-s2aqob",
        words="kubernetes-observability",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-k6dqwc",
        words="dispatch-control-plane: maintainer-driven",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec",
        id="livespec-3rfjga",
        words="codex-plugin-hook-path-regression",
        said_at=date(2026, 11, 2),
        blocked_by=(),
    ),
)

validate_structure.ensure(entries=RADAR)
