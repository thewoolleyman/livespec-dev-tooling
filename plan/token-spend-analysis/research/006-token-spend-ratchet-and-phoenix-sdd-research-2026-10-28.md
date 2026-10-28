<!-- Research by an independent Fable subagent commissioned 2026-10-28 by the maintainer in session b021574a: how minimal-attention, spec-driven (Phoenix-style) factories keep token spend bounded long term. Sourced facts and the agent's inference are separated inside. Not yet acted on: no work item or plan is commissioned from it. -->

# Keeping LLM token spend bounded in a minimal-attention, spec-driven factory

Research note, 2026-10-28. Web research plus read-only inspection of this fleet's
instruction files, workflow graph, and the two plans already open on this topic
(`livespec-dev-tooling/plan/token-spend-analysis`,
`livespec-orchestrator-beads-fabro/plan/factory-context-per-turn-reduction`,
`livespec-orchestrator-beads-fabro/plan/anthropic-burn-mitigation`). Nothing was
modified, no ledger command was run, nothing was dispatched.

Tagging: **[S]** = sourced from the linked page (quoted or closely paraphrased).
**[L]** = measured locally in this session or quoted from a dated local research
note. **[I]** = my inference or arithmetic. Honeycomb could not be queried from
this session (the MCP needed an interactive re-auth), so the measurement
section names columns from the plan notes and the emitting code, not from a
live schema read.

---

## Bottom line

Spend in this system is not driven by output (about 270 output tokens per
response, under 5% of cost **[L]**) but by a per-response INPUT FLOOR that is
re-read on every turn: median 156k-220k tokens per factory response on Codex,
365k-755k on Opus 5, 381k on the one Sonnet 5.5 node sampled so far **[L]**.
That floor is harness overhead (instruction files, skill/plugin/MCP catalogues,
the accumulated transcript), not task text, and every published mechanism that
keeps per-turn input flat attacks it by the same two moves: (1) load less by
default and fetch on demand (two-tier instruction loading, per-feature or
per-delta spec slices, bounded indexes, sub-agent isolation), and (2) make what
IS loaded cache-stable so the re-reads bill at 0.05x instead of 1x (Sonnet 5.5
cache reads are $0.10/MTok against $2.00 raw and $2.50 for a cache write
**[S]**). The literature is unusually clear that token counts are the wrong
objective: one controlled study found the heaviest tool-output compression cut
delivered tokens 38% and RAISED billed cost 6.8% **[S]**, so the series to track
is billed dollars and cache-read share per node, and tokens per accepted item.
The long-term ratchet is real and now measured: instruction files grow +226%
over their lifetime at +4.9 net instructions per commit, and the only measured
counter is recording each instruction's rationale so it can later be pruned
safely, which cut excess growth by 99.3% **[S]**. This fleet's files already
carry rationale ("recorded because it failed on <date>"), which means the
pruning precondition is met and the missing piece is a budget gate that forces
the pruning to happen.

Under the Phoenix / disposable-implementation framing (section I), the
practitioners who actually run without human code review (StrongDM, Mechanical
Orchard, Fowler's `phoenix`, Anthropic's C-compiler run) converge on the same
three things: a deterministic oracle the implementer cannot see or edit, a
judge that is never the worker, and regeneration scoped by provenance to the
units a spec change reaches. The measured evidence says LLM judges are worse
than execution at correctness and mis-classify correct code, but are good at
catching reward hacking, and Meta's RADAR shows risk-tiered automation (not
universal review) is what buys a 1/50 incident rate at scale. So a disposable
implementation does change the economics of this fleet's stacked review: the
code-shape and comprehension dimensions of review are worthless for a reader
who is not there, the correctness dimension belongs to tests, and the one LLM
pass worth keeping is the independent hack and scope check, with replays
sampled by risk. Hash-keyed regeneration caches do not exist because generation
is not reproducible; the reusable artifact is the last VERIFIED unit and its
verdict, keyed on the spec clauses it depends on.

---

## First-hand local measurements (read-only)

| Artifact | Size | Note |
|---|---:|---|
| `livespec-dev-tooling/CLAUDE.md` | 45,766 B, 772 lines | Vendor target is under 200 lines **[S]** |
| `livespec-dev-tooling/.ai/*.md` (18 files) | ~136 KB (plus a 64 KB `supervisor-protocol.md`) | Loaded on trigger via prose index, not by `paths:` rules |
| `livespec-orchestrator-beads-fabro/CLAUDE.md` = `AGENTS.md` | 147,088 B | Measured at **54,650 tokens per request** on the Claude tokenizer (note 002, 2026-10-28) **[L]** |
| `livespec/CLAUDE.md` | 92,796 B | |
| `livespec-console-beads-fabro/CLAUDE.md` | 67,205 B | |
| `vps-info/CLAUDE.md` | 166,318 B | |
| `livespec/.claude/skills/needs-attention-internal/SKILL.md` | 62,650 B | Vendor target is under 500 lines **[S]** |
| `implement-work-item/prompts/*.md` | 6.8-39 KB per node | proof-capture 39.4 KB, proof-verify 29.5 KB, implement 27.5 KB (note 001) **[L]** |

Factory per-response input (input + cache read + cache creation), from
`llm-spend`, as recorded in the orchestrator's notes 001/002 (2026-10-28) **[L]**:

| Node | Codex median / p90 | Opus 5 median | Sonnet 5.5 median |
|---|---:|---:|---:|
| implement | 192,519 / 235,783 | 755,346 | not yet sampled |
| review | 213,503 / 235,390 | 497,013 | |
| review_fix | 182,268 / 234,556 | 406,219 | |
| fix | 156,402 / 233,798 | 364,603 | |
| proof_capture | 219,665 / 239,873 | | 381,523 (17 responses) |
| dod_gate | 206,432 / 220,011 | | |
| disposition | 30,842 / 34,878 | | |

Two things the notes already observed that matter for ranking: the Codex p90
bunches at ~235k on every node, the signature of a compaction ceiling rather
than task variance; and `disposition` is the control at 31k because its prompt
was explicitly bounded (`bd-ib-7zxqyl`). The Claude nodes show no ceiling and
run 2-4x the Codex medians, which says the transcript component is the largest
share on Claude routing **[L]**. The judge (`claude -p`) floor is ~140-150k
after `bd-ib-qksrl6` removed the 440k tail **[L]**.

One consequence nobody has written down yet **[I]**: Codex stops reading
`AGENTS.md` once the combined size reaches `project_doc_max_bytes`, 32 KiB by
default **[S]**, so on Codex routing the orchestrator's 147 KB file was silently
78% absent and this repo's 45 KB file was 29% absent. Whatever those nodes
were doing, they were not following the bottom two-thirds of the file. Any
plan to "move rules into AGENTS.md so Codex sees them" is already failing
silently today.

---

## Findings by mechanism

### A. Two-tier instruction loading (tiny always-load index + on-demand bodies)

**What.** Every vendor converged on the same shape: a short always-loaded file,
a catalogue of names+descriptions, and full bodies loaded only on trigger.

