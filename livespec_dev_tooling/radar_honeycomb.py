"""Budgeted, injectable reads of the scheduler's committed Honeycomb query specs.

The MCP transport is deliberately a seam.  Production supplies a JSON-RPC
``tools/call`` transport for Honeycomb's ``run_query`` tool; tests supply the
same small protocol without network or credentials.  The reader owns the
per-tick cache and spending rule, so neither transport may accidentally spend
the shared MCP key twice for one spec.
"""

import http.client
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Protocol, cast
from urllib.parse import urlsplit

from livespec_dev_tooling.radar_honeycomb_models import (
    FALLBACK_TABLE,
    MAX_QUERIES_PER_TICK,
    TICK_SPECS,
    ColumnValue,
    InputValue,
    QuerySpec,
    TickSnapshot,
)

__all__: list[str] = [
    "DEFAULT_MCP_ENDPOINT",
    "HoneycombReader",
    "JsonRpcMcpClient",
    "McpClient",
    "McpResponse",
    "reader_from_environment",
]

DEFAULT_MCP_ENDPOINT: Final[str] = "https://mcp.honeycomb.io/mcp"
_MCP_KEY_ENV: Final[str] = "HONEYCOMB_MCP_API_KEY_LIVESPEC"
_MCP_TIMEOUT_SECONDS: Final[float] = 30.0


@dataclass(frozen=True, kw_only=True)
class McpResponse:
    """The injectable MCP response seam."""

    payload: Mapping[str, object] | None
    failure_reason: str | None


class McpClient(Protocol):
    """A transport that runs one named Honeycomb MCP tool."""

    def run_query(
        self, *, api_key: str, endpoint: str, payload: Mapping[str, object]
    ) -> McpResponse: ...


@dataclass(frozen=True, kw_only=True)
class McpRequest:
    """The HTTPS request the JSON-RPC client sends, retained as a testable value."""

    endpoint: str
    data: bytes
    headers: Mapping[str, str]

    def get_header(self, *, name: str) -> str | None:
        """Return one request header for protocol-level assertions."""
        return self.headers.get(name)


def urlopen(*, request: McpRequest, timeout: float) -> http.client.HTTPResponse:
    """One patchable HTTPS-only boundary around the standard-library connection."""
    target = urlsplit(request.endpoint)
    path = f"{target.path or '/'}?{target.query}".rstrip("?")
    connection = http.client.HTTPSConnection(target.netloc, timeout=timeout)
    connection.request("POST", path, body=request.data, headers=dict(request.headers))
    return connection.getresponse()


class JsonRpcMcpClient:
    """The production Honeycomb client: a JSON-RPC ``tools/call`` for ``run_query``."""

    def run_query(
        self, *, api_key: str, endpoint: str, payload: Mapping[str, object]
    ) -> McpResponse:
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "scheduler-honeycomb-reader",
                "method": "tools/call",
                "params": {"name": "run_query", "arguments": payload},
            }
        ).encode("utf-8")
        request = McpRequest(
            endpoint=endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request=request, timeout=_MCP_TIMEOUT_SECONDS) as response:
            decoded: object = json.loads(response.read().decode("utf-8"))
        return McpResponse(payload=cast("Mapping[str, object]", decoded), failure_reason=None)


def reader_from_environment(*, client: McpClient, endpoint: str | None = None) -> "HoneycombReader":
    """Build a reader from the MCP key injected by ``with-livespec-env.sh``."""
    return HoneycombReader(
        api_key=os.environ[_MCP_KEY_ENV],
        budget=MAX_QUERIES_PER_TICK,
        client=client,
        endpoint=endpoint or DEFAULT_MCP_ENDPOINT,
    )


@dataclass(kw_only=True)
class HoneycombReader:
    """One admission tick's bounded Honeycomb reader and cache."""

    api_key: str
    budget: int
    client: McpClient
    endpoint: str
    _cache: dict[str, InputValue] = field(default_factory=dict, init=False)
    _queries_spent: int = field(default=0, init=False)

    def read_spec(self, *, spec: QuerySpec) -> InputValue:
        """Read one spec once in this tick, or return its flagged conservative default."""
        cached = self._cache.get(spec.name)
        if cached is not None:
            return cached
        if self._queries_spent >= self.budget:
            return self._cache_fallback(
                spec=spec, reason=f"per-tick query budget spent ({self.budget})"
            )
        self._queries_spent += 1
        reply = self.client.run_query(
            api_key=self.api_key,
            endpoint=self.endpoint,
            payload={
                "dataset": spec.dataset,
                "calculations": list(spec.calculations),
                "filters": list(spec.filters),
                "breakdowns": list(spec.breakdowns),
                "time_range": spec.window_seconds,
            },
        )
        if reply.failure_reason is not None or reply.payload is None:
            return self._cache_fallback(
                spec=spec, reason=reply.failure_reason or "MCP returned an empty response"
            )
        structured = reply.payload["structuredContent"]
        table: Mapping[str, object] = (
            cast("Mapping[str, object]", structured)
            if isinstance(structured, Mapping)
            else cast("Mapping[str, object]", {})
        )
        raw_rows: object = table.get("rows", ())
        rows = cast("list[object] | tuple[object, ...]", raw_rows)
        value = InputValue(
            rows=tuple(
                cast("Mapping[str, ColumnValue]", row) for row in rows if isinstance(row, Mapping)
            ),
            inputs="live",
            failure_reason=None,
        )
        self._cache[spec.name] = value
        return value

    def read_tick(self) -> TickSnapshot:
        """Return every fixed tick input; a single failure makes the whole snapshot conservative."""
        values = {spec.name: self.read_spec(spec=spec) for spec in TICK_SPECS}
        failed = next(
            (value.failure_reason for value in values.values() if value.inputs == "fallback"), None
        )
        fallback_values = {
            spec.name: self._fallback(spec=spec, reason=failed or "Honeycomb unavailable")
            for spec in TICK_SPECS
        }
        return TickSnapshot(
            values=(values, fallback_values)[failed is not None], queries_spent=self._queries_spent
        )

    def _cache_fallback(self, *, spec: QuerySpec, reason: str) -> InputValue:
        value = self._fallback(spec=spec, reason=reason)
        self._cache[spec.name] = value
        return value

    def _fallback(self, *, spec: QuerySpec, reason: str) -> InputValue:
        return InputValue(
            rows=FALLBACK_TABLE[spec.name],
            inputs="fallback",
            failure_reason=reason,
        )
