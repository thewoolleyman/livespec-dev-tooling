"""The scheduler Honeycomb reader spends a bounded number of injectable MCP calls."""

import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import Request

import pytest

from livespec_dev_tooling.radar_honeycomb_models import TICK_SPECS

pytestmark = pytest.mark.integration


@dataclass
class StubMcpClient:
    """An in-memory MCP seam that records exactly the queries the reader spends."""

    response: object
    calls: list[tuple[str, str, Mapping[str, object]]] = field(default_factory=list)

    def run_query(self, *, api_key: str, endpoint: str, payload: Mapping[str, object]) -> object:
        self.calls.append((api_key, endpoint, payload))
        return self.response


@dataclass(kw_only=True)
class StubHttpResponse:
    """A context-managed HTTP response for the concrete JSON-RPC transport."""

    body: bytes

    def __enter__(self) -> "StubHttpResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


@dataclass(kw_only=True)
class StubHttpsConnection:
    """A no-network HTTPS connection that captures the concrete opener's wire request."""

    host: str
    timeout: float
    requests: list[tuple[str, str, bytes, dict[str, str]]] = field(default_factory=list)

    def request(self, *, method: str, url: str, body: bytes, headers: dict[str, str]) -> None:
        self.requests.append((method, url, body, headers))

    def getresponse(self) -> StubHttpResponse:
        return StubHttpResponse(body=b"{}")


