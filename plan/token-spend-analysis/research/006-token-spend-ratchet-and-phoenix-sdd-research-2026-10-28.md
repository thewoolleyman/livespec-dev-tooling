<!-- Commissioned 2026-10-28 by the maintainer in session b021574a; web research by an independent Fable subagent. Rewritten the same day: real llm-spend metrics added, the maintainer's ten questions answered, and the prose cut to lists. Not yet acted on: nothing is commissioned from it except the separate tool-output plan recorded on epic livespec-dev-tooling-6lv7ze. -->

# Keeping LLM token spend bounded in a minimal-attention, spec-driven factory

Tags: **[M]** measured in `llm-spend` on 2026-10-28; **[L]** from a dated local
note or file; **[S]** sourced from the linked page; **[I]** inference.

## 1. Summary

- **What costs money.** Input that is re-read on every turn. It is not output.
  - Output is 3-10% of cost wherever the price split is recorded **[M]**.
  - A factory response reads a median of 195k-218k input tokens on Codex and
    340k-430k on Claude **[M]**.
- **What fills that input.** Harness overhead: instruction files, skill and
  plugin catalogues, and the growing transcript. The task text is a small part.
- **What everyone else does about it.** Two moves:
  1. Load less by default and fetch on demand.
  2. Keep what is loaded identical between calls, so it bills at the cache-read
     price.
- **What to measure.** Dollars per accepted item, not tokens. One controlled
  study cut tokens 38% and *raised* cost 6.8% **[S]**.
- **The ratchet is real.**
  - Instruction files grow +226% over their lifetime **[S]**.
  - Recording each rule's rationale lets it be pruned safely, which cut excess
    growth 99.3% **[S]**.
  - This fleet already records rationale. What is missing is a gate that forces
    the pruning.
- **What Phoenix-style factories keep** (they run with no human code review):
  1. A deterministic check the implementer cannot see or edit.
  2. A judge that is never the worker.
  3. Regeneration limited to the code a spec change reaches.

## 2. Measured spend

### 2.1 Totals, last 7 days (to 2026-10-28 ~21:30Z) [M]

Query: `SUM(cost_usd)`, `spend.schema in [2, 6]`, correction rows kept so
retracts net out. USD is API list price; the bill is subscription quota, so
read USD as relative weight.

| Consumer | Provider | USD | Share |
|---|---|---:|---:|
| Local Claude sessions | Anthropic | 4,239 | 28% |
| No consumer recorded (rows before attribution began 10-25) | Anthropic | 3,657 | 25% |
| Factory nodes | OpenAI (Codex) | 3,491 | 23% |
| Host judges (`claude -p`) | Anthropic | 2,074 | 14% |
| Factory nodes | Anthropic | 870 | 6% |
| Local Codex sessions | OpenAI | 556 | 4% |
| **Total** | | **14,887** | |

By model: opus-5.5 $4,274; opus-4.8 $3,667; gpt-5.6-terra $3,530;
sonnet-5.5 $1,210; opus-5 $1,176; fable-5.1 $512; gpt-6-astra $347;
gpt-5.6-luna $10; haiku-5.5 $1.

### 2.2 Daily trend [M]

| Day | Total | Factory | Local | `claude -p` |
|---|---:|---:|---:|---:|
| 10-15 to 10-24 (avg) | ~1,220 | not attributed | not attributed | not attributed |
| 10-25 | 3,931 | 366 | 2,459 | 998 |
| 10-26 | 2,741 | 1,228 | 622 | 780 |
| 10-27 | 3,156 | 2,063 | 737 | 170 |
| 10-28 (to ~21:30Z) | 1,276 | 703 | 421 | 127 |

- Before 10-25 rows carry no consumer, so the split is unknown.
- The jump on 10-25 is partly real and partly coverage: factory Codex spend
  first reached `llm-spend` that day (note 005).

### 2.3 Host judges (`claude -p`) [M]

- Daily cost fell from $984 (10-25, opus-4.8) to $123 (10-28, sonnet-5.5)
  after coordinator rulings R47/R48/R66 moved the judges off Opus.
- 1,500 of the week's $2,074 is opus-4.8 in the orchestrator repo, all
  before the switch.
- **Cost is cache writes.** On rows with a price split:
  - cache write $331 of $360 (92%);
  - 72.3M tokens written at the 1-hour price, 0 at the 5-minute price;
  - 89.5M tokens read back.
  A one-shot judge pays the 2x 1-hour write and rarely re-reads it.

