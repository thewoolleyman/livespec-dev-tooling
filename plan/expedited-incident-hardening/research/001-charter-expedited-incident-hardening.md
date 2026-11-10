## The maintainer's statement of what done means

Every hardening follow-up carried out of expedited-incident-response-flag is closed or explicitly dispositioned, so the expedited incident path has no known residual gap left untracked.

## Definition of Done assertions derived from that statement

- Every child moved here from expedited-incident-response-flag is closed or carries a recorded disposition.
- Each queued follow-up (a) through (f) on the parent epic is filed here as a child work item.

## Topic

This plan is the successor of plan `expedited-incident-response-flag` (epic
livespec-dev-tooling-bqnzcm). It holds that plan's hardening follow-ups: the
non-carrier children and the queued follow-up ideas that no Definition of Done
bullet of the parent needs. They move here so they cannot hold the parent's
archive.

## Origin and authority

- The parent's CARRIER TABLE (coordinator rule P5), posted on bqnzcm at
  2026-11-10T20:41:18Z, classified every open child of bqnzcm as a carrier of
  a parent Definition of Done bullet or as a follow-up. It said follow-ups move
  to a successor plan named `expedited-incident-hardening`.
- The coordinator's rulings R301 (legacy-coordinator-agent), recorded on bqnzcm
  at 2026-11-10T20:42:35Z, settled the open questions in that table. hlxbsv is
  not a carrier. bd-ib-oxx6eo moves to the hardening plan. v46q5g is a carrier.
- R301 orders the move NOW, before the parent's phase-8 carrier-map event, so
  that no non-carrier child can hold the parent's archive.

## Definition of Done provenance

The maintainer did not dictate a Definition of Done for this plan. The
statement and both assertions come from the session that opened it, under
the coordinator's R301 ruling. They are recorded as session-derived in the
first handoff entry, as the plan operation requires of an unattended creation.

## Children moved here from expedited-incident-response-flag

Each one is re-parented with `reparent_plan_child`, and each rationale cites R301.

- livespec-dev-tooling-rmig3q: the incident-authority test fakes model outages
  in shapes the real reader never emits. It is blocked by fdquen.
- livespec-dev-tooling-j2rdde: an incident repair that touches
  .github/workflows is always refused. Moved per the parent's 2026-11-09 22:22Z
  disposition.
- livespec-dev-tooling-wbvbj6: incident release recovery is unreachable. Moved
  per the same 22:22Z disposition.
- livespec-dev-tooling-ek36t5: the root fix for the claim-token race drill's
  single barrier, which came out of the wacdfl grade.
- livespec-dev-tooling-2g2j4f: hardening of the incident observer role. It
  waits for the observer pin roll, because the pin line must be the only role
  diff from v1.192.1.
- livespec-dev-tooling-evcphw: hardening of the incident fleet audit
  (pagination and `-I`).
- livespec-dev-tooling-hlxbsv: merged, and not a carrier per R301(2). The LOW
  fixes A and B, plus the N1-N3 notes from the #3966 grade, finish here.

bd-ib-oxx6eo, the test that walks one incident across both repositories, is
moved here by R301(3). It lives in the orchestrator tenant and has no parent
and no edges. It is NOT a child of bqnzcm, and a parent-child edge cannot cross
tenants, so it is tracked here by reference only.

## Queued follow-ups filed as children here

These are the follow-ups queued on bqnzcm in the comments "HARDENING FOLLOW-UPS
QUEUED" (2026-11-10T21:53:24Z) and "HARDENING FOLLOW-UP QUEUED, (f)"
(2026-11-10T21:58:28Z), plus the fdquen re-review notes. Each is filed as one
child.

- (a) A verb or mark that closes a drill incident chain, at fleet scope (every
  incident-authority tenant). Today a drill item stays at
  reverting/repayment-owed forever. The four drill items feh3s4, lli7hc,
  sdxw2v and wxeybc stay open as evidence, labelled incident:drill. They are
  not children of bqnzcm.
- (b) After a restart, the principal resumes a prepared publication by itself.
  The thhgeg cycle B needed a /reconcile with retry_publish=true. The spec
  requires only a recoverable receipt, so this is hardening, not a gap.
- (c) Observer isolation on its own host, behind a hardened server. The
  parent's 20:43:37Z scope event deferred it here, unless the measurement
  taken after option A shows dropped reads.
- (d) The role-test pin: the incident observer role tests assert the literal
  release string.
- (e) hlxbsv notes N1-N3 from the coordinator's grade of #3966 (PASS at
  f4b5b1c3). N1 pins _MATRIX_CALL to a release tag; the reviewer's wording is
  kept verbatim in the child. N2 catches constructor errors that are not
  YAMLError. N3 splits out the call-site module.
- (f) fdquen notes N3-N5. No global bound on attempts exists. An operator
  /reconcile skips the back-off. No documented route clears the quarantine or
  terminal states.

The parent's 21:53Z comment used the label (e) for "hlxbsv A+B and
bd-ib-oxx6eo", and its 21:58Z comment used (f) for the hlxbsv N1-N3 item. This
plan follows the lettering of its opening brief instead: (e) is the hlxbsv
N1-N3 item and (f) is the fdquen N3-N5 item. hlxbsv A+B and bd-ib-oxx6eo come
here through the moves above.
