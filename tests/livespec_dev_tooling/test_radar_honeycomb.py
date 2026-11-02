"""The scheduler Honeycomb reader spends a bounded number of injectable MCP calls."""

from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest

from livespec_dev_tooling.radar_honeycomb import HoneycombReader, McpResponse
from livespec_dev_tooling.radar_honeycomb_models import TICK_SPECS

pytestmark = pytest.mark.integration


@dataclass
class StubMcpClient:
    """An in-memory MCP seam that records exactly the queries the reader spends."""

    response: McpResponse
    calls: list[tuple[str, str, Mapping[str, object]]] = field(default_factory=list)

    def run_query(
        self, *, api_key: str, endpoint: str, payload: Mapping[str, object]
    ) -> McpResponse:
        self.calls.append((api_key, endpoint, payload))
        return self.response


def test_reader_uses_raw_mcp_rows_and_caches_a_repeat_spec_read() -> None:
    """A raw JSON result wins over rendered text and a repeat read costs no second query."""
    spec = TICK_SPECS[0]
    client = StubMcpClient(
        response=McpResponse(
            payload={
                "structuredContent": {"rows": [{"available_memory_bytes": 2048.0}]},
                "content": [{"type": "text", "text": "| wrong | table |"}],
            },
            failure_reason=None,
        )
    )
    reader = HoneycombReader(
        api_key="injected-mcp-key",
        budget=1,
        client=client,
        endpoint="https://mcp.example.test/mcp",
    )

    first = reader.read_spec(spec=spec)
    second = reader.read_spec(spec=spec)

    assert first.inputs == "live"
    assert second == first
    assert len(client.calls) == 1
    api_key, endpoint, payload = client.calls[0]
    assert api_key == "injected-mcp-key"
    assert endpoint == "https://mcp.example.test/mcp"
    assert payload["dataset"] == spec.dataset
    assert payload["calculations"] == list(spec.calculations)


@pytest.mark.parametrize(
    ("response", "budget", "expected_reason"),
    [
        (
            McpResponse(payload=None, failure_reason="endpoint host does not resolve"),
            1,
            "does not resolve",
        ),
        (McpResponse(payload=None, failure_reason="MCP returned an error"), 1, "returned an error"),
        (McpResponse(payload=None, failure_reason=None), 0, "budget spent"),
    ],
)
def test_reader_returns_the_committed_flagged_fallback_for_every_failure(
    *, response: McpResponse, budget: int, expected_reason: str
) -> None:
    """No endpoint, MCP, or budget failure leaks a partial live snapshot."""
    client = StubMcpClient(response=response)
    reader = HoneycombReader(
        api_key="injected-mcp-key", budget=budget, client=client, endpoint="bad-host"
    )

    snapshot = reader.read_tick()

    assert snapshot.values
    assert all(value.inputs == "fallback" for value in snapshot.values.values())
    assert all(
        expected_reason in (value.failure_reason or "") for value in snapshot.values.values()
    )
    assert len(client.calls) == (0 if budget == 0 else 1)
