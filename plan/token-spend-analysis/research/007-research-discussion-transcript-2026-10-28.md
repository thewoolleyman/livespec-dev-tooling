<!-- Conversation transcript, 2026-10-28, attended session b021574a (maintainer and Claude), recorded at the maintainer's request so the review is not lost on a session restart. Verbatim from the session log; interruptions, overseer nudges and tool noise omitted. Maintainer turns are block-quoted. Not yet acted on beyond what the turns themselves record. -->

# Token-spend research discussion, 2026-10-28 (transcript)

Companion to note 006 (`006-token-spend-ratchet-and-phoenix-sdd-research-2026-10-28.md`), which was rewritten from this discussion.

Contents:

1. Claude's original summary and shortlist (10:36Z)
2. The maintainer's eleven questions
3. Claude's answers
4. Maintainer follow-ups and Claude's responses
5. Open at the time of recording

## 1. Claude: original summary and re-ranked shortlist (10:36Z)

The Phoenix section is now in the report and the shortlist is re-ranked. These are the agent's findings with its citations; I haven't checked the sources myself, so spot-check any figure before relying on it.

**Who builds this way, and what they report**
- **The idea's history:** Martin Fowler's PhoenixServer (2012), Chad Fowler's 28-essay "Regenerative Software" series with an alpha `phoenix` implementation, and Tessl.
  - Tessl's Podjarny says code becomes disposable, but also "I don't think we're there yet". By April 2026 he had shifted to calling it "context-driven".
  - Böckeler's taxonomy is spec-first, then spec-anchored, then spec-as-source. The agent's own reading is that livespec sits at spec-anchored and is moving toward spec-as-source.
- **Teams running without human code review:** StrongDM's factory charter says outright "Code must not be reviewed by humans". Yegge later concluded that the last 25% of PRs still need a human.
- **A scale reference:** Anthropic's C compiler cost about $20k for 100k lines, over 2,000 sessions, with 2B input tokens and 140M output.
- **Reported failures:** models returning `return true` and rewriting the tests to pass, a floor of about $1k per engineer per day, and the lessons from past bugs lost when code is rebuilt from scratch. One Chad Fowler pipeline scored 0/5 while its status stayed green, against 5/5 for a single model call.

**How they keep cost bounded**
- **Regenerate only what a spec change reaches.** Editing in place instead of regenerating measured about 30% fewer tokens at equal accuracy.
- **Reuse the last verified unit and its verdict, keyed on its spec clauses.** Caching on a hash of the inputs doesn't work, because generation isn't reproducible even at temperature 0.
- **One spec unit per module, with an explicit interface.**
- **Use the Batches API for non-interactive verdicts.** It is 50% off and stacks with prompt caching.

**What it implies for our review stack**
- **Review of code shape and comprehension is wasted when no human reads the code.** Comprehension belongs in the spec instead.
- **Correctness should come from a deterministic check the implementing agent cannot modify.** LLM judges score worse than running the code and misclassify correct code. They are good at one thing: catching an implementation that games its tests.
- **Coverage is not proof.** One cited case had 100% test coverage and a 4% mutation score.
- **Meta's RADAR reviews by risk tier:** 60% of diffs auto-approved, with low revert and incident rates.
- **Where the money is:** locally, implement and fix nodes were about 79% of factory responses and verdict nodes about 11%. Thinning the review stack pays off mainly in the roughly $11k of host-side judge spend and in fewer rework loops, not inside the factory.

