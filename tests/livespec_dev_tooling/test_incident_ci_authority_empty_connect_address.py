"""An empty connect-address variable means unset, as a workflow expression renders it.

GitHub Actions has no way to leave a variable out conditionally: an `env:` line whose
expression is false, or which names an undefined repository variable, sets the empty
string. Dialing by hostname is what unset means, so empty must mean that too.
"""

from __future__ import annotations

import pytest

from livespec_dev_tooling.incident_ci_authority import _connect_address

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR"


def test_an_empty_connect_address_means_dial_by_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_VARIABLE, "")
    assert _connect_address() is None