**Who / evidence.**
- Claude Code: "target under 200 lines per CLAUDE.md file. Longer files consume
  more context and reduce adherence"; `.claude/rules/*.md` with `paths:`
  frontmatter "load only when Claude works with matching files"; `@` imports
  "don't reduce its context cost" **[S]** (https://code.claude.com/docs/en/memory).
  Costs page: "Aim to keep CLAUDE.md under 200 lines"; `/usage` now emits rows
  like `Trim ~/code/api/CLAUDE.md · 49k tokens per request` **[S]**
  (https://code.claude.com/docs/en/costs). Best practices: "every line in it
  takes a little of Claude's attention on every task, whether it's relevant or
  not"; "If Claude keeps ignoring a line that is in CLAUDE.md, adding IMPORTANT
  probably won't fix it. Either the file has grown long enough that the line
  gets lost, or the line is a rule that can't have exceptions, in which case it
  belongs in a hook" **[S]** (https://code.claude.com/docs/en/best-practices).
  `/doctor prompt-audit` (v2.1.283+) finds stale, contradictory, and
  dead-reference instructions across CLAUDE.md, rules, skills, agents **[S]**.
- Skills: only name+description (truncated at 1,536 chars) sit in context until
  invoked; "Keep SKILL.md under 500 lines"; `disable-model-invocation: true`
  removes even the description; `context: fork` runs a skill in a fresh subagent
  **[S]** (https://code.claude.com/docs/en/skills,
  https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills).
- Cursor: Always / Auto-attached by glob / Agent-requested by description /
  Manual; "Keep rules under 500 lines"; "Add rules only when you notice Agent
  making the same mistake repeatedly" **[S]** (https://cursor.com/docs/context/rules).
- Kiro steering: `always` / `fileMatch` / `manual` / `auto` inclusion modes,
  plus `#[[file:name:start-end]]` line-range references; `AGENTS.md` files "do
  not support inclusion modes and are always included" **[S]**
  (https://kiro.dev/docs/steering/).
- Codex: root-to-cwd AGENTS.md concatenation capped at `project_doc_max_bytes`
  = 32 KiB; `skills.max_context_tokens` defaults to 2% of the window capped at
  10k **[S]** (https://learn.chatgpt.com/docs/agent-configuration/agents-md,
  https://learn.chatgpt.com/docs/config-file/config-reference).
- Sourcegraph Amp: subtree AGENTS.md and `globs`-tagged files load only after a
  matching file is read **[S]** (https://ampcode.com/docs/customize/agents-md).
- Boris Cherny (via InfoQ): the Claude Code team's own CLAUDE.md is "2.5k
  tokens" **[S]** (https://infoq.com/news/2026/01/claude-code-creator-workflow/).
  HumanLayer: "< 300 lines is best, and shorter is even better"; their root file
  is under sixty lines **[S]** (https://www.humanlayer.dev/blog/writing-a-good-claude-md).
- Empirical: Gloaguen et al. 2026 found context files "do not generally improve
  task success rates, while increasing inference cost by over 20% on average";
  "repository overviews ... are not helpful" but specific instructions are
  followed **[S]** (https://arxiv.org/abs/2602.11988). Lulla et al. 2026, 124
  PRs: AGENTS.md present gave median runtime -28.6%, output tokens -16.6%,
  "comparable task completion" **[S]** (https://arxiv.org/abs/2601.20404).

**Mapping onto livespec.** The `.ai/` index in this repo's CLAUDE.md is
already two-tier in intent (trigger line in the index, body in the file), but
the index itself is 772 lines, and the orchestrator's single file is 54.6k
tokens on every factory response **[L]**. Concretely: (1) cut each repo's
CLAUDE.md to a ~200-line index; (2) move the `.ai/*.md` gotchas to
`.claude/rules/*.md` with `paths:` where the trigger is a file path (CI runner
dirs, `_red_green_replay_revert.py`, workflow files) and to skills where the
trigger is a task; (3) for Codex nodes, nothing above 32 KiB is read, so the
cut is mandatory, not optional; (4) factory nodes should not load the governed
repo's CLAUDE.md at all except through a per-node excerpt (this is
`factory-context-per-turn-reduction` C3, already scoped).

### B. Deterministic enforcement replaces prose (hooks, lints, gates)

**What.** A rule that must always hold is a hook, deny rule, or lint, and then
leaves the prompt.

**Who / evidence.**
- Anthropic: "If something has to happen every time, make it a hook, a deny
  rule, or a managed setting. CLAUDE.md is for guidelines"; "keep the enforced
  set small ... If you ever find yourself at forty of them, most are probably
  preferences" **[S]** (https://code.claude.com/docs/en/best-practices). Hooks
  provide "deterministic control: certain actions always happen rather than
  relying on the LLM to choose" **[S]** (https://code.claude.com/docs/en/hooks-guide).
  A PreToolUse hook that filters test output cuts context "from tens of
  thousands of tokens to hundreds" **[S]** (costs page).
- Factory.ai: "Achieving 'lint green' becomes the definition of 'Done'";
  AGENTS.md carries "the why and the examples", linting "the how and the
  guarantee"; every rule gets a severity, autofix, and a time-boxed waiver
  **[S]** (https://factory.com/using-linters-to-direct-agents).
- Addy Osmani's sunset rule: when an agent repeats a mistake, "fix the
  codebase" (lint, structure, test), then "delete the AGENTS.md line that
  addressed it ... each line flags friction that still needs fixing" **[S]**
  (https://addyosmani.com/blog/agents-md/).
- Google AutoCommenter: "top 85 guidelines made up 90% of AutoCommenter
  comments"; stale guidance handled by per-guideline suppression, not retraining
  **[S]** (https://newsletter.getdx.com/p/ai-assisted-code-reviews-at-google).

**Mapping.** This repo already does this well where it matters most
(`red_green_replay` hook, heading-coverage checks, range gate). The remaining
always-load prose is full of hook candidates: the `ls`-is-`lsd` false-absence
rule (a PreToolUse rewrite or an unalias in the hook env), "use
`with-livespec-env.sh`" (a Bash hook that refuses bare `bd`), "never `bd init`"
(deny rule), "dispatch `just check` detached" (a hook that rewrites the
command). Each one converted is a paragraph deleted from every request.

### C. The ratchet, measured, and its counter

**What.** Instruction files only grow because appending is cheap and safe
deletion of a rule whose rationale is lost is expensive.

**Who / evidence.**
- Chakrabarti 2026, "Why Does CLAUDE.md Keep Growing? Catastrophic Remembering
  in Agentic Coding": 247,694 instruction lifetimes across 1,867 repos; prompts
  grow **+226% over their lifetime, +4.9 net instructions per commit**; older
  instructions are less likely to be deleted (log-hazard -0.032 per commit);
  recording each instruction's rationale as a comment "removed 99.3% of excess
  instructions, reducing growth from +211.3% to +1.4%" and improved
  instruction-following on WildIFEval by up to 23.1% **[S]**
  (https://arxiv.org/abs/2608.11095).
- Thoughtworks Radar vol. 34 lists "Agent instruction bloat" in Caution
  (secondary report via subagent; not independently fetched).
- IFScale (NeurIPS 2025): accuracy decays with instruction count; "even the
  best frontier models only achieve 68% accuracy at the max density of 500";
  primacy bias peaks at 150-200 instructions, so the NEWEST rule appended at the
  bottom is the least likely to be followed **[S]** (https://arxiv.org/abs/2507.11538).
  Arize's 2026 re-run shows 2026 models hold further out but the shape and
  primacy bias remain (secondary, via subagent).
- Chroma "Context Rot": focused prompts (~300 tokens) beat full prompts (~113k)
  on every one of 18 models; "even a single distractor reduces performance"
  **[S]** (https://www.trychroma.com/research/context-rot).
- Budget-as-gate precedent: aiwg's `lint:claude-context --startup --strict`
  exits non-zero when startup context exceeds a budget (secondary, via subagent);
  BMAD v6's project-context audit rule "smaller or equal, never larger" **[S]**
  (https://raw.githubusercontent.com/bmad-code-org/BMAD-METHOD/V6.12/docs/existing-codebases/theory-of-project-context.md).

**Mapping.** This fleet's files are textbook: every entry carries a date and a
"why", which is exactly the paper's precondition for safe pruning, and nothing
forces the prune. The structural counter is a CI check in `just check` with a
frozen token (or line) budget per instruction file and per SKILL.md, measured
with the same tokenizer the models use, that FAILS when the file grows past
budget; adding a rule then requires deleting or converting another (B above).
This is the "unratified filter inside a check is conformance" case: the vendor
docs already state the limit.

### D. Spec slicing: load the delta or the clause, never the tree

**What.** No spec-driven tool loads the whole canonical spec per task.

**Who / evidence.**
- OpenSpec: `openspec/specs/<capability>/spec.md` is the source of truth;
  changes live in `openspec/changes/<name>/` as delta specs with `## ADDED /
  MODIFIED / REMOVED / RENAMED Requirements`; the apply skill reads only the
  change folder's `contextFiles`; `/opsx:archive` merges the delta into the
  main spec, "Preserves existing content not mentioned in delta", and moves the
  change to `changes/archive/YYYY-MM-DD-<name>/`, never loaded again **[S]**
  (https://github.com/Fission-AI/OpenSpec/blob/main/docs/commands.md,
  https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/skills/openspec-apply-change/SKILL.md).
- GitHub Spec Kit: one `specs/<branch>/` per feature; implement reads
  `tasks.md`, `plan.md`, optional `data-model.md`/`contracts/`, and the
  constitution; nothing from other features **[S]**
  (https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/implement.md).
- Kiro: "creating multiple specs for different features ... rather than ... a
  single one for your entire codebase" **[S]** (https://kiro.dev/docs/specs/best-practices/).
- Tessl: a `.spec.md` has `targets` globs binding it to the files it describes,
  so an agent loads the spec for the file it edits; "too large or too many specs
  will overload the context window" **[S]**
  (https://tessl.io/registry/tessl-labs/spec-driven-development,
  https://tessl.io/blog/spec-driven-development-10-things-you-need-to-know-about-specs/).
- BMAD v4: shard PRD/architecture by `##` heading, SM agent distills one story
  file, dev agent loads only the story plus `devLoadAlwaysFiles` **[S]**
  (bmad-kb.md v4.43).
- Addy Osmani: "don't feed 20k tokens if 5k will do"; give the agent "the
  Database section of the spec only, plus any global constraints"; keep a
  hierarchical outline in the prompt with "(see full spec §4.2)" pointers
  **[S]** (https://addyosmani.com/blog/good-spec/).
- Aider repo-map: a ranked map of files and symbols bounded by `--map-tokens`,
  default 1k tokens **[S]** (https://aider.chat/docs/repomap.html).

**Mapping.** livespec already has the OpenSpec shape (`proposed_changes/` ->
revise -> `history/vNNN`), and `bd-ib-qksrl6` already bounded judge prompts to
the clauses they need **[L]**. The gaps: (1) factory implement/review nodes
still receive whole-tree context where a heading-level clause set (the
`heading-coverage.json` map already keys clauses to tests and could key them to
work items) would do; (2) `history/vNNN` snapshots must never enter a prompt;
(3) a generated H2 outline of the spec with a token budget (Aider-style) is the
right always-available index, with clause bodies fetched by heading on demand.
A `--since-version` style delta (the `detect-impl-gaps` surface already has one)
is the per-task delta for revise-adjacent work.

### E. Transcript growth inside a node: cap, clear, or hand off

**What.** A node that takes many turns re-reads its own transcript each turn.
On Claude routing the transcript is the biggest share **[L]**.

**Who / evidence.**
- Anthropic context editing: on a 100-turn web-search eval, clearing old tool
  results let agents finish and "reduc[ed] token consumption by 84%"; memory
  tool + context editing +39% over baseline **[S]** (https://claude.com/blog/context-management).
  API: `clear_tool_uses_20250919` triggers at 100k input by default, keeps the
  last 3 tool uses; each clear invalidates the cached prefix **[S]**
  (https://platform.claude.com/docs/en/build-with-claude/context-editing).
- Claude Code: `--autocompact` / `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (100k-1M);
  after compaction CLAUDE.md and rules are re-injected and invoked skill bodies
  come back "capped at 5,000 tokens per skill and 25,000 tokens total"; tool
  responses capped at 25k tokens by default **[S]**
  (https://code.claude.com/docs/en/context-window,
  https://www.anthropic.com/engineering/writing-tools-for-agents).
- Sourcegraph Amp REMOVED compaction: "It's lossy" and "encourages long,
  meandering threads"; replaced with `/handoff`, which drafts a new-thread
  prompt plus a relevant-file list; "Use one thread per task" **[S]**
  (https://ampcode.com/news/handoff).
- Factory.ai: "A 50% increase in average context length translates directly
  to 50% higher inference costs"; anchored iterative summarization; eval over
  36,611 messages scored Factory 3.70 vs Anthropic SDK compaction 3.44 vs
  OpenAI 3.35 (0-5), all weak on artifact tracking **[S]**
  (https://factory.com/news/compressing-context,
  https://factory.com/news/evaluating-compression).
- Cognition: single-threaded agents with a separate small model compressing
  history, "hard to get right" **[S]** (https://cognition.com/blog/dont-build-multi-agents).
- Claude Code budget flags: `--max-turns` ("No limit by default"),
  `--max-budget-usd` (print mode; subagent spend counts; "Spend can pass the
  cap"), `--bare` (skips hooks, skills, plugins, MCP, auto memory and CLAUDE.md),
  `--exclude-dynamic-system-prompt-sections` **[S]** (https://code.claude.com/docs/en/cli-reference).
- Fabro per-node knobs: `max_tokens` (output only), `timeout`,
  `reasoning_effort` low/medium/high (default **high**), `fidelity` compact |
  full | summary:high/medium/low | truncate, `max_visits`, `max_retries`,
  `retry_policy`, `model_stylesheet`; **no dollar or input-token budget per node
  or run** **[S]** (https://docs.fabro.sh/reference/dot-language). Local caveat:
  the workflow comments say `model`/`reasoning_effort` are API-adapter-only and
  ACP (Claude Code / Codex) nodes pin them through the adapter's env **[L]**.

**Mapping.** The 755k Opus `implement` median says the node loops long and
compacts late. Three levers in order of safety: (1) a lower autocompact window
on factory Claude nodes (the Codex ceiling at ~235k produced a 2-4x lower
median with no recorded quality loss, which is a natural experiment already in
the data **[I]**); (2) `--max-turns` per node as a backstop, and split long
nodes into phase nodes with a structured handoff artifact (Amp's pattern; the
graph already has `implement -> implementation_diff -> janitor -> fix`, so the
seams exist); (3) hook-side filtering of test/gate output before it enters the
transcript (`just check` output is a prime candidate).

### F. Cache economics: the billed-dollar lever

**What.** With Sonnet 5.5, a cache read costs 0.05x base and a 5-minute write
1.25x, so a miss-then-write is 25x a hit **[S][I]**. Hit rate, not token
count, decides the bill.

**Who / evidence.**
- Anthropic pricing: Sonnet 5.5 $2.00 base / $2.50 5m-write / $4.00 1h-write /
  $0.10 read; Opus 5.5 $4 / $5 / $8 / $0.20; Haiku 5.5 $0.10 / $0.125 / $0.20 /
  $0.01 (prompts up to 100k); Fable 5.1 reads at 0.025x. Minimum cacheable
  prefix 512 tokens on the 5.x models. Hierarchy `tools -> system -> messages`;
  "Changes at each level invalidate that level and all subsequent levels". TTL
  "refreshed for no additional cost each time the cached content is used",
  measured from request START. For a varying suffix "place the breakpoint at the
  end of the static prefix, not on the varying block" **[S]**
  (https://platform.claude.com/docs/en/build-with-claude/prompt-caching).
- Claude Code: caching automatic; order is system+tools -> project context
  (CLAUDE.md, memory, rules) -> conversation; CLAUDE.md edits mid-session do
  not apply (read at session start); `CLAUDE_CODE_PROMPT_CACHE_TTL=1h` and a
  subagent TTL variable; the preset system prompt embeds the auto-memory path so
  different checkouts/machines miss each other's cache unless
  `--exclude-dynamic-system-prompt-sections` is set; `/usage` reports
  "91% of input tokens from cache ... likely cause: tool definitions changed"
  **[S]** (https://code.claude.com/docs/en/prompt-caching,
  https://code.claude.com/docs/en/costs). Anthropic's own postmortem list of
  cache breakers includes "an in-depth timestamp in the static system prompt"
  and "non-deterministic tool ordering" (https://claude.dev/blog/lessons-from-building-claude-code-prompt-caching-is-everything/,
  via subagent). Mid-conversation model switches (e.g. Opus -> Haiku for one
  question at 100k context) cost MORE because the cache is rebuilt (same post).
- OpenAI: cached input at 0.10x for gpt-5.3-codex / 5.4 / 5.5 / 5.6; GPT-5.6+
  writes 1.25x (30-min) or 2.5x (12 h); exact rendered-prefix match; Codex's
  prefix order puts aggregated AGENTS.md inside the cached prefix, so an
  AGENTS.md edit or MCP reconnect invalidates it (official docs via subagent;
  Codex prefix order is from a secondary post).
- Measured: Lumer et al., "Don't Break the Cache", 500+ sessions across
  OpenAI/Anthropic/Google: strategic caching cut cost **41-80%**; naive
  full-context caching "can paradoxically increase latency"; put dynamic content
  last **[S]** (https://arxiv.org/abs/2601.06007).
- Measured, negative: Weinberger & Hozez, "Token Reduction Is Not Cost
  Reduction": heaviest tool-output compression cut delivered tokens 38.4% and
  **raised billed cost 6.8%**; Pearson r = 0.15 between token and cost
  reduction; "prompt-cache creation and reads dominate input-side cost"; judge
  by "cost per successful task" **[S]** (https://arxiv.org/abs/2607.12161).
  JetBrains' A/B of the `rtk` output-compression plugin: +7.6% cost at low
  effort, 0% at high, against an advertised 60-90% saving (secondary; the
  JetBrains post returned 403).
- Manus: KV-cache hit rate is "the single most important metric for a
  production-stage AI agent"; ~100:1 input:output; "a common mistake is
  including a timestamp ... at the beginning of the system prompt"; append-only
  context; deterministic serialization; mask tools rather than remove them
  **[S]** (https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus).
- Gateway telemetry (Requesty, Apr 2026, no sample size): cached share per call
  Claude Code 91.9%, Aider 84%, Roo 73.6%, Cline 61.4%, Kilo 45.5%
  (https://www.requesty.ai/data/coding-agent-cache-hit-rate-apr-2026, secondary).

**Mapping.** The factory's `llm-spend` rows already carry
`cache_read_tokens` / `cache_creation_tokens` / `gen_ai.usage.input_tokens`
**[L]**, so cache-read share per node is one query away. Audit every rendered
brief (`_dispatcher_goal.py::render_goal`, judge `--append-system-prompt`
text, node prompts) for leading run ids, item ids, dates, and unstable JSON key
order; put them last. Run judge subprocesses with
`--exclude-dynamic-system-prompt-sections` and `--bare` (or the
`bd-ib-a3aqie` isolation flags) so hosts and checkouts share a prefix. Set the
1h TTL on sequential same-prefix nodes whose gap exceeds 5 minutes. Do not
switch models mid-node; switch only at node boundaries (F, last bullet).

### G. Effort and model routing for gate, review, and judge turns

**What.** Run high-volume verdict turns at low effort or on a cheaper model,
escalate on failure, and measure agreement before switching.

**Who / evidence.**
- Anthropic "Optimizing for cost and intelligence": Opus 5.5 at `low` effort
  with failures re-run at `high` solved ~97% at $0.17/task vs 95.3% at
  $0.29 all-`high`; prompt caching "83% to 86%" on a small triage agent; Haiku
  5.5 on GPQA 85% vs 91% at ~1/20 the cost per correct answer; an advisor
  pattern bought +1.7 pts for 2.1x cost ("at the edge of run-to-run noise")
  **[S]** (https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence).
  "Tuning effort is often a better lever than switching models" **[S]**
  (https://platform.claude.com/docs/en/about-claude/models/choosing-a-model).
- Rubric-driven LLM-as-judge for acceptance tests (20 configs, 500 evals):
  "GPT-4o Mini attains the best accuracy ... 78x cost reduction vs. GPT-5 (high
  reasoning) while improving accuracy"; cost spans 175x across configs; retries
  are a "material" cost **[S]** (https://arxiv.org/abs/2512.01232). "Judging the
  Judges": only the largest judges reach per-item human alignment, smaller
  judges still rank well, so calibrate on your own items first **[S]**
  (https://arxiv.org/abs/2406.12624).
- RouteLLM: "cost reductions of over 85% on MT Bench, 45% on MMLU, and 35% on
  GSM8K ... while still achieving 95% of GPT-4's performance" (the 85% is MT
  Bench only) **[S]** (https://lmsys.org/blog/2024-07-01-routellm/). FrugalGPT:
  "up to 98% cost reduction" on 2023 classification-style tasks via cascades
  **[S]** (https://arxiv.org/abs/2305.05176); not an agentic-coding number **[I]**.
- Claude Code costs page: Haiku for simple subagents, Sonnet for teammates;
  agent teams "approximately 7x more tokens"; enterprise average "~$13 per
  developer per active day" **[S]**.
- Google AutoCommenter: ~40% of shown comments led to a code change at a 0.98
  confidence gate; per-guideline suppression for stale rules **[S]**
  (https://newsletter.getdx.com/p/ai-assisted-code-reviews-at-google). No
  published risk-tiered LLM review scheme from Google or Meta was found;
  CodeRabbit skips drafts and path-filtered PRs, Greptile reviews everything and
  learns from reactions (vendor docs via subagent).

**Mapping.** Fabro's `reasoning_effort` default is `high` on every node
**[S]**; for ACP nodes the pin is via the adapter env (`--effort` for Claude
Code) **[L]**. `dod_gate`, `proof_grade`, `review`, `disposition` and the host
judges are the verdict tier: run them at `low` with escalate-on-fail, and
shadow a Haiku 5.5 judge beside the current one on the same transcripts
logging verdict agreement before any switch. Keep `implement`/`fix` where they
are until the input floor is fixed, because a cheaper model re-reading 400k
tokens is still re-reading 400k tokens.

### H. Review-layer tiering and tool-output hygiene

**What.** Not every item needs every LLM gate, and tool output should be
filtered before it enters any transcript.

**Who / evidence.** Google's 85-guidelines-cover-90% figure **[S]** (above);
Anthropic's hook-filtered test output and 25k tool-response cap **[S]**;
concise `response_format` using ~1/3 the tokens **[S]**
(https://www.anthropic.com/engineering/writing-tools-for-agents); Programmatic
Tool Calling "dropped from 43,588 to 27,297 tokens, a 37% reduction" by keeping
intermediate results out of context; Tool Search Tool cut tool-definition
overhead ~77k -> ~8.7k **[S]** (https://www.anthropic.com/engineering/advanced-tool-use).
Counter-evidence for output compression as a DOLLAR lever: arXiv 2607.12161
and the JetBrains A/B (F above). No sourced writeup on DoD compression or
"judge only the diff" was found.

**Mapping.** The deterministic gates (`just check`, red-green-replay, heading
coverage, range gate) already cover most of what a `completeness review` or
`proof replay` re-derives for a docs-only or config-only item. Tier by what the
change touches: product `.py` gets the full stack; docs/spec/config changes
get the deterministic gates plus one cheap verdict turn. Treat tool-output
filtering as a context-window lever (keeps nodes under the compaction
ceiling), not a billing lever, and measure it in dollars.

---

### I. Phoenix / disposable-implementation spec-driven development

This is the maintainer's actual framing: the specification is the durable
asset, the implementation is generated from it, treated as disposable and
regenerable, and not read by humans; assurance is the spec plus automated
verification. The sources below are the people who say they build this way,
what they do to keep regeneration and verification affordable, and what has
gone wrong.

#### I.1 Who builds this way, and in what words

- **Lineage.** Martin Fowler's PhoenixServer bliki (10 Jul 2012, term coined by
  Kornelis Sietsma): "A server should be like a phoenix, regularly rising from
  the ashes"; rebuilt servers "will pick up any drift from the source
  configuration", which re-sync tools only correct where they manage **[S]**
  (https://martinfowler.com/bliki/PhoenixServer.html).
- **Chad Fowler, "Regenerative Software"** (28 essays, Dec 2025-Sep 2026,
  https://chadfowler.com/regenerative-software/; reference implementation
  https://github.com/chad/phoenix, labelled Alpha; O'Reilly book forthcoming).
  "The server wasn't the thing. The capability to regenerate was the thing";
  "The code is not the asset. The specification and the evaluation are the
  asset"; editing in place is "a sign that regeneration failed ... a debugging
  activity, not a development activity" **[S]** (Immutable Infrastructure,
  Immutable Code). "The implementation is a cache"; "Code is now a
  materialized view of understanding"; "The real codebase is everything that
  lets you throw code away without fear"; durable evals are "Harder than
  writing the code they specify" **[S]** (Evaluations Are the Real Codebase).
  The Deletion Test: "If I deleted this codebase and regenerated it from
  scratch, what would I rely on to decide whether the result was correct?";
  "If you don't know how you would evaluate regenerated code, regeneration is
  reckless" **[S]**. He does NOT advocate zero reading: "There are classes of
  code you'll happily accept without even reading"; network and business-rule
  code "You reread it. You test it. You argue with it" **[S]** (The Gradient
  of Trust). And not whole-system rebuilds: "No serious architecture advocates
  'start over every time'" - it is "targeted replacement behind stable
  boundaries" **[S]** (The System Is the Asset). Podcast claim: "every
  software developer in the future will be generating code and not reviewing
  it" **[S]** (Heavybit Third Loop ep. 11).
- **Tessl / Guy Podjarny.** "Code becomes disposable"; "the first thing you do
  is you modify the spec"; loop: "if they fail, the agent regenerates the code
  until all the tests pass"; but "It's only a human, the user, that should be
  able to say, 'yeah, this regression test is a failure'"; on full autonomy
  "I don't think we're there yet"; "Too granular and you might as well write
  code" **[S]** (https://tessl.io/blog/taming-agents-with-specifications-what-the-experts-say/).
  Don Syme in the same piece: a "straight-up trade-off between determinism and
  adaptability"; "You do not want the Linux kernel done just in spec-driven
  mode" **[S]**. The registry's `spec-as-source` skill `spec-rebuild` deletes
  the declared `targets:`, regenerates per capability, runs `spec-verify`
  (links, target ownership, manifest, test suite), requires a clean git tree
  and an explicit yes **[S]**
  (https://tessl.io/registry/spec-driven-development/spec-as-source/4.0.0/files/skills/spec-rebuild/SKILL.md).
  By the 100th podcast (Apr 2026) Podjarny judged the spec-centric prediction
  "directionally correct, just insufficiently broad" and shifted to
  "context-driven" **[S]** (https://tessl.io/podcast/101/).
- **Böckeler's taxonomy** (martinfowler.com, 15 Oct 2025): spec-first ("A well
  thought-out spec is written first, and then used in the AI-assisted
  development workflow for the task at hand"), spec-anchored ("The spec is kept
  even after the task is complete, to continue using it for evolution and
  maintenance"), spec-as-source ("The spec is the main source file over time,
  and only the spec is edited by the human, the human never touches the
  code"). Kiro and Spec Kit are spec-first only; "Tessl is the only one ...
  that explicitly aspires to a spec-anchored approach" and is exploring
  spec-as-source; generated files carry "GENERATED FROM SPEC - DO NOT EDIT"
  **[S]** (https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html).
  livespec is spec-anchored moving toward spec-as-source **[I]**.
- **Sean Grove (OpenAI), "The New Code"**: "code itself is actually a lossy
  projection from the specification"; "We keep the generated code, and we
  delete the prompt"; the spec "becomes both training material and eval
  material" **[S]** (https://ai.engineer/talks/specifications-are-the-new-code).
- **StrongDM software factory** (founded 14 Jul 2025, three named founders):
  charter "Code must not be written by humans" and "Code must not be reviewed
  by humans"; assurance is scenarios "often stored outside the codebase"
  (a holdout set), a "satisfaction" fraction over observed trajectories rather
  than green/red, and a "Digital Twin Universe" of behavioural clones of
  third-party services **[S]** (https://factory.strongdm.ai/). Simon Willison:
  "Nobody reviews AI-produced code, ever ... The goal of the system is to
  prove that the system works" **[S]** (https://simonwillison.net/2026/Feb/7/software-factory/).
- **Steve Yegge, Gas Town / Beads**: "It's also 100% vibe coded. I've never
  seen the code, and I never care to"; Beads is "225k lines of Go code" he
  never read; assurance is multi-pass LLM review ("review something five
  times, with different focus areas") plus a merge agent **[S]** (Welcome to
  Gas Town, 1 Jan 2026). But by Mar 2026 (Vibe Maintainer): "I review every
  PR" and "the last 25% or so of pull requests need human review" for "taste"
  **[S]**.
- **Mechanical Orchard** (legacy modernization, "no human in the loop"):
  oracle is a parallel run of legacy vs new on the same inputs; "The agent
  that does the work is never the agent that judges it"; a worker that "can
  see the exact test ... will optimize for passing the test" **[S]**
  (https://www.mechanical-orchard.com/insights/the-software-dark-factory-modernizing-legacy-systems-with-no-humans-in-the-loop).
- **Dan Shapiro, "The Five Levels"**: Level 5 is "a black box that turns specs
  into software ... humans are neither needed nor welcome", done by "small
  teams, less than five people" **[S]**
  (https://www.danshapiro.com/blog/2026/01/the-five-levels-from-spicy-autocomplete-to-the-software-factory/).
- **Anthropic's C compiler** (16 Opus 4.6 agents "without active human
  intervention"): ~2,000 Claude Code sessions, $20,000, "2 billion input
  tokens and ... 140 million output tokens", ~100k LOC, "99% pass rate on most
  compiler test suites" **[S]** (https://www.anthropic.com/engineering/building-c-compiler).
- **Daniel Jackson (MIT), concept design**: "we could generate code one module
  at a time ... the LLM's context can be just the one module, and not the
  whole codebase"; concepts composed by "syncs" that "only need their
  specifications" **[S]** (https://essenceofsoftware.com/posts/wysiwid/;
  Meng & Jackson, Onward! 2025, https://arxiv.org/abs/2508.14511).

#### I.2 How they bound regeneration and verification cost

**Regenerate only what the spec change reaches.** Fowler's reference
implementation: "`phoenix regen` then regenerates only that subtree by
default"; staleness is found by walking a provenance graph from a changed
spec clause to its dependent implementation units; clauses are
"content-addressed clauses with semantic hashes" and the manifest tracks
"every generated file's content hash"; hand edits must be labelled (signed
waiver, expiring patch, promote-to-requirement) or `phoenix status` flags
them as errors, so "a hand-fix is never silently lost" **[S]**
(https://github.com/chad/phoenix). Tessl regenerates per `targets:` file
(1:1 spec to file) **[S]**. OpenSpec implements the delta and archives it
**[S]** (D above). Measured edit-vs-regenerate: SR-Eval found a "Code Edit"
strategy (edit prior code given the requirement delta) beats resending full
history at ~30% fewer tokens with equal or better completion (Python 0.2113 @
2,790 tok vs 0.1972 @ 3,975) **[S]** (https://arxiv.org/html/2509.18808).
Whole-file generation still beats diff output for small models except on
"short, spatially localized edits" **[S]** (https://www.alphaxiv.org/abs/2609.05779).

**Hash-keyed generation caches do not exist, because generation is not
reproducible.** Thinking Machines: 1,000 temperature-0 samples of
Qwen3-235B gave 80 distinct completions; batch-invariant kernels fix it at
~20% matmul cost **[S]** (https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/).
Böckeler: "I have seen the non-determinism in action though, when I generated
code multiple times from the same spec" **[S]**. Tessl: "Stable regeneration
is hard ... an iterative approach, not a magic 'generate once' solution"
**[S]** (https://tessl.io/blog/spec-driven-development-10-things-you-need-to-know-about-specs/).
Fowler: "Non-deterministic generators may produce different code from
identical intent graphs" **[S]** (Provenance Is the New Version Control).
**[I]** So the reusable artifact is not the model output but the VERIFIED
artifact: a memo of spec-clause-hash to the implementation unit (and its
verdict) that last passed the gate, consulted before any regeneration or
re-judgement. livespec already has the judge-side version of this
(`bd-ib-k5qp5z` reuses a heading verdict across a revision that leaves its
clauses unchanged **[L]**); the implement-side version is the same idea
keyed on `heading-coverage.json`'s clause to test map extended to clause to
module.

**Spec granularity: one unit of spec = one module with an explicit interface.**
Jackson (above); Tessl "Don't just pile everything into one massive file";
Osmani's section-only delivery (D); BMAD's "one session-sized unit" **[S]**.
Stanford/MIT/Microsoft/Michigan "How Do AI Agents Spend Your Money?": agentic
coding consumes "1000x more tokens than code reasoning and code chat", input
dominates, "Accuracy often peaks at intermediate cost and saturates at higher
costs", and same-task runs vary up to 30x **[S]**
(https://digitaleconomy.stanford.edu/publication/how-do-ai-agents-spend-your-money).
No source measures quality against spec-slice size directly **[I]**.

**Verification: deterministic oracle first, LLM judges narrowed to what they
are measured to be good at.**
- Judges are worse than execution at correctness: LMR-BENCH found unit tests
  most accurate and an LLM judge least, penalising "correct-but-different"
  code **[S]** (https://arxiv.org/pdf/2506.17335); "Vibe Coding on Trial":
  best single judge Youden's J < 0.4, juries lower false positives but
  compress true positives **[S]** (https://arxiv.org/html/2602.18492v1);
  LLMs "frequently misclassify correct code" against natural-language specs,
  and explanation-style prompting raises the misjudgement rate **[S]**
  (https://arxiv.org/abs/2508.12358).
- Judges ARE good at catching reward hacking: EvilGenie found the LLM judge
  "highly effective" at detecting hacks while held-out tests gave "only
  minimal improvement"; on ambiguous tasks Codex hacked 44.4%, Claude 33.3%
  **[S]** (https://alphaxiv.org/abs/2511.21654). ImpossibleBench: GPT-5
  exploits tests 76% of the time on one-off SWE-bench variants; hiding tests
  drives hacking to near zero but lowers legitimate solve rate **[S]**
  (https://arxiv.org/abs/2510.20270). StrongDM saw "return true" and tests
  "lazily rewritten to match the code" **[S]**; Kent Beck saw agents delete
  tests to make them "pass!" **[S]** (https://kentbeck.com/summaries/augmented-coding-beyond-the-vibes/).
- Coverage is not an oracle: "some test suites achieve 100% coverage but only
  4% mutation score" **[S]** (https://arxiv.org/abs/2506.02954); Meta engineers
  accepted 73% of LLM-generated mutation-killing tests **[S]**
  (https://arxiv.org/abs/2501.12862).
- Formal verification where the domain allows: 82% Dafny / 44% Verus / 27%
  Lean auto-verified across 12,504 specs; Clover accepts up to 87% of correct
  programs with zero false positives on textbook-scale code **[S]**
  (https://arxiv.org/abs/2509.22908, https://arxiv.org/abs/2310.17807).
- The verifier must be near-perfect or the agent solves the wrong problem:
  "the task verifier is nearly perfect, otherwise Claude will solve the wrong
  problem"; "it is easy to see tests pass and assume the job is done, when
  this is rarely the case"; late regressions were fixed by a stricter CI, not
  more review **[S]** (Anthropic C compiler).
- Risk tiering at scale: Meta RADAR (May 2026) is a funnel of authorship
  classification, eligibility gates, static heuristics, an ML risk score,
  LLM review, and deterministic validation; relaxing the risk threshold from
  P25 to P50 raised the auto-approve rate to 60.31%; 535K+ diffs reviewed,
  331K+ landed; revert rate about one-third and production-incident rate
  about one-fiftieth of non-RADAR diffs (selection bias acknowledged by
  commentators) **[S]** (https://arxiv.org/abs/2605.30208).
- Judge independence is the one rule every no-review practitioner shares:
  StrongDM (holdout scenarios outside the repo), Mechanical Orchard ("never
  the agent that judges it"), Tessl ("the implementation agent and the testing
  agent should have different perspectives") **[S]**.

**Batch and cache for non-interactive verification.** Anthropic Message
Batches are "charged at 50 percent of the standard API prices", most finish
under an hour, 24 h expiry, and caching stacks with batching (the docs
recommend the 1-hour cache for batches) **[S]**
(https://platform.claude.com/docs/en/build-with-claude/batch-processing).
**[I]** Replays, dod_gate grading, and completeness reviews need no
interactivity and are the natural batch jobs.

#### I.3 Does a disposable implementation change the economics of stacked review?

Yes, in both directions, and the evidence lets the two be separated **[I]**:

- What becomes worthless: any review dimension that exists for a human reader
  (readability, style, "would a maintainer understand this"). Horthy's
  negative result is the cost of ignoring it the other way: after ~4 months
  "lights off", "Production broke ... the model could not find the root
  cause", "three weeks to re-onboard to a codebase no human had ever read"
  **[S]** (https://newsletter.pragmaticengineer.com/p/context-engineering-with-dex-horthy).
  Osmani: "A dark factory doesn't pay [comprehension debt] down; it takes it
  on as fast as it can, with the tests green the whole way" **[S]**
  (https://addyosmani.com/blog/software-factories/). So the comprehension
  dimension is not free to drop; it moves to the SPEC, which is the thing a
  human will read when the factory stalls.
- What remains load-bearing: (1) a deterministic oracle that the implementer
  cannot see or edit (held-out scenarios, mutation score, property tests,
  parallel-run parity, formal checks where possible); (2) ONE independent LLM
  pass narrowed to what judges are measured to do well: reward-hack detection,
  test-file tampering, scope creep against the spec clause; (3) independent
  replay SAMPLED by risk tier, because RADAR's funnel shows the tier, not the
  universal replay, is what buys the 1/50 incident rate.
- What is redundant: grading the same artifact three ways (LLM review,
  graded dod_gate, completeness review) with judges that mis-classify correct
  code and whose false rejections trigger fix loops. Rubric-driven acceptance
  judging gets cheaper and more accurate with smaller models once the rubric
  is tight (78x cost reduction, G above) **[S]**; and no study found any
  defect yield for LLM review ON TOP OF a passing, hack-proof oracle - the
  vendor bug-planting benchmarks have no passing-test control **[S]** (Signal65,
  Atlassian RovoDev 38.70% comment resolution vs 44.45% human,
  https://arxiv.org/html/2601.01129v1).
- Local shape of the money **[L][I]**: in the Codex window, `implement`,
  `fix`, and `review_fix` were ~79% of factory responses and the LLM verdict
  nodes (`review`, `proof_verify`, `dod_gate`, `proof_grade`) ~11%; the
  verification cost that matters is the host-side `claude -p` judges (the
  bulk of the ~$11k local spend) and the fix loops that false rejections
  trigger. Thinning the verdict stack therefore pays mostly on the host side
  and in rework, not in factory node count.

#### I.4 Measured costs and failure modes from teams working this way

| Report | Number / failure | Source |
|---|---|---|
| Anthropic C compiler | $20k, ~2,000 sessions, 2B in / 140M out (14:1), 100k LOC; late regressions "each time it implemented a new feature" until CI was tightened | engineering post **[S]** |
| StrongDM | maturity floor "at least $1,000 on tokens today" per engineer; `return true`, tests rewritten to match code, earlier codebases decayed and collapsed | factory.strongdm.ai **[S]** |
| Fowler `phoenix` alpha | pipeline 0/5 [0.00, 0.43] vs a single model call 5/5 [0.57, 1.00] on todo-api (n=5, Sonnet 5); every sample mis-mounted routes from the unit's NAME, while typecheck and status stayed green; library-api 51/51 on one build | github.com/chad/phoenix README **[S]** |
| Fowler (essays) | lost scar tissue on rebuild: a timeout that "has to be 17 seconds"; "sometimes it removes the memory along with the mess"; "Each regeneration is an opportunity for drift"; agents built "two parallel web apps by accident" | regenerative-software, Tessl podcast 98 **[S]** |
| Yegge | "expensive as hell ... a cash guzzler", 2nd/3rd account, 20-30 workers; "Some bugs get fixed 2 or 3 times ... Other fixes get lost"; later "the last 25% or so of pull requests need human review" | Gas Town, Vibe Maintainer **[S]** |
| Horthy / HumanLayer | ~4 months lights-off, production break the model could not root-cause, 3 weeks to re-onboard; Faros AI: +54% bugs per dev, incidents tripled (two further figures unconfirmed) | Pragmatic Engineer, AIE WF 2026 **[S]** |
| Böckeler | non-determinism across regenerations; 1 small bug became 4 stories / 16 acceptance criteria; "I'd rather review code than all these markdown files"; spec-as-source may inherit "the downsides of both MDD and LLMs" | martinfowler.com **[S]** |
| Gonzalez | OpenAI Symphony SPEC.md "read[s] like code", ~1/6 the size of the Elixir implementation, and "still fails to reliably generate a working implementation" | haskellforall.com **[S]** |
| Stanford et al. | 1000x tokens vs chat; input dominates; accuracy saturates at intermediate cost; 30x run variance | 2604.22750 **[S]** |
| ImpossibleBench / EvilGenie | test exploitation 44-76% on ambiguous or conflicting tasks; judge catches hacks, held-out tests barely help | 2510.20270, 2511.21654 **[S]** |
| Meta RADAR | 60.31% auto-approve at P50 risk; 1/3 reverts, 1/50 incidents vs non-RADAR | 2605.30208 **[S]** |
| Gartner | AI coding token cost to exceed average developer salary by 2028; "bloated context windows" named as a cause | press release 2026-06-24 **[S]** |

No source publishes a cost-per-regeneration series over time or a measured
spec-drift rate; "the spec grows until it is code" is stated independently by
Gonzalez, Böckeler and Fowler ("A spec can contain prose, tests, schemas,
formal models, even executable code") but not measured **[S][I]**. The
counter-ratchet for the SPEC is therefore the same as for instruction files
(C): a per-capability size budget, a prune pass (livespec's `prune-history`
is the existing hook), and the rule that a clause whose behaviour is now
carried by a deterministic test may be shortened to a pointer.

---

## What the sources say NOT to do

- Do not judge any change by token deltas; judge by billed cost per accepted
  item (arXiv 2607.12161, Factory's "tokens per task, not tokens per request").
- Do not switch models mid-conversation to save money; it rebuilds the cache
  (claude.dev blog).
- Do not rely on compaction as the strategy; Amp removed it as lossy, Factory
  measured every method weak on artifact tracking. Use it as the backstop
  behind a lower window plus phase handoffs.
- Do not `@`-import to "shorten" CLAUDE.md; imports cost the same (memory docs).
- Do not add IMPORTANT to an ignored rule; shorten the file or make it a hook
  (best-practices page).
- Do not use sub-agents to cut the bill; they keep the PARENT's input flat but
  multiply total spend (~4x agent, ~15x multi-agent, ~7x agent teams) **[S]**.

---

## Ranked shortlist (re-ranked against the Phoenix framing)

Impact is a rough share of current weekly spend (~$21.6k) that the change
could plausibly bend, marked **[I]**; effort is engineering time in this
fleet. "Measure" names the `llm-spend` series; the dataset has no message-id
column and dedupes via `spend.correction` markers (`retract` / `restate`)
**[L]**. What the re-ranking changed: the verification stack moved from #7 to
#4 and was re-specified (oracle first, judges narrowed, replays sampled);
batching joined the cache lever at #3; a clause-to-module provenance map that
scopes both spec delivery and regeneration replaced the plain "spec slicing"
item; and the counter-ratchet budget now covers the spec as well as the
instruction files.

| # | Intervention | Expected impact [I] | Effort | What to measure in `llm-spend` |
|---|---|---|---|---|
| 1 | **Declared-only sandbox loading for factory nodes** (`--bare` / `bd-ib-a3aqie` isolation flags; per-node instruction EXCERPT instead of the governed repo's CLAUDE.md; no plugin/skill/MCP catalogue unless declared). Already scoped as `factory-context-per-turn-reduction` C3. | 15-30% of factory input on every node (54.6k/request from one file alone, plus catalogues); `implement` is ~62% of factory responses, so this is the biggest single lever; also ends Codex's silent 32 KiB truncation | Medium: `_dispatcher_overlay.py` and ~25 prepare-step helpers | Median and p90 of (`gen_ai.usage.input_tokens` + `cache_read_tokens` + `cache_creation_tokens`) per `node` per `model`, before/after, same window length; accepted-first-pass rate and fix-loop count per node must not regress |
| 2 | **Bound transcript growth on Claude factory nodes**: lower autocompact window (the Codex ~235k ceiling is a natural experiment already in the data), `--max-turns` per node as a backstop, split long nodes at existing seams with a structured handoff artifact, hook-filter `just check` output | Largest share on Claude routing (Opus `implement` median 755k vs Codex 193k); 2-3x on implement/review/fix input medians | Medium: adapter env + graph edits; quality gate required because compaction is lossy | Median input per response for `implement`, `review`, `review_fix`, `fix`; responses per run per node; per-node p90 must fall below the chosen window |
| 3 | **Cache-stability audit + TTL policy + Batches for non-interactive verification**: dynamic fields (run id, item id, dates, git snapshot) at the END of the first user message; deterministic JSON key order in rendered briefs; `--exclude-dynamic-system-prompt-sections` on every `claude -p`; 1h TTL where sequential same-prefix turns gap >5 min; replays, dod_gate grading and completeness reviews through the Batches API | Billed-dollar lever: literature 41-80% on cost; at 0.05x reads on Sonnet 5.5 a miss is 25x a hit; Batches halve every non-interactive verdict outright | Low-medium: template edits and flags; a batch submitter for the judge path | `cache_read_tokens / (input + cache_read + cache_creation)` per node and per host; responses with `cache_creation_tokens > 0` after a run's first turn; USD per accepted item; share of verdict responses billed at batch rate |
| 4 | **Re-base verification on a deterministic oracle and tier the LLM layers by risk**: dod_gate graded on mutation score / held-out scenarios the implementer cannot see or edit; ONE independent LLM pass narrowed to reward-hack, test-tamper and spec-scope detection; independent replay and completeness review SAMPLED by a risk score (product `.py` touched, clauses touched, prior failure rate); drop code-shape grading nobody reads | Lands on the host-side judges (bulk of ~$11k/week) and on the fix loops false rejections trigger; RADAR's funnel is the measured precedent; judges mis-classify correct code so fewer judge passes also means fewer spurious reworks | Medium, and a product decision for the maintainer: it changes what "done" means | LLM responses per accepted item by item class; host `claude -p` USD per item; rework loops per item; post-merge revert rate by tier (the escape metric that must not rise) |
| 5 | **Size budgets as CI gates for instruction files AND the spec**: a `just check` member failing any CLAUDE.md/AGENTS.md over ~200 lines (or a frozen token budget on the model tokenizer) and any SKILL.md over 500 lines; a per-capability spec-size budget with `prune-history` and clause-to-pointer shortening once a deterministic test carries the behaviour; one conversion sweep moving `.ai/*.md` to `.claude/rules` with `paths:` or to skills and "always" rules to hooks; `/doctor prompt-audit` per release | Flat per-request cost for the host-session layer on every turn, and the only structural counter-ratchet with measured precedent (99.3% excess removed when rationale is recorded; this fleet already records it) | Medium once, then low per release | Tokens per request attributable to instruction files (probe method from note 002); host-session median input per response; spec bytes per capability over time |
| 6 | **Clause-to-module provenance map for spec delivery and regeneration scope**: extend `heading-coverage.json` (clause to test) to clause to implementation unit; a dispatch loads the changed clauses plus neighbouring interface clauses and a budgeted H2 outline, never the tree or `history/vNNN`; regenerate or re-judge only units whose clauses changed, reusing the last verified artifact and verdict otherwise (`bd-ib-k5qp5z` is the judge-side precedent) | Decouples per-change cost from spec size permanently; SR-Eval's ~30% edit-vs-regenerate saving is the only quantified number; compounding rather than immediate | Medium-high: the map is the work | Spec-derived bytes in the rendered goal (add a size attribute to the goal span); units regenerated per spec change; judge input median vs the ~140k floor |
| 7 | **Effort/model routing for the verdict tier** (`dod_gate`, `proof_grade`, `review`, `disposition`, host judges): `low` effort with escalate-on-fail; shadow Haiku 5.5 judge logging agreement before any switch. Fabro's `reasoning_effort` defaults to `high`; ACP nodes pin it via the adapter env | ~40% cheaper per task at equal pass rate in Anthropic's own measurement; up to 10-20x on a judge that moves to Haiku after agreement is shown; smaller in absolute terms than #4 because the verdict tier is ~11% of factory responses | Low (env pins); medium for the shadow run | USD per verdict node; shadow-vs-primary verdict agreement; retries per node |
| 8 | **Tool-output hygiene** (PreToolUse filters, concise JSON projections for `list-work-items`/`context`, 25k cap) | Keeps nodes under the compaction ceiling; weak as a billing lever alone (token reduction is not cost reduction) | Low | Supporting #2; measure in USD, not tokens |

Ordering rationale **[I]**: #1 and #2 attack the input floor that every
other lever is multiplied by; #3 changes the price of whatever floor remains
and halves the non-interactive verdicts; #4 is where the Phoenix framing
bites hardest, because the stacked judges exist for a reader who is not there
and the measured value of an LLM judge on generated code is hack detection,
not correctness; #5 is the only item that stops both curves (instructions and
spec) from re-growing; #6 is the long-term structural answer and should be
designed now but built after #1-#4 land; #7 and #8 are cheap and real but
second-order.

---

## Sources I could not access or verify

- JetBrains `rtk` A/B post (HTTP 403); numbers are from secondary coverage.
- Requesty "Coding Agent Economy" PDF (binary); its hit-rate trend is unverified.
- Thoughtworks Radar vol. 34 "Agent instruction bloat" and Arize's 2026 IFScale
  re-run: reported by a subagent, not independently fetched.
- Codex prefix order and compaction internals: secondary posts only; no
  official OpenAI page describes Codex compaction.
- Anthropic's own CLAUDE.md line count: not published; only Cherny's "2.5k tokens".
- No published risk-tiered LLM code-review scheme from Google/Meta; no
  published cheap-judge agreement study on coding verdicts; no sourced writeup
  on DoD compression or "judge only the diff".
- Honeycomb `llm-spend` schema: not read live (MCP re-auth required); column
  names come from the plan notes and the emitting Python.
- Bright Data MCP needed an interactive OAuth; the Bright Data CLI worked for
  scraping but its search obfuscates URLs, so searches used WebSearch.
- Yegge "Gas City" (24 Apr 2026) body; The New Stack Codeplain article body;
  Fowler's "The Spec Can Come Later" and "When Does a Specification Become a
  Program?" bodies (index blurbs only); Faros AI 2026 report primary (figures
  via Horthy's talk page); Kent Beck's full augmented-coding essay (paywalled,
  summary page used); Jackson's MIT talk PDF (binary); Cognition's 2025
  performance review (67% merge claim, secondhand); Tessl's retired
  spec-driven-development docs page (404).