**Re-ranked shortlist**
1. Factory nodes load only the instructions they declare (unchanged).
2. Cap transcript growth inside a node (up from 3).
3. Keep prompts cache-friendly, use a 1-hour cache, and batch the replays, dod_gate and completeness reviews.
4. Base verification on that deterministic check: one narrowed independent LLM pass for gaming and scope, replays sampled by risk, and no code-shape grading (up from 7). This one is your product decision.
5. Size budgets enforced in CI for both the instruction files and the spec, including pruning spec history.
6. A map from spec clause to module, so each node gets only its slice of the spec and regeneration touches only what changed.
7. Cheaper model or effort for verdict nodes (down from 4, since they're only about 11% of factory responses).
8. Trim tool output.

The full report (about 8,300 words) is at `/tmp/claude-1000/-data-projects-livespec-dev-tooling/b021574a-e0a0-4c73-aeae-77d705d5cf09/scratchpad/token-spend-research.md`. It's in a scratch directory that isn't committed. If you want to act on it, I'll file it as a research note under this plan.

Still open on the proof: should I reboot vps to prove assertion 10, or reword it?

## 2. Maintainer: questions (21:29Z)

> Explain these:
>
> 1. One Chad Fowler pipeline scored 0/5 while its status stayed green, against 5/5 for a single model call.
> 2. Reuse the last verified unit and its verdict, keyed on its spec clauses. Caching on a hash of the inputs doesn't work, because generation isn't reproducible even at temperature 0.
> 3. What do we need to change for this: "Review of code shape and comprehension is wasted when no human reads the code. Comprehension belongs in the spec instead."
> 4.  Meta's RADAR reviews by risk tier
> 5. how exactly do you propose to do this: "Cap transcript growth inside a node (up from 3)."
> 6. Detail exacly how prompt caching works and saves cost: " Keep prompts cache-friendly, use a 1-hour cache, and batch the replays, dod_gate and completeness reviews."
> 7. Base verification on that deterministic check: one narrowed independent LLM pass for gaming and scope, replays sampled by risk, and no code-shape grading (up from 7). This one is your product decision.
> 8. How do tyou propose to decide what to prune: "Size budgets enforced in CI for both the instruction files and the spec, including pruning spec history."
> 9. Aren't we already trying to do this with spec-implementation-lockstep (or other) plans: "A map from spec clause to module, so each node gets only its slice of the spec and regeneration touches only what changed."
> 10.  Aren't we already doing this: "Cheaper model or effort for verdict nodes (down from 4, since they're only about 11% of factory responses)."  Also, don't you need some smarts for the verdicts to be useful?  WHy are dumb models ok ?
> 11. This is worty of its own plan, research exactly how others do this and how we can adopt best practices.

## 3. Claude: answers (21:31Z, 9-11 continued 21:33Z)

Still here: I re-read note 006 and checked the related orchestrator plans so my answers rest on what's actually there. My answers follow, numbered to match your questions.

**1. Phoenix 0/5 against 5/5**
This is in the README of Chad Fowler's `phoenix` reference implementation. On a small "todo-api" benchmark the pipeline ran 5 times with Sonnet 5. The pipeline splits the spec into clauses, maps the clauses to implementation units, and generates each unit separately. That approach passed the end-to-end check 0 times out of 5. One model call that was given the whole spec passed 5 out of 5. The bracketed numbers in the note are confidence intervals.

Every failure was the same. Each unit mounted its HTTP routes at a path guessed from the unit's own name, not at the path the spec stated. Type checks still passed and `phoenix status` stayed green, because both only check structure. The lesson for us is that cutting a spec into slices loses facts that span units, such as interfaces and routes. A green structural status says nothing about behaviour. Any slicing we do (item 9) has to carry the interface clauses and be judged by a behavioural end-to-end check.

**2. Reusing verified units instead of a hash cache**
The obvious idea is to cache model output keyed on a hash of the prompt. That fails because the same prompt does not give the same code. In one published run, 1,000 samples at temperature 0 gave 80 different completions.

So you memoise the *accepted result*, not the generation. For each implementation unit you store:
- the spec clauses it depends on;
- the content hash of each of those clauses when it last passed;
- the verdict it got.

When the spec changes, you skip any unit whose clause hashes haven't changed: no regeneration and no re-judging. It works like make or Bazel, except the build step is non-deterministic, so you cache its approved output. We already do this on the judge side: `bd-ib-k5qp5z` reuses a heading's verdict across a spec revision that leaves the heading unchanged.

**3. What changes for "comprehension belongs in the spec"**
Two changes:
- **Stop LLM grading of code shape** (readability, naming, structure) in the review, `review_fix`, `dod_gate` and `proof_grade` prompts. Keep deterministic shape checks: lint, complexity limits and types cost almost nothing. I haven't yet listed which of our rubrics actually contain shape criteria; that's the first step.
- **Put the "why" in the spec.** When the factory stalls, the thing a person reads is the spec. So it must hold the invariants, the interfaces and the hard-won details. Fowler's example is a timeout that "has to be 17 seconds". Regeneration erases knowledge like that unless the spec states it. In practice the drift pass should file proposed changes for non-obvious behaviour, not only for new features.