### 2.4 Factory nodes, last 7 days [M]

USD per node, corrections included:

| Node | Codex USD | Claude USD | Responses (Codex / Claude) |
|---|---:|---:|---:|
| implement | 2,178 | 334 | 27,995 / 2,063 |
| review_fix | 323 | 50 | 4,315 / 261 |
| proof_capture | 290 | 134 | 3,698 / 542 |
| review | 203 | 113 | 1,878 / 345 |
| fix | 178 | 85 | 2,544 / 481 |
| unattributed | 154 | 0 | 2,117 / 0 |
| dod_gate | 83 | 67 | 617 / 121 |
| proof_verify | 82 | 67 | 856 / 218 |
| disposition | 0 | 10 | 36 / 11 |

- `implement` is $2,512 of about $4,360 (58%) and 30k of about 48k responses.
- The verdict nodes (`review`, `dod_gate`, `proof_verify`) are about $615 (14%).

Input tokens per response, last 3 days, rows that carry a node [M]:

| Node | Codex P50 / P90 | Claude sonnet-5.5 P50 / P90 | Claude cache-read share |
|---|---|---|---:|
| implement | 195k / 235k | 374k / 640k | 98% |
| review | 214k / 236k | 372k / 415k | 88% |
| proof_capture | 218k / 240k | 380k / 410k | 95% |
| proof_verify | 217k / 227k | 361k / 379k | 88% |
| dod_gate | 204k / 219k | 341k / 349k | 73% |
| fix | 181k / 241k | 427k / 531k | 100% |
| disposition | 34k (luna) | 104k / 357k | 31% |

- Every Codex P90 sits at about 235k: the compaction ceiling, not task size.
- Claude nodes have no such ceiling and run about 1.8x the Codex median.
- `disposition` is the control: its prompt was explicitly bounded (`bd-ib-7zxqyl`).

### 2.5 Local sessions [M]

- Median input per response: 222k (10-26), 301k (10-27), 239k (10-28).
- Top spenders this week: orchestrator repo $1,071; `petri-factory-on-gmktec`
  $762; `gitops-fleet-capacity-monitoring` $333; `github-app-checks-read` $279.
- Cache writes are $378 of $1,293 (29%) on rows with a price split.

### 2.6 Telemetry gaps (fix before trusting a before/after)

1. **No cache split on factory Codex.** The spans carry none; the board assumes
   90% cached. Codex cache-share claims are therefore not measured.
2. **$3,657 of local Claude has no consumer**, from rows before 10-25.
3. **Price-split columns are partial.** `usd.*` covers only about 30% of local
   rows, so component shares above are for the rows that have them.
4. **Codex node is `pending` on the original row.** The node arrives on the
   restate, and tokens live only on originals. So per-node Codex token
   percentiles use the subset of rows that carry a node (about 2.4k of 44k in
   3 days).
5. **Sonnet 5.5 cache-read price disagrees.** The research quoted $0.10/MTok;
   the emitter (`emit_spend.py`) prices $0.20/MTok. Verify against the
   pricing page before relying on cache ratios.
6. **No tool-output measurement.** `llm-spend` cannot see tool-result size. The
   separate tool-output plan needs a transcript-side probe.

## 3. Local file sizes [L]

| File | Size |
|---|---:|
| `livespec-dev-tooling/CLAUDE.md` | 45.8 KB, 772 lines (vendor target: under 200 lines) |
| `livespec-orchestrator-beads-fabro/CLAUDE.md` = `AGENTS.md` | 147 KB, 54,650 tokens per request (orchestrator note 002) |
| `livespec/CLAUDE.md` | 92.8 KB |
| `livespec-console-beads-fabro/CLAUDE.md` | 67.2 KB |
| `vps-info/CLAUDE.md` | 166 KB |
| `livespec/.claude/skills/needs-attention-internal/SKILL.md` | 62.7 KB (vendor target: under 500 lines) |
| `implement-work-item/prompts/*.md` | 6.8-39 KB per node |

- **Codex silently truncates.** It stops reading `AGENTS.md` at
  `project_doc_max_bytes`, 32 KiB by default **[S]**.
  - The orchestrator's 147 KB file is 78% unread on Codex nodes.
  - This repo's 45 KB file is 29% unread.

## 4. What others do, by mechanism

