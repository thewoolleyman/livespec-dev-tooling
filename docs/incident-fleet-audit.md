# The incident fleet audit

`just incident-fleet-audit` and `just incident-enable <owner/repo>` implement the closing
paragraph of `SPECIFICATION/contracts.md` §"Expedited incident execution". Work item
`livespec-dev-tooling-3wcldx`, plan `expedited-incident-response-flag`.

## What is read, and from where

Nothing here is steerable by the caller. There is no owner switch; the claims are the file this
code was released with; the consumer clones are the siblings of this code's primary checkout; the
account is the one the account database names for the running uid. No environment variable moves
any of them. The recipes run `uv run --no-sync` so the audit never rewrites the venv it reads.

| Source | Read |
| --- | --- |
| Membership and identity | livespec core's `.livespec-fleet-manifest.jsonc` from core's default branch over the git transport, read twice. The second read must be byte-identical (by digest) to the first, or the manifest is unauthenticated. |
| Claims | `config/incident-fleet-evidence.json`: the operator's statement of disposition, owner, proof and the release build a row expects. A claim never carries serving evidence; a `serving_build` key is refused. |
| Serving version | One reader per capability, below. Each is read twice, independently; a claim counts only when both reads equal its release build. |

A read that cannot be taken is **unverified**: the row is `unclassified`, the consumer is left out
of the ready list and the findings name the consumer and the capability.

## One reader per capability

| Capability | Serving version | Unverified when |
| --- | --- | --- |
| `gate-readers` | the commit `direct_url.json` records for `livespec_dev_tooling` in the consumer's own `.venv` (release-keyed when the consumer runs its own source, below). The consumer's interpreter is never run. | no clone, no `.venv` (for example `openbrain`, `resume`, `homelab` on a host that has none), no or several installs, an install that is not a recorded revision, a tracked modification in an own-source checkout (an untracked file does not count), or a release-keyed reason below |
| `templates` | the one commit that every pin of this library's reusable workflows (`.github/workflows/...@ref`) and composite actions (`.github/actions/...@ref`) names, across ALL of the consumer's default-branch `.github/workflows/*.yml` files, read from one blobless clone (a tag is resolved to its commit); a consumer that runs its own local workflows (this library always, any other consumer with no such pin) is release-keyed against its default-branch commit, below | an unreadable workflow directory or file, pins that disagree, a ref that names no tag or commit, no template use at all (for example `dolt-server`) |
| `driver-hooks` | `plugin=<commit>` for every plugin the consumer's `.claude/settings.json` enables, from the install record whose project path is the consumer's clone, with its plugin cache present | an enabled plugin that is not installed for this project, no cache, an unreadable registry |
| `recovery-authorization` | the controller's serving version plus the single always-bypass GitHub App on the consumer's default-branch ruleset | no verified controller, no or several bypass actors, not an always-bypass Integration |
| `independent-controller` | `v<version>@<commit>` of the venv the RUNNING `livespec-incident-observer.service` main process was started from, and only if the process started after that install | the unit is not `active`/`running`, the process is not the packaged observer command, no single recorded install, the process predates its install, or the repository is not the one the observer serves (`thewoolleyman/livespec-dev-tooling`) |

The controller reader never opens the protected `controller.json` (the operator cannot read it, and
a release name written there is a claim) and never consults the auditor's own package.

## Release-keyed rows: a consumer that serves from its own source

Two reads would otherwise key to the consumer's own commit: the gate readers of a consumer whose
`.venv` is an editable install of its own checkout, and the templates of a consumer that runs its
own local workflows. A claim committed to `config/incident-fleet-evidence.json` can never name the
commit that contains it, so those reads are keyed to a RELEASE
(`livespec_dev_tooling/_incident_fleet_release_keyed.py`):

- The serving build is the newest `vX.Y.Z` tag that is an ancestor of the serving commit (the
  checkout's HEAD, or the default-branch tip read in the consumer's clone on this host). The tag's
  commit must be confirmed on the remote; so must every release a claim names.