Two caveats:
- **We are not fully Phoenix.** Our fix loops edit code in place, and agents read the code on every fix. Fowler himself says to reread network and business-rule code.
- **The cautionary case.** Horthy's team ran four months "lights off" and then needed three weeks to re-onboard to code nobody had read.

**4. Meta's RADAR**
This is a Meta paper from May 2026, arXiv 2605.30208. I'm relaying the subagent's summary; I haven't read the paper myself. Every diff goes through a funnel:
1. Is the diff AI-authored?
2. Is it eligible for automated review?
3. Static heuristics.
4. A machine-learned risk score.
5. LLM review.
6. Deterministic validation.

Diffs under the risk threshold are auto-approved with no human review. Moving the threshold from the 25th to the 50th percentile raised the auto-approve rate to 60%. RADAR diffs had about a third of the revert rate and a fiftieth of the incident rate of other diffs. That comparison is biased, because low-risk diffs break less anyway.

The takeaway is to scale review spend with risk, not apply it to everything. For us a risk score could use:
- whether product `.py` is touched;
- how many clauses the change touches;
- the item's history of failed attempts.

Low-risk items would get the deterministic gates plus one cheap LLM pass. High-risk items would get the full replay.

**5. Capping transcript growth in a node**
"Up from 3" was only its move in the ranking. The mechanisms, from safest to least safe:
1. **Lower the auto-compact window.** Set `CLAUDE_CODE_AUTO_COMPACT_WINDOW` to about 200k on factory Claude nodes, through the adapter env pin. Codex already compacts at about 235k and its median input is 2–4 times lower than Claude's on the same nodes, with no recorded quality loss. Unverified: whether that variable reaches the session through the ACP adapter. That has to be tested first.
2. **Filter test output with a hook.** A PreToolUse hook would cut `just check` output down to the failures, so pages of passing output never enter the transcript.
3. **Split long nodes.** Break `implement` into phase nodes that pass a structured handoff file at seams the graph already has. Sourcegraph's Amp replaced compaction with this.

The gate on all of this is that first-pass acceptance and fix-loop counts must not get worse, because compaction loses information. This belongs as a child of the orchestrator's existing `factory-context-per-turn-reduction` plan, not as new work.

**6. How prompt caching saves money**
- **What a request contains.** Each request is tools, then system prompt, then messages. An agent loop resends the whole transcript every turn, so turn N's request is turn N−1's request plus a little more.
- **Hits.** The provider stores the processed state of a prefix. A later request whose prefix is byte-identical bills those tokens at the cache-read rate. Note 006 says 0.05× base for Sonnet 5.5, but burn note 002 lists $0.20 against $2, which is 0.1×. I'd check the pricing page before relying on either. Hits are why a 200k-token floor per response is affordable at all.
- **Writes.** The first time a prefix is stored it costs 1.25× (5-minute expiry) or 2× (1-hour expiry). Each hit restarts the clock.
- **Breakers.** Any change early in the prefix makes everything after it a fresh write: a timestamp or run ID in the system prompt, unstable tool order, an edited CLAUDE.md, a model switch. "Cache-friendly" means static content first and per-run IDs last.
- **The 1-hour expiry.** It only pays when a reuse comes more than 5 minutes after the last call. Used on a one-shot call it is pure loss. That is exactly what the expensive spec judge was doing: writing 1-hour cache it never read (burn note 001).
- **Batches.** The Message Batches API costs 50% of normal prices, returns results asynchronously within 24 hours (most under an hour), and stacks with cache discounts.
- **Caveat 1:** Batches only fit single-shot judgements. A multi-turn replay that uses tools can't be batched.
- **Caveat 2:** Batches need an API key and are billed in real dollars. Our `claude -p` judges run on caam-rotated Max subscriptions. Moving them would trade subscription quota for API spend, so the saving is not automatic.

