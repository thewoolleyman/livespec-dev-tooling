"""No committed value trigger fires on silence: it fires only on positive evidence of a fault.

Honeycomb reads an aggregate (MIN, MAX, AVG, SUM, a percentile) over no
datapoints as 0, and a trigger whose threshold 0 crosses therefore fires on
ABSENCE rather than on the value it watches. Measured on 2026-11-13:

- Partial silence. A group or window whose other columns arrived without the
  aggregated one reads 0 (bootstrap-credentials-and-onboarding, on
  hetzner-xubuntu's md RAID, tailnet and Dolt-tunnel triggers, which emailed the
  maintainer false alerts). A `<column> exists` filter fixes this case.
- Total silence. With the collector stopped and NO rows at all, `MIN(ok) < 1`
  still fired, exists filter or not (legacy-coordinator-agent, 20:44Z). A probe
  pair proved the remedy (record on livespec-dev-tooling-s2aqob): over an empty
  host `MIN(ok) < 1` fired while `MAX(SUB(1, $ok)) > 0` stayed quiet; one
  synthetic ok=0 point fired the second, and it resolved once the point aged out.

So the rule this module holds every definition to (Rule G) is:

1. A non-count value trigger's threshold must not be crossed by 0. A "below v"
   check is written as a positive shortfall: MIN(x) < v becomes
   MAX(SUB(v, $x)) > 0, AVG(x) < v becomes AVG(SUB(v, $x)) > 0, and MAX(x) < v
   becomes MIN(SUB(v, $x)) > 0. It is the same condition on real data, and an
   empty result reads 0, which never crosses > 0.
2. Such a shortfall keeps a `<column> exists` filter on every source column its
   calculated field reads, for partial silence (filters combined with AND).

Count-based dead-men (COUNT, COUNT_DATAPOINTS, ...) are exempt on purpose: firing
on silence is their whole job, and they stay the one page a collector gap
produces.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

_TRIGGERS = Path(__file__).resolve().parents[2] / "ci-runner" / "observability" / "triggers"
_DEFINITIONS = sorted(_TRIGGERS.glob("*.json"))
_COUNT_OPS = frozenset(
    {"COUNT", "COUNT_DATAPOINTS", "COUNT_DISTINCT", "CONCURRENCY", "HISTOGRAM_COUNT"}
)
_FIELD_REFERENCE = re.compile(r"\$([A-Za-z0-9_.]+)")


def _zero_crosses(*, op: str, value: float) -> bool:
    return {
        "<": value > 0,
        "<=": value >= 0,
        ">": value < 0,
        ">=": value <= 0,
        "=": value == 0,
        "!=": value != 0,
    }.get(op, False)


def _value_calculation(*, definition: dict[str, Any]) -> dict[str, Any] | None:
    calculations = (definition.get("query") or {}).get("calculations") or []
    if not calculations or "op" not in (definition.get("threshold") or {}):
        return None
    calculation = calculations[0]
    if calculation.get("op") in _COUNT_OPS or not calculation.get("column"):
        return None
    return calculation


def fires_on_an_empty_result(*, definition: dict[str, Any]) -> bool:
    """Whether a value trigger's threshold is crossed by the 0 an empty result reads as."""
    if _value_calculation(definition=definition) is None:
        return False
    threshold = definition["threshold"]
    return _zero_crosses(op=threshold["op"], value=float(threshold.get("value", 0)))


def shortfall_sources_without_exists(*, definition: dict[str, Any]) -> list[str]:
    """Name each source column a SUB(v, ...) shortfall reads without an AND-combined exists filter."""
    calculation = _value_calculation(definition=definition)
    if calculation is None:
        return []
    query = definition["query"]
    expressions = {
        f.get("name"): f.get("expression", "") for f in query.get("calculated_fields") or []
    }
    expression = expressions.get(calculation["column"], "")
    if not expression.replace(" ", "").startswith("SUB("):
        return []
    filters = query.get("filters") or []
    combined_with_and = query.get("filter_combination", "AND") == "AND"
    return [
        source
        for source in sorted(set(_FIELD_REFERENCE.findall(expression)))
        if not (combined_with_and and {"column": source, "op": "exists"} in filters)
    ]


