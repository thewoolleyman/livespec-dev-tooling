---
topic: ci-publish-public-route
author: claude-sonnet-5-5
created_at: 2026-11-17T00:53:16Z
---

## Proposal: Ratify POST /ci/publish as a public route and the publisher list that provisions it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

SPECIFICATION/contracts.md already requires the incident CI publisher to publish the PASSED aggregate to the controller, authenticated by the forge-issued identity token. It does not make that route public: the public-ingress paragraph lists only /callback and /ordinary-action, and says every other installation publishes those same routes and only those. This proposal ratifies POST /ci/publish as a public route for an installation whose CI identity policy is provisioned, and states the rule for the list of approved publisher commits that provisions it.

### Motivation

The released 1.215.0 observer serves POST /ci/publish on its tailnet listener, but incident_observer_ci_publisher_shas is empty by the 2026-11-15 ruling until the route is ratified, so ci-identity.json is not rendered and every expedited pull-request run is recorded UNPUBLISHED with identity-not-provisioned (measured on run 43990097062, 2026-11-17, generation-4 arm 48dbd496). A published record, and the bqnzcm.4 PR 2 caller job that produces it, wait on this ratification. A public route is a contract and security surface, so it needs the spec first. Incident work item: livespec-dev-tooling-yekiyj; plan expedited-incident-response-flag.

### Proposed Changes

Add to `contracts.md`, directly after the paragraph that begins "Public ingress the role publishes MUST remain production's alone", this paragraph:

`POST /ci/publish` is the one further public route, and it is public only for an installation whose CI identity policy is provisioned. The controller MUST authenticate a publication to it by the forge-issued identity token for the publishing job, verified against that installation's policy, and MUST NOT authenticate it by the query secret, the control secret, a label, a variable or anything a candidate tree writes. A publication confers no admission, merge authority or normal factory proof, and every refusal the controller answers to it is retained as this section already requires. The committed observer role MUST publish `/ci/publish` on the funnel port, at its exact path for livespec-dev-tooling's installation and at `/<name>/ci/publish` for every other production installation, proxied to the same route on that installation's own loopback listener with the `/<name>` prefix stripped, if and only if that installation's list of approved incident CI publisher commits is non-empty. With an empty list the role MUST NOT publish the route, MUST remove any policy an earlier apply installed, and the controller then answers every publication with `identity-not-provisioned`. A publisher commit MUST be listed only once it is on that repository's default branch, because the token names the commit the publishing job ran and a pull request's own commit is rewritten by rebase-merge. A roll of the publisher MUST list the old and the new commit, then move the callers' pin, then drop the old commit. The sentence above that says every other production installation publishes "those same routes, and only those" is read together with this paragraph: `/callback` and `/ordinary-action` are the routes every installation publishes, and `/ci/publish` is the route a provisioned installation publishes in addition.

Add to `scenarios.md`:

## Scenario: the funnel publishes the CI publication route only for an installation whose publisher list is non-empty

```gherkin
Scenario: the funnel publishes the CI publication route only for an installation whose publisher list is non-empty
  Given a production installation whose list of approved incident CI publisher commits is empty
  When the observer role is applied
  Then the funnel port does not publish that installation's CI publication route
  And the installation's controller answers a publication with identity-not-provisioned
  Given the same installation after one publisher commit that is on its default branch is listed
  When the observer role is applied again
  Then the funnel port publishes that installation's CI publication route at its own path and no other path
  And a publication authenticated by the forge-issued identity token for a job running that commit is verified against the installation's policy
```

