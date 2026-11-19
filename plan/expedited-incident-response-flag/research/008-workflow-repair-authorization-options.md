# 008 — Who may authorize a workflow-file repair inside an incident (livespec-dev-tooling-jtuxzn)

Status: options and one recommendation, for the maintainer. NOT an implementation item. The coordinator ruled
(2026-11-19) that the dispatcher must not ticket `jtuxzn` until the authorization model below is ratified, because
workflow edits that remove or reduce gates stay the maintainer's (coordinator-duties section 12).

## The measured problem

On incident `livespec-dev-tooling-ypvfll` (master red at 00cc04ba1) an expedited-repair commit was refused with
`incident-hook-refused: workflow publication requires separately scoped canonical authorization`. The refusal is
`livespec_dev_tooling/incident_hook_scope.py:199-200` (`validate_scope`): after the paths-subset check passes, any
changed path under `.github/workflows/` fails unconditionally in expedited-repair mode. No authority record can carry
such a scope today. `docs/incident-host-hook.md` lists workflow publication as required plan work. So a master-red
incident whose repair is a CI workflow edit cannot use the expedited path.

## What has to be decided

Not a code change but an authorization-model change: which party may put a workflow path into an incident's
canonical scope, and what the hook checks before it admits the path. The hook can only enforce what the authority
record carries; the question is what the record may carry and who may write it.

## Options

**A. Maintainer-attested workflow scope.** The attempt's canonical record gains an optional list of exact workflow
paths. Only a maintainer-attested record (a `human_attested` receipt, the existing proof mode) may write it. The hook
admits a workflow path only when it is listed exactly and the attestation is current for that attempt generation.
- For: keeps section 12 intact (every workflow edit in an incident is a maintainer act); smallest new trust surface.
- Against: the maintainer must be reachable inside an incident, which is the case the lane exists to speed up.

**B. Coordinator-authorized, gate-non-reducing only.** The coordinator may write the scope, but only for a diff a
mechanical detector proves removes no required job, no `needs:` entry of `ci-green`, and no step of a gating job.
Anything the detector cannot prove non-reducing is refused and falls back to A.
- For: no maintainer wait on the common case (a revert of a publishing step, as ypvfll's own first route was).
- Against: needs a trustworthy gate-reduction detector (a new check with its own false-negative risk); section 12 says
  reducing edits are the maintainer's, so this narrows the maintainer's role by a rule an agent writes.

**C. Keep the refusal; route workflow incidents through the revert lane only.** A workflow repair that is a
revert of the commit that broke master uses `EXPEDITED_INCIDENT_RESPONSE_REVERT` and its inverse boundary; a forward
workflow fix stays on the normal lane.
- For: no authorization change at all.
- Against: leaves forward workflow fixes slow. Not verified by me whether the revert lane admits workflow paths today;
  that must be read before this option is considered viable.

## Recommendation

A, with B's detector added later only as an additional refusal (never as a grant). A is the only option that needs no
new agent-written trust rule, and its cost (maintainer reachability) is an operational one the maintainer can accept
or not. Verify C's premise on the revert lane first; if it already admits workflow reverts, the remaining gap is only
forward workflow fixes and A covers it.

## What a ratification needs

The scope-authorization model is likely a safety guarantee under spec-scope-criteria, so it goes through
`propose-change` and `revise` before any item is filed. Only the part the ratified design leaves (the hook reading a
workflow-scope field, its refusal naming the missing authorization) becomes the ticketed implementation, and that part
is what `jtuxzn`'s Definition of Done already describes.
