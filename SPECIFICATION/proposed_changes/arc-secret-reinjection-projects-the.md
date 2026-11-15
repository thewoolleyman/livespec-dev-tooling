---
topic: arc-secret-reinjection-projects-the
author: claude-opus-5-5 (h5r75q seat)
created_at: 2026-11-15T14:28:44Z
---

## Proposal: The ARC secret reinjection projects the livespec-ai-arc GitHub App credential into its own Secret for organization scale sets

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph to non-functional-requirements.md section "Runner-pool node rebuild recipe" and two scenarios to scenarios.md. The CI node's ARC secret reinjection MUST project the livespec-ai organization's ARC GitHub App credential (app id, installation id, private key) into its own Secret, arc-github-app-installation-livespec-ai in namespace arc-runners (keys github_app_id, github_app_installation_id, github_app_private_key), for organization-registered scale sets. It takes the values from the environment the homelab shared-credentials launcher sets as consumer livespec-ai-arc (LIVESPEC_AI_ARC_APP_ID, LIVESPEC_AI_ARC_INSTALLATION_ID, LIVESPEC_AI_ARC_PRIVATE_KEY, read from the SSM parameters under /gitops/v1/shared/providers/github/livespec-ai-arc/). It runs as a dedicated non-root user whose Kubernetes identity may write only that Secret, and it leaves the personal-account Secret arc-github-app-installation unchanged. A missing value makes it exit non-zero, name the missing variable, print no credential value, and leave the organization Secret unchanged.

### Motivation

Work item livespec-dev-tooling-h5r75q was classed spec-change tier at filing: no ratified text states this behaviour, and the nearest home is "## Runner-pool node rebuild recipe". It carries step (b) owed by livespec-dev-tooling-xyi5vu (plan stale-base-merge-options, epic livespec-dev-tooling-xowhol), the move of the fleet's repositories to the livespec-ai organization. Today ci-runner/k3s/secret-reinjection/inject-github-app-secret.sh projects only the personal-account ARC App credential (thewoolleyman-ci-runners) into arc-github-app-installation, from systemd LoadCredentialEncrypted credentials. That App cannot mint registration tokens for livespec-ai repositories, so no scale set can register at the organization. mi-homelab/homelab#1207 declares the SSM consumers /gitops/v1/shared/providers/github/livespec-ai-arc/{app-id,installation-id,private-key} (account 672283019497, region us-west-2), and central-credential-service has written them. tenant-fleet-credentials, which owns the host credential composition, directed that the organization credential reaches the node only through the homelab shared-credentials launcher's environment (consumer livespec-ai-arc), never as sealed per-value systemd credentials. The launcher refuses to run its child as root, so the projection runs unprivileged with Kubernetes access limited to the one Secret it writes. Keeping the organization credential in its own Secret leaves every personal-account scale set working through the cutover. How organization scale sets reference the new Secret belongs to xyi5vu's converge step (c), not to this proposal.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Runner-pool node rebuild recipe", insert the following paragraph immediately after the paragraph that begins "**Live converge from the control node.**" and before the paragraph that begins "**Rehearsed before trusted.**":

**ARC GitHub App credentials, one Secret per account.** The node's ARC secret reinjection (`ci-runner/k3s/secret-reinjection/`) MUST keep each GitHub App credential that the runner scale sets authenticate with in its own Kubernetes Secret in namespace `arc-runners`, one Secret per GitHub account the scale sets register at. The personal-account credential stays in the Secret `arc-github-app-installation`. For scale sets registered at the `livespec-ai` organization, the reinjection MUST project the `livespec-ai-arc` GitHub App credential into the Secret `arc-github-app-installation-livespec-ai`, with the data keys `github_app_id`, `github_app_installation_id` and `github_app_private_key`. That projection MUST take its three values only from the environment that the homelab shared-credentials launcher gives it as the runtime manifest consumer `livespec-ai-arc`: `LIVESPEC_AI_ARC_APP_ID`, `LIVESPEC_AI_ARC_INSTALLATION_ID` and `LIVESPEC_AI_ARC_PRIVATE_KEY` (the private key as issued, in PEM form). The launcher reads them at launch from the AWS SSM parameters under `/gitops/v1/shared/providers/github/livespec-ai-arc/`. The projection MUST NOT read them from a systemd credential or `$CREDENTIALS_DIRECTORY`, and the node MUST NOT seal any of the three values on the host; only the host's bootstrap key is sealed there. The projection MUST run as a dedicated non-root user, because the launcher refuses to run its child as root. That user's Kubernetes identity MUST be allowed to write only the Secret `arc-github-app-installation-livespec-ai` in namespace `arc-runners`, and MUST NOT be allowed to read or write any other Secret. The projection MUST leave the Secret `arc-github-app-installation` unchanged, byte for byte. When any of the three environment values is missing or empty (the launcher could not read its parameter), the projection MUST exit non-zero, MUST name each missing variable, and MUST leave the Secret `arc-github-app-installation-livespec-ai` unchanged. The projection MUST NOT print, log or pass on a command line any credential value, in failure or in success: the private key MUST reach `kubectl` without appearing in argv.

In SPECIFICATION/scenarios.md, insert the following two scenarios immediately after "## Scenario: the listener read-back prints no count when the read of the always-on nodes fails" and before "## Scenario: a node-loss drill holds one agent node NotReady and restores it without touching its workloads":

## Scenario: the ARC secret reinjection projects the livespec-ai-arc credential and leaves the personal-account Secret unchanged

Given the homelab shared-credentials launcher, as consumer `livespec-ai-arc`, has set `LIVESPEC_AI_ARC_APP_ID`, `LIVESPEC_AI_ARC_INSTALLATION_ID` and `LIVESPEC_AI_ARC_PRIVATE_KEY` from the SSM parameters under `/gitops/v1/shared/providers/github/livespec-ai-arc/`

And the Secret `arc-github-app-installation` in namespace `arc-runners` carries the personal-account ARC App credential

When the organization projection of the ARC secret reinjection runs on the CI node as its dedicated non-root user

Then the Secret `arc-github-app-installation-livespec-ai` in namespace `arc-runners` MUST carry those three values under `github_app_id`, `github_app_installation_id` and `github_app_private_key`

And the Secret `arc-github-app-installation` MUST be byte-identical to its value before the run

And the run's output MUST NOT contain any of the three values

## Scenario: the ARC secret reinjection refuses the organization projection when a livespec-ai-arc value is missing

Given the Secret `arc-github-app-installation-livespec-ai` in namespace `arc-runners` holds a credential

And the launcher could not read one of the three `livespec-ai-arc` SSM parameters, so its environment variable is missing or empty

When the organization projection of the ARC secret reinjection runs

Then the projection MUST exit non-zero

And its output MUST name the missing variable and MUST NOT contain any credential value

And the Secret `arc-github-app-installation-livespec-ai` MUST be unchanged

No new `## ` heading is proposed in non-functional-requirements.md. The two new `## Scenario:` headings above are the only new H2 headings; the revise that accepts them MUST add their `tests/heading-coverage.json` rows.