- A claim for such a row names a release (for example `v1.193.0`), never a commit. It may name an
  older release than the newest: the claim is judged against the release it names.
- It is judged PER ROW. A row serves the claimed release only while every file of that row's
  surface at the serving commit is byte-identical to that release's. Commits, and later releases,
  that touch only files outside the surface leave the row serving. A surface is the exact file set
  its reader serves from (`livespec_dev_tooling/_incident_fleet_surface_files.py`): the surface's
  roots, pinned by a test, plus the in-package modules they import or run and the local workflows
  and actions they call. It is never the whole tree, because this repository's master moves many
  times an hour and cuts several releases a day.
- Releases are compared newest first, one `git diff --name-only` per release shared by every
  surface of the capability. A surface stops serving at the first release that changed one of its
  files, and every older release is judged changed since it too, naming the files found changed
  there, without another comparison. Comparing stops once no surface still serves.
- An unclassified release-keyed row names its reason in the findings: no release ancestor, a tag
  the remote does not confirm, the surface's changed or absent files, a claim naming a release that
  is not an ancestor of HEAD, a release whose changed files could not be read, or a tracked
  modification.
- The `serving` line prints the newest release, `release vX.Y.Z at HEAD <commit>`; each row that
  classifies through a release claim prints the release its claim named, at that HEAD.

On the dev host (2026-11-10) only `thewoolleyman/livespec-dev-tooling` is read this way, for both
capabilities.

## The ready list and enablement

A consumer is ready when every row is classified, none is `deliberately-normal`, at least one is
`implemented`, and all five capabilities were read. A `not-applicable` row needs a recorded reason,
the manifest identity and a serving version equal to its release build, and never makes a consumer
ready on its own. `just incident-enable` runs its own fresh audit and, only for a ready
repository, writes the enablement record to the controller installation that serves it, through
that installation's control route (`POST /enablement` on its local listener, with the projected
`LIVESPEC_INCIDENT_CONTROL_SECRET`; run it through the credential wrapper). The step posts to
`127.0.0.1:<port>`, so it MUST run on the controller host itself (for this repository's production
installation, the `vmi3006760` dev host, port 8765): from any other host it reaches no installation
and refuses as unreachable. The controller confirms
the manifest identity with its own two reads of core's default branch before it retains anything,
answers an exact retry with the retained record, and serves the reading on the read-only query
route (`/enablement/read`). The step refuses, naming the missing evidence (or the
unauthenticated-manifest finding), for any other repository, and names the controller's refusal,
an unreachable controller, or a repository no installation serves. No dev-host file stands in for
the record (`livespec-dev-tooling-qmuk7z`, spec v205). The fence is armed and disarmed by explicit
writes to the same route (`/fence/arm`, `/fence/disarm`); arming is refused until a record binds
the current identity. The controller refuses any of these operations, retaining nothing, when it
names a repository other than its installation's.

## The readers at each vantage

Once an incident flag selects expedited repair or emergency revert in an ordinary invocation, the
execution resolver reads the record before it produces the context (`livespec-dev-tooling-exdkra`).
A trusted normal-master or normal-factory-follow-up origin, and an invocation with both flags
absent, never read it. The reading is one of `enabled`, `absent`, `stale`, `revoked`,
`unavailable` or `no-installation`, and each vantage records it in the artefact it already
produces:

- **The dev-host hooks** ask the installation `INSTALLATION_PORTS` names for the repository
  (`POST 127.0.0.1:<port>/enablement/read` with the projected
  `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN`). They compare the identity the controller confirmed
  against their own read of core's default branch, and read `stale` when the two differ. The
  reading is the `enablement` field of the hook's printed receipt, or of its revert hand-off.
- **The incident CI entrance** reads the same route at plan time through the observer URL. The
  reading is the plan's `enablement` field. It is not part of the plan identity that the entrance
  rechecks, so a reading that changes between rechecks refuses nothing while the installation is
  disarmed.
- **The controller** reads its own record. Its `/arm` receipt carries the reading as
  `enablement`. Its `/current` and `/admitted` answers read the record only while the fence is
  armed, which is the only time they can refuse.

