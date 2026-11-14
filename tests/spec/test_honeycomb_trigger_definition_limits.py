"""Every committed Honeycomb trigger definition fits the limits the Honeycomb API enforces.

`ci-runner/observability/triggers/apply-triggers.sh` converges each `*.json`
beside it, and before it sends one it refuses a definition the API would answer
with a 400, among them a `description` longer than 1023 characters. That refusal
happens at APPLY time, which is after merge: on 2026-11-11
`k8s-events-silent.json` (livespec-dev-tooling-a4rd4f) merged with a
1235-character description, passed every gate, and was refused only when the
host apply ran, leaving its dead-man unconverged until a follow-up merged. This
test reads every committed trigger so the same limit fails in CI instead.

It asserts only the limits the applier itself checks locally before sending,
so a definition this test admits is one the applier will try to send.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_TRIGGERS = Path(__file__).resolve().parents[2] / "ci-runner" / "observability" / "triggers"
_DESCRIPTION_LIMIT = 1023
_DEFINITIONS = sorted(_TRIGGERS.glob("*.json"))


def test_the_trigger_directory_holds_definitions() -> None:
    assert _DEFINITIONS, f"no trigger definitions under {_TRIGGERS}"


@pytest.mark.parametrize("definition", _DEFINITIONS, ids=lambda path: path.name)
def test_a_trigger_description_fits_the_honeycomb_limit(definition: Path) -> None:
    description = json.loads(definition.read_text(encoding="utf-8")).get("description", "")
    assert len(description) <= _DESCRIPTION_LIMIT, (
        f"{definition.name}: description is {len(description)} chars; Honeycomb refuses a trigger "
        f"description over {_DESCRIPTION_LIMIT}, and apply-triggers.sh refuses it before sending"
    )
