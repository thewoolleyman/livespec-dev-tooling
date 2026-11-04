# CI job boundaries and protected session integration review

This design review preserves a proposed integration diff for the existing
`livespec-dev-tooling-egy3ri` / `livespec-dev-tooling-47ij37` carriers under plan
`livespec-dev-tooling-bqnzcm`. It changes no operational workflow. The two
companion `.patch` files are review artifacts; copying them into this research
directory does not apply their contents. They are not an activation, a
ratification, factory proof, serving-build evidence or workflow authorization.
The existing maintainer local-only exception permits developing this plan;
ordinary credential-wrapped gates still govern its actual source publications.

## Observed integration defect and correction

The earlier review-only preflight installed its independently approved release
in the `incident-ci-mode-fence` job's `RUNNER_TEMP`. The direct Action then
invoked the same pathname from a different job. Jobs have independent runner
filesystems: an opaque workflow session handle cannot transport an upstream
virtual environment. The earlier preflight exposed only `incident`, without
an explicit output carrying its session handle. Neither defect was a shipped
production capability; both were defects in the prior proposed diff.

The corrected dev-tooling patch gives every incident direct Action invocation
its own approved Git-tag/immutable-commit bootstrap and frozen, isolated
installation. A fresh temporary directory supports repeated Action calls in
one job. Only that invocation's bootstrap step output supplies its Python
interpreter. No upstream executable artifact, candidate checkout fallback,
latest-tag guess or consumer virtual environment supplies trusted code.

The reusable workflow explicitly transports the opaque session handle,
protected observer URL and query-only secret, and requests OIDC permission for
its own job. The direct client receives current repository, actual PR/base/head,
run/attempt and approved tag/revision inputs. The concrete workflow and core
template expose the proposed preflight `session` output and explicitly refuse
an empty output even when preflight exits zero. The packaged inventory digest
binds this exact proposed concrete workflow. All 71 existing normal members
and the coverage producer/consumer dependency remain. The normal direct Action
command is unchanged. The root quality jobs still run their complete normal
commands; no reduced incident branch is armed by these artifacts.