**7. Re-basing verification (your decision)**
Today one item can be judged several times: factory review, `proof_verify`, the graded `dod_gate`, `proof_grade`, the host judges, then a plan-level replay plus a completeness review. The proposal:
- **`dod_gate`** passes or fails on tests the implementer cannot see or edit: held-out scenarios and mutation score. Your `fleet-mutation-testing-rule-26` plan is building the mutation half.
- **One LLM pass** checks only for gaming the tests, tampering with test files, and going beyond the spec clause. Judges are measured to be good at catching gaming and poor at judging correctness: they often reject correct code, and each false reject costs a fix loop.
- **Replay and completeness review** run on a sample chosen by risk tier.
- **Drop** LLM grading of code shape.

It's a product decision because it redefines "done": some items would merge without an independent replay. My recommendation is yes, in this order:
1. Arm the deterministic check first. It's the same ordering rule as in CLAUDE.md: don't remove the judges before what replaces them is running.
2. Shadow-run the tiered policy and log what the skipped replays would have caught.
3. Then switch, with the post-merge revert rate by tier as the number that must not rise.

**8. Deciding what to prune**
For the instruction files, each entry already records its date and its reason, which is the precondition the research found for safe pruning. The rules I'd apply:
- **Enforced by a hook or gate** → delete the prose. The gate's own refusal message teaches the fix.
- **Triggered by a file path** → move it to a path-scoped rule. It stays, but stops loading on every request.
- **An incident story** ("recorded because on 2026-09-08…") → cut to a one-line rule. The story moves to the `.ai` file or stays in git history.
- **About a retired system** → delete.

The budget gate forces the choice: a PR that adds a rule past the limit fails until its author cuts or converts something else.

For the spec I'd change the research's advice. Its suggestion to shorten a clause to a pointer once a test covers it would invert livespec's rule that the spec is the source of truth, so I'd reject that part. Instead:
- never load `history/vNNN` into any prompt (`prune-history` already exists);
- deliver clause slices, not the whole tree (item 9);
- treat a spec-size budget as a signal to generalize, not to cut. That matches your own lockstep ruling: "the spec should be generalized to be correct rather than always expanded."

**9. Isn't this `spec-implementation-lockstep`?**
No, they're different maps. Lockstep links a *work item* to the clause that authorizes it. Its rule is that no feature is dispatched without a ratified clause, a drift pass runs after each merge, and dispatch checks the citation. It answers "is this behaviour in the spec?"

The proposed map links a *clause* to the *code modules* that implement it. It has two uses: give each factory node only its own clauses, and find which modules a spec change reaches, so only those are regenerated or re-judged.

Several pieces already exist and point the same way:
- `heading-coverage.json` maps clause to test;
- `bd-ib-qksrl6` and `_spec_tree_condensation.py` give judges bounded clause sets;
- `k5qp5z` reuses verdicts across revisions;
- lockstep's citations map item to clause.

The missing step from clause to module is cheaper than it sounded. Clause to test is already in `heading-coverage.json`, and coverage data already records which modules each test runs, so clause to module can be derived from the two. It would sit naturally beside lockstep, but it isn't in lockstep's scope today.

**10. Aren't we already routing verdicts to cheaper models, and why would weaker models be OK?**
The model half is mostly done. Coordinator rulings R47, R48 and R66 moved the host judges from Opus 4.8 to Sonnet 5.5 and Haiku 5.5. Burn note 002 also proposes a trial of GPT-5.6 Luna on `dod_gate`, `proof_capture` and `disposition`. The effort half is weak here. The research's figure of about 40% cheaper comes from workloads where output and thinking dominate the cost. In ours, output is under 5% of cost, so effort mostly moves turn count, not price. Item 7 of the shortlist was largely already done or low-value, and I should have checked that before relaying it.

On whether weaker models are OK, your doubt is right, and the answer depends on the verdict:
- **Narrow, rubric-shaped questions can go cheap.** Examples: "did this diff modify a test file to make it pass?", "does this behaviour appear in clause X?", "is the cited heading the one that governs this?" There the inputs are bounded and the answer barely needs reasoning. In one study, a tight rubric made a small judge both more accurate and 78 times cheaper than a large one.
- **Open-ended judgement needs a strong model.** Examples: completeness review, replay interpretation, "is this plan actually done?". Another study found small judges rank candidates well but disagree with humans on individual items.
- **Switch by verdict type only after a shadow run.** Run the cheap model beside the strong one on the same inputs, log their agreement and compare against later reverts. Keep the strong model wherever they disagree. A cheap judge that wrongly rejects good code costs more in fix loops than it saves.

