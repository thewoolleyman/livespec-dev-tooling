# The server-side-revert exemption — reconciling ci-gate-discipline with red-green-replay

Two maintainer-level directives were mutually blocking BY CONSTRUCTION until
2026-09-07. This document is the reconciliation both of them now point at, and
the reason the exemption it describes is not the escape hatch either forbids.

Authored for work-item `livespec-dev-tooling-j2qa`.

## The two directives, and why they collided

**Rule 1 — livespec's `.ai/ci-gate-discipline.md`.** When master CI is red and
local commits are themselves blocked by that red, "create the revert
SERVER-SIDE (a GitHub revert PR via the web UI or API), WHICH NO LOCAL HOOK
MEDIATES." Merging that revert restores green with no gate weakened. The
directive holds even when the gate blocks the very change that would repair the
red, and it forbids adding any lever, flag or severity knob without exception.

**Rule 2 — `check-red-green-replay`.** Every commit in `origin/master..HEAD`
that touches product impl `.py` must carry TDD trailer evidence: a
`TDD-Red-*`/`TDD-Green-*` pair or `TDD-Suite-Green-*`. Those trailers are
stamped by the local `commit-msg` hook.

A server-side revert cannot carry TDD trailers PRECISELY BECAUSE no local hook
mediates it — which is the property Rule 1 requires it to have. So the
sanctioned remedy for a gate deadlock was refused by the gate suite in the
common case, since impl changes are what turn master red.

## The deadlock, measured

livespec-overseer, 2026-08-22. A full observed instance, not a hypothetical.

| Time | Event |
| --- | --- |
| 10:29:49Z | PR 1626 merges as `f5e1d45`, adding statements to `run_tick` and tripping PLR0915 (31 > 30) in `overseer/_supervisor_tick.py` and its `.claude-plugin/` mirror. |
| from then | master CI run 32571990095 FAILS at `check-lint` and `ci-green`. |
| 10:23:14Z | last dispatch-id in the fabro journal. |
| 10:25:57Z | last green/done outcome; every outcome after it fails. |
| 11:17:07Z | PR 1630 opened — a SERVER-SIDE revert of `f5e1d45`, created exactly as Rule 1 directs and citing it. |
| 11:18:01Z | `check-red-green-replay` FAILS PR 1630: `red-green-replay-range-missing-trailers`, `violating_commits: ["32c27a244f5ba8035e8c8d3d596305ea8d670f1e"]`. |

Both exits were closed. The server-side route was refused by the range gate.
The local route the gate's own hint prescribed — re-author through the hook,
force-push — is unreachable while master is red, because `check-master-ci-green`
sits inside the same `check:` aggregate that runs at pre-push. What remained was
a per-occurrence human bypass of a required check: a human unblocking a machine
deadlock, requested and waited on and repeated at every future occurrence.

## What the exemption keys on

Two conjoined properties, BOTH required. Implemented in
`livespec_dev_tooling/checks/_red_green_replay_revert.py`.

### 1. Authorship by the forge's own signing key — the unforgeable half

The commit object must carry an OpenPGP signature that verifies against a
keyring built from GitHub's web-flow public keys **pinned as material in that
module**, and nothing else. GitHub signs every commit its web UI and API create
with that key. Producing such a signature requires GitHub's PRIVATE key, which
no agent, hook or contributor holds.

This is the property a subject line does not have. `git commit -m 'Revert
"..."'` costs an agent one line; a committer of `GitHub <noreply@github.com>`
costs it one environment variable. Neither produces a signature. **A
subject-string carve-out is exactly the abuse Rule 1 exists to prevent** — an
agent can produce one at will — which is why the exemption is not keyed on one.

The keyring is built fresh in a private temporary `GNUPGHOME` per verification,
so the ambient `~/.gnupg` of whoever runs the gate can neither add a signer the
pin does not name nor remove one it does. The trust root is a module constant:
no environment variable, no `[tool.livespec_dev_tooling]` key, no CLI flag and
no config file reaches it. The keyword-only `trust_root` parameter is a
test seam reachable only in-process; the check's CLI entry point passes nothing.