def test_reader_caches_repeats_and_returns_flagged_fallback_for_failures() -> None:
    """No endpoint, MCP, or budget failure leaks a partial live snapshot."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "radar_honeycomb.py"
    assert module_path.is_file(), "the scheduler needs a Honeycomb reader"
    reader_module = importlib.import_module("livespec_dev_tooling.radar_honeycomb")
    spec = TICK_SPECS[0]
    client = StubMcpClient(
        response=reader_module.McpResponse(
            payload={"structuredContent": {"rows": [{"available_memory_bytes": 2048.0}]}},
            failure_reason=None,
        )
    )
    reader = reader_module.HoneycombReader(
        api_key="injected-mcp-key", budget=1, client=client, endpoint="bad-host"
    )
    assert reader.read_spec(spec=spec).inputs == "live"
    assert reader.read_spec(spec=spec).inputs == "live"
    assert len(client.calls) == 1
    assert all(value.inputs == "live" for value in reader.read_tick().values.values())

    unavailable = reader_module.HoneycombReader(
        api_key="injected-mcp-key",
        budget=1,
        client=StubMcpClient(
            reader_module.McpResponse(payload=None, failure_reason="does not resolve")
        ),
        endpoint="bad-host",
    ).read_tick()
    exhausted = reader_module.HoneycombReader(
        api_key="injected-mcp-key", budget=0, client=client, endpoint="bad-host"
    ).read_tick()
    assert all(value.inputs == "fallback" for value in unavailable.values.values())
    assert all(
        "does not resolve" in (value.failure_reason or "") for value in unavailable.values.values()
    )
    assert all(
        "budget spent" in (value.failure_reason or "") for value in exhausted.values.values()
    )

    invalid_rows = reader_module.HoneycombReader(
        api_key="injected-mcp-key",
        budget=1,
        client=StubMcpClient(
            response=reader_module.McpResponse(
                payload={"structuredContent": {"rows": "invalid"}}, failure_reason=None
            )
        ),
        endpoint="bad-host",
    ).read_spec(spec=spec)
    assert invalid_rows.inputs == "fallback"
    assert invalid_rows.failure_reason == "MCP returned invalid rows"


def test_reader_from_environment_uses_injected_key_and_endpoint_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The constructor consumes the wrapper's MCP key and permits an endpoint override."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "radar_honeycomb.py"
    assert module_path.is_file(), "the scheduler needs a Honeycomb reader"
    reader_module = importlib.import_module("livespec_dev_tooling.radar_honeycomb")
    monkeypatch.setenv("HONEYCOMB_MCP_API_KEY_LIVESPEC", "injected-mcp-key")
    client = StubMcpClient(
        response=reader_module.McpResponse(payload=None, failure_reason="not called")
    )
    overridden = reader_module.reader_from_environment(
        client=client, endpoint="https://unresolvable.invalid/mcp"
    )
    defaulted = reader_module.reader_from_environment(client=client)
    assert overridden.api_key == "injected-mcp-key"
    assert overridden.endpoint == "https://unresolvable.invalid/mcp"
    assert defaulted.endpoint == reader_module.DEFAULT_MCP_ENDPOINT


def test_json_rpc_client_uses_the_mcp_endpoint_and_returns_raw_tool_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production seam sends Honeycomb's ``run_query`` JSON-RPC request over HTTPS."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "radar_honeycomb.py"
    assert module_path.is_file(), "the scheduler needs a Honeycomb reader"
    reader_module = importlib.import_module("livespec_dev_tooling.radar_honeycomb")
    assert hasattr(reader_module, "JsonRpcMcpClient"), "the reader needs an MCP JSON-RPC transport"
    requests: list[tuple[Request, float]] = []

    def open_request(*, url: Request, timeout: float) -> StubHttpResponse:
        requests.append((url, timeout))
        return StubHttpResponse(
            body=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "query-1",
                    "result": {"structuredContent": {"rows": [{"available_memory_bytes": 3.0}]}},
                }
            ).encode()
        )

    monkeypatch.setattr(reader_module, "urlopen", open_request)
    response = reader_module.JsonRpcMcpClient().run_query(
        api_key="injected-mcp-key",
        endpoint="https://override.invalid/mcp",
        payload={"dataset": "metrics"},
    )
    request, timeout = requests[0]
    assert timeout > 0
    assert request.full_url == "https://override.invalid/mcp"
    assert request.get_header("Authorization") == "Bearer injected-mcp-key"
    assert isinstance(request.data, bytes)
    assert json.loads(request.data) == {
        "jsonrpc": "2.0",
        "id": "scheduler-radar",
        "method": "tools/call",
        "params": {"name": "run_query", "arguments": {"dataset": "metrics"}},
    }
    assert response.failure_reason is None
    assert response.payload == {"structuredContent": {"rows": [{"available_memory_bytes": 3.0}]}}


def test_json_rpc_client_flags_unreachable_and_invalid_mcp_replies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The concrete transport turns endpoint and wire failures into reader fallback reasons."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "radar_honeycomb.py"
    assert module_path.is_file(), "the scheduler needs a Honeycomb reader"
    reader_module = importlib.import_module("livespec_dev_tooling.radar_honeycomb")

    def unavailable(*, url: Request, timeout: float) -> StubHttpResponse:
        _ = url, timeout
        raise OSError("does not resolve")

    monkeypatch.setattr(reader_module, "urlopen", unavailable)
    failed = reader_module.JsonRpcMcpClient().run_query(
        api_key="injected-mcp-key", endpoint="https://unresolvable.invalid/mcp", payload={}
    )
    assert failed.payload is None
    assert failed.failure_reason == "MCP request failed: does not resolve"

    def invalid_response(*, url: Request, timeout: float) -> StubHttpResponse:
        _ = url, timeout
        return StubHttpResponse(body=b"[]")

    monkeypatch.setattr(
        reader_module,
        "urlopen",
        invalid_response,
    )
    invalid = reader_module.JsonRpcMcpClient().run_query(
        api_key="injected-mcp-key", endpoint="https://override.invalid/mcp", payload={}
    )
    assert invalid.payload is None
    assert invalid.failure_reason == "MCP returned non-object JSON"


def test_https_opener_uses_only_the_endpoint_host_and_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production opener maps the committed HTTPS endpoint to one HTTPS request."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "radar_honeycomb.py"
    assert module_path.is_file(), "the scheduler needs a Honeycomb reader"
    reader_module = importlib.import_module("livespec_dev_tooling.radar_honeycomb")
    connections: list[StubHttpsConnection] = []

    def connect(*, host: str, timeout: float) -> StubHttpsConnection:
        connection = StubHttpsConnection(host=host, timeout=timeout)
        connections.append(connection)
        return connection

    monkeypatch.setattr(reader_module, "HTTPSConnection", connect)
    response = reader_module.urlopen(
        url=reader_module.McpRequest(
            full_url="https://mcp.honeycomb.io/mcp",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
        timeout=9.0,
    )
    assert response.read() == b"{}"
    assert connections[0].host == "mcp.honeycomb.io"
    assert connections[0].timeout == 9.0
    assert connections[0].requests == [
        ("POST", "/mcp", b"{}", {"Content-Type": "application/json"})
    ]