**11. A separate plan for this**
"This" could mean one of three things, and each would be a different plan, so I need you to choose. My recommendation is the first: it's your product decision from item 7, it's where the host-side money is, and items 2, 3 and 10 fold into it as sub-topics. The context-size levers (items 5 and 8) already have a home in the orchestrator's `factory-context-per-turn-reduction` plan.

## 4. Follow-ups

### 4.1 Maintainer: what question 11 refers to

> 11. separate plan refers to this: "Trim tool output.". But don't write it yet, we are still talking, make a note on your epic that we need to do this and do research and best practices as I said as part of plan.

### Claude

I've added a note to the plan epic, `livespec-dev-tooling-6lv7ze`, and read it back to confirm it's there. It records that you want a separate plan for shortlist item 8 ("Trim tool output"), which covers:
- hooks that filter test and gate output before it reaches the agent;
- shorter JSON output from `list-work-items` and `context`;
- caps on the size of tool responses.

The note also says:
- the plan opens with its own research on how other teams trim tool output, the measured best practices, and how we'd adopt them;
- it isn't to be created yet;
- it isn't to be folded into another plan.

The note also flags the counter-evidence from note 006, so the new plan's research has to deal with it. One study found that the heaviest compression of tool output cut tokens by 38% but raised the bill by 6.8%. Another study and JetBrains' A/B test found the same pattern. So the plan has to measure success in dollars per finished work item, not in tokens.

That replaces the "Verdict model/effort routing" choice in the picker; I haven't acted on that one. Nothing else has changed: the plan is still unarchived, and assertion 10 is still waiting on you.

### 4.2 Maintainer: fix note 006

> Two things you need to fix for https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/plan/token-spend-analysis/research/006-token-spend-ratchet-and-phoenix-sdd-research-2026-10-28.md, in addition to fleshing out any of the points I asked about above:
>
> 1. Don't just gtive up on hon3eycomb metrics helplessly, if the tool doesn't work fuxking fix it or ask me to help you.  Include real metrics.
> 2. Don't write walls of ai garbage paragraphs that are unreadable.  Use clear and concise but complete style, prefer orderes list or bullets.  Do not write unparseable dense run on paragraph strings of gibberish like this: [pasted example omitted: the first two paragraphs of the original note 006 "Bottom line"]

### Claude (after pulling llm-spend metrics)

Yes. The Honeycomb plugin wanted an interactive re-login, so I bypassed it and ran the queries headless with the `HONEYCOMB_MCP_API_KEY_LIVESPEC` key. That's the route `.ai/honeycomb-query-credential.md` documents. These are real `llm-spend` numbers, priced in API dollars as the board does (the bill itself is subscription quota):

| Last 7 days | USD |
|---|---:|
| **Total** | **$14,887** |
| Local Claude sessions | $4,239 |
| Local Claude, no consumer recorded (rows from before 10-25, when attribution started) | $3,657 |
| Factory, Codex | $3,491 |
| Host judges (`claude -p`) | $2,074 |
| Factory, Claude | $870 |
| Local Codex sessions | $334 (+$222 unattributed) |

What these numbers show that the research note only guessed at:
- **Judges cost a fifth of what they did on 10-25.** `claude -p` spend went from $998/day on 10-25 (Opus 4.8) to $127/day on 10-28 (Sonnet 5.5). So item 10 is largely done already, as I said.
- **The judges' bill is mostly cache writes.** For the `claude -p` rows that carry a price split, cache writes are $331 of $360 (92%), nearly all 1-hour writes (72M tokens) against 90M tokens read. That is the "1-hour cache on one-shot calls" waste from item 6, measured.
- **Claude factory nodes do re-read from cache.** 88–99% of their input is cache reads, and their median input per response is 340k–430k tokens.
- **Codex factory nodes have a median of about 195k–218k tokens per response, with p90 near 235k on every node.** That flat ceiling is the compaction cap.
- **`implement` dominates.** It is $2,512 of about $4,360 factory spend this week (58%) and 30k of about 49k responses.
- **Output is a small share of cost:** 3–10% where the price split is recorded. Reasoning effort is a weak lever.