@pytest.mark.parametrize("definition", _DEFINITIONS, ids=lambda path: path.name)
def test_a_value_trigger_does_not_fire_on_an_empty_result(definition: Path) -> None:
    loaded = json.loads(definition.read_text(encoding="utf-8"))
    assert not fires_on_an_empty_result(definition=loaded), (
        f"{definition.name}: threshold {loaded['threshold']} is crossed by 0, which is what an "
        "empty result reads as, so the trigger fires on silence; write it as a positive "
        "shortfall, AGG'(SUB(v, $x)) > 0"
    )


@pytest.mark.parametrize("definition", _DEFINITIONS, ids=lambda path: path.name)
def test_a_shortfall_trigger_filters_to_rows_carrying_its_source_columns(definition: Path) -> None:
    missing = shortfall_sources_without_exists(
        definition=json.loads(definition.read_text(encoding="utf-8"))
    )
    assert not missing, f"{definition.name}: no AND-combined `exists` filter on {missing}"


def _health_check(*, op: str, value: float) -> dict[str, Any]:
    return {
        "query": {
            "calculations": [{"op": "MIN", "column": "livespec.host.md.ok"}],
            "filters": [{"column": "livespec.host.md.ok", "op": "exists"}],
            "breakdowns": ["md.device"],
        },
        "threshold": {"op": op, "value": value, "exceeded_limit": 1},
    }


def _shortfall(*, filters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "query": {
            "calculated_fields": [
                {"name": "unrelated", "expression": "$other.column"},
                {
                    "name": "share_deficit",
                    "expression": "SUB(0.25, DIV($mem.available, $mem.limit))",
                },
            ],
            "calculations": [{"op": "MAX", "column": "share_deficit"}],
            "filters": filters,
        },
        "threshold": {"op": ">", "value": 0},
    }


@pytest.mark.parametrize(("op", "value"), [("<", 1), ("<=", 0), (">", -1), (">=", 0), (">=", -2)])
def test_rejecting_control_a_threshold_zero_crosses_fires_on_an_empty_result(
    op: str, value: float
) -> None:
    assert fires_on_an_empty_result(definition=_health_check(op=op, value=value))


def test_rejecting_control_a_shortfall_missing_one_source_exists_is_refused() -> None:
    definition = _shortfall(filters=[{"column": "mem.available", "op": "exists"}])
    assert shortfall_sources_without_exists(definition=definition) == ["mem.limit"]


def test_rejecting_control_an_or_combined_exists_filter_is_refused() -> None:
    definition = _shortfall(
        filters=[
            {"column": "mem.available", "op": "exists"},
            {"column": "mem.limit", "op": "exists"},
        ]
    )
    definition["query"]["filter_combination"] = "OR"
    assert shortfall_sources_without_exists(definition=definition) == ["mem.available", "mem.limit"]


def test_admitting_control_the_proven_shortfall_shape_passes_both_rules() -> None:
    definition = _shortfall(
        filters=[
            {"column": "mem.available", "op": "exists"},
            {"column": "mem.limit", "op": "exists"},
        ]
    )
    assert not fires_on_an_empty_result(definition=definition)
    assert shortfall_sources_without_exists(definition=definition) == []


def test_admitting_control_a_count_dead_man_may_fire_on_silence() -> None:
    definition = _health_check(op="<", value=1)
    definition["query"]["calculations"] = [
        {"op": "COUNT_DATAPOINTS", "column": "livespec.host.md.ok"}
    ]
    assert not fires_on_an_empty_result(definition=definition)
    assert shortfall_sources_without_exists(definition=definition) == []


def test_admitting_control_a_raw_positive_threshold_needs_no_exists() -> None:
    definition = _health_check(op=">", value=3)
    definition["query"]["filters"] = []
    assert not fires_on_an_empty_result(definition=definition)
    assert shortfall_sources_without_exists(definition=definition) == []


def test_admitting_control_a_definition_with_no_threshold_is_not_judged() -> None:
    definition = _health_check(op="<", value=1)
    del definition["threshold"]
    assert not fires_on_an_empty_result(definition=definition)
    assert shortfall_sources_without_exists(definition=definition) == []
