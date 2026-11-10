"""The installed canonical reader's refusals, exactly as it prints them, for every fake.

A fake reader whose outage looks different from the real one makes a test pass while
production misclassifies the outage. That happened once already (livespec-dev-tooling-fdquen,
review of livespec-dev-tooling#4002 at cb89aac6): the fake answered a down tenant with a
bare `exit 1`, the real reader answers with its own named refusal, and the writer under
test journaled a real outage as terminal. Every fake of `incident_authority.py` should
take its refusal shape from here.

Each value below was read from the installed orchestrator build `456712f1af12`
(livespec-orchestrator-beads-fabro, `scripts/livespec_orchestrator_beads_fabro/`):

- the exit status and reply envelope: `commands/incident_authority.py`, `_reply`
  (`json.dumps(response, sort_keys=True)`, exit 78 for any refusal);
- `incident-authority-unavailable`: `effects/_incident_authority_reader.py`, every read
  (`read-current`, `read-history`, the lifecycle actions' own reading) that meets one of
  `_OUTAGES` (a Dolt connection, command, credential, mapping or missing-tenant error);
- `incident-transition-unavailable` and `incident-transition-outcome-unknown`:
  `effects/_incident_authority_transition.py`, a `commit_transition` that meets the same
  outages before, or after, its write may have landed;
- `incident-genesis-unavailable` and `incident-genesis-outcome-unknown`:
  `effects/_incident_genesis_writer.py`, the same for a genesis write;
- `incident-filing-unavailable`: `effects/_incident_entry_writer.py`, a failed record
  append;
- `incident-receipt-unavailable`: `commands/incident_local_gate_receipt.py` and
  `incident_local_gate_lookup.py`;
- the claim outcomes `_claim` reports as `incident-rollback-conflict-lifecycle-refused`:
  `_store_claim_tokens.py`.

The three shapes an outage really takes, each with a helper here:

1. the reader's own named refusal: exit 78 and one of `OUTAGE_CODES` (`refusal_reply`);
   measured live, the installed reader pointed at a closed Dolt port answers exit 78
   with `incident-authority-unavailable` and a "connection refused" detail;
2. a crash: a lifecycle action that meets an outage mid-action can leak the exception
   uncaught, which is exit 1, a traceback on stderr and NOTHING on stdout
   (`CRASH_EXIT`, `crash_stderr`);
3. the client's own timeout: the reader never answers within the liveness ceiling,
   which the client names `incident-authority-timeout`.
"""

from __future__ import annotations

import json

__all__: list[str] = [
    "AUTHORITY_UNAVAILABLE",
    "CLAIM_OUTCOMES",
    "CRASH_EXIT",
    "FILING_UNAVAILABLE",
    "GENESIS_OUTCOME_UNKNOWN",
    "GENESIS_UNAVAILABLE",
    "OUTAGE_CODES",
    "RECEIPT_UNAVAILABLE",
    "REFUSED_EXIT",
    "TRANSITION_OUTCOME_UNKNOWN",
    "TRANSITION_UNAVAILABLE",
    "crash_stderr",
    "refusal_reply",
]

REFUSED_EXIT = 78
CRASH_EXIT = 1
AUTHORITY_UNAVAILABLE = "incident-authority-unavailable"
TRANSITION_UNAVAILABLE = "incident-transition-unavailable"
GENESIS_UNAVAILABLE = "incident-genesis-unavailable"
FILING_UNAVAILABLE = "incident-filing-unavailable"
RECEIPT_UNAVAILABLE = "incident-receipt-unavailable"
TRANSITION_OUTCOME_UNKNOWN = "incident-transition-outcome-unknown"
GENESIS_OUTCOME_UNKNOWN = "incident-genesis-outcome-unknown"
OUTAGE_CODES = frozenset(
    {
        AUTHORITY_UNAVAILABLE,
        TRANSITION_UNAVAILABLE,
        GENESIS_UNAVAILABLE,
        FILING_UNAVAILABLE,
        RECEIPT_UNAVAILABLE,
        TRANSITION_OUTCOME_UNKNOWN,
        GENESIS_OUTCOME_UNKNOWN,
    }
)
CLAIM_OUTCOMES = (
    "claim-changed",
    "claim-transition-pending",
    "claim-lease-expired",
    "claim-unobservable",
    "claim-token-missing",
)


def refusal_reply(*, code: str, detail: str) -> str:
    """One refusal exactly as the installed reader prints it on stdout (exit 78)."""
    return json.dumps(
        {
            "schema": 1,
            "status": "refused",
            "result": {"code": code, "detail": detail},
            "authorizes_current_effects": False,
            "normal_factory_proof": False,
        },
        sort_keys=True,
    )


def crash_stderr(*, action: str) -> str:
    """The traceback a lifecycle action leaks when an outage escapes it (stdout stays empty)."""
    return (
        "Traceback (most recent call last):\n"
        '  File "scripts/bin/incident_authority.py", line 1, in <module>\n'
        f"livespec_orchestrator_beads_fabro._beads_client.BeadsConnectionError: {action}: "
        "Dolt server unreachable at 127.0.0.1:3307: connection refused\n"
    )