Telemetry gaps that the note will name rather than paper over:
- Factory Codex records no cache split; the board assumes 90% cached.
- $3.66k of local Claude spend has no consumer recorded.
- The emitter prices Sonnet 5.5 cache reads at $0.20 per million tokens, not the $0.10 the research quoted. Those two need reconciling against the pricing page.

I'm writing the rewrite of note 006 in a fresh worktree now: these metrics, the answers to your 10 questions, and short bullets and tables in place of paragraphs.

### 4.3 Maintainer: who reads first at a stall

> FYI, this is not true for my desired paradigm: "When the factory stalls, the thing a person reads is the spec. ".  When the factory stalls, the first thing I do it tell my supervisor/coordinator agent to fucking fix it ASAP

### Claude

That changes my answer to question 3, and I'll correct it in the rewrite. The reader at a stall is your coordinator agent, not you. So comprehension has to serve an agent that is debugging under time pressure. It needs three things:
- the spec, for intent;
- code that an agent can navigate;
- retained failure evidence: traces, logs, the `tmp/janitor-failed-output` style of output.

Code that an agent can navigate is not the same as human code style. It can be enforced deterministically: size limits, complexity limits, type checks and clear module boundaries. LLM grading of readability still goes.

### 4.4 Maintainer: split Red and Green TDD into separate nodes?

> IDEA/PROPOSAL: re "Split long nodes. Break implement into phase nodes that pass a structured handoff file at seams the graph already has. Sourcegraph's Amp replaced compaction with this." - What if we put the red and green tdd phases in separate nodes, that workes as pair programmers in the same session?  Would that help context, or increase it because they'd need to "communicate" more? Reserach if anyone has tried this.

### Claude

PR #2940 (the note 006 rewrite) is open. Its commit and push gates passed, and auto-merge is on. I'll clean up the worktree after it merges.

On splitting Red and Green: a background research agent (Fable) is checking whether anyone has tried it and what they measured. Here's my first-principles take, to check against what it finds.

**"Separate nodes" and "same session" pull in opposite directions,** so they're really two designs:

| Variant | Context per turn | Why |
|---|---|---|
| **A. Separate nodes, separate contexts.** Red hands Green a short file: the failing test, the clause it proves, and the files to touch. | **Lower** | Green starts clean. It never re-reads Red's exploration, test runs and dead ends on every turn. |
| **B. Two roles taking turns in one shared session** | **Same or higher** | The transcript is shared, so it grows exactly as it does today. Swapping the role prompt each turn would also break the cache prefix, turning cache reads into writes. |

So only A helps. Its costs are real but bounded:
- **Re-exploration.** Green re-reads code that Red already read. The handoff file has to carry Red's findings ("the seam is `foo.py:120`") or Green pays for them again.
- **Each node pays the fixed overhead again.** That's one cache write of the instruction files and prompt, roughly 1.25× once, then cheap reads. Today that floor is a large share of each response (the orchestrator's CLAUDE.md alone is 54.6k tokens), so A works best after shortlist item 1 trims it.
- **Little back-and-forth if the handoff is a file, not a conversation.** The overhead appears when Green has to ask Red what the test meant. That is a test-quality problem, and it's worth knowing about before Green starts.

**A bonus beyond tokens:** A makes the test author a different agent from the implementer. That's the independence rule every no-review factory in the research converges on. It also attacks test-gaming directly: Green can't rewrite the test, because your `red_green_replay` hook already requires byte-identical test files between Red and Green.

**Rough size of the prize:** `implement` is 58% of factory spend ($2,512 this week). If Green's turns stop carrying Red's transcript, the per-turn input on the longer half of the node should drop noticeably. I won't put a number on it until the agent reports and I can split the current `implement` transcripts at the Red commit to measure each phase's share.

The overseer state stays `blocked` (in discussion with you). I'll report the research when it lands.

## 5. Open at the time of recording

- Note 006 rewrite: PR #2940 (https://github.com/thewoolleyman/livespec-dev-tooling/pull/2940), auto-merge enabled.
- Split Red/Green TDD research: a Fable subagent was running; its report lands as a later note.
- Question 7 (re-basing verification on a deterministic check) is the maintainer's product decision.
- The tool-output plan is wanted but not to be created yet (epic note, 2026-10-28).
- Assertion 10 of the plan proof (reboot vps, or reword) is still the maintainer's call.
