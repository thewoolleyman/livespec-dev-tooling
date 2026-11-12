---
topic: one-unretried-github-api-answer
author: claude-opus-5-5
created_at: 2026-11-12T15:31:25Z
---

## Proposal: Every forge call the incident-ci job, ci-green and the incident label workflow make retries an unusable answer, prints what it got, and an unreadable pull-request body fails the selection by name

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add paragraphs to `## Expedited incident execution`, before the trusted-label paragraph, and two scenarios. Every GitHub REST call made by the incident-ci job, the ci-green job, the incident label workflow and the released incident CI entrance retries an attempt in these cases: a 5xx status, no status, a rate limit (429 or a rate-limit 403), or, for a read, a body that is not JSON. A call makes at most six attempts, and each attempt stops at 30 seconds. The waits double from 2 seconds. A rate-limited answer waits as its `Retry-After` or `X-RateLimit-Reset` header says, or 60 seconds doubling when neither is present. All the waits of one call total at most 300 seconds, after which the call fails at once naming the call. Every other answer fails at once. Each failed attempt prints the call, attempt, status, kind, next wait and the first 256 escaped bytes of the answer. When the pull-request body read fails, the selection step fails naming it and never treats the unreadable body as armed, as carrying a block or as lacking one. A write is retried without a re-read only when it is idempotent (the hold release and the cancel) or the answer was rate limited. A non-idempotent write (the hold create and the re-run) whose outcome is unknown ends `outcome-unknown`. Its step re-reads the state it changes, by the hold's `external_id` or the run's `run_attempt`, and repeats the write at most twice. The rule is defined once per trust boundary. For workflow steps it is a new composite Action, `forge-read`, which puts `livespec-forge-read` on the job's path. For the released entrance it is `budgeted_gh`. A required test holds the two definitions equal. §"Composite Actions wire contract" gains the Action's bullet.

### Motivation

Work item livespec-dev-tooling-levu6j (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm) is held at its spec-change tier. Its filing judgement (spec v204, linked topic `one-unretried-github-api-answer`) found that the ratified text never says that the incident-ci job's forge reads retry, print what they got, live in one shared definition, or fail by name without selecting incident work. The only retry rule, the fleet `gh` read-failure classification, governs the fleet conformance surface, not this job.

The defect, measured. `.github/workflows/ci.yml` reads the forge in the `incident-ci` job with bare `gh api` under `bash -e -o pipefail`. There are two such reads. The latest-release read (`gh api "repos/${GITHUB_REPOSITORY}/releases/latest" --jq .tag_name`, ci.yml:931) runs on EVERY event. The selection step's pull-request body read (`gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}" --jq '.body // ""'`, ci.yml:966) runs on every pull request. On livespec-dev-tooling#4339, an ordinary unarmed pull request, run 43243495155 job 131269893794 failed at the body read with `invalid character 'S' looking for beginning of value`. GitHub had answered with a body that was not JSON, possibly a secondary-rate-limit page, and the step printed nothing else: no status and no bytes. Because `incident-ci` is in `ci-green`'s `needs`, the required check went red. The released entrance makes a third read in-process (`livespec_dev_tooling/incident_ci_event.py:31`, one `gh_read` of `repos/{repository}/pulls/{number}` with no retry). It runs on every pull request whose body carries a block, including an unexpedited factory-repayment follow-up that retains one, so the same transient answer can redden that pull request too.