Inherited Git configuration was a second real defect in the draft. An actual
Git regression set `GIT_CONFIG_COUNT=1` and `core.hooksPath` to a candidate
post-checkout hook: the exact approved release checkout executed it. The
regression failed as expected (**1 failed in 3.61 seconds**) before correction.
Every proposed bootstrap now runs child tools under `env -i`, fresh HOME/TMPDIR,
fixed runner binary paths, disabled Git global/system configuration and system
attributes, empty Git initialization templates,
and the pinned setup-uv step's explicit absolute `uv-path` output instead of
PATH discovery. Candidate UV/Python/Git variables are not forwarded. The
reusable incident branch no longer runs candidate toolchain setup before that
bootstrap. [The pinned setup-uv action declares `uv-path`](https://github.com/astral-sh/setup-uv/blob/d0cc045d04ccac9d8b7881df0226f9e82c39688e/action.yml).

This is child-environment isolation, not a protected-runner proof. Absolute
binaries and step outputs are trusted only on a provisioned clean runner with
protected workflow ordering. Arbitrary candidate code executed earlier in the
same job could replace those binaries, tamper with outputs, or run through shell
startup before the scrub. A sanitizer cannot restore that trust; the eventual
service must authenticate a protected workflow whose ordering and execution
isolation prevent it. Package build dependencies and external release/registry
services remain outside these controlled fixture proofs. No install is claimed
secure against an already compromised runner.

## Proposed prerequisite interface

These are exact proposed callsite obligations, not a claim that either module
or endpoint exists. At this review, `incident_ci_session` and `/ci/session`
were unshipped. A later implementation may revise the interface deliberately;
these patches must then be regenerated and reviewed against that implementation.

| Boundary | Proposed call and required result |
| --- | --- |
| Protected preflight | `python -I -m livespec_dev_tooling.incident_ci_session preflight` may write `session=<opaque canonical handle>` to `GITHUB_OUTPUT` only after authenticated admission. Missing output refuses before candidate execution. |
| Direct member | `python -I -m livespec_dev_tooling.incident_ci_session direct --session <handle> --check-name <literal> --working-directory <path>` uses the job's own approved interpreter and fresh job OIDC. Free-form extra argv remains refused pending its structured contract. |
| Reusable workflow | An explicit optional `workflow_call` secret transports only the query token. Each matrix job requests `id-token: write`, `actions: read`, `pull-requests: read` and `contents: read`. Callers must permit those scopes. |
| Session admission | The controller independently binds protected/reusable OIDC workflow identity and immutable revision, repository, real PR/base/head, run id/attempt, approved release tag/revision, registered consumer manifest, retained observer arm/digest, and current canonical mode epoch. A caller-provided handle or token grants none of these. |
| Member outcome | Authenticated real forge job/check identities, exact graph and produced/consumed artifacts determine conclusions. Candidate JSONL or an asserted check name cannot authorize success. |
| Final aggregate and merge | Recheck current epoch, mode, PR/head/base, run/attempt and session against actual completed work; stale or unobservable state refuses. The actual merge authority must participate immediately before its effect. |

Query-only credentials cannot arm, bind, publish genesis or mint lifecycle
ownership. Every member independently authenticates its current job rather
than treating another job's admission as permission to execute. A PR-editable
workflow cannot attest its own protected provenance; the trust policy must name
a normally released immutable reusable/required workflow boundary. Different
consumers need their own registered normal graph; dev-tooling's 71-member
inventory cannot stand in for another repository's manifest.

## Canonical contract and implementation boundary

Dev-tooling `SPECIFICATION/contracts.md`, “Expedited incident execution”,
already requires head/mode changes to invalidate stale verdicts, exact repair
PR/head projection, complete normal master, independent observer admission and
fenced recovery. Implementing a mode epoch, strict session identity and final
checks can conform to those existing requirements without inventing a new
incident policy exception. A local observer invalidation primitive is useful
preparatory source work, but it is not complete all-writer or premerge proof.

Actual callsites must be coupled. At this review,
`.github/workflows/auto-enable-merge.yml` enabled ordinary `gh pr merge --auto
--rebase` without consulting an incident epoch. Adding label-event CI alone
cannot invalidate a previously successful same-head required check before
GitHub can merge it. Observing `/current` more often does not close that race.
The rollout must ensure every sanctioned mode/label writer invalidates old
admission before mutation, and provision a forge-enforced merge path that checks
the same fence. Out-of-band human/UI label edits and independent merge actors
must be covered by that policy or explicitly prevented from admitting an
incident. A webhook arriving after mutation is not the required pre-mutation
exclusion. This is missing integration and provisioned authority, not evidence
that the preflight-only diff should be activated.

Canonical absent-root publication is a separate prerequisite. Orchestrator
`SPECIFICATION/contracts.md`, “Expedited incident lifecycle”, already requires
server-side conditional exclusion across incident/factory writers and a named
capability refusal when unavailable. The existing `bd-ib-dzbwaq` amendment
`incident-authority-genesis-and-pre-pr-carrier` specifies the stronger atomic
first-root plus exact expected dispatch claim, branch-reserved → head-published
→ authenticated PR-bound carrier, lost-reply receipts and all-writer factory
transfer. Its public generic claim-token prerequisite remains the existing
`bd-ib-jjws2` owner. Do not treat a local observer epoch, metadata update,
insert-only comment or new local session store as that missing canonical
provider. Implement canonical ownership through those existing owners and
verify their normal release/adoption; do not file a duplicate or dispatch a new
implementation of any already hand-landed plan child.

The two artifacts remain unready for operational publication until protected
session code, authenticated outcome accounting, mode/all-writer coupling,
actual merge policy, released serving adoption and fleet proof exist. Their
workflow line changes also need the maintainer's real `approval:workflow-edit`
on the existing carrier; an agent never sets it. The product inventory constant
would require genuine Red/Green before governed publication. Core template
adoption follows its owning spec/release route. These conditions do not block
independently useful source changes that retain their narrower honest scope.

## Exact artifacts and measured validation

| Artifact | SHA256 |
| --- | --- |
| `003-ci-job-boundary-dev-tooling.patch` | `adc182ab295b1a4f4d0ac29597be02422667dd41c74e7a6c3eae627e6f43a767` |
| `003-ci-job-boundary-livespec-template.patch` | `16aaf1155e6ed20245282aff79daf4edc05d0222f1fda137fc5aa475defc5b62` |
| Resulting proposed concrete `ci.yml` | `9294fe8dc081a776f74eb01fa2aeaebdc8254de97b4dbe6b7147853b4ec5741a` |
| Proposed direct Action | `25bde5a48cf1de7b9c6f6fd0d94617906cb062f3f888ba2b37631517736172d0` |

The temporary pack `/tmp/bqnzcm-ci-job-boundary-review-20261104` contains the
fixture scripts, saved before/after trees, rendered template, actionlint
composite harness, exact interface JSON and logs. Its final actual test command
was `mise exec -- uv run pytest -q
/tmp/bqnzcm-ci-job-boundary-review-20261104/test_job_boundary.py`: **13 passed in
16.72 seconds**, recorded exit 0. Tests use actual Git operations and frozen uv
installs of a dependency-free fixture release. They reproduce the prior absent
cross-job interpreter; exercise independent job installs, repeated same-job
invocations, wrong commit refusal and poisoned candidate cwd isolation; prove
missing session module fails without candidate fallback; inspect exact normal
command/OIDC/secret transport; execute empty session-output refusal; prove the
actual candidate post-checkout hook no longer runs; and refuse relative uv paths
while ignoring candidate PATH, UV/Python/Git environment configuration.
The controlled `gh` adapter is a fixture, not authenticated production release
or OIDC evidence.

`actionlint` exited 0 for the proposed concrete and reusable workflows, rendered
core template and typed composite harness. `git apply --check` exited 0 for both
patches against their saved baselines and the actual dev-tooling/core primary
checkouts. The installed CI parser independently found all 71 original normal
members and their retained coverage dependency; workflow and embedded inventory
digests matched. The primary heads observed when retaining evidence were
dev-tooling `13f542be9c02170ce1a1c3a06aec1cf20e405381` and core
`34e18ec43ff68aaee700661603229218f7339b39`; the artifacts are proposed diffs,
not claims those heads include their contents.

Temporary evidence hashes are: `test_job_boundary.py`
`bfcc2c806b460d254f6c51c588d572155e63626d21b72c244ddac7e29d0aa563`,
`bootstrap_fixture.py`
`2e7dbd5be2975298f44cb33c29f94c70537c611bcabb6cc9c58c8684a942bdb0`,
`prior-run-check.yml`
`ac9c60398745a97faed270b23bf1e988dd6abb8e16f3c69e5d6376f5f29251ed`,
`job-boundary-tests.txt`
`72e64fd7054758663687a4d09e340e62de7fd1013343bf465e2fc38ef115ffc6`,
and `proposed-interface.json`
`38c7935286ae17ef2c9227fe0aab13de5b4382d652579f2f89a32d8265e54c06`.
The fixture executables are deliberately not duplicated into the plan. The
committed artifacts preserve the proposed diffs and these observations, not a
permanent test runner: if scratch is removed, reconstruct the controlled fixture
or add proper governed integration tests before relying on a new validation
claim. Hashes alone are not replayed proof.
