---
topic: delegated-gate-authority-reading-members-on-pushing-host
author: claude-opus-5-5
created_at: 2026-10-21T15:24:17Z
---

## Proposal: Run authority-reading members of a delegated gate on the pushing host and AND them into the verdict

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Amend the "What the delegated gate runs" bullet of contracts.md §"Delegated pre-push gate". A check-set member that declares it reads an authorization held outside the tree — today the work-items ledger (`check-no-workflow-edits` reading `approval:workflow-edit`) and the forge's repository administration settings (`check-branch-protection-alignment`) — runs on the pushing host, not in the gate Job. The delegated verdict is green only when the Job is green AND every such member passes on the pushing host. The gate pod is given no new credential.

### Motivation

Measured 2026-10-19 on livespec-dev-tooling-38wh (work-item livespec-dev-tooling-gpttcc): an authorized edit under `.github/workflows/` carried the maintainer's `approval:workflow-edit`. Its delegated push failed in gate Job `gate-livespec-dev-tooling-54f19942138d` on `check-no-workflow-edits: the ledger-held authorization could not be evaluated -- FAILING CLOSED`, because the pod holds no `bd` and no ledger credential. The same guard passed on the VPS under the credential wrapper. Failing closed is correct for the guard, but it leaves the delegated venue unable to judge this class of change at all, so every authorized workflow edit has to fall back to the Explicit local route. livespec's first delegated run failed `check-branch-protection-alignment` the same way (HTTP 403 on the gate forge credential, work-item livespec-dev-tooling-eqcsbt). Both members' verdicts depend on authority the pod is deliberately not given. Running them where that authority already lives keeps the Job judging what is a function of the tree, mirrors the ratified token-match rule that already runs world-reading members on the pushing host (§"Token memoization"), and distributes no credential to the cluster. Two alternatives were rejected. A read-only ledger and forge-admin credential in the pod is a credential-distribution change. Passing the label into the Job at render time would make the Job trust a pusher-supplied authorization, the very thing the guard exists to refuse. The amendment is scoped to AUTHORITY-reading members on purpose, not every world-reading member: running host-tooling-reading members on the pushing host would bring back host-dependent verdicts on the VPS, the failure class livespec-dev-tooling-weuhac and livespec-dev-tooling-vxkmab closed.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Delegated pre-push gate", replace the bullet beginning `- **What the delegated gate runs.**` with:

- **What the delegated gate runs.** The gate Job runs the same check recipe the local fall-through runs — the consumer's own gate recipe, the next bullet —, against the committed tree at the pushing worktree's `HEAD`, which is published to the cluster's gate mirror under a ref named by that tree's hash. A check in that set that cannot reach a credential it needs fails inside the gate Job where the local fall-through would only warn. The one exception is a member that declares it reads an AUTHORIZATION held outside the tree: the work-items ledger (for example a maintainer approval label) or the forge's repository administration settings. Such a member does not run in the gate Job. The pre-push gate runs it on the pushing host, with the pushing host's own credentials, against the same committed tree, before or beside submitting the Job. The delegated verdict is green only when the gate Job is green AND every such member passes on the pushing host. A failure of such a member refuses the push and names the member and that it ran on the pushing host. A pushing host that cannot evaluate such a member refuses the push as that member's failure; it never treats an unevaluated authorization as granted. The declaration is carried with the member, as its purity declaration is (§"Token memoization"), and a member with no such declaration runs in the gate Job. This exception grants the gate Job no credential: the authority a member reads stays with the host that already holds it.

No heading is added, renamed or removed, so `tests/heading-coverage.json` is unchanged.
