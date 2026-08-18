# Fleet, Signaling, And Secret Handling

Use this when changing fleet coordination workflows, GitHub App automation,
maintainer signaling, or secret projection. This file records operator
preferences and host-location facts; it does not carry secret values.

## Maintainer Signaling

Do not default to cron-driven workflows whose primary behavior is posting PR or
issue comments, applying labels, or pinging maintainers. For this repository's
small-team workflow, those side effects are treated as noisy reminders rather
than useful enforcement.

Prefer one of these shapes:

- prevent the bad state with a refusal or hard check;
- clear the state automatically when the existing merge and CI gates allow it;
- surface the state inside a tool the maintainer intentionally invoked.

Existing release-please, auto-merge, pin-freshness, and release-park workflows
are acceptable because they participate in release or pin-currency mechanics.
New notification-only automation needs a stronger justification and should not
be the first design offered.

## Fleet Coordination Currency

The current fleet source of truth is livespec core's committed fleet manifest,
read by dev-tooling fleet conformance and release fan-out. The older
topic-search model is historical. Repository topics remain a discovery safety
net, not the membership authority.

When wiring or reconciling a fleet member, use the dev-tooling fleet surfaces
documented in `SPECIFICATION/contracts.md`, especially the central conformance
and reconcile sections. Declared-before-wired remains the governing shape: a repo is
declared in the manifest before reconcile tooling treats it as a fleet member —
but under livespec core's registration-last birth procedure (ratified v210),
that declaration is the FINAL act of a birth, landing only once the repository
exists, is clonable, and is ready; wiring runs immediately after it.

Pin-and-bump PRs use the `chore:` prefix to avoid release-please feedback
loops. Manual pin edits should follow the same prefix convention.

## Secret Projection

The `thewoolleyman-factory-bot` GitHub App credentials and beads tenant password are
project secrets. They are injected through the livespec 1Password environment,
not stored in this repository and not pasted into agent output.

Authoritative host locations:

- 1Password environment id: `fufpvkvatwkmqjzvilvfnemsue`
- encrypted service-account token:
  `/etc/credstore.encrypted/1password-env-wrapper-livespec`
- installed wrapper: `/usr/local/bin/with-livespec-env.sh`
- wrapper factory repo: `/data/projects/1password-env-wrapper/`

Use the wrapper for commands that need these values:

```bash
source /data/projects/1password-env-wrapper/with-livespec-env.sh <command>
```

Probe only for presence, never values. For beads/Dolt work, a safe probe is a
command that checks `BEADS_DOLT_PASSWORD` is non-empty without printing it.

For GitHub App work, the projected source env vars are `GITHUB_APP_ID` and
`GITHUB_PRIVATE_KEY`; fleet reconcile writes Actions secrets named `APP_ID` and
`APP_PRIVATE_KEY` through stdin. The private key is stored as a single-line PEM
in the environment and must be rewrapped before use by JWT tooling.
