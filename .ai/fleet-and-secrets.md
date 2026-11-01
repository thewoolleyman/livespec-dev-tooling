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

## The Credential Wrapper Scrubs The Session Environment

Measured 2026-09-04; carried from session auto-memory on 2026-10-18.
`/usr/local/bin/with-livespec-env.sh` re-execs through `sudo` and then
`exec env -i` so that `op run` sees a clean environment. Only an explicit
carry-through list survives, so session-scoped markers do not reach a wrapped
call. With `LIVESPEC_PLAN_UNATTENDED=1` set in the session,

```bash
/usr/local/bin/with-livespec-env.sh -- sh -c 'echo ${LIVESPEC_PLAN_UNATTENDED:-unset}'
```

printed `unset`. The orchestrator's `is_unattended_session` therefore returned
False, and `resume_directive` answered `ask=True, reason='interactive resume'`
for a resume that was genuinely unattended — a plausible directive, not an
error.

When a wrapped call must observe a session variable, pass it back in at the
inner boundary:

```bash
/usr/local/bin/with-livespec-env.sh -- env LIVESPEC_PLAN_UNATTENDED=1 python3 script.py
```

The wrapper is for credentials; it is not a transparent environment
passthrough.

## A Workflow-File Push Needs The Wrapper Too

A push that changes anything under `.github/workflows/` needs three things before the pre-push gate admits it:

1. A per-change `.livespec-workflow-edit-exemption` in the branch, with exactly one `work_item=<ledger-id>` line and one `reason=` line. An exemption inherited from master is refused.
2. The `approval:workflow-edit` label on that work item. An agent sets it only on the maintainer's explicit per-case authorization.
3. The push run inside the credential wrapper:

   ```bash
   mise exec -- just gate-start -- /usr/local/bin/with-livespec-env.sh -- mise exec -- git push -u origin <branch>
   ```

The delegated gate Job skips `check-no-workflow-edits` because it reads an authorization held outside the tree, so the check runs on the pushing host and calls `bd show <item>`. Without the wrapper that call fails with `Error 1045 (28000): Access denied`, and the push is refused as `HOST_AUTHORITY_REFUSED` even when the label is set. Measured 2026-11-01 on livespec-dev-tooling-jw3cyl (PR #3046): it took three pushes — missing exemption, then missing wrapper, then admitted.
