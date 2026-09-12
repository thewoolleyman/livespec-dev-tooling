# How a 15-second race became a 14-hour silent outage

Initial research note for the `plugin-cache-provisioning-integrity` plan
thread. Incident measured 2026-08-12/13 from `livespec-overseer`; the fix
site is this repo's `livespec_dev_tooling/fleet/ensure_plugins.py`.

The defect record is **`livespec-dev-tooling-s1ic`** — read its live state
and description from the ledger for the full timestamped evidence; cite it,
do not re-file it. This note carries the reasoning that does not belong in
a work-item: why the obvious framings are wrong, and which constraints any
fix has to respect.

## What happened, in one paragraph

Two Claude sessions started in the same second (a paired agent launch:
worker plus supervisor, same repo). Both fired `SessionStart`, both ran
`ensure_plugins`. One rebuilt the shared marketplace working tree under
`~/.claude/plugins/marketplaces/livespec-overseer/` while the other's
`claude plugin install` copied `.claude-plugin/` out of that same tree
mid-teardown. The copier saw one empty `skills/overseer/` directory and
nothing else, copied exactly that, exited 0, and stamped the install
successful 21 seconds later. The resulting cache ref held **zero files**.
Three repos then adopted that ref as a plain cache hit over the next two
hours, and three skills — `supervise-plan`, `overseer`, `foreman` — were
silently absent from every session in those repos for 14 hours.

## The three framings that are wrong, and why

Each of these is where a reader naturally lands first. Each costs real time.

**"The plugin release was broken."** It was not. `git ls-tree origin/release`
at the exact installed sha carries `plugin.json`, all three
`skills/*/SKILL.md` and all three `prose/*.md`. After deleting the ref and
re-running the ordinary provisioning recipe, the re-extract produced 112
files, byte-identical to `origin/release` for every file checked. Nothing
upstream of the cache was ever wrong, so nothing upstream of the cache needs
fixing.

**"It is a transient race; races are rare and self-correcting."** The race
IS rare — 58 of 59 cached refs for that plugin were intact, and a second
paired launch that same day came through clean. But the consequence is not
transient, and that asymmetry is the whole defect. The cache is keyed by
commit sha, so once the empty directory existed every later install treated
it as a hit. `claude plugin update` answered `already at the latest version`
every time, correctly, because the version stamp WAS current. A one-in-59
write error became permanent because nothing ever re-reads what it wrote.

**"Serializing provisioning is the fix."** It is half the fix, and the
weaker half. A lock prevents the NEXT poisoning; it does nothing for a ref
already poisoned, which stays broken until the upstream sha changes. The
repair half — detect a vacuous extract and re-install it — is what actually
ends an outage, and it also happens to be the half that works without
assuming every writer on the host cooperates with our lock. Ship both;
prioritize validation.

## The constraint that shaped the acceptance

`registry_findings` already exists and already ran, green, throughout the
entire incident. It confirms that `installed_plugins.json` holds a record
whose `projectPath` matches the project root. That is a true statement about
the REGISTRY and says nothing about the DIRECTORY the registry points at.

The module's own docstring says a zero exit from a scoped plugin command
does not establish which project's record it touched, so provisioning is
confirmed against the record itself. That reasoning is sound and the check
is worth keeping — it just proves a different proposition than the one a
reader assumes. This incident is what conflating those two propositions
costs, and it is the reason the acceptance says a ref containing zero files
must be a finding and never a pass, in those words.

## Why the trigger is deliberately out of scope

The paired-launch pattern belongs to `livespec-overseer`, and spacing those
launches is tempting because it is easy and it addresses the thing that
visibly fired. It should not be this thread's fix. Spacing narrows the
window without closing it; any hand launch, any unrelated repo's session
start, or any two operators working at once reopens it. The contended
resource is host-global shared state, so the guard belongs at that boundary,
in this repo, where it protects every consumer regardless of who launches
what. A separate overseer-side item for launch spacing may still be worth
filing as defense-in-depth, but it is not a substitute and must not be
allowed to close this thread.

## Constraints any implementation has to respect

- **The lock is host-wide, not per-repo.** The two racing sessions were in
  the SAME repo, so a per-repo lock would have prevented nothing. The
  contended state is `~/.claude/plugins/`.
- **The lock spans the whole command loop.** The hazard is the gap between
  one run mutating a marketplace tree and another copying out of it, so a
  per-command lock leaves the window open.
- **Lock acquisition must fail soft.** A session start that cannot take the
  lock within a bounded wait reports a finding and skips provisioning. It
  must never hang a session start, and it must never fall through to
  provisioning unguarded. A skipped provision is recoverable; the poisoned
  ref was not.
- **Purge-then-reinstall is safe on a vacuous ref specifically.** A ref with
  zero files has nothing to lose, which the 2026-08-12 repair confirmed in
  practice. This does not generalize to a partially-populated ref, and the
  validator should not attempt to repair one — report it and stop.

## Open question, carried deliberately

Three sessions AFTER the break (11:21Z, 11:32Z, 14:05Z) did list the skills,
though the poisoned ref was never modified after 10:34:40. They must have
resolved a different install path. Neither this analysis nor the
`livespec-overseer` supervisor pass that first found the incident has
explained those three. It is recorded here so it is not mistaken for
settled; it does not block either guard, and it may simply be repos pinned
to older shas.
