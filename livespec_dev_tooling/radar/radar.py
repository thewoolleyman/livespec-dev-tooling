"""The committed, ordered maintainer radar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

__all__: list[str] = ["RADAR", "RadarEntry"]


@dataclass(frozen=True, kw_only=True, slots=True)
class RadarEntry:
    """One target the maintainer has placed on the ordered radar."""

    kind: Literal["plan", "item"]
    tenant: str
    id: str
    words: str
    said_at: date
    blocked_by: tuple[str, ...] = ()


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
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-6vuiwe",
        words="VPS load: dev-host-test-gate-load",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-sv6m5p",
        words="VPS load: implement-test-performance",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-nmuyjc",
        words="Fleet capacity balancing: kubernetes-sandbox-backend",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-me5aqz",
        words="Fleet capacity balancing: gmktec-factory-placement",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-opbzv3",
        words="Fleet capacity balancing: factory-idle-with-ready-work",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-overseer",
        id="overseer-uzvcbn",
        words="herdr-overseer",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-b2jzxw",
        words="anthropic-burn-mitigation",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-vspttc",
        words="codex-implement-cost-per-run",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-qy5wol",
        words="sandbox-commit-gate-ceiling",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-qgwxo4",
        words="dev-host-disk-retention",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-dev-tooling",
        id="livespec-dev-tooling-s2aqob",
        words="kubernetes-observability",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec-orch-beads-fabro",
        id="bd-ib-k6dqwc",
        words="dispatch-control-plane: maintainer-driven",
        said_at=date(2026, 11, 2),
    ),
    RadarEntry(
        kind="plan",
        tenant="livespec",
        id="livespec-3rfjga",
        words="codex-plugin-hook-path-regression",
        said_at=date(2026, 11, 2),
    ),
)
