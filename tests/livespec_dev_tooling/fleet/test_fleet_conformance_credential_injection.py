"""The credential-class rule answers from an INJECTED token, not the ambient env.

`holds_app_class_credential` was one of the three genuine Result-return
violations livespec-dev-tooling-9sl0 triaged, and it is the one whose
correct disposition is RESTRUCTURE rather than convert: it is disqualified
from livespec v179 member 1 by clause (c) (it read `GH_TOKEN` /
`GITHUB_TOKEN`), yet it HAS NO FAILURE MODE — an absent variable yields
`""` yields `False`. A `Result` there would carry an UNINHABITED failure
track, the exact outcome v179's own rationale forbids. So it is a MEASURED
FALSE POSITIVE of clause (c): a syntactic proxy for "has an expected
failure mode" that an unfailing environment read defeats.

Injecting the token pushes the environment read out to the two lane
`main()` supervisors, which are already deliberate side-effect boundaries,
and leaves the rule itself mechanically total. Precedent:
`classify_role_key_declarations` (#841), where injection REMOVED the I/O
rather than typing it.

This file pins the INJECTION, not the prefix rule — the prefix rule's own
branches stay pinned beside the vantage behavior in
`test_fleet_conformance.py` and `test_fleet_conformance_admin.py`. What is
asserted here is the property the restructure exists to create: the ambient
environment CANNOT change the answer, so no caller inherits a credential
verdict it did not pass in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._contract_rows import CENTRAL_APP_VANTAGE, CENTRAL_VANTAGE
from livespec_dev_tooling.fleet.fleet_conformance import (
    central_run_vantages,
    holds_app_class_credential,
)

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_APP_TOKEN = "ghs_app-installation-token"
_OPERATOR_TOKEN = "ghp_operator-pat"


def test_credential_class_answers_from_the_token_passed_in(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ambient `ghs_` env token does NOT make an injected operator PAT App-class.

    The environment is set to the OPPOSITE class of the injected token in
    both directions, so a body that still consulted `os.environ` would
    answer wrongly in both — asserting only one direction would pass
    against a function that ignored its argument entirely.
    """
    monkeypatch.setenv("GH_TOKEN", _APP_TOKEN)
    monkeypatch.setenv("GITHUB_TOKEN", _APP_TOKEN)
    operator = holds_app_class_credential(token=_OPERATOR_TOKEN)
    monkeypatch.setenv("GH_TOKEN", _OPERATOR_TOKEN)
    monkeypatch.setenv("GITHUB_TOKEN", _OPERATOR_TOKEN)

    assert operator is False and holds_app_class_credential(token=_APP_TOKEN) is True


def test_central_run_vantages_answers_from_the_token_passed_in(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vantage set follows the injected token, with the env set against it.

    `central_run_vantages` is the one caller of the rule that is NOT itself
    a boundary, so the token has to reach it as a parameter too — otherwise
    the environment read merely relocates one call deeper and the rule stays
    disqualified by clause (c) one hop away.
    """
    monkeypatch.setenv("GH_TOKEN", _APP_TOKEN)
    monkeypatch.setenv("GITHUB_TOKEN", _APP_TOKEN)
    operator = central_run_vantages(token=_OPERATOR_TOKEN)
    monkeypatch.delenv("GH_TOKEN")
    monkeypatch.delenv("GITHUB_TOKEN")

    assert operator == frozenset({CENTRAL_VANTAGE}) and central_run_vantages(
        token=_APP_TOKEN
    ) == frozenset({CENTRAL_VANTAGE, CENTRAL_APP_VANTAGE})
