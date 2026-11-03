"""Budgeted, injectable reads of the scheduler's committed Honeycomb query specs."""

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.client import HTTPResponse, HTTPSConnection
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
_MCP_TIMEOUT_SECONDS: Final[float] = 10.0


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
    """The small request surface the MCP transport and its test seam share."""

    full_url: str
    data: bytes
    headers: Mapping[str, str]
    method: str

    @property
    def get_header(self) -> Callable[[str], str | None]:
        """Expose the standard request-header lookup shape to the test seam."""
        return self.headers.get


def urlopen(*, url: McpRequest, timeout: float) -> HTTPResponse:
    """Open one HTTPS MCP request without permitting arbitrary URL schemes."""
    endpoint = urlsplit(url.full_url)
    connection = HTTPSConnection(host=endpoint.netloc, timeout=timeout)
    connection.request(
        method=url.method,
        url=endpoint.path,
        body=url.data,
        headers=dict(url.headers),
    )
    return connection.getresponse()


@dataclass(frozen=True, kw_only=True)
class JsonRpcMcpClient:
    """The production Honeycomb MCP JSON-RPC transport."""

    def run_query(
        self, *, api_key: str, endpoint: str, payload: Mapping[str, object]
    ) -> McpResponse:
        """Call ``run_query`` and preserve its raw structured result when available."""
        request = McpRequest(
            full_url=endpoint,
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "scheduler-radar",
                    "method": "tools/call",
                    "params": {"name": "run_query", "arguments": payload},
                }
            ).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(url=request, timeout=_MCP_TIMEOUT_SECONDS) as response:
                decoded: object = json.load(response)
            result = cast("Mapping[str, object]", decoded)["result"]
        except TypeError:
            return McpResponse(payload=None, failure_reason="MCP returned non-object JSON")
        except (OSError, ValueError, KeyError) as error:
            return McpResponse(payload=None, failure_reason=f"MCP request failed: {error}")
        return McpResponse(
            payload=cast("Mapping[str, object]", result),
            failure_reason=None,
        )


_DEFAULT_MCP_CLIENT: Final[McpClient] = JsonRpcMcpClient()


def reader_from_environment(
    *, client: McpClient = _DEFAULT_MCP_CLIENT, endpoint: str | None = None
) -> "HoneycombReader":
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
        structured = reply.payload.get("structuredContent")
        table: Mapping[str, object] = (
            cast("Mapping[str, object]", structured) if isinstance(structured, Mapping) else {}
        )
        rows: object = table.get("rows", ())
        if not isinstance(rows, list | tuple):
            return self._cache_fallback(spec=spec, reason="MCP returned invalid rows")
        raw_rows = cast("tuple[object, ...]", rows)
        result = InputValue(
            rows=tuple(
                cast("Mapping[str, ColumnValue]", row)
                for row in raw_rows
                if isinstance(row, Mapping)
            ),
            inputs="live",
            failure_reason=None,
        )
        self._cache[spec.name] = result
        return result

    def read_tick(self) -> TickSnapshot:
        """Return every fixed tick input; a single failure makes the whole snapshot conservative."""
        values = {spec.name: self.read_spec(spec=spec) for spec in TICK_SPECS}
        failed = next(
            (value.failure_reason for value in values.values() if value.inputs == "fallback"), None
        )
        if failed is not None:
            values = {spec.name: self._fallback(spec=spec, reason=failed) for spec in TICK_SPECS}
        return TickSnapshot(values=values, queries_spent=self._queries_spent)

    def _cache_fallback(self, *, spec: QuerySpec, reason: str) -> InputValue:
        result = self._fallback(spec=spec, reason=reason)
        self._cache[spec.name] = result
        return result

    def _fallback(self, *, spec: QuerySpec, reason: str) -> InputValue:
        return InputValue(rows=FALLBACK_TABLE[spec.name], inputs="fallback", failure_reason=reason)