While the installation is disarmed, no vantage refuses on its reading. While it is armed, a
vantage that holds the installation's answer refuses expedited repair on every reading but
`enabled`, and refuses an emergency revert on every such reading except `unavailable`. The refusal
is the named `incident-not-enabled` configuration refusal, and it names the repository, the
installation and the reading. A vantage that cannot reach its installation reads `unavailable`
with no arming state, records that, and refuses nothing. The controller's own armed answers are
the fence that no entrance can skip.

## The committed claims

`config/incident-fleet-evidence.json` holds only claims backed by something read from the fleet
(`livespec-dev-tooling-v46q5g`, `livespec-dev-tooling-ri2lwi`). Each claim names its disposition,
owner, proof reference and the serving build read for its capability on the day its proof names,
bound to core's manifest `59912fe1…`. A claim goes stale when that build moves (a pin bump, a
plugin update, a release that touches a release-keyed surface) or when core's manifest changes;
its row then prints `unclassified` and the finding names the build the claim expected against the
one read. Refresh the claim from a new read; never copy the new serving value in without re-reading
what it proves. `tests/livespec_dev_tooling/test_incident_fleet_committed_claims.py` holds every
claim to its schema: a known surface once per consumer, a disposition, an owner, a proof reference,
a reason or an incident record, a release build in its capability's serving form, and a binding to
the committed manifest identity and one of its applicable consumers (fixture
`tests/livespec_dev_tooling/fixtures/incident_fleet/core-fleet-manifest.jsonc`). It names no claim's
value, so a refresh edits only this file. The same checks run on
`tests/livespec_dev_tooling/fixtures/incident_fleet/claims-wellformed.json`, broken one field at a
time.

Fourteen claims: four `implemented` and ten `not-applicable`.

- `Normal master context` for this library (gate-reader capability, release-keyed, `v1.198.0`),
  `implemented`. Incident chain `livespec-dev-tooling-t26bbr` landed two expedited commits on
  master, and each master push still ran the complete normal job graph with the incident flags
  forced absent. The same-item unexpedited factory repayment livespec-dev-tooling#4204 then merged
  on full checks and removed the repair marker, and `complete-incident` closed the chain at
  generation 19. The surface's five files are byte-identical from `v1.195.0` through `v1.198.0`.
  The claim's `proof_ref` names the runs, commits and reads.

- `Fast-gate timing`, `Focused test selection` and `Touched-file coverage` for this library
  (gate-reader capability,
  release-keyed, `v1.198.0`), `implemented`. The committed, authenticated records for the
  closed `livespec-dev-tooling-t26bbr` chain and the `livespec-dev-tooling-gig42c` R3 scratch
  drill exercise these local-gate behaviors; the former's normal factory repayment is
  livespec-dev-tooling#4204. Each claim identifies the incident record and its source roots,
  and only names `v1.198.0` because that exercised release's complete surface is unchanged at
  the serving checkout.

- `Generated projects` for this library (release-keyed, `v1.198.0`) and, at the one release of this
  library's templates that every pin of its reusable workflows and composite actions names in each
  repository's default-branch workflows (read 2026-11-12), for `livespec-console-beads-fabro`
  (`v1.197.0`) and for `livespec-driver-claude`, `livespec-driver-codex`, `livespec-driver-pi`,
  `livespec-overseer` and `livespec-runtime` (`v1.199.0`). Each default-branch tree holds no
  `copier.yml`, `.copier-answers.yml` or `.jinja` path. Core's `copier.yml` scaffolds
  `livespec-impl-*` orchestrator plugin repositories, and the two fleet repositories generated from
  it, `livespec-orchestrator-beads-fabro` and `livespec-orchestrator-git-jsonl`, each carry a
  `.copier-answers.yml`.
- `Focused test selection`, `Touched-file coverage` and `Full coverage producers/consumers` for
  `hetzner-xubuntu-info`, at the gate readers its dev-host `.venv` records (`v1.195.0`): it has no
  test file and runs neither pytest nor coverage, locally or in CI.

