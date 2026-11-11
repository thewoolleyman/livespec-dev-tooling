---
topic: a-gh-failure-status-needs-its-http-marker
author: claude-fable-5-1
created_at: 2026-11-11T15:58:55Z
---

## Proposal: A gh failure's status needs its HTTP marker

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add one paragraph to contracts.md §"Cross-repo coordination automation surface" → "Fleet surface — central conformance and reconcile", the section that governs `livespec_dev_tooling/fleet/`, stating how the fleet `gh` seam classifies a failed read from `gh`'s standard error. A kind is taken from an HTTP status only when the standard error presents the number as an HTTP status, never from a bare digit run: standard error whose only 5xx digit run is not an HTTP status (such as `… with the number of 512.`) is not `server_error`; every form in which `gh` relays a real HTTP 5xx (`gh: Bad Gateway (HTTP 502)`, `HTTP 503: Service Unavailable`, and git's `fatal: unable to access '<url>': The requested URL returned error: 502`) is still `server_error`; and the same rule holds for the 429, 403 and 404 alternatives, so a digit run that is not an HTTP status never yields `rate_limited`, the secondary-limit kind, `forbidden` or `not_found`. No heading is added, so `tests/heading-coverage.json` is unchanged.

### Motivation

Repays the deferred spec debt recorded on incident item livespec-dev-tooling-t26bbr (plan expedited-incident-response-flag, research note 007 §4.4 and step 6.4). The incident: the fleet `gh` failure classifier (`livespec_dev_tooling/fleet/_read_failure.py`, `classify_gh_failure`) read any 5xx digit run as a server error, so a permanent failure was retried as a transient. The item's Definition of Done carries three statements — B1 (a bare 5xx digit run is not `server_error`), B1c (every real relayed HTTP 5xx form still is), and B2 (the same rule for the 429, 403 and 404 alternatives) — and the ratified spec states none of them: the item references `## Cross-repo coordination automation surface`, whose fleet-surface subsection describes the obligation table and the two modes but not the read-failure kinds the `gh` seam produces. The incident attempts edited no spec file; the debt is repaid here, before the factory repayment dispatch, so the repayment is judged against ratified text rather than against the Definition of Done alone. The paragraph is placed under the H2 the item already references, so the item's governing heading is unchanged and no new heading or coverage row is needed; the behaviour is already exercised by the classifier's test module (`tests/livespec_dev_tooling/fleet/test_read_failure.py`), which the factory repayment extends.

### Proposed Changes

In `contracts.md` §"Cross-repo coordination automation surface" → "Fleet surface — central conformance and reconcile", insert the following paragraph directly after the paragraph that begins "**Vendored-tree pin fidelity (the `vendored-tree-matches-pin` obligation row).**" and directly before the paragraph that begins "**Local-vantage first-touch reconcile — `python -m livespec_dev_tooling.fleet.local_reconcile`.**":

> **A `gh` failure's status needs its HTTP marker (the fleet `gh` read-failure classification).** The fleet surface reads GitHub through one `gh` seam, and a failed read is classified from `gh`'s standard error into one retry-relevant kind — `rate_limited` (the kind a secondary-limit body also selects), `forbidden`, `not_found`, `server_error`, or `transport` for everything else — because `rate_limited` and `server_error` are retried while `forbidden` and `not_found` are not. A kind MUST be taken from an HTTP status only when the standard error presents that number as an HTTP status, never from a bare digit run. The classifier MUST return a kind other than `server_error` for standard error whose only 5xx digit run is not an HTTP status, such as `… with the number of 512.` It MUST still return `server_error` for every form in which `gh` relays a real HTTP 5xx: `gh: Bad Gateway (HTTP 502)`, `HTTP 503: Service Unavailable`, and git's `fatal: unable to access '<url>': The requested URL returned error: 502`, which `gh repo clone` and `gh pr checkout` pass through. The same rule holds for the 429, 403 and 404 alternatives: a digit run that is not an HTTP status MUST NOT yield `rate_limited`, the secondary-limit kind, `forbidden` or `not_found`.

No `## ` heading is added or changed, so `tests/heading-coverage.json` and the debt register are untouched. No other file changes.
