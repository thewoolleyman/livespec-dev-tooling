"""Every committed value trigger filters to rows that carry the column it aggregates.

Honeycomb evaluates MIN, MAX, AVG, SUM or a percentile over a group or a window
that holds no datapoints of the aggregated column as 0. A value trigger whose
threshold 0 crosses (`MIN(ok) < 1`, `AVG(hit_ratio) < 0.5`) therefore fires on
ABSENCE rather than on the value it watches: grouped, a group whose other
columns arrived without this one evaluates as 0; ungrouped, a window in which
the column did not arrive does the same. Measured on 2026-11-13 by
bootstrap-credentials-and-onboarding on hetzner-xubuntu's md RAID, tailnet and
Dolt-tunnel triggers, which emailed the maintainer false alerts. The fix is a
`<column> exists` filter (Rule G of the legacy-coordinator-agent sweep).

Count-based dead-men (COUNT, COUNT_DATAPOINTS, ...) are exempt on purpose.
Firing on silence is their whole job, and an exists filter would not change
what they count. Silence is theirs to report; a value trigger reports values.

A calculated field is checked through the columns its expression references,
so `MIN(DIV($a, $b)) < 0.25` needs `a exists` and `b exists`.
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


def _source_columns(*, query: dict[str, Any], column: str) -> list[str]:
    for field in query.get("calculated_fields") or []:
        if field.get("name") == column:
            return sorted(set(_FIELD_REFERENCE.findall(field.get("expression", ""))))
    return [column]


def zero_data_problems(*, definition: dict[str, Any]) -> list[str]:
    """Name each column a zero-crossing value trigger aggregates without an exists filter."""
    query = definition.get("query") or {}
    calculations = query.get("calculations") or []
    threshold = definition.get("threshold") or {}
    if not calculations or "op" not in threshold:
        return []
    calculation = calculations[0]
    column = calculation.get("column")
    if calculation.get("op") in _COUNT_OPS or not column:
        return []
    if not _zero_crosses(op=threshold["op"], value=float(threshold.get("value", 0))):
        return []
    filters = query.get("filters") or []
    combined_with_and = query.get("filter_combination", "AND") == "AND"
    return [
        source
        for source in _source_columns(query=query, column=column)
        if not (combined_with_and and {"column": source, "op": "exists"} in filters)
    ]


@pytest.mark.parametrize("definition", _DEFINITIONS, ids=lambda path: path.name)
def test_a_value_trigger_filters_to_rows_carrying_its_column(definition: Path) -> None:
    missing = zero_data_problems(definition=json.loads(definition.read_text(encoding="utf-8")))
    assert not missing, (
        f"{definition.name}: no `exists` filter on {missing}; a group or window with no datapoints "
        "of the column evaluates as 0 and crosses this threshold, so the trigger fires on absence"
    )


def _value_trigger(*, filters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "query": {
            "calculations": [{"op": "MIN", "column": "livespec.host.md.ok"}],
            "filters": filters,
            "breakdowns": ["md.device"],
        },
        "threshold": {"op": "<", "value": 1, "exceeded_limit": 1},
    }


def test_rejecting_control_a_min_trigger_without_exists_is_refused() -> None:
    assert zero_data_problems(definition=_value_trigger(filters=[])) == ["livespec.host.md.ok"]


def test_rejecting_control_an_or_combined_exists_filter_is_refused() -> None:
    definition = _value_trigger(filters=[{"column": "livespec.host.md.ok", "op": "exists"}])
    definition["query"]["filter_combination"] = "OR"
    assert zero_data_problems(definition=definition) == ["livespec.host.md.ok"]


def test_rejecting_control_a_calculated_field_needs_every_source_column() -> None:
    definition = {
        "query": {
            "calculated_fields": [
                {"name": "share", "expression": "DIV($mem.available, $mem.limit)"}
            ],
            "calculations": [{"op": "MIN", "column": "share"}],
            "filters": [{"column": "mem.available", "op": "exists"}],
        },
        "threshold": {"op": "<", "value": 0.25},
    }
    assert zero_data_problems(definition=definition) == ["mem.limit"]


def test_admitting_control_the_same_trigger_with_exists_passes() -> None:
    definition = _value_trigger(filters=[{"column": "livespec.host.md.ok", "op": "exists"}])
    assert zero_data_problems(definition=definition) == []


def test_admitting_control_a_count_dead_man_needs_no_exists() -> None:
    definition = _value_trigger(filters=[])
    definition["query"]["calculations"] = [
        {"op": "COUNT_DATAPOINTS", "column": "livespec.host.md.ok"}
    ]
    assert zero_data_problems(definition=definition) == []


def test_admitting_control_a_threshold_zero_cannot_cross_needs_no_exists() -> None:
    definition = _value_trigger(filters=[])
    definition["query"]["calculations"] = [{"op": "MAX", "column": "k8s.container.restarts"}]
    definition["threshold"] = {"op": ">", "value": 3}
    assert zero_data_problems(definition=definition) == []
