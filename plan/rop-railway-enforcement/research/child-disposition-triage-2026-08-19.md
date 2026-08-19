# Child disposition triage, 2026-08-19 — the eleven that block archive

`8o8e.19`–`.29` are the archive blocker: the gate refuses while any child is undisposed,
and none of these eleven is closed. **The disposal is the maintainer's call.** This note
does not take it. It does the part that can be done without taking it — read all eleven,
classify each against this epic's actual scope, and put a recommendation with evidence
beside it, so the decision is a review rather than a re-derivation.

**This epic's scope, from its own title:** the ROP railway requirement is enforced by a
check that scans zero files — arm it, then remediate. A child belongs here if it is about
the railway rule, the check that enforces it, or the conversions it demands.

## The cut: 4 stay, 7 leave

| child | subject | recommend |
|---|---|---|
| `.19` | driver-codex `check_tmux_segment`'s `Failure` arm is dead code — railway-typed guard carrying nothing | **KEEP** |
| `.21` | beads-fabro `_config.py` read-vs-write swallow; unparseable config mis-diagnosed, pre-push gate silently skipped | **KEEP** |
| `.25` | livespec config WRITE half destroys a commented `.livespec.jsonc` and reports success | **KEEP** |
| `.28` | v179 has no exemption for a function total by ratified contract | **KEEP** |
| `.20` | `check-no-lloc-soft-warnings`' release lever has no setter anywhere in the fleet | re-parent |
| `.22` | beads-fabro branch protection and `check-master-ci-green` read different signals | re-parent |
| `.23` | `export-ci-telemetry.sh` is four distinct versions across 8 repos | re-parent |
| `.24` | beads-fabro carries two copies of `livespec_runtime` at different versions | re-parent |
| `.26` | a fleet-wide justfile refactor is a cross-repo API change | re-parent |
| `.27` | four degradation sites delegate safety to an invariant retired at v103 | re-parent |
| `.29` | nothing compares a `contracts.md`-stated encoding against the function shipping it | re-parent |

### Why the four stay

They are all **the railway rule itself**, not merely code that happens to be broken:

- **`.19`** is `.28`'s mirror image. `.28` is a function convicted with no reachable
  failure track; `.19` is a function *already* railway-typed whose failure arm is
  unreachable. Same defect — **a `Result` whose failure track is uninhabited** — seen from
  the converted and unconverted sides. They should be disposed together, and `.19` is
  evidence that converting-for-conformance can manufacture exactly the dead track `.28`
  warns about.
- **`.21`** and **`.25`** are both **a write half that swallows a failure and reports
  success** — the precise defect the railway exists to prevent. `.21`'s consequence is a
  silently skipped pre-push gate, which is this epic's founding lesson in another costume:
  enforcement that reports green while enforcing nothing.
- **`.28`** now carries measured evidence (see `canonical-branch-probe-2026-08-19.md`) and
  awaits a maintainer pricing of the duplication trade.

### Why the seven leave

None is about the railway. They cluster into two families that deserve their own tracks:

**Enforcement that does not enforce** — `.20` (a documented lever no CI sets), `.27` (four
sites delegating to a check retired at v103, which never existed), `.22` (branch protection
and the gate reading different signals). ⚠️ **This family is the same SHAPE as this epic's
founding finding and that is exactly why it must not live here.** A check scanning zero
files, a lever with no setter, and a guard delegating to a retired invariant are one class
— *asserted enforcement that computes nothing* — and it is a bigger, more valuable class
than the ROP railway. Folding it into a conversion track buries it.

**Fleet artifact drift** — `.23` (four versions of one script), `.24` (two copies of a
library at different versions), `.26` (a justfile refactor as an unversioned cross-repo API
change), `.29` (a stated encoding nothing compares against what ships). One class:
**duplicated artifacts with no mechanism holding the copies equal.** ▶️ And note it is the
SAME class as this thread's `72-file` universe finding and as overseer's 44-file mirror —
so a "fleet artifact single-sourcing" track would already have five members before it
opened.

## ⛔ A CLOSEABLE ITEM IS SITTING UNLANDED — `.21`

`8o8e.21`'s fix was **authored, gate-passed, and never landed.** The Green patch is in
this thread's own research at `research/8o8e21-green.patch`, and it is the same patch the
2026-08-19 local-inference pilot measured against as ground truth.

**Verified on beads-fabro master today:** `commands/_config.py` still has the swallow —
`_read_root_mapping` returns a bare `dict[str, Any]`, still `return {}` on
`JsoncFailure`, and `ConfigUnreadable` does not exist in the file. **The fix has not
landed anywhere.**

⚠️ **Judge `.21` as a BUG, not as a conversion — the distinction changes whether it is
blocked.** `_config.py` is `_`-prefixed, so the shipped scan skips it and it is convicted
only under the deferred 601 basis. If `.21` were a conversion, the standing interim
constraint would hold it until the panel rules. **It is not.** The defect — an unparseable
config mis-diagnosed as a missing prefix, a configured `fabro_bin` discarded, and the
pre-push ledger-conformance gate silently skipped — is real under every basis. The railway
is the mechanism of the fix, not the reason for it.

▶️ **So `.21` is landable now, is the cheapest of the eleven to dispose, and has been
sitting for two weeks.** Whether the patch still applies after that drift is unverified
here and must be checked before landing.

## What this note deliberately does not do

It does not re-parent, close, or edit any of the eleven. Seven re-parentings need target
tracks that do not exist yet, and creating them is a scoping decision — for the maintainer,
who is mid-triage and does not need a session inventing homes for their work items.