### A. Load a short index always; load bodies on demand

- **Claude Code:** CLAUDE.md under 200 lines; `.claude/rules/*.md` with `paths:`
  load only for matching files; `@` imports do NOT reduce cost
  (https://code.claude.com/docs/en/memory). Skills keep only name and
  description in context until invoked; SKILL.md under 500 lines
  (https://code.claude.com/docs/en/skills).
- **Cursor:** rules are Always / glob-attached / agent-requested / manual
  (https://cursor.com/docs/context/rules).
- **Kiro:** `always` / `fileMatch` / `manual` / `auto`; AGENTS.md is always
  included (https://kiro.dev/docs/steering/).
- **Codex:** AGENTS.md capped at 32 KiB; skills capped at 2% of the window
  (https://learn.chatgpt.com/docs/agent-configuration/agents-md).
- **Size in practice:** the Claude Code team's own CLAUDE.md is about 2.5k
  tokens (InfoQ); HumanLayer's root file is under 60 lines.
- **Evidence on value:**
  - Context files add over 20% cost with no general success gain; repository
    overviews do not help, but specific instructions are followed
    (https://arxiv.org/abs/2602.11988).
  - AGENTS.md presence: -28.6% runtime, -16.6% output tokens
    (https://arxiv.org/abs/2601.20404).
- **Here:** the `.ai/` index is two-tier in intent, but the index itself is 772
  lines.

### B. Turn always-true rules into hooks and gates

- **Anthropic:** "If something has to happen every time, make it a hook, a deny
  rule, or a managed setting." (https://code.claude.com/docs/en/best-practices)
- **Factory.ai:** lint green is the definition of done; AGENTS.md carries the
  why, lints carry the guarantee (https://factory.com/using-linters-to-direct-agents).
- **Osmani's sunset rule:** when an agent repeats a mistake, fix the codebase,
  then delete the AGENTS.md line (https://addyosmani.com/blog/agents-md/).
- **Candidates here:**
  1. the `ls`-is-`lsd` false-absence rule (unalias in the hook env);
  2. "use `with-livespec-env.sh`" (refuse bare `bd`);
  3. "never `bd init`" (deny rule);
  4. "dispatch `just check` detached" (rewrite the command).

### C. The ratchet and its counter

- **Measured growth:** 247,694 instruction lifetimes over 1,867 repos; +226%
  growth; +4.9 net instructions per commit; recorded rationale removed 99.3%
  of excess (https://arxiv.org/abs/2608.11095).
- **More rules, worse following:** 68% accuracy at 500 instructions; the newest
  rule at the bottom is followed least (https://arxiv.org/abs/2507.11538).
- **Focused prompts win:** about 300-token prompts beat about 113k-token prompts
  on all 18 models tested (https://www.trychroma.com/research/context-rot).
- **Budget gates exist elsewhere:** aiwg `lint:claude-context --strict`; BMAD v6
  "smaller or equal, never larger".

### D. Give the agent the spec slice, not the tree

- **OpenSpec:** delta specs per change, archived after merge and never loaded
  again (https://github.com/Fission-AI/OpenSpec).
- **Spec Kit:** one spec folder per feature.
- **Tessl:** each spec declares the files it targets; "too large or too many
  specs will overload the context window".
- **BMAD:** shards by heading. **Aider:** repo map capped at 1k tokens.
- **Here:**
  - livespec already has the delta shape (`proposed_changes` → revise →
    `history/vNNN`).
  - `bd-ib-qksrl6` bounded judge prompts to their clauses.
  - Factory nodes still get whole-tree context.

### E. Bound the transcript inside a node

- **Anthropic context editing:** clearing old tool results cut tokens 84% on a
  100-turn eval; every clear invalidates the cached prefix
  (https://claude.com/blog/context-management).
- **Claude Code:** `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (100k-1M); tool responses
  capped at 25k tokens.
- **Amp:** removed compaction as lossy and replaced it with `/handoff` into a new
  thread (https://ampcode.com/news/handoff).
- **Factory.ai:** 50% more context means 50% more cost; every compaction method
  scores weak on artifact tracking.
- **Fabro:** per-node `fidelity`, `max_visits`, `timeout`, `reasoning_effort`
  (default high). There is no token or dollar budget per node
  (https://docs.fabro.sh/reference/dot-language).

### F. Cache economics

See answer 6 in section 5 for how caching works.

- **Measured savings:** strategic caching cut cost 41-80% over 500+ sessions;
  put dynamic content last (https://arxiv.org/abs/2601.06007).
- **Hit rate is the metric:** Manus calls KV-cache hit rate "the single most
  important metric"; a timestamp at the top of the system prompt breaks it.
- **Measured negative:** compressing tool output cut tokens 38.4% and raised
  cost 6.8%; token and cost reduction correlate at only r = 0.15
  (https://arxiv.org/abs/2607.12161).

### G. Model and effort for verdict turns

- **Anthropic:** Opus 5.5 at low effort with escalation on failure solved about
  97% at $0.17/task, against 95.3% at $0.29 all-high
  (https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence).
- **Rubric-driven acceptance judging:** the smallest model was the most
  accurate, at 78x lower cost (https://arxiv.org/abs/2512.01232).
- **Calibration matters:** small judges rank well but agree with humans less on
  individual items (https://arxiv.org/abs/2406.12624).

### H. Tool-output hygiene

- **Moved to its own plan** (maintainer direction 2026-10-28, recorded on the
  epic).
- **Evidence it saves tokens:**
  - hook-filtered test output cuts context "from tens of thousands of tokens to
    hundreds";
  - Programmatic Tool Calling -37% tokens;
  - Tool Search cut definitions from about 77k to 8.7k tokens.
- **Evidence it may not save dollars:** arXiv 2607.12161 and the JetBrains
  `rtk` A/B (+7.6% cost at low effort).

### I. Phoenix-style (disposable implementation) practice

Who builds this way:
- **Chad Fowler, "Regenerative Software":**
  - "The code is not the asset. The specification and the evaluation are the
    asset."
  - "If you don't know how you would evaluate regenerated code, regeneration
    is reckless."
  - He still rereads network and business-rule code.
  - Reference implementation: https://github.com/chad/phoenix.
- **Tessl (Podjarny):**
  - "Code becomes disposable."
  - Regenerate until the tests pass.
  - Only a human may call a regression test wrong.
  - On full autonomy: "not there yet".
  - Links: https://tessl.io/blog/taming-agents-with-specifications-what-the-experts-say/
    and https://tessl.io/blog/spec-driven-development-10-things-you-need-to-know-about-specs/.
- **StrongDM:**
  - "Code must not be reviewed by humans."
  - Holdout scenarios stored outside the repo.
  - A satisfaction fraction, not green/red.
  - Behavioural clones of third-party services (https://factory.strongdm.ai/).
- **Mechanical Orchard:** a parallel run of legacy against new; "The agent that
  does the work is never the agent that judges it."
- **Anthropic's C compiler:** 16 agents, about 2,000 sessions, $20k, 2B input
  tokens, 99% pass on most compiler suites. "The task verifier is nearly
  perfect, otherwise Claude will solve the wrong problem."
- **Böckeler's taxonomy:** spec-first, spec-anchored, spec-as-source. livespec is
  spec-anchored moving toward spec-as-source **[I]**
  (https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html).

What the evidence says about verification:
- **Judges are worse than tests at correctness:**
  - LLM judges reject correct-but-different code (https://arxiv.org/pdf/2506.17335);
  - best single judge Youden's J < 0.4 (https://arxiv.org/html/2602.18492v1).
- **Judges are good at catching test-gaming:**
  - EvilGenie: the judge catches hacks, held-out tests barely help
    (https://alphaxiv.org/abs/2511.21654);
  - ImpossibleBench: GPT-5 exploits tests 76% of the time on conflicting tasks
    (https://arxiv.org/abs/2510.20270).
- **Coverage is not an oracle:** 100% coverage can mean a 4% mutation score
  (https://arxiv.org/abs/2506.02954).
- **Risk tiering works at scale:** Meta's RADAR (https://arxiv.org/abs/2605.30208).
  See answer 4.

Measured failures:

| Who | What went wrong |
|---|---|
| Fowler `phoenix` | 0/5 against 5/5 for one model call; see answer 1 |
| StrongDM | `return true`; tests rewritten to match the code |
| Yegge | "Some bugs get fixed 2 or 3 times ... Other fixes get lost"; later reviews the last 25% of PRs |
| Horthy / HumanLayer | 4 months lights-off, then a production break nobody could root-cause; 3 weeks to re-onboard |
| Böckeler | the same spec generated different code on each run |

## 5. Answers to the maintainer's questions (2026-10-28)

### 1. The 0/5 against 5/5 result

- **Source:** the README of Chad Fowler's `phoenix` reference implementation.
- **Setup:** a `todo-api` benchmark, 5 runs each on Sonnet 5.
  - The pipeline splits the spec into clauses, maps clauses to units, and
    generates each unit separately: **0 of 5** passed end to end.
  - One model call given the whole spec: **5 of 5**.
  - The brackets in the source are 95% confidence intervals.
- **Failure:** every run mounted HTTP routes at a path guessed from the unit's
  name, not at the path the spec stated.
- **Why nobody noticed:** type checks and `phoenix status` check structure, not
  behaviour, so both stayed green.
- **Lessons for us:**
  1. Slicing a spec drops facts that span units (interfaces, routes). A slice
     must carry its interface clauses.
  2. Only an end-to-end behavioural check catches this.

### 2. Reuse the last verified unit, keyed on its clauses

- **Why a hash cache fails:** the same prompt does not reproduce the same code.
  1,000 samples at temperature 0 gave 80 different completions
  (https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/).
- **What to store instead,** per implementation unit:
  1. the spec clauses it depends on;
  2. each clause's content hash when the unit last passed;
  3. the verdict.
- **On a spec change:** skip every unit whose clause hashes are unchanged. No
  regeneration and no re-judging.
- **Analogy:** make or Bazel with a non-deterministic compiler, so you cache the
  approved output, not the function.
- **Already here:** `bd-ib-k5qp5z` reuses a heading verdict across a revision
  that leaves the heading unchanged.

### 3. Where comprehension goes when no human reads the code

Correction (maintainer, 2026-10-28): at a stall, the first reader is the
coordinator agent, told to fix it immediately. A person does not read the spec
first. So comprehension must serve an agent debugging under time pressure.

- **The agent needs:**
  1. the spec, for intent and the hard-won details (Fowler's timeout that "has
     to be 17 seconds");
  2. code an agent can navigate;
  3. retained failure evidence: traces, `llm-spend`, `tmp/janitor-failed-output`.
- **Changes:**
  1. Remove LLM grading of human code style (readability, naming taste) from
     the `review`, `review_fix`, `dod_gate` and `proof_grade` rubrics. First
     step: list which rubrics contain such criteria (not done yet).
  2. Keep navigability as deterministic gates: file and function size limits,
     complexity limits, types, module boundaries. They cost nothing per item.
  3. The drift pass files proposed changes for non-obvious behaviour, not only
     for new features.
  4. Treat failure-evidence retention as part of the oracle. A stall the
     coordinator cannot diagnose costs more than a review pass.
- **Caveats:**
  - Fix loops edit code in place; the implementation is not regenerated from
    scratch.
  - Horthy's team needed 3 weeks to recover after 4 months lights-off.

### 4. Meta's RADAR

- **Paper:** arXiv 2605.30208 (May 2026). This summary came from the subagent;
  the paper has not been read first-hand.
- **The funnel every diff passes through:**
  1. Is the diff AI-authored?
  2. Is it eligible for automated review?
  3. Static heuristics.
  4. A machine-learned risk score.
  5. LLM review.
  6. Deterministic validation.
- **Result:** diffs under the risk threshold land without human review.
  - Raising the threshold from P25 to P50: 60.31% auto-approved.
  - 535k diffs reviewed, 331k landed.
  - About 1/3 the revert rate and 1/50 the incident rate of other diffs.
  - Selection bias: low-risk diffs break less anyway.
- **For us, a risk score from:**
  1. product `.py` touched;
  2. number of clauses touched;
  3. the item's prior failed attempts.
- **Tiers:**
  - Low: deterministic gates plus one cheap LLM pass.
  - High: full replay.

### 5. Capping transcript growth in a node

In order of safety:
1. **Lower the compaction window on Claude factory nodes.**
   - Set `CLAUDE_CODE_AUTO_COMPACT_WINDOW` to about 200k through the adapter env.
   - Evidence: Codex compacts at about 235k and its median is about half of
     Claude's on the same nodes (2.4) with no recorded quality loss.
   - Unverified: whether the variable reaches the session through the ACP
     adapter. Test that first.
2. **Filter test output with a hook.**
   - A PreToolUse hook cuts `just check` output to the failures.
   - Note: this belongs to the separate tool-output plan.
3. **Split long nodes into phases with a handoff file.**
   - Candidate seams already in the graph: `implement` → `implementation_diff`
     → `janitor` → `fix`.

- **Quality gate:** first-pass acceptance and fix-loop count per node must not
  worsen. Compaction loses information.
- **Home:** the orchestrator's `factory-context-per-turn-reduction` plan.

### 6. How prompt caching saves money

1. **What is cached.**
   - A request is `tools` → `system` → `messages`. The provider stores the
     processed state of a prefix.
   - A later request whose prefix is byte-identical bills those tokens at the
     cache-read price: about 0.1x base per the emitter (see 2.6 item 5).
2. **Why agents depend on it.**
   - Each turn resends the whole transcript, so turn N's prefix is turn N-1's
     request.
   - Claude factory nodes read 73-100% of their input from cache (2.4).
3. **What a write costs.**
   - Storing a prefix costs 1.25x (5-minute expiry) or 2x (1-hour expiry).
   - Each hit restarts the clock.
4. **What breaks the cache.** Any change early in the prefix makes everything
   after it a fresh write:
   - a timestamp or run id in the system prompt;
   - unstable tool order;
   - an edited CLAUDE.md;
   - an MCP reconnect;
   - a model switch.
5. **How to stay cache-friendly.**
   - Static content first; ids, dates and per-run data last.
   - Deterministic JSON key order.
   - `--exclude-dynamic-system-prompt-sections` on `claude -p`, so checkouts
     share a prefix.
6. **When the 1-hour expiry pays.** Only when the same prefix is reused more
   than 5 minutes later.
   - On a one-shot call it is pure loss.
   - Measured: judges wrote 72M 1-hour tokens this week for $331 of $360 (2.3).
   - Fix: 5-minute expiry for one-shot judges, or batch many statements
     sharing a heading into one call that reuses the prefix.
7. **Batches.**
   - Asynchronous, 50% off all tokens, stacks with cache discounts; results
     within 24 h, usually under 1 h.
   - Fits single-shot judgements only. A multi-turn replay that uses tools
     cannot be batched.
   - Needs an API key and real dollars. The judges currently run on
     caam-rotated subscriptions, so the saving is not automatic.

### 7. Base verification on a deterministic check (maintainer decision)

- **Today:** one item can be judged by:
  - factory `review`;
  - `proof_verify`;
  - the graded `dod_gate`;
  - `proof_grade`;
  - the host judges;
  - plus the plan-level replay and completeness review.
- **Proposal:**
  1. `dod_gate` passes or fails on tests the implementer cannot see or edit:
     held-out scenarios and mutation score. `fleet-mutation-testing-rule-26`
     builds the mutation part.
  2. One LLM pass checks only test-gaming, test-file tampering and going beyond
     the spec clause.
  3. Replay and completeness review are sampled by risk tier.
  4. LLM grading of code shape is dropped (answer 3).
- **Why it is a product decision:** some items would merge without an
  independent replay.
- **Recommended order:**
  1. Arm the deterministic check first; never remove the judges before what
     replaces them is running.
  2. Shadow-run the tiered policy, logging what the skipped replays would have
     caught.
  3. Switch.
  4. The number that must not rise: post-merge revert rate by tier.
- **Money at stake [M]:**
  - verdict nodes about $615/week;
  - host judges $2,074/week before the model switch, about $125/day after;
  - fix loops caused by false rejections are not yet measured.

### 8. How to decide what to prune

Instruction files (each entry already carries its date and reason):

| Entry type | Action |
|---|---|
| Enforced by a hook or gate | Delete the prose; the gate's refusal message teaches the fix |
| Triggered by a file path | Move to a `.claude/rules` file with `paths:`; it stops loading every request |
| An incident story ("recorded because on <date> ...") | Cut to a one-line rule; the story moves to `.ai/` or git history |
| About a retired system | Delete |

- **The budget gate forces the choice:** a PR that pushes a file past its budget
  fails until its author cuts or converts something.

The spec:
- **Rejected from the original research:** shortening a clause to a pointer at
  its test. That would make the test the source of truth and invert livespec.
- **Instead:**
  1. Never load `history/vNNN` into a prompt (`prune-history` exists).
  2. Deliver clause slices, not the tree (answer 9).
  3. Read a spec-size budget as a signal to generalize, per the maintainer's
     2026-10-19 ruling: "the spec should be generalized to be correct rather
     than always expanded."

### 9. Is this `spec-implementation-lockstep`?

No. The two link different things:

| | lockstep | proposed map |
|---|---|---|
| Links | work item → clause that authorizes it | clause → code modules that implement it |
| Answers | "Is this behaviour in the spec?" | "Which clauses does this node need? Which modules does this spec change reach?" |
| Used at | dispatch (citation check), post-merge drift pass | prompt assembly and regeneration scope |

- **Pieces that already exist:**
  1. `tests/heading-coverage.json`: clause → test.
  2. `bd-ib-qksrl6` and `_spec_tree_condensation.py`: bounded clause sets for
     judges.
  3. `bd-ib-k5qp5z`: verdict reuse across revisions.
  4. lockstep citations: item → clause.
- **The missing link can be derived:** clause → test (have) plus test → module
  from coverage data (have).
- **Risk:** answer 1. Interface clauses must travel with every slice.

### 10. Model and effort for verdict nodes

- **Model: largely done.** R47/R48/R66 moved host judges to Sonnet 5.5 and
  Haiku 5.5.
  - Measured: $984/day to $123/day (2.3).
  - Burn note 002 also proposes a GPT-5.6 Luna trial on `dod_gate`,
    `proof_capture` and `disposition`.
- **Effort: weak lever here.**
  - Output is 3-10% of cost (2.1), so effort mostly changes turn count, not
    price.
  - The research's "about 40% cheaper" figure came from workloads where output
    dominates.
- **Why a cheaper model can be good enough, and where it cannot:**
  - **Narrow, rubric-shaped verdicts can go cheap.** Examples: "did this diff
    modify a test to make it pass?", "is this behaviour in clause X?". Inputs
    are bounded and the answer needs little reasoning. A tight rubric made a
    small judge more accurate and 78x cheaper (G).
  - **Open-ended verdicts need a strong model.** Examples: completeness review,
    replay interpretation, "is this plan done?". Small judges rank well but
    disagree with humans on individual items.
- **Rule:** switch per verdict type only after a shadow run.
  1. Run the cheap model beside the strong one on the same inputs.
  2. Log agreement and compare against later reverts.
  3. Keep the strong model wherever they disagree.
  - Reason: a cheap judge that wrongly rejects good code costs more in fix
    loops than it saves.

## 6. Ranked shortlist (revised with measurements)

| # | Change | Why, with measurement | Status |
|---|---|---|---|
| 1 | Factory nodes load only declared context: no repo CLAUDE.md, no plugin, skill or MCP catalogues | 54.6k tokens per request from one file; `implement` is 58% of factory USD; ends Codex's silent 32 KiB truncation | Scoped as `factory-context-per-turn-reduction` C3 |
| 2 | Bound transcript growth on Claude factory nodes (answer 5) | Claude medians about 1.8x Codex on the same nodes | Belongs in the same orchestrator plan |
| 3 | Cache policy: dynamic content last; 5-minute expiry for one-shot judges; batch judgements that share a heading | Judges: 92% of cost is 1-hour cache writes | Not started |
| 4 | Verification on a deterministic check, LLM layers tiered by risk (answer 7) | Verdict nodes about $615/week plus host judges; fix loops not yet measured | Maintainer decision |
| 5 | Size budgets in CI for instruction files; spec slices, never history (answer 8) | This repo's file is 772 lines, the orchestrator's is 147 KB | Not started |
| 6 | Clause → module map (answer 9) | Decouples cost per change from spec size | Design now, build after 1-4 |
| 7 | Verdict model routing (answer 10) | Judges already $984 → $123/day | Largely done; shadow-run any further switch |
| 8 | Tool-output hygiene | Measure in dollars; token cuts can raise cost | Separate plan (epic note, 2026-10-28) |

Before any before/after claim, close the telemetry gaps in 2.6, items 1, 4 and 5.

## 7. Not verified

- JetBrains `rtk` A/B (HTTP 403); Requesty cache-hit report (binary PDF).
- Thoughtworks Radar vol. 34 "Agent instruction bloat"; Arize's IFScale re-run
  (subagent report only).
- Codex compaction internals: secondary posts only.
- RADAR paper: subagent summary, not read first-hand.
- No published risk-tiered LLM code-review scheme from Google; no cheap-judge
  agreement study on coding verdicts.
- Sonnet 5.5 cache-read price (2.6 item 5).
