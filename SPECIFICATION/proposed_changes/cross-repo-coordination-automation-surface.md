---
topic: cross-repo-coordination-automation-surface
author: claude-opus-4-7
created_at: 2026-05-24T20:55:19Z
---

## Proposal: extend-spec-md-with-cross-repo-coordination-surface

### Target specification files

- SPECIFICATION/spec.md

### Summary

Extend the spec.md §"Architecture > Two consumption surfaces" enumeration to acknowledge the cross-repo coordination automation surface as a functional sub-category of the existing composite-Actions-and-reusable-workflows surface. The two top-level consumption surfaces (Python package + Actions/workflows) remain correct; the new content names a CI-orchestration sub-category and a cross-repo coordination sub-category within the second surface and cross-references the contracts.md sections that pin each sub-category's wire contract.

### Motivation

The current spec.md acknowledges reusable workflows in the abstract but enumerates only reusable-check-matrix.yml as a concrete shipped workflow. The cross-repo coordination mechanism declared in livespec/SPECIFICATION/contracts.md §"Cross-repo coordination — pin-and-bump" is half-built (livespec's release-dispatch.yml fans out but no consumer has a handler) and has no contractual owner — livespec's spec describes WHAT the mechanism must do, but no library's spec describes HOW. dev-tooling is the right owner per its existing build-time scope and its already-published reusable-workflows channel; the spec must acknowledge the expanded scope so subsequent contracts.md and constraints.md extensions have a clear top-level reference. The user's plan calls for ONE owning location for the cross-repo coordination contract, with consumer-side footprint limited to three thin shim workflows.

### Proposed Changes

Insert a new bulleted paragraph at the end of `spec.md` §"Architecture > Two consumption surfaces", after the existing two surface bullets, with the following content:

> The composite-Actions-and-reusable-workflows surface includes two functional categories. The **CI-orchestration category** ships reusable workflows and Actions that consumers wire into their per-repo `ci.yml` to execute the shared check suite (e.g., `reusable-check-matrix.yml`). The **cross-repo coordination category** ships reusable workflows that implement the pin-and-bump mechanism declared in `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump" — release-dispatch fan-out, autodiscovery-driven bump-pin pull requests, vendored-library re-bump, and periodic pin-freshness sweeps. Each category's full inventory and wire contract is pinned in `contracts.md` §"Reusable workflows wire contract" and §"Cross-repo coordination automation surface" respectively.

Rationale for placement: the new content extends the existing surface enumeration without altering it. The "two surfaces" framing (Python package + Actions/workflows) remains correct; the new content names a functional sub-partition WITHIN the second surface and cross-references the contracts.md sections that pin each sub-partition's contract.


## Proposal: add-cross-repo-coordination-automation-contract-to-contracts-md

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a comprehensive new top-level section §"Cross-repo coordination automation surface" to contracts.md, codifying the reusable workflow inventory (reusable-release-dispatch.yml, reusable-bump-pin-from-dispatch.yml, reusable-pin-freshness.yml), sibling discovery via the livespec-sibling GitHub topic, pin autodiscovery rules across .livespec.jsonc / pyproject.toml / .vendor.jsonc / .copier-answers.yml, the repository_dispatch payload contract, the GitHub App auth model with soft-fail semantics, the chore: PR commit convention to avoid release-please cycles, the pin-freshness threshold default, and the fallback known-good-pin mechanism. The section also migrates three specific clauses currently in livespec's spec that belong here, and extends the library's semver-stable surface enumeration to cover the new elements.

### Motivation

Livespec's contracts.md §"Cross-repo coordination — pin-and-bump" declares the mechanism is REQUIRED and partially specifies it (the consumer compat block schema, the dispatch trigger discipline). The IMPLEMENTATION contract (workflow inventory, autodiscovery rules, payload shape, auth model, PR conventions) is not specified in either repo today — it lives implicitly in livespec's release-dispatch.yml YAML comments. dev-tooling is the correct owner because (a) its build-time scope already permits network I/O from workflows, (b) it already publishes a `uses:`-pinned reusable-workflows channel, (c) every consumer already binds to its pinned tag, satisfying the DRY discipline (the per-consumer footprint is three thin shim workflows, all real logic lives here). The user's plan requires autodiscovery for all pin formats (no per-consumer registries), full automation with manual intervention only as a fallback for broken state, and the contract to be hosted in this library since this library is the implementation owner.

### Proposed Changes

Add a new top-level section `## Cross-repo coordination automation surface` to `SPECIFICATION/contracts.md`, positioned after the existing §"Reusable workflows wire contract" section and before §"Versioning". The new section's full content follows:

---

## Cross-repo coordination automation surface

This section codifies the reusable GitHub workflow surface that implements livespec's pin-and-bump mechanism (per `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump") uniformly across every livespec-governed sibling repository. The contract here is the canonical implementation specification; livespec's spec declares the policy, this section owns the implementation surface. Per the DRY discipline, every consumer's per-repo coordination footprint is three thin shim workflows that delegate to the reusable workflows defined here; no coordination logic is duplicated across consumers.

### Sibling discovery

Every livespec-governed sibling repository MUST carry the `livespec-sibling` GitHub topic on its repository metadata. The coordination workflows discover siblings via `gh search repos --owner <org> --topic livespec-sibling --json name` at dispatch time. A repository missing the topic is silently excluded from dispatch; this is the supported mechanism for opting out (e.g., during sibling repo bootstrap before it is ready to receive bumps).

The topic-based discovery mechanism MUST be the sole source of truth for the sibling set. A static registry file (e.g., a `siblings.yml` in this library) is FORBIDDEN — the discovery is autodiscovery by design, so adding a new sibling requires no edits to this library's source.

### Reusable workflow inventory

The library MUST ship the following reusable workflows under `.github/workflows/`, each with a `workflow_call` trigger and the inputs/outputs declared below. Each workflow's path is the semver-stable identifier consumers reference via `uses:`.

#### `reusable-release-dispatch.yml`

Fan-out dispatcher invoked by each sibling's own `release-dispatch.yml` shim on `on: release: types: [published]`.

Inputs:
- `source_repo` (string, required) — the publishing repository's short name (e.g., `livespec-runtime`).
- `tag` (string, required) — the published release tag (e.g., `v0.3.0`).
- `release_url` (string, required) — the GitHub release page URL, used in downstream PR descriptions.

Secrets: `APP_ID`, `APP_PRIVATE_KEY` (inherited via `secrets: inherit`).

Behavior: discovers siblings per §"Sibling discovery", excludes `source_repo` from the dispatch matrix, fires a `repository_dispatch` event to each remaining sibling carrying the payload contract per §"`repository_dispatch` payload contract". A 404 from any sibling (e.g., App not installed) surfaces as a workflow annotation and does NOT fail the dispatch loop (soft-fail per §"Soft-fail semantics").

#### `reusable-bump-pin-from-dispatch.yml`

Per-consumer handler invoked by each sibling's own `bump-pin-from-dispatch.yml` shim on `on: repository_dispatch: types: [sibling-released]`.

Inputs:
- `source_repo` (string, required) — extracted from `client_payload.source_repo`.
- `tag` (string, required) — extracted from `client_payload.tag`.
- `release_url` (string, optional) — extracted from `client_payload.release_url`; included in the PR body for traceability.

Behavior: clones the consumer repository, runs the pin-autodiscovery walk per §"Pin autodiscovery rules", edits every matching pin to `tag`, runs `just check`, commits with the `chore:`-prefixed message per §"PR commit-message convention", opens an auto-merge PR via the GitHub App per §"GitHub App auth model".

When autodiscovery surfaces zero matching pins (the consumer does not depend on `source_repo`), the workflow exits `0` with a workflow annotation explaining the no-op.

When the consumer's `.vendor.jsonc` carries an entry for the normalized form of `source_repo`, the workflow ADDITIONALLY invokes the consumer's `just vendor-update <lib>` recipe before running `just check`, so re-vendoring lands atomically in the same commit as the manifest pin update.

#### `reusable-pin-freshness.yml`

Periodic safety-net workflow invoked by each sibling's own `pin-freshness.yml` shim on `on: schedule: cron: ...`.

Inputs:
- `staleness_threshold_releases` (integer, optional, default `1`) — the number of intermediate releases beyond which a pin is considered stale.

Behavior: runs the pin-autodiscovery walk per §"Pin autodiscovery rules", queries each discovered source repository's latest release tag via `gh release view --json tagName`, and opens a bump PR per `(source_repo, current_pin, latest_tag)` triple where the latest tag is at least `staleness_threshold_releases` ahead of the current pin. Reuses the bump-PR-opening machinery from `reusable-bump-pin-from-dispatch.yml`.

The freshness workflow is the safety net for missed dispatches, releases that occurred before this surface was wired in, and any future class of dispatch failure that does not auto-recover.

### Pin autodiscovery rules

The pin-autodiscovery walk inspects the consumer repository for every supported pin format and yields a normalized `(pin_format, file_path, pin_key, current_value)` record per discovered pin. The walk MUST cover the following formats:

- **`.livespec.jsonc` `compat.pinned`** — every top-level key in `.livespec.jsonc` whose value contains a `compat` object with `pinned` and `livespec` fields. The top-level key's name is the pin's consumer-self-identifier; the pin's source repo is always `livespec` (a `compat.pinned` field always pins the consumer to a livespec release tag).
- **`pyproject.toml` `[tool.uv.sources]`** — every entry in `[tool.uv.sources]` whose `git` field matches the source repository's GitHub URL. The `tag` field is the pin's current value.
- **`.vendor.jsonc`** — every entry in `.vendor.jsonc`'s `libraries` array whose `name` matches the normalized form of the source repository's Python package name (hyphen-to-underscore for Python package convention). The `upstream_ref` field is the pin's current value.
- **`.copier-answers.yml` `_commit`** — the singular `_commit` field, present in projects generated via `copier copy` / `copier update`. The implicit source repository is the one referenced by `_src_path`; the field's value is a git ref (commit SHA or tag).

The walk MUST be tolerant of missing files — a consumer without a `.vendor.jsonc` simply yields no `.vendor.jsonc`-format records. The walk MUST also be tolerant of pin formats it does not recognize; an unrecognized format produces no record and a workflow annotation noting the unrecognized file for human inspection.

Source-repository-name normalization for `.vendor.jsonc` matching: replace every `-` in the source repo's short name with `_` (e.g., `livespec-runtime` matches `livespec_runtime`). Other pin formats use the source repo's short name verbatim.

### `repository_dispatch` payload contract

Every `repository_dispatch` event fired by the coordination surface MUST carry the following shape:

```json
{
  "event_type": "sibling-released",
  "client_payload": {
    "source_repo": "<short-name>",
    "tag": "<vX.Y.Z>",
    "release_url": "<GitHub release page URL>"
  }
}
```

The `event_type` value is fixed at the literal `"sibling-released"`. The `client_payload` shape is the semver-stable contract; adding new fields is a MINOR bump, removing or renaming existing fields is a MAJOR bump.

### GitHub App auth model

The coordination surface MUST authenticate via a GitHub App installation token, NOT via `GITHUB_TOKEN`. The App MUST be installed on every sibling repository and MUST hold the following permissions:

- `contents: write` — to commit the bump and create branches.
- `pull-requests: write` — to open the bump PR.
- `metadata: read` — to read repository metadata for sibling discovery.

The token is minted at runtime via `actions/create-github-app-token@v1` with the App's `APP_ID` and `APP_PRIVATE_KEY` secrets passed via `secrets: inherit` from each consumer shim. The App's private key has no calendar expiration, so token expiry does NOT silently break the surface.

The rationale for App-token over `GITHUB_TOKEN` mirrors the existing `auto-update-branches.yml` and `auto-enable-merge.yml` choices in livespec: pushes authored by `GITHUB_TOKEN` do not trigger downstream CI workflows (GitHub's workflow-recursion ceiling), which would leave bump PRs permanently `BLOCKED` with no CI re-runs against the updated head SHA.

### Soft-fail semantics

A 404 response from a target sibling during dispatch (App not installed on that sibling, or repository missing) MUST surface as a workflow annotation and MUST NOT fail the dispatch loop. Other 4xx and 5xx responses MUST fail the dispatch job for that sibling but MUST NOT cascade to other siblings (each sibling occupies its own matrix entry with `fail-fast: false`).

### PR commit-message convention

Bump-pin PRs MUST use the Conventional Commits `chore:` prefix on the PR title and the commit subject. The `chore:` prefix is explicitly excluded from triggering a release-please version bump per the Conventional Commits → semver mapping at `livespec/SPECIFICATION/contracts.md` §"Plugin versioning"; this prevents an automatic-bump-PR cycle where a sibling's release triggers a bump PR in this library which triggers another release of this library which triggers another round of bump PRs.

The PR title template is `chore(deps): bump <source_repo> pin to <tag>`. The PR body MUST include the `release_url` from the dispatch payload for traceability.

### Pin-freshness threshold defaults

The `staleness_threshold_releases` input to `reusable-pin-freshness.yml` defaults to `1` — any pin one or more releases behind the latest tag triggers a bump PR. A consumer MAY override via the input on its `pin-freshness.yml` shim if its cadence demands higher tolerance for drift.

The cron cadence is consumer-owned; the dev-tooling reusable workflow accepts whatever schedule the shim declares. The recommended cadence is daily (`0 13 * * *`) — frequent enough to catch missed dispatches within one business day, infrequent enough to avoid noise.

### Fallback to known-good pin

When a bump PR's `just check` fails on the new pin, the bump PR MUST remain open with the check failure marked. The consumer's last green pin remains the active pin on `master` until the failure is resolved.

Resolution paths, in order of preference:

1. **Auto-rollback (future).** A planned future workflow `reusable-pin-rollback.yml` MAY revert the pin to the most recent commit on `master` whose `just check` last passed, on detection of N consecutive failing bump attempts. This future surface is OUT OF SCOPE for v1 and is named here only to reserve the design space; a subsequent propose-change cycle defines its contract.
2. **Manual pin to known-good.** A human contributor edits the pin file directly to a known-good tag, commits with the `chore:` prefix per §"PR commit-message convention", and merges. This is the v1 fallback for any failure the planned auto-rollback would have handled.

The `bump-pin` workflow MUST NOT silently force-push past a failing check. The auto-merge label is the consumer's standard auto-merge label (configurable per consumer via repo settings); the workflow only attaches the label, it does not bypass branch-protection gates.

### Self-hosting

The library is itself a sibling consumer of its own coordination automation surface. The library's own `.github/workflows/` MUST include the three consumer shims (`release-dispatch.yml`, `bump-pin-from-dispatch.yml`, `pin-freshness.yml`) and the repository MUST carry the `livespec-sibling` topic. The shims delegate to the reusable workflows at the library's own currently-pinned release tag; consequently the library pin-and-bumps itself when livespec releases.

The self-hosting bootstrap (initial publication of the coordination workflows) is a one-time manual step performed by a human contributor; thereafter the system perpetuates via its own dispatches. The bootstrap is described in this library's `non-functional-requirements.md` §"Coordination-surface bootstrap procedure" (which lands as a separate amendment in the same revise pass that lands this contract).

### Migration notes

The following content currently in `livespec/SPECIFICATION/contracts.md` MUST migrate here as part of this proposal's acceptance, and MUST be replaced by a cross-reference in livespec's spec:

- The "auto-merge bot architecture deferred; v1 MAY rely on manual bump-pin PRs" half-sentence at livespec contracts.md §"Cross-repo coordination — pin-and-bump" — superseded by this section's full automation contract.
- The reusable-workflow inventory specifics from livespec contracts.md §"Shared code sync — livespec-dev-tooling" — the consumption-shape sentence stays in livespec, the workflow inventory is now this library's surface.
- The specific surface enumeration in livespec contracts.md §"Shared code sync — livespec-dev-tooling" — the semver-stable surface PRINCIPLE stays in livespec, the specific list of covered surface elements is now extended below in §"Semver coverage extension".

### Semver coverage extension

The semver-stable surface declared in `constraints.md` §"Semver discipline" is hereby extended to cover the following new elements introduced by this section:

- Each reusable workflow's path AND its declared inputs / outputs / secrets contract.
- The `repository_dispatch` payload contract (event type + `client_payload` shape).
- The sibling discovery mechanism (the `livespec-sibling` topic name).
- The pin autodiscovery rules' format coverage (adding a new pin format is a MINOR bump; removing or breaking compatibility of an existing format is a MAJOR bump).

Pure implementation changes that preserve every element above MAY land via PATCH bump per the existing discipline.


## Proposal: extend-constraints-md-network-io-and-semver-coverage

### Target specification files

- SPECIFICATION/constraints.md

### Summary

Two targeted extensions to constraints.md. (a) Extend §"No network I/O" to clarify that the no-network-I/O constraint applies only to Python check modules; reusable workflows and composite Actions MAY perform network I/O (and MUST, for the cross-repo coordination surface's gh api invocations). (b) Extend §"Semver discipline" to add the cross-repo coordination automation surface elements to the semver-stable surface enumeration: each reusable workflow's input/output schema, the repository_dispatch payload shape, the sibling discovery mechanism (livespec-sibling topic name), and the pin autodiscovery rules' format coverage are all subject to MAJOR-bump-on-breaking-change.

### Motivation

The existing §"No network I/O" reads as if network I/O is universally forbidden, but the constraint's intent is determinism of check modules — workflows have always been able to use gh and other network tools. The new cross-repo coordination surface makes this distinction load-bearing, so the constraint should state it explicitly. Similarly, §"Semver discipline" currently enumerates three surface elements (check invocation set, composite Action contracts, reusable workflow contracts); the new cross-repo coordination surface adds four more that must be covered by the same MAJOR-bump-on-break discipline. Without these extensions, the surface contract is implicit and subject to drift.

### Proposed Changes

Two targeted extensions to `SPECIFICATION/constraints.md`.

**(a) Extend §"No network I/O".** Replace the existing single paragraph with the following expanded version:

> No check module under `livespec_dev_tooling/checks/` MAY perform network I/O. Reading the local filesystem and invoking project-local subprocesses (git, ruff, pyright, pytest, mise) is permitted; reaching out to a remote HTTP/HTTPS/SSH endpoint, opening a socket, or invoking a tool that does any of the above is forbidden. The constraint exists so that every check is deterministic against the consuming repo's working tree alone, regardless of network availability.
>
> Reusable workflows under `.github/workflows/` and composite Actions under `.github/actions/` MAY perform network I/O. The cross-repo coordination automation surface (per `contracts.md` §"Cross-repo coordination automation surface") depends on `gh api` invocations for sibling discovery, repository dispatch, and bump-PR creation. The no-network-I/O constraint is scoped specifically to Python check modules because their determinism guarantee is load-bearing for the consumer's local `just check` and CI gates; workflow-level network I/O runs in GitHub-Actions-managed environments where network availability is itself part of the runtime contract.

**(b) Extend §"Semver discipline".** Replace the existing surface enumeration (the bulleted list of three elements) with the following expanded version:

> The library's semver-stable surface is:
>
> - The `python -m livespec_dev_tooling.checks.<slug>` invocation set (each slug's argv contract and exit-code semantics).
> - The composite Action paths and their declared inputs / outputs.
> - The reusable workflow paths and their declared inputs / outputs / secrets / concurrency.
> - The cross-repo coordination automation surface elements pinned by `contracts.md` §"Cross-repo coordination automation surface" §"Semver coverage extension" — the `repository_dispatch` payload contract, the `livespec-sibling` GitHub topic name, and the pin autodiscovery rules' format coverage.

The remaining paragraphs of §"Semver discipline" (the MAJOR / MINOR / PATCH bump rules and the Conventional Commits → release-please mapping) are unchanged.

Rationale for both extensions: the existing constraints were authored before the cross-repo coordination automation surface existed. Both sections are correct in their current form for the original surface but silent on the new surface's distinguishing characteristics (workflows do network I/O; the new surface adds three semver-stable elements). The extensions make the constraints' scope explicit.

