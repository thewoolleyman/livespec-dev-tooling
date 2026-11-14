"""The incident claims path reads as determinate, so dev-tooling tests keep their retry.

livespec-dev-tooling-bjimt7: every test file's closure reaches
`livespec_dev_tooling/_incident_fleet_sources.py`. Its committed-claims path was
written as a repository-rooted base joined to a NAME, which the plugin reads as
an undeterminable path, so every failing test in this repository was withheld
from retry. SPECIFICATION non-functional-requirements.md "Untouched-test retry":
a join of string literals after a `__file__`-derived base is determinate.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling._incident_fleet_sources import CLAIMS_RELATIVE_PATH, COMMITTED_CLAIMS
from livespec_dev_tooling.flake_retry_decisions import _module_facts, retry_withheld_reason_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCES = _REPO_ROOT / "livespec_dev_tooling" / "_incident_fleet_sources.py"
# A plain test file whose closure reaches the sources module and has no
# undeterminable path chain of its own.
_REACHING_TEST = _REPO_ROOT / "tests" / "livespec_dev_tooling" / "test_flake_retry_paths.py"


def test_the_incident_sources_module_names_its_claims_path_determinately() -> None:
    """The plugin reads the claims path's literal segments, not an unknown name."""
    facts = _module_facts(repo_root=_REPO_ROOT, path=_SOURCES)

    assert facts is not None
    assert facts.undeterminable_paths is False
    assert "config/incident-fleet-evidence.json" in facts.literals


def test_a_test_reaching_the_incident_sources_module_keeps_its_retry() -> None:
    """With an empty change set nothing withholds the retry of such a test."""
    reason = retry_withheld_reason_for(
        repo_root=_REPO_ROOT, test_path=_REACHING_TEST, memo={}, change_paths=set()
    )

    assert reason is None


def test_the_committed_claims_path_is_unchanged() -> None:
    """The literal spelling still resolves to the repository root joined with the name."""
    assert Path("config") / "incident-fleet-evidence.json" == CLAIMS_RELATIVE_PATH
    assert COMMITTED_CLAIMS.relative_to(_REPO_ROOT) == CLAIMS_RELATIVE_PATH
