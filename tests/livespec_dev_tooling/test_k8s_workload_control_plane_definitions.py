"""The workload and control-plane board and triggers are committed, valid, and traceable."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

_OBSERVABILITY = Path(__file__).resolve().parents[2] / "ci-runner" / "observability"
_TRIGGERS = _OBSERVABILITY / "triggers"
_BOARD = _OBSERVABILITY / "boards" / "k8s-workload-control-plane.json"
_WORK_ITEM = "livespec-dev-tooling-t6om4l"
_FACTORY_NAMESPACES = ["factory", "factory-mi-homelab"]

_TRIGGER_FILES = (
    "k8s-factory-container-oom-crashloop",
    "k8s-factory-pod-pending",
    "k8s-factory-quota-near-hard",
    "k8s-api-server-readiness-failing",
    "k8s-datastore-etcd-check-failing",
    "k8s-datastore-filesystem-used",
    "k8s-datastore-request-latency-p99",
    "k8s-controller-zero-available",
    "k8s-arc-listener-not-ready",
    "k8s-cluster-state-silent",
    "k8s-control-plane-silent",
)

_BOARD_COLUMNS = (
    "k8s.pod.phase",
    "k8s.container.restarts",
    "k8s.container.status.last_terminated_reason",
    "k8s.container.status.reason",
    "k8s.persistentvolumeclaim.claims",
    "k8s.event.reason",
    "k8s.resource_quota.used",
    "k8s.resource_quota.hard_limit",
    "livespec.ci_k3s.readiness_check",
    "apiserver_storage_size_bytes",
    "livespec.ci_k3s.datastore_used_bytes",
    "etcd_request_duration_seconds",
    "k8s.deployment.available",
    "k8s.deployment.desired",
    "livespec.ci_pool.queue_pending",
    "livespec.ci_pool.queue_admitted",
    "livespec.ci_pool.queue_resource_usage",
    "livespec.ci_pool.queue_resource_quota",
)


def _dict(*, value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return {str(key): item for key, item in cast("dict[object, object]", value).items()}


def _list(*, value: object) -> list[object]:
    assert isinstance(value, list)
    return list(cast("list[object]", value))


def _load(*, path: Path) -> dict[str, object]:
    return _dict(value=json.loads(path.read_text(encoding="utf-8")))


def _triggers() -> dict[str, dict[str, object]]:
    return {name: _load(path=_TRIGGERS / f"{name}.json") for name in _TRIGGER_FILES}


def test_every_trigger_description_names_emitter_receiver_item_and_runbook() -> None:
    for name, definition in _triggers().items():
        description = str(definition["description"])
        assert "Emitter:" in description, name
        assert "Receiver:" in description, name
        assert _WORK_ITEM in description, name
        assert "Runbook:" in description, name


def test_no_k8s_metrics_trigger_uses_a_bare_count_calculation() -> None:
    for name, definition in _triggers().items():
        for calculation in _list(value=_dict(value=definition["query"])["calculations"]):
            entry = _dict(value=calculation)
            assert entry["op"] != "COUNT" or "column" in entry, name
    oom = _dict(value=_triggers()["k8s-factory-container-oom-crashloop"]["query"])
    assert oom["calculations"] == [
        {"op": "COUNT_DATAPOINTS", "column": "k8s.container.status.reason"},
    ]


def test_every_trigger_fits_honeycomb_limits_and_has_a_unique_name() -> None:
    definitions = _triggers()
    names = [str(definition["name"]) for definition in definitions.values()]
    assert len(set(names)) == len(names)
    for definition in definitions.values():
        assert len(str(definition["name"])) <= 120
        assert len(str(definition["description"])) <= 1023


def test_every_k8s_trigger_window_is_at_most_four_times_its_frequency() -> None:
    paths = sorted(_TRIGGERS.glob("k8s-*.json"))
    assert paths
    for path in paths:
        definition = _load(path=path)
        time_range = cast("int", _dict(value=definition["query"])["time_range"])
        frequency = cast("int", definition["frequency"])
        assert time_range <= 4 * frequency, path.name


def test_factory_triggers_are_scoped_to_the_two_factory_namespaces() -> None:
    for name in (
        "k8s-factory-container-oom-crashloop",
        "k8s-factory-pod-pending",
        "k8s-factory-quota-near-hard",
    ):
        query = _dict(value=_triggers()[name]["query"])
        filters = _list(value=query["filters"])
        assert {
            "column": "k8s.namespace.name",
            "op": "in",
            "value": _FACTORY_NAMESPACES,
        } in filters, name


def test_dead_man_triggers_are_ungrouped_and_use_a_twenty_minute_window() -> None:
    for name, column in (
        ("k8s-cluster-state-silent", "k8s.pod.phase"),
        ("k8s-control-plane-silent", "livespec.ci_k3s.readiness_check"),
    ):
        definition = _triggers()[name]
        query = _dict(value=definition["query"])
        assert "breakdowns" not in query, name
        assert query["time_range"] == 1200, name
        assert query["calculations"] == [{"op": "COUNT_DATAPOINTS", "column": column}], name
        assert definition["threshold"] == {"op": "<", "value": 1, "exceeded_limit": 1}, name


def test_thresholds_match_the_specification_windows() -> None:
    triggers = _triggers()

    def window(name: str) -> object:
        return _dict(value=triggers[name]["query"])["time_range"]

    def threshold(name: str) -> dict[str, object]:
        return _dict(value=triggers[name]["threshold"])

    assert window("k8s-factory-pod-pending") == 900
    assert threshold("k8s-factory-pod-pending")["value"] == 20
    assert window("k8s-factory-quota-near-hard") == 900
    assert threshold("k8s-factory-quota-near-hard") == {
        "op": ">=",
        "value": 0.9,
        "exceeded_limit": 1,
    }
    assert window("k8s-api-server-readiness-failing") == 180
    assert window("k8s-datastore-request-latency-p99") == 300
    assert threshold("k8s-datastore-filesystem-used")["value"] == 0.8
    assert window("k8s-controller-zero-available") == 300
    assert window("k8s-arc-listener-not-ready") == 300


def test_board_panels_are_unique_valid_and_cover_every_required_series() -> None:
    board = _load(path=_BOARD)
    assert board["type"] == "flexible"
    assert len(str(board["name"])) <= 255
    assert len(str(board["description"])) <= 1024
    panels = [_dict(value=panel) for panel in _list(value=board["panels"])]
    panels = [panel for panel in panels if panel["type"] == "query"]
    annotations = [_dict(value=panel["annotation"]) for panel in panels]
    names = [annotation["name"] for annotation in annotations]
    keys = [panel["key"] for panel in panels]
    assert len(set(map(str, names))) == len(names)
    assert len(set(map(str, keys))) == len(keys)
    for panel, annotation in zip(panels, annotations, strict=True):
        assert panel["query_style"] in ("graph", "table", "combo")
        assert len(str(annotation["name"])) <= 320
        assert len(str(annotation["description"])) <= 1023
    text = json.dumps(panels)
    for column in _BOARD_COLUMNS:
        assert column in text, column


def test_board_panels_do_not_overlap() -> None:
    board = _load(path=_BOARD)
    occupied: set[tuple[int, int]] = set()
    for item in _list(value=board["panels"]):
        panel = _dict(value=item)
        position = {key: int(str(value)) for key, value in _dict(value=panel["position"]).items()}
        cells = {
            (x, y)
            for x in range(position["x_coordinate"], position["x_coordinate"] + position["width"])
            for y in range(position["y_coordinate"], position["y_coordinate"] + position["height"])
        }
        assert not cells & occupied, panel.get("key")
        occupied |= cells
