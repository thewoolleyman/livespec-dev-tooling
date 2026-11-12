"""Consumer-tier coverage for compilation-cache warm-set lag scenarios."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_GAUGES = _ROOT / "ci-runner" / "observability" / "ci-cache-gauges.sh"
_HELPER = _ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "sccache-warm-lag.py"


def _transition_module() -> object:
    """Load the populator's pure transition helper as its consumer does."""
    assert _HELPER.is_file(), (
        "the populator must ship a pure per-repository warm-set lag transition helper; "
        "without it, busy skips can only be counted as fleet totals"
    )
    spec = importlib.util.spec_from_file_location("sccache_warm_lag", _HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_busy_skips_start_and_accumulate_per_repository_lag() -> None:
    """Two busy skips preserve the cache record and age one repository's warm set."""
    module = _transition_module()
    previous = {
        "consecutive_skipped_busy": 1,
        "last_built_commit": "old",
        "last_built_toolchain": "1.80.0",
        "lag_started_at_epoch": 100,
    }

    updated = module.transition(
        previous=previous,
        outcome="busy",
        run_started_at_epoch=200,
        default_branch_commit="new",
        checkout_toolchain="1.81.0",
        cache_record_commit="old",
        cache_record_toolchain="1.80.0",
    )

    assert updated == {
        "consecutive_skipped_busy": 2,
        "last_built_commit": "old",
        "last_built_toolchain": "1.80.0",
        "lag_started_at_epoch": 100,
    }


def test_current_or_recorded_build_clears_lag_and_a_failed_build_does_not() -> None:
    """A successful/current warm set clears; every read-but-non-busy failure breaks the streak."""
    module = _transition_module()
    previous = {
        "consecutive_skipped_busy": 3,
        "last_built_commit": "old",
        "last_built_toolchain": "1.80.0",
        "lag_started_at_epoch": 100,
    }
    for outcome in ("current", "built"):
        assert module.transition(
            previous=previous,
            outcome=outcome,
            run_started_at_epoch=200,
            default_branch_commit="new",
            checkout_toolchain="1.81.0",
            cache_record_commit="new",
            cache_record_toolchain="1.81.0",
        ) == {
            "consecutive_skipped_busy": 0,
            "last_built_commit": "new",
            "last_built_toolchain": "1.81.0",
            "lag_started_at_epoch": None,
        }
    assert module.transition(
        previous=previous,
        outcome="failed",
        run_started_at_epoch=200,
        default_branch_commit="new",
        checkout_toolchain="1.81.0",
        cache_record_commit="old",
        cache_record_toolchain="1.80.0",
    ) == {**previous, "consecutive_skipped_busy": 0}


def test_unreadable_and_unvisited_cache_records_follow_the_required_preservation_rules() -> None:
    """An unreadable record keeps old fields; a pre-record stop keeps the whole prior state."""
    module = _transition_module()
    previous = {
        "consecutive_skipped_busy": 2,
        "last_built_commit": "old",
        "last_built_toolchain": "1.80.0",
        "lag_started_at_epoch": 100,
    }
    assert module.transition(
        previous=previous,
        outcome="unreadable",
        run_started_at_epoch=200,
        default_branch_commit="new",
        checkout_toolchain="1.81.0",
        cache_record_commit=None,
        cache_record_toolchain=None,
    ) == {**previous, "consecutive_skipped_busy": 0}
    assert (
        module.transition(
            previous=previous,
            outcome="unvisited",
            run_started_at_epoch=200,
            default_branch_commit="new",
            checkout_toolchain="1.81.0",
            cache_record_commit=None,
            cache_record_toolchain=None,
        )
        == previous
    )


def test_failed_build_after_a_stale_or_missing_record_starts_the_lag() -> None:
    """A failed build that read a stale/missing record starts the lag once, and never restarts it."""
    module = _transition_module()
    fresh = {
        "consecutive_skipped_busy": 0,
        "last_built_commit": None,
        "last_built_toolchain": None,
        "lag_started_at_epoch": None,
    }
    for cache_record in (("old", "1.81.0"), ("new", "1.80.0"), (None, None)):
        started = module.transition(
            previous=fresh,
            outcome="failed",
            run_started_at_epoch=200,
            default_branch_commit="new",
            checkout_toolchain="1.81.0",
            cache_record_commit=cache_record[0],
            cache_record_toolchain=cache_record[1],
        )
        assert started == {
            "consecutive_skipped_busy": 0,
            "last_built_commit": cache_record[0],
            "last_built_toolchain": cache_record[1],
            "lag_started_at_epoch": 200,
        }
        assert (
            module.transition(
                previous=started,
                outcome="failed",
                run_started_at_epoch=300,
                default_branch_commit="new",
                checkout_toolchain="1.81.0",
                cache_record_commit=cache_record[0],
                cache_record_toolchain=cache_record[1],
            )["lag_started_at_epoch"]
            == 200
        )


def _trigger_met_by_repository(*, tmp_path: Path, schedule: str) -> dict[str, int] | None:
    """Run the host emitter against a fake collector and read its trigger-met datapoints."""
    now = int(time.time())
    warm_root = tmp_path / "warm"
    warm_root.mkdir(parents=True)
    sets = {
        "streak-two-long-lag": {"consecutive_skipped_busy": 2, "lag_started_at_epoch": now - 5000},
        "streak-one-long-lag": {"consecutive_skipped_busy": 1, "lag_started_at_epoch": now - 5000},
        "streak-two-short-lag": {"consecutive_skipped_busy": 2, "lag_started_at_epoch": now - 100},
        "current": {"consecutive_skipped_busy": 0, "lag_started_at_epoch": None},
    }
    (warm_root / "populate-manifest.json").write_text(
        json.dumps({"published_at_epoch": now, "sccache_warm_sets": sets}), encoding="utf-8"
    )
    cronjob = tmp_path / "cronjob.yaml"
    cronjob.write_text(f'  schedule: "{schedule}"\n', encoding="utf-8")
    received: list[bytes] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            received.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    environment = {
        **os.environ,
        "CI_RUNNER_HEARTBEAT_OTLP": f"http://127.0.0.1:{server.server_port}/v1/metrics",
        "CI_CACHE_WARM_ROOT": str(warm_root),
        "CI_CACHE_POPULATOR_CRONJOB": str(cronjob),
        "CI_CACHE_HOOK_TEMPLATE": str(tmp_path / "absent-template"),
        "CI_CACHE_PROXY_STATUS_URL": "http://127.0.0.1:1/nginx_status",
        "CI_CACHE_REDIS_PORT": "1",
        "STATE_DIRECTORY": str(tmp_path / "state"),
    }
    subprocess.run(
        ["bash", str(_GAUGES)], env=environment, check=False, capture_output=True, timeout=60
    )
    thread.join(timeout=10)
    server.server_close()
    if not received:
        return None
    metrics = json.loads(received[0])["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    for metric in metrics:
        if metric["name"] == "livespec.ci_cache.sccache.warm_set_lag_trigger_met":
            return {
                point["attributes"][0]["value"]["stringValue"]: int(point["asInt"])
                for point in metric["gauge"]["dataPoints"]
            }
    return {}


def test_trigger_gauge_derives_its_bounds_from_the_populator_schedule(tmp_path: Path) -> None:
    """Two intervals and the runs in them follow the CronJob's minute step, not fixed figures."""
    thirty = _trigger_met_by_repository(tmp_path=tmp_path / "thirty", schedule="*/30 * * * *")
    assert thirty == {
        "streak-two-long-lag": 1,
        "streak-one-long-lag": 0,
        "streak-two-short-lag": 0,
        "current": 0,
    }
    # At a 60-minute step, two intervals is 7200 s, so a 5000 s lag is not yet past them.
    sixty = _trigger_met_by_repository(tmp_path=tmp_path / "sixty", schedule="*/60 * * * *")
    assert sixty is not None and sixty["streak-two-long-lag"] == 0
    # A schedule that is not a minute step is unreadable as an interval: no trigger datapoint.
    assert _trigger_met_by_repository(tmp_path=tmp_path / "daily", schedule="0 3 * * *") == {}
