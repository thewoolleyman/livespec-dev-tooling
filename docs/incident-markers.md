# Python incident comment carriers

`livespec_dev_tooling.incident_markers.validate_python_repair_marker` checks
one Python source string for the exact comment
`# EXPEDITED_INCIDENT_RESPONSE flag: <incident-item-id>` and returns its line
locations. Standalone and inline comments are accepted. String literals,
docstrings, foreign incident IDs and comments containing extra prose do not
satisfy the marker requirement. The entire source must parse and tokenize
before any matching comment is accepted.

The caller supplies `source` from changed code or tests and the incident ID
from an authenticated operation. This helper does not select those files,
authenticate an incident, choose an execution mode, establish historical PR
provenance or authorize a workflow edit. It has no environment-based switch
and is not wired into commit, range, replay or factory-provenance admission.

Its `Result` reports `invalid-incident-marker-identity`,
`unreadable-incident-marker-source` or `missing-incident-marker` on refusal.
A successful result proves only that Python file's comment carrier.

Live admission still requires the orchestrator's canonical authenticated
attempt reader: repository/item/attempt/phase/operation identity, exact PR,
base/head and complete landed commits, current generation and ownership,
durable historical provenance, and a separate scoped host authorization
receipt for workflow edits. No local JSON or marker can replace that reader.
Repair requires the resulting marker; revert validates the original receipt
and may remove it; normal factory cleanup removes it. Those phase decisions
belong to the authenticated caller rather than this syntax helper.