Scope (coordinator grade PASS-WITH-FIXES on livespec-dev-tooling#4353, FIX 2: one mechanism, every call site). `ci-green` is the one required check. Its own read of its run's jobs (`gh api --paginate "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?filter=latest&per_page=100"`, ci.yml:1152) is today an ad-hoc `read_jobs || { sleep 5; read_jobs; } || { sleep 15; read_jobs; }` (ci.yml:1154), with no status, no bytes and no rate-limit wait. The incident label workflow holds `ci-green` on the head with bare calls, and the proposal covers each of them:

- the reads at incident-label-ci.yml:92, :94, :107, :120, :133 and :144;
- the hold create at :101;
- the cancel at :113, inside a 30-try loop that retries every failure alike, a 409 for a run not yet queued included;
- the re-run at :129;
- the release `PATCH` at :145.

A change needed in more than one place is the finding (coordinator-duties §10), so every one of these call sites goes through the one command.

Rate limits (FIX 1). The maintainer's standing ruling, recorded on epic livespec-dev-tooling-6tgd2z on 2026-11-03 at 14:06:47Z (coordinator-duties §2), reads: "Retrying on a 429 (and multiple times after a incremental backoff wait if it happens mutiple times) should be a no brainer." A rate-limited answer is therefore retried, honouring `Retry-After`, and otherwise `X-RateLimit-Reset` when `X-RateLimit-Remaining` is `0`. These are the headers GitHub documents for its primary and secondary limits, and its guidance for a secondary limit with neither header is to wait at least a minute. Hence 60 seconds, doubling. The coordinator's suggested total bound of five minutes became a 300-second budget across all of one call's waits. Six attempts of at most 30 seconds plus 300 seconds of waits is at most eight minutes. That fits `ci-green`'s existing 10-minute timeout, which therefore needs no change, as well as `incident-ci`'s 90 minutes and the label job's 250. The attempt cap went from five to six so that a call can still see one answer after a rate-limit wait and a few transient failures. The waits need response headers, and both homes can read them: `gh api --include` prints them on standard output. The `budgeted_gh` module docstring records that `gh` surfaces headers only under `--include` or `GH_DEBUG=api`, and that its reads deliberately pass neither, so the entrance's read must pass `--include`.

Relation to the fleet `gh` read-failure classification (contracts.md §"Cross-repo coordination automation surface", the paragraph headed "A `gh` failure's status needs its HTTP marker"). This rule reuses that classification's HTTP-marker rule, its kinds and its retry of `rate_limited` and `server_error`. It adds two retried cases: an attempt that got no HTTP status (`transport` with no status), and `not_json`. That classification classifies refused reads, and a 2xx answer that is not JSON is not one. Nothing in that classification is contradicted.

POST-retry decision (FIX 2): re-read before retrying, except where the answer proves the request did not take effect. A rate-limited answer is GitHub refusing the request before acting on it, so any write is safe to repeat after one. For any other retryable answer (5xx, no status), a write's effect is unknown. Each label-workflow write was judged from the code:

- **Release `PATCH` (:145).** It sets the same `status=completed conclusion=neutral` fields every time, so repeating it is harmless.
- **Cancel (:113).** It is already followed by a loop that waits for the run to complete (:119-127). A second cancel of a cancelling run changes nothing, and GitHub answers it 409, which that step's 30-try loop already treats as not accepted yet. Both writes are marked idempotent and retried like reads.
- **Hold create (:101).** It is not idempotent, because a second create makes a second hold. The proposal requires the create to carry `external_id` = run id and run attempt, so that a re-read of `repos/<repo>/commits/<head>/check-runs?check_name=ci-green&filter=all` (the read the release already makes at :143-144) can find it. A stray duplicate would be released anyway, since the release completes every hold up to `HOLD_ID` (:144), but the re-read keeps the step from creating one at all.
- **Re-run (:129).** It is not idempotent, because a second re-run of a run already re-running is refused, or restarts it. Its effect shows on `repos/<repo>/actions/runs/<id>` as a higher `run_attempt` or a status other than `completed`. That is the read the step already makes at :107, :120 and :133, which needs only to read `run_attempt` before the write as well.

The re-read is call-specific, so it stays at the call site. The command's part is to refuse to guess: it ends an unknown-outcome write with exit status 75, `outcome-unknown`.

Why now. Under the maintainer's adopt-all ruling (epic livespec-dev-tooling-bqnzcm, 2026-11-12T14:56Z), every consumer in livespec core's committed `.livespec-fleet-manifest.jsonc` will carry an `incident-ci` job, so a read copied inline here would spread to 21 more repositories. The coordinator's fleet scope for this item is every repository whose ci.yml carries `incident-ci` or `ci-green`, with the 4 adopters first under the G1 ruling. Both rulings are rollout decisions, recorded here and not in the spec.

Shared-home decision: a composite Action, `forge-read`, not a released `livespec_dev_tooling` module.

1. The latest-release read is what LOCATES the released package, so a released module cannot make it: the job installs the release only after that read (ci.yml:927-946).
2. Consumers already pin this library's composite Actions from their `ci.yml`. The bump-pin rewrite already rewrites those `uses:` refs (`github_workflow_uses_ref`, `.github/actions/bump-pin-rewrite/action.yml`), and the fleet audit's template reader already reads `.github/actions/...@ref` pins as serving evidence (`livespec_dev_tooling/_incident_fleet_template_reader.py`).
3. The Action puts a COMMAND on the job's path rather than making the call as its own step. The calls stay inside the steps that use them, so the selection step keeps its shell event test and its single `block=present` write. The label workflow keeps its one `run:` script and its loops, and no step of a gating job gains an event-conditioned `if:`.
4. The incident label workflow checks nothing out, and `tests/livespec_dev_tooling/test_incident_ci_label_events.py` pins its job to exactly `actions: write`, `checks: write` and `pull-requests: read`. It therefore references the Action at a release tag rather than gaining `contents: read` for a checkout. One consequence for ordering: the Action must ship in a release before that workflow can adopt it.

Defined once per trust boundary (FIX 3, accepted with a condition). The entrance runs only released code (`-I`, ci.yml:987-988), while `./.github/actions/forge-read` in this repository is candidate-tree code. The entrance therefore keeps the same rule in `livespec_dev_tooling/budgeted_gh.py`, the package's one `gh` read boundary. That module's client is already built with `max_attempts=1` precisely because "retry policy belongs to the caller". The condition: a test drives both implementations through one script of answers and fails on any difference in kinds, retries, waits, stop or printed fields.

In-flight alignment (align with every item). This proposal inserts only BEFORE the trusted-label paragraph (after the repair-output paragraph), and its scenarios only BEFORE `an expedited PR defers coverage and spec work while master runs normally`. No draft below touches those gaps, so they all still apply in any merge order:

- livespec-dev-tooling#4333 (v205, the enablement record), and its twin #4328 carrying the same bytes, append paragraphs at the END of `## Expedited incident execution`, and scenarios after the fleet-audit command scenario.
- livespec-dev-tooling#4311 inserts four paragraphs immediately AFTER the trusted-label paragraph, and its scenario after `an expedited PR defers coverage and spec work while master runs normally`.
- The draft under topic `the-fleet-audit-can-read` (branch spec/the-fleet-audit-can-read) inserts after the scratch-installation paragraph and after the paragraph that begins "The fleet audit MUST expand".

livespec-dev-tooling#4336 (topic `a-gate-job-retries-a`, §"Delegated pre-push gate") is also compatible. It retries the gate Job's anonymous git fetches, which are different reads on a different transport.

Not covered. The checkout and the `uv pip install git+https://...@<tag>` fetch are git-transport reads, not REST calls, and are governed elsewhere (livespec-dev-tooling#4336, #4337).

What an implementation must change (static self-check against the live workflows and tests/, 2026-11-12).

- **`tests/consumer/test_ci_incident_scratch_push.py`.** Its select-step test pins `if [ "$GITHUB_EVENT_NAME" = "pull_request" ] && [ -n "$PR_NUMBER" ]; then` and exactly one `block=present`. Both survive if only the `gh api` line becomes a `livespec-forge-read` call. Its ref-read guard needs nothing, because the Action reads no ref.
- **`tests/livespec_dev_tooling/test_incident_ci_workflow_wiring.py`.** It mutates the exact line `      - name: Select incident work from an authenticated PR read` and the entrance's `if:` line, and it lifts exactly one anchored `grep -qE` prefilter. All three must stay, and the new Action step must carry no `if:` (the `event_conditioned` rule).
- **`tests/livespec_dev_tooling/test_incident_ci_omission_wiring.py`.** It refuses any ci.yml that names the `EXPEDITED_INCIDENT_RESPONSE` flag, and any `omitted` writer outside the entrance step. It mutates `      - name: Every required leg was created and concluded success\n        env:\n` exactly once, so that step's name and its env-first form must stay or the control must move.
- **`tests/livespec_dev_tooling/test_ci_green_required_legs_wiring.py`.** It pins ci-green's reader step EXACTLY: the `gh api --paginate ... --jq '.jobs[] | {name, status, conclusion}'` line, the `read_jobs || { sleep 5; ...}` branch and the reader invocation. It also replays that projection over fixtures captured with it. The pin must be rewritten for the command, whose `--paginate` answer is one JSON array of pages, projected for example with `jq -c '.[].jobs[] | {name, status, conclusion}'` on `ubuntu-latest`. The pin's fail-closed properties must keep holding: the reader invocation stays the step's last command, an unreadable list still ends in a non-zero exit, and there is no `set +e`, `trap` or `shell:` override.
- **`tests/livespec_dev_tooling/test_incident_ci_label_events.py`.** It pins the label workflow's exact strings, all of which change to the command form:
  - `_HEAD_READ`, `_HOLD_POST`, `_HOLD_FIELDS`, `_RERUN`, `_CANCEL` and `_RELEASE`;
  - the `_RETRY` regex `if gh api -X POST ".../cancel" >/dev/null; then break`;
  - `_HOLDS_SELECT`, now applied by `jq` to the command's output.

  It also pins the job's permissions exactly. Those stay unchanged under the release-tag decision, but a new `uses:` step must not trip its single-job and no-`${{` rules. The hold create gains an `external_id` field.
- **`tests/consumer/test_composite_actions_wire_contract.py`.** It needs a `forge-read` entry (no inputs, no outputs).
- **`tests/livespec_dev_tooling/test_incident_ci_event.py`.** It monkeypatches a single `gh_read`. Its failed-reply refusal test must inject the wait so that six attempts do not sleep, the refusal cause must name the pull-request read, and the read must pass `--include` for the rate-limit headers.
- **`livespec_dev_tooling/_incident_fleet_surface_files.py`** (read by `tests/livespec_dev_tooling/test_incident_fleet_release_keyed.py`). It maps `.github/workflows/incident-label-ci.yml` to the "PR mode transport" row and `ci.yml` to two CI rows. The Action's files must join each of those rows.
- **A new equality test.** It holds the Action's command and the entrance's `budgeted_gh` read equal over the scripted answers that the last contracts paragraph lists.

### Proposed Changes

### contracts.md §"Expedited incident execution"

Insert the following text immediately after the paragraph that begins "Repair output MUST contain a legal adjacent code/test comment", and immediately before the paragraph that begins "A trusted PR-specific label plus structured receipt MUST project mode only into the exact repair PR/head before initial CI." No in-flight draft inserts into this gap (see the in-flight alignment in the Motivation):

> Every forge call that the `incident-ci` job, the `ci-green` job and the incident label workflow (`.github/workflows/incident-label-ci.yml`) make MUST retry an answer it cannot use, so that one unusable answer never decides the required check. A forge call is one request to the GitHub REST API: a read (`GET`) or a write (any other method). The rule covers every call a workflow step of those jobs makes: today the `incident-ci` job's latest-release read and pull-request body read; `ci-green`'s read of its own run's jobs; and the incident label workflow's reads of the pull request, of its CI runs and of the head's `ci-green` check runs, with its writes that create a `ci-green` hold, cancel a CI run, re-run it and release the hold. It also covers the released incident CI entrance's own read of the pull request. The released incident CI entrance (the entrance) is `python -m livespec_dev_tooling.incident_ci_process`, which the `incident-ci` job installs from this library's latest release and runs only on a pull request whose body carries a `livespec-incident-ci` block. An attempt MUST be retried when it carries an HTTP 5xx status, when it got no HTTP status at all (including an attempt stopped at its time limit), when it is rate limited (an HTTP 429, or an HTTP 403 that the fleet `gh` read-failure classification (§"Cross-repo coordination automation surface") reads as a primary or secondary rate limit), or, for a read, when its answer body does not parse as JSON whatever its status. A read's attempt whose status is 2xx and whose body parses as JSON is the read's answer. A write's attempt whose status is 2xx is the write's answer whatever its body, and that body is parsed only where the caller reads a value from it. Any other attempt MUST fail the call at once, without a retry: an HTTP 401, 404, 409 or 422 answer, or a 403 that is not a rate limit, whose body parses as JSON.

> A call MUST make at most six attempts and MUST stop each attempt after a time limit of no more than 30 seconds. Before each further attempt it MUST wait. After a rate-limited answer it MUST wait the number of seconds that answer's `Retry-After` header names; without that header, until the time its `X-RateLimit-Reset` header names, when its `X-RateLimit-Remaining` header is `0`; with neither, 60 seconds, doubled on each further rate-limited answer of the same call. After any other retryable answer it MUST wait 2 seconds, doubled on each further wait of the call (2, 4, 8, 16, 32). A wait a header names MUST be raised to the doubling wait the call would otherwise take next (2 seconds, doubled once for each earlier wait of the call) when it is shorter. The waits of one call MUST total no more than 300 seconds: when the next wait would take the total past 300 seconds, the call MUST NOT wait and MUST fail at once, naming the call, its kind and the wait it was asked for. A call therefore ends within eight minutes, and a job that makes one MUST time out later than that, as `ci-green` (10 minutes), `incident-ci` (90) and the label workflow's job (250) already do. An attempt's status MUST be taken only from an HTTP status the answer presents as one, as that classification requires, never from a bare digit run. Each failed attempt MUST be named by that classification's kind for its status (`rate_limited`, `server_error`, `forbidden`, `not_found`, or `transport` for an attempt with no HTTP status or with any other status), or by `not_json` for a 2xx read answer whose body does not parse as JSON. The kinds are that classification's, and so is the retry of `rate_limited` and `server_error`. This rule adds two retried cases: a `transport` attempt that got no HTTP status, and `not_json`. An attempt that got no usable answer tells the job nothing about the forge's state.

> Each failed attempt MUST print one line naming the call, the attempt number out of six, the HTTP status the attempt carried (`none` when it carried none), its kind, the wait it takes next, and the first 256 bytes of the answer body, or of `gh`'s standard error when the attempt got no body. Those bytes MUST be printed on that one line with every line break, control byte, non-ASCII byte and backslash written as an escape, so that no answer can open a line of its own or a workflow command. A call that ends without an answer MUST make its step fail with an error naming the call and its last status: the latest-release read fails its step, and `ci-green`'s read of its run's jobs fails `ci-green` closed. When the pull-request body read ends without an answer, the selection step MUST fail naming the pull-request body read and its last status, and MUST NOT write its `block` output, so the entrance does not run and the job writes no `omitted` value. A body that could not be read MUST NOT be treated as carrying a `livespec-incident-ci` block, as armed, or as lacking a block: the step MUST NOT select incident work from it and MUST NOT report that it selected nothing. When the entrance's read of the pull request ends without an answer, the entrance MUST refuse with a cause naming that read, and MUST NOT observe an event from it.

> A write MUST be retried without a re-read only when repeating it cannot do it twice. A write is idempotent when repeating it leaves the forge as one success would. The label workflow has two: its release of a hold, a `PATCH` that completes the check run as neutral with the same fields every time, and its cancel of a CI run. A repeated cancel of a run already cancelling changes nothing, and GitHub answers it 409, which the step's own loop already reads as not accepted yet. An idempotent write MUST be retried exactly as a read is. Every other write MUST be repeated by the call only after a rate-limited answer, which shows the forge refused the request without acting on it: the hold's create (`POST repos/<repo>/check-runs`) and the re-run (`POST repos/<repo>/actions/runs/<id>/rerun`). After any other retryable answer the write's outcome is unknown, so the call MUST NOT repeat it. The call MUST print the failed attempt's line and end with exit status 75, `outcome-unknown`, naming the write. The calling step MUST then re-read, through the same command, the state the write changes. It MUST repeat the write only when that re-read shows the write did not take effect:
>
> - The hold's create MUST carry an `external_id` made of the label workflow's run id and run attempt. It took effect when the head's `ci-green` check runs list one with that `external_id`, and the step MUST then use that check run's id as its hold.
> - The re-run took effect when the run's `run_attempt` exceeds the attempt the step read before asking for it, or when the run's status is no longer `completed`.
>
> A step MUST repeat an `outcome-unknown` write at most twice. It MUST fail naming the write when a re-read ends without an answer or a third `outcome-unknown` answer arrives. A hold left behind by such a failure keeps the head unmergeable, as a failed step already does.

> The rule MUST be defined once per trust boundary. Workflow steps run code from the tree or the release their workflow names, and for them the rule MUST be defined in this library's composite Action `forge-read` (§"Composite Actions wire contract"). The Action puts one command on the job's path: `livespec-forge-read <call-name> [--method <method>] [--field <name>=<value>]... [--idempotent] [--paginate] <endpoint>`. The command makes the call the preceding paragraphs define and writes the answer body to its standard output. Any method other than `GET` is a write, and it is idempotent only when `--idempotent` is passed. With `--paginate` the command requests every page, each request an attempt within the call's one bound, and writes one JSON array of the pages' answers in order. It writes only the answer, and a step that needs a value extracts it with a tool its runner already has. Every forge call that a workflow step of an `incident-ci` job, a `ci-green` job or an incident label workflow makes MUST go through that command. This holds in this repository and in every consumer whose workflows carry those jobs. Such a step MUST NOT carry a bare `gh api` call or its own retry of a forge call's failure. A loop that waits for a forge state to change, such as a cancel to be accepted or a run to complete, is not a retry, and it stays the step's.
>
> This repository's `incident-ci` and `ci-green` jobs already check the tree out, and MUST use the Action from that tree (`./.github/actions/forge-read`). The incident label workflow checks nothing out, and its job holds only `actions: write`, `checks: write` and `pull-requests: read`. It MUST therefore reference the Action at a release tag of this library, as a consumer does, rather than gain `contents: read` for a checkout. A consumer MUST reference the Action at a release tag of this library, in the `uses:` pin form this library's bump-pin rewrite already rewrites. The Action's files are part of every published surface whose workflows use it, so the fleet audit MUST count them among the files of every surface row whose files include `.github/workflows/ci.yml` or `.github/workflows/incident-label-ci.yml`.
>
> The entrance sits on the other side of the trust boundary: it runs only released code, while in this repository the Action is candidate-tree code. The entrance's read MUST therefore apply the same rule through this package's own GitHub read boundary, `livespec_dev_tooling.budgeted_gh`, never through the Action, and MUST read the response headers the rate-limit waits need. This repository MUST carry a test that holds the two definitions equal. The test MUST drive both through the same scripted sequences of answers:
>
> - a 2xx answer whose body is not JSON;
> - an HTTP 502;
> - an attempt that gets no HTTP status;
> - an attempt that reaches its time limit;
> - an HTTP 429 with `Retry-After`;
> - a secondary-limit 403 with `X-RateLimit-Reset` and `X-RateLimit-Remaining: 0`;
> - a rate-limited answer with neither header;
> - a rate-limited answer whose wait exceeds the remaining budget;
> - an HTTP 404 whose body is JSON.
>
> The test MUST fail when the two definitions differ in the kinds they assign, the attempts they retry, the waits they take, where they stop, or the fields of the lines they print.

### contracts.md §"Composite Actions wire contract"

Replace "The library MUST ship at minimum four composite Actions:" with "The library MUST ship at minimum five composite Actions:". Then append the following bullet after the `publish-flake-retries` bullet, as the list's last entry:

> - **`forge-read`**. Inputs: none. Outputs: none. Permissions: none of its own; each call authenticates with the calling job's `GH_TOKEN` and needs only the permission its endpoint needs. Performs: one step that adds the Action's own directory to the job's `GITHUB_PATH`, so that every later step of the job can run `livespec-forge-read <call-name> [--method <method>] [--field <name>=<value>]... [--idempotent] [--paginate] <endpoint>`, the retrying forge call that §"Expedited incident execution" defines, including its exit status 75 (`outcome-unknown`) for a non-idempotent write whose outcome is unknown. The command MUST need nothing beyond bash, the `gh` CLI and `python3`, so that it runs before the job installs any Python package. It MUST NOT print the token it calls with.

### scenarios.md

Insert the following two scenarios, in this order, immediately after the closing fence of `## Scenario: incident commit provenance remains verifiable on normal master` and immediately before `## Scenario: an expedited PR defers coverage and spec work while master runs normally`. Put each body in a ```gherkin fence, as its neighbours are:

> ## Scenario: an incident-ci forge read retries an unusable answer and an unreadable pull-request body fails the selection by name
>
> ```gherkin
> Given an ordinary pull request whose body carries no `livespec-incident-ci` block
> And GitHub answers the incident-ci job's pull-request body read with a body that is not JSON on the first attempt, with HTTP 502 on the second, with HTTP 429 carrying `Retry-After: 20` on the third, and with the pull request's JSON on the fourth
> When CI runs on that pull request
> Then each of the three failed attempts MUST print one escaped line naming the pull-request body read, its attempt number, its HTTP status and kind, the wait it takes next and the first bytes of its answer
> And the read MUST wait 2 seconds after the first attempt, 4 seconds after the second and 20 seconds after the 429
> And the selection step MUST read the fourth attempt's answer, select nothing and pass
> And when GitHub instead answers every attempt with an HTTP 5xx status, the read MUST stop after six attempts, and the selection step MUST fail naming the pull-request body read and its last status, MUST NOT write its block output and MUST NOT report that it selected nothing
> And then the released incident CI entrance MUST NOT run, and the job MUST NOT write an omitted value
> And when GitHub answers with HTTP 429 carrying a `Retry-After` longer than the read's remaining wait budget, the read MUST fail at once, naming the pull-request body read, `rate_limited` and the wait it was asked for
> And an HTTP 404 answer whose body is JSON MUST fail the read at its first attempt without a retry
> And when GitHub answers every attempt of ci-green's read of its own run's jobs with an HTTP 5xx status, ci-green MUST fail closed after six attempts, naming that read.
> ```

> ## Scenario: an incident label event's forge writes repeat only what did not take effect
>
> ```gherkin
> Given a same-repository pull request whose newest CI run on its head is still in progress
> And GitHub creates the incident label workflow's `ci-green` hold but answers the create with HTTP 502
> When the expedited-incident-response label is added to that pull request
> Then the shared command MUST NOT repeat the create, and MUST end it with exit status 75, outcome-unknown, naming the create
> And the step MUST re-read the head's `ci-green` check runs, find the hold whose external id is this job's run id and run attempt, and use that hold without creating another
> And when that re-read finds no such hold, the step MUST repeat the create, at most twice
> And a cancel of the run answered with HTTP 503 MUST be repeated by the shared command without a re-read, because a repeated cancel changes nothing
> And a re-run answered with HTTP 429 carrying `Retry-After: 10` MUST be repeated after 10 seconds without a re-read, because a rate-limited request did not take effect
> And a re-run answered with HTTP 502 MUST be repeated only after a re-read shows the run's `run_attempt` unchanged and its status still `completed`.
> ```

### Heading-coverage debt the revise owes

No `## ` heading is added, removed or renamed in contracts.md. Each of the two new `## Scenario:` headings in scenarios.md MUST get one `tests/heading-coverage.json` row in the revise commit (CLAUDE.md "Revise co-edit discipline"). Each row carries:

- `"spec_root": "SPECIFICATION"` and `"spec_file": "scenarios.md"`;
- the heading, copied from the spec file;
- `"test": "TODO"` and `"work_item": "livespec-dev-tooling-levu6j"`;
- a `reason` that names the tier.

Example reason for the first scenario: "Spec-first: a real test at the integration tier or above is owed for this scenario: the committed incident-ci select step and ci-green reader step run under bash with the forge-read Action's command against a stub `gh` scripted with not-JSON, 502, 429 Retry-After and pull-request answers, then six 5xx answers, an over-budget 429 and a JSON 404; livespec-dev-tooling-levu6j owns it."

Example reason for the second scenario: "Spec-first: a real test at the integration tier or above is owed for this scenario: the committed incident label workflow script runs under bash with the forge-read Action's command against a stub `gh` that creates a hold but answers 502, then answers a cancel 503 and a re-run 429 and 502; livespec-dev-tooling-levu6j owns it."

The revise MUST then run `just generate-heading-coverage-debt-register` and stage the regenerated `tests/heading-coverage-debt.json`.