### 2. A verified parent-commit relationship — the narrowness half

The commit must have exactly one parent; must name a reverted commit that is an
ANCESTOR of `origin/master`; and — the load-bearing part — for every product
impl `.py` path it touches, its blob must be BYTE-IDENTICAL to the blob at that
path in the reverted commit's own first parent.

That is a content proof rather than a claim. It establishes that the commit
introduces NO product code that was not already on master before the commit
being undone, and the TDD evidence for that state already exists: it is on the
commit that first introduced it, which passed this same gate. **The exemption
transfers evidence rather than waiving it.**

The `This reverts commit <sha>.` line is used only as a LOOKUP HINT for which
ancestor to compare against. It carries no authority: forging it buys nothing,
because the named commit must still be an ancestor of `origin/master`, the
byte-identity must still hold, and the signature must still verify.

### What is deliberately still refused

- A hand-authored revert with identical content, an identical
  `This reverts commit` body and a spoofed `GitHub <noreply@github.com>`
  committer — no forge signature.
- A revert carrying a real, cryptographically valid signature by a key that is
  simply not the pinned one.
- A correctly-signed revert that also slips in one new product line — it is not
  restoring already-gated bytes.
- A correctly-signed revert naming a commit absent from `origin/master`.
- A conflict-resolved revert whose bytes no longer match the reverted commit's
  parent. A hand-resolved conflict is new code no commit has evidence for, so it
  is outside the exemption on purpose.
- An ordinary untrailered impl commit — the discriminating control. Without it
  the change would be indistinguishable from disabling the check.

Every one of these has a test in
`tests/livespec_dev_tooling/checks/test_red_green_replay_revert.py`, and the
2026-08-22 range above is the regression fixture.

### Where it fails closed

Anything that prevents the verification from completing — `gpg` absent from a CI
image, an unreadable object, a git that did not run, a stale pin after a GitHub
key rotation — answers "no exemption" and restores the pre-existing verdict. A
failure here can only ever make the gate STRICTER: the deadlock returns, nothing
is admitted. The remedy hint names the `gpg`-on-PATH precondition so an operator
whose genuine revert was still convicted knows where to look.

## The prose each side must carry

Rule 1 and Rule 2 must each acknowledge the other, so that an implementer cannot
satisfy one and believe the work done.

**This repository's side is landed.** The `RED_GREEN_REPLAY_PROTOCOL` constant
in `livespec_dev_tooling/checks/_red_green_replay_modes.py` — emitted verbatim
by every rejection branch — now names `ci-gate-discipline.md`, states the
server-side-revert reconciliation, and repeats that this is the ONLY exemption
and that adding a flag, a skip or a severity knob remains forbidden without
exception. `red_green_replay.py`'s module docstring and this repository's
`AGENTS.md` carry the same reconciliation.

**livespec's side is a CROSS-REPO deliverable and is NOT landed by this
change.** `livespec/.ai/ci-gate-discipline.md` lives in the `livespec`
repository, which a factory branch here cannot reach. Its server-side-revert
section needs the reciprocal paragraph:

> The server-side revert is not merely unmediated by the local hooks — it is
> RECOGNISED by them. `check-red-green-replay`'s commit-range gate exempts a
> revert that verifies against GitHub's pinned web-flow signing key AND is
> byte-identical to the reverted commit's parent at every product impl `.py`
> path it touches, so the route this section mandates reaches a mergeable state
> with no gate weakened and no per-occurrence human bypass. The exemption is
> keyed on evidence an agent cannot fabricate, never on a subject line, and it
> is the only one: it does not reopen the lever/flag/severity-knob this section
> forbids. See livespec-dev-tooling's
> `docs/server-side-revert-exemption.md` and
> `livespec_dev_tooling/checks/_red_green_replay_revert.py`.

Until that paragraph lands, the reconciliation is one-directional and a reader
arriving from the livespec side will not know the gate now admits the route.