Every other row stays `unclassified`, and the findings name each row's missing evidence: no
committed claim, a claim bound to another manifest identity, a malformed claim, a claim for a
runtime surface of an instruction-only adopter, an unreadable serving version, a release build that
is not the serving version read, a serving version an independent re-read did not confirm, or a
release-keyed reason above. The reasons behind those rows, measured on 2026-11-11:

- **Not adopted yet.** No installed plugin build (core, the Claude driver, the orchestrator) carries
  incident guidance, and no consumer other than this library, core, the orchestrator, the overseer
  and the Codex driver references the flag. A row is `deliberately-normal` only when someone rules
  that it is. Not having adopted the feature yet is not that ruling.
- **The adopt-or-normal ruling (2026-11-12).** The maintainer ruled, in words recorded verbatim on
  epic livespec-dev-tooling-bqnzcm ("OK stick with just the 4, lets get this plan done and
  deployed and ready for retro"), that `livespec-dev-tooling`, `livespec`,
  `livespec-orchestrator-beads-fabro` and `livespec-overseer` adopt expedited incident mode, and
  that the other 18 manifest consumers are `deliberately-normal`. Each of their claims cites that
  ruling: who made it, when, and where it is recorded. A `deliberately-normal` row classifies from
  the ruling alone, with no release build and no serving read. The one read that contradicts it is
  a serving version of the consumer's own incident installation (`independent-controller` or
  `recovery-authorization`), which leaves the row `unclassified` and names the contradiction. A
  shared gate-reader, template or driver-hooks build is printed and contradicts nothing. A consumer
  with any `deliberately-normal` row is never ready, and one whose rows are all
  `deliberately-normal` or `not-applicable` is not named for lacking serving-version evidence. An
  instruction-only adopter's two guidance rows carry a claim of either kind, and an `implemented`
  one needs no incident record (spec v207, livespec-dev-tooling-kddu2b).
- **No `implemented` claim.** One needs the incident item, the cumulative scope digest and the
  normal factory proof of an incident that exercised the surface, read from that incident's record.
  The remaining local-gate rows are deliberately still unclassified: `Hook installation and
  wiring`, `Pre-commit before mode selection`, `Commit-msg and TDD`, `Pre-push`, `Explicit
  commands and parallel aggregation`, `Full coverage producers/consumers`, `Normal evidence
  caches`, and `Agent tool and stop guards`. `Commit-msg and TDD` and `Full coverage
  producers/consumers` now import `flake_retry_filer.py`, which differs from the v1.198.0
  exercised surface. The other local-gate rows lack a matching exercised incident receipt. The
  dev-host drill `livespec-dev-tooling-bqnzcm.3.1` must exercise and claim all eight; this audit
  is not weakened to classify them early.
- **Open carriers in this library.** The controller and recovery rows that this library could
  classify each have an open carrier or a proof the observer docs still owe. These are First-failure
  observer (`q6eyrr`, `jpfdcx`), Existing reconciler coordination (`ariayn`), Failed-run retention
  (`zapgpu`), Workflow-edit authorization (`j2rdde`), Emergency revert and merge authority
  (`fdquen`), and Recovery dependency independence and Late regression/cleanup (the outage and
  recovery drills `docs/incident-observer.md` lists as still required). Operator factory routing is
  in the overseer's installed prose but not in the orchestrator's plan, implement or drive prose.
- **Unreadable serving builds.** A row whose capability reads `-` cannot classify whatever it
  claims. This covers every recovery-authorization and independent-controller row outside this
  library, the template rows of `dolt-server`, `hetzner-xubuntu-info`, `homelab`, `openbrain` and
  `resume`, and five of the seven instruction-only adopters, whose enabled plugins are not
  installed for their clones on this host. The other two, `local-llm` and `vps-info`, read a
  driver-hooks build, but that build carries no incident guidance.

## Not done by this item

- **Arming production.** Every reader ships disarmed. The production installation's fence is armed
  only after the fleet audit lists this repository ready, the step records it, and a scratch-branch
  proof reads `enabled` at the hook and in the CI plan (spec v205's ordering).
