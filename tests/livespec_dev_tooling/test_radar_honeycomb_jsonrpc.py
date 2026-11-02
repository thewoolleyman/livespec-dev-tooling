"""The production MCP transport speaks Honeycomb's JSON-RPC tools/call surface."""

import json

import pytest

from livespec_dev_tooling import radar_honeycomb
from livespec_dev_tooling.radar_honeycomb_models import TICK_SPECS

pytestmark = pytest.mark.integration


class FakeResponse:
    """A minimal urlopen response for the transport's context-manager boundary."""

    def __init__(self, *, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_jsonrpc_transport_uses_mcp_key_endpoint_override_and_tools_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The concrete client posts `run_query`, and the environment factory uses the wrapper key."""
    assert hasattr(
        radar_honeycomb, "JsonRpcMcpClient"
    ), "the reader needs a concrete JSON-RPC MCP client"

    recorded: dict[str, object] = {}

    def urlopen(*, request: object, timeout: float) -> FakeResponse:
        recorded["request"] = request
        recorded["timeout"] = timeout
        return FakeResponse(body=b'{"structuredContent": {"rows": []}}')

    monkeypatch.setattr(radar_honeycomb, "urlopen", urlopen)
    monkeypatch.setenv("HONEYCOMB_MCP_API_KEY_LIVESPEC", "wrapper-injected-key")
    client = radar_honeycomb.JsonRpcMcpClient()
    response = client.run_query(
        api_key="wrapper-injected-key",
        endpoint="https://unresolvable-override.example/mcp",
        payload={"dataset": TICK_SPECS[0].dataset},
    )
    reader = radar_honeycomb.reader_from_environment(client=client)
    overridden = radar_honeycomb.reader_from_environment(
        client=client, endpoint="https://override.example/mcp"
    )

    request = recorded["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert response.failure_reason is None
    assert request.get_header(name="Authorization") == "Bearer wrapper-injected-key"
    assert body["method"] == "tools/call"
    assert body["params"] == {"name": "run_query", "arguments": {"dataset": "metrics"}}
    assert reader.endpoint == radar_honeycomb.DEFAULT_MCP_ENDPOINT
    assert overridden.endpoint == "https://override.example/mcp"

    connection_calls: dict[str, object] = {}

    class FakeConnection:
        """A no-network HTTPS connection used to exercise the transport boundary."""

        def __init__(self, host: str, *, timeout: float) -> None:
            connection_calls["host"] = host
            connection_calls["timeout"] = timeout

        def request(self, method: str, path: str, *, body: bytes, headers: dict[str, str]) -> None:
            connection_calls["method"] = method
            connection_calls["path"] = path
            connection_calls["body"] = body
            connection_calls["headers"] = headers

        def getresponse(self) -> FakeResponse:
            return FakeResponse(body=b'{"structuredContent": {"rows": []}}')

    monkeypatch.undo()
    monkeypatch.setattr(radar_honeycomb.http.client, "HTTPSConnection", FakeConnection)
    response = radar_honeycomb.urlopen(request=request, timeout=2.0)

    assert response.read() == b'{"structuredContent": {"rows": []}}'
    assert connection_calls["host"] == "unresolvable-override.example"
    assert connection_calls["path"] == "/mcp"
