# Tailnet posture: no tags, no keys, no joins

Read this before proposing any network route into or out of the tailnet, any
Tailscale key, tag, ACL or grant change, or any way for GitHub-hosted runners
(or any other off-tailnet caller) to reach a fleet host.

## The posture

The authority is `/data/projects/tailscale-admin/AGENTS.md`, sections
"Maintainer-approved tailnet posture (2026-08-17)" and "autogroup:member
exclusion". Read them there. In short:

- **No tags, ever.** Every device is an ordinary untagged `autogroup:member`
  with full mutual access. The Tailscale login is the security barrier.
- **Tags are viral.** A tagged node leaves `autogroup:member` and can no longer
  see the rest of the tailnet without explicit grants.
- **No agent adds a tag declaration, issuer scope, auth key, advertised tag or
  tag assignment** without the maintainer's explicit authorization for that
  exact action. Agents may document proposals only.

## What it means for this repository

When something outside the tailnet must reach a tailnet host, **do not propose
a tailnet join** (a Tailscale GitHub Action step, an ephemeral runner node, an
auth key in a CI secret). Both ways to do it break the posture:

- **An OAuth-minted key must carry a tag.** Tailscale will not mint an untagged
  key from an OAuth client, so this route needs a tag.
- **An untagged, user-owned key in a CI secret** makes every run a full-access
  member and swaps the login barrier for a shared secret.

Use one of these instead:

- **A token-guarded public path.** The precedent is the incident observer's
  `/callback`, published through a path-scoped Funnel on the VPS. Only that
  path is public, and it refuses a request that lacks the right credential. See
  `ansible/roles/incident_observer/README.md`.
- **Deferral.** Record the need and leave it unarmed.

This was proposed twice. The latest, on 2026-11-10 under
livespec-dev-tooling-jpfdcx, suggested a Tailscale GitHub Action join with a
tagged OAuth key so hosted runners could reach the incident observer.
