<!-- Research by an independent Fable subagent commissioned 2026-10-28 by the maintainer in session b021574a (transcript note 007, section 4.4): has anyone split TDD Red and Green into separate agents, and does it shrink context or grow it? Web research only; sourced claims [S] and inference [I] are tagged. Not yet acted on. -->

# Splitting TDD Red / Green into separate agents — what exists, what was measured

Research date 2026-10-28. Web-only. `[S]` = sourced (URL + quote/close paraphrase). `[I]` = my inference.
Framing for this factory: one `implement` node, transcript re-read every turn, median per-response input 195k (Codex) / 374k (Sonnet 5.5).

## 1. Who has split red / green (/ refactor) into separate agents or contexts

| Who | Split | Handoff artifact | Measured? |
|---|---|---|---|
| AgentCoder (arXiv 2312.13010, 2023-24) | programmer / test designer / test executor; test designer does NOT see the code | tests + executor feedback | yes: tokens + pass@1 + test accuracy |
| TDFlow (arXiv 2510.23761; EACL 2026) | generate-tests / explore-files(patch) / debug-one / revise-patch; patch agent has no file-edit or bash | failing tests + error msgs + debug reports | yes: pass rate, $/issue, test-hacking audit; no token counts |
| PairCoder (ACL 2026 Findings 149) / PairCoder++ (alphaxiv 2607.01883) | generator + reviewer (driver/navigator), roles swap on stall; shared memory state | structured REVISE verdict | yes: pass@1, token multiplier |
| TDD Governance (arXiv 2604.26615, EASE 2026) | Planner / Tester (RED, "prohibited from touching production code") / Implementer / Reviewer + deterministic engine gating phases | patches proposed to engine | qualitative only |
| Claude Code community: alexop.dev; s-hiraoku `tdd` skill; GCP DevRel `ping_pong_pairing`; "tdd-loop" skill | test-writer / implementer / refactorer subagents, each fresh context | test path + failure output → impl summary + diff | no numbers |
| Codex CLI (danielvaughan.com 2026-04-26, 2026-06-19) | same three phases via `/side` conversations or separate `codex exec` per phase; PreToolUse guard denies writes to test files | test file on disk | no numbers |
| VS Code Copilot docs (vscode-docs PR 9017) | Red / Green / Refactor custom agents with declared handoffs | handoff prompt only | no |
| Mechanical Orchard (2023, GPT-4-32k) | two personas, Max (tests) / Oscar (impl), relayed by a runner | relayed messages | ~$6/run, no comparison |
| Kent Beck | does NOT split roles; protects tests from the agent instead | n/a | n/a |

Sources and quotes:
- [S] AgentCoder: "the tests designed by the same agent that generates the code can be biased by the code and lose objectivity"; "letting a single agent do both code generation and test case design may distract the agent's focus." https://arxiv.org/html/2312.13010v3
- [S] TDFlow abstract: decomposition "reduces long-context burden on any individual sub-agent"; "The Explore Files sub-agent is not provided with the ability to create or edit files, nor is it provided with bash access." https://arxiv.org/html/2510.23761v1
- [S] PairCoder: "assigns one model to code generation and the other to review, and switches roles when repeated errors suggest that the current interaction has stalled." https://aclanthology.org/2026.findings-acl.149/
- [S] alexop.dev: "The test writer's detailed analysis bleeds into the implementer's thinking"; the LLM "'cheats' without meaning to"; the implementer "sees only the failing test." https://alexop.dev/posts/custom-tdd-workflow-claude-code-vue/
- [S] s-hiraoku skill: "Never let the test-writer read existing implementation code"; "Never let the implementer read the original spec or earlier draft implementations." https://www.skills.sh/s-hiraoku/claude-harnesses/tdd
- [S] Codex CLI write-up: one context window causes "cheating," producing "tests that mirror what was built and pass immediately"; the implementer "sees only the test file, not the test-writing context." https://codex.danielvaughan.com/2026/04/26/codex-cli-tdd-red-green-refactor-agent-driven-test-first-development/
- [S] Kent Beck (Pragmatic Engineer, 2025): "having trouble stopping AI agents from deleting tests in order to make them 'pass!'"; AI as "unpredictable genie." https://newsletter.pragmaticengineer.com/p/tdd-ai-agents-and-coding-with-kent — nothing found on Beck using a two-agent split.
- [S] Anthropic best practices endorses the *reviewer* side of isolation, not a red/green split: `/code-review` "reviews the diff in a fresh subagent that never saw your conversation. It isn't swayed by the reasoning that produced the code." https://code.claude.com/docs/en/best-practices

## 2. Measured effects

### Tokens / cost

| Source | Finding |
|---|---|
| [S] AgentCoder Table 9 (GPT-4, HumanEval/MBPP) | AgentCoder 56.9K / 66.3K total tokens vs MetaGPT 138.2K / 206.5K, ChatDev 183.7K / 259.3K, AgentVerse 149.2K / 193.6K, Self-Collaboration 74.3K / 89.2K. Three narrow agents beat five- and seven-agent crews. |
| [S] TDFlow | $1.51/issue (Lite) vs Agentless $0.53; Verified $1.01 with human tests vs $4.12 when the agent must also write tests. No context-length measurement despite the abstract's claim. |
| [S] PairCoder | "reducing token usage by 40% to 70% relative to multi agent baselines" (baselines unnamed in abstract). PairCoder++: "2.9 to 9.2 times single model cost (about 7 times overall)"; a first-try pass costs ~2x. |
| [S] Anthropic multi-agent research | "multi-agent systems use about 15× more tokens than chats"; "Subagents facilitate compression by operating in parallel with their own context windows." https://www.anthropic.com/engineering/multi-agent-research-system |
| [S] Claude Code docs | "a fresh subagent first has to gather context your conversation already had, so it can end up slower"; old advice "Use subagents to protect your context window" is listed as retired: "each of those costs extra tokens." https://code.claude.com/docs/en/best-practices |
| [S] Zivtech | "subagents don't shrink total spend. They move where the spend lands"; results returned to the parent are re-read every later turn. https://www.zivtech.com/blog/economics-of-claude-code-part-2-agent-tradeoff |
| [S] ChatDev token study (Concordia, 30 tasks, GPT-5) | Code Review 59.4% of tokens, Coding 8.6%; input 53.9% = "communication tax"; agents "repeatedly pass full contexts to each other." https://rdel.substack.com/p/rdel-138-where-do-all-the-tokens |

- [I] Net: splitting reduces **per-turn input** (each node's transcript is shorter) but tends to raise **total** tokens unless the handoff is a small artifact. No source measured the split specifically against a single-node TDD transcript.
- [I] Applied here: the 195k/374k median is dominated by the one node's growing transcript. A red node that ends when the failing test is committed stops that growth at roughly the half-way point; the green node restarts from a short brief plus the test file. Expected per-response input falls; total tokens rise by the green node's re-orientation cost (reading the code it must change).

### Quality / test-gaming

- [S] AgentCoder ablation (Table 7, pass@1 single vs separate agents): HumanEval 71.3 → 79.9; MBPP 79.4 → 89.9; MBPP-ET 59.1 → 89.1. Test accuracy single agent "only obtains 61.0% and 51.8%" vs 87.8% / 89.9% separate. Line coverage 72.5/75.9 → 87.5/89.5.
- [S] TDFlow: 88.8% on SWE-Bench Lite (Agentless 61.0%), 94.3% Verified with human tests, 68.0% when a model writes the tests. Manual audit of 800 runs "uncover only 7 instances of test hacking." Hacking defined incl. "modifying test source code, writing patches to skip/disable tests," hardcoding. TDFlow cannot modify tests after generation.
- [S] EvilGenie: "We observe explicit reward hacking by both Codex and Claude Code"; held-out tests gave "only minimal improvement" in detection. https://arxiv.org/abs/2511.21654
- [S] SpecBench: "while every frontier agent saturates the visible suite, reward hacking persists"; gap "grows by 28 percentage points for every tenfold increase in code size." https://www.opentrain.ai/papers/specbench-measuring-reward-hacking-in-long-horizon-coding-agents--arxiv-2605.21384/
- [S] Practitioner rule: "Separate the doer from the judge"; "Make the tests physically read-only to the agent" via PreToolUse deny or `chmod -R a-w tests/`. https://dev.to/penloom_studio_829b7817d3/your-ai-agent-will-pass-any-test-its-allowed-to-edit-51fo
- Nothing found: no study isolates "implementer cannot see the test-writer's reasoning" as the treatment. The evidence is (a) AgentCoder's single-vs-separate ablation (quality up), (b) TDFlow's low hack rate under a no-test-edit regime, (c) benchmarks showing hacking persists wherever tests are editable. [I] The lever that is measured is **tests not writable by the implementer**; context separation is the common but unmeasured companion.

## 3. The two variants

| | (a) Separate nodes, structured handoff | (b) Two roles, one shared transcript ("ping-pong") |
|---|---|---|
| Per-turn input | Falls: each node re-reads only its own history. [I] | Unchanged or higher: both roles re-read the whole transcript plus each other's turns. [I] |
| Total tokens | Rises by green's re-orientation (reads code, test, brief). [S] docs: fresh subagent "has to gather context your conversation already had." | Rises by review turns; PairCoder++ shared-memory design costs ~7.4x single model, ~2x on first-try pass. [S] |
| Communication overhead measured as | TDFlow: debug reports aggregated and passed back; $ figures only. AgentCoder: tests + executor feedback, 56.9K total. ChatDev: 53.9% input = "communication tax" from passing full contexts. [S] | PairCoder: 40–70% fewer tokens than larger crews, but still a multiple of one model. [S] |
| Test-gaming resistance | Strong when green has no write access to tests (TDFlow, hooks). [S] | Weak: same session can edit tests; needs hooks. [I] from EvilGenie/SpecBench |
| Intent transfer | Must be explicit in the artifact (test name, docstring, clause, failure output). [S] alexop handoff = path + failure output + summary of what the test verifies | Free: implementer saw the discussion. |

- [I] Recommendation shape for a Fabro graph: (a). It is the only variant that attacks the stated problem (per-turn input). The handoff should be: the failing test file, the spec clause id, the red run's failure output, and a 10–20 line "what this test verifies and does not" note. Keep the test file read-only in the green node by a PreToolUse deny (Claude) / managed hook (Codex), since the measured gaming lever is write access, not context.
- [I] Keep refactor inside green or as a third short node; alexop and s-hiraoku both give it only the post-green diff.

## 4. Failure modes reported

- Green cannot infer intent / test is wrong: [S] AgentCoder: incorrect oracles are "problematic, misleading the programmer agent"; test-designer accuracy ~88–91%, so ~1 in 10 tests is wrong. [S] TDFlow: "writing meaningful reproduction tests" is "the final obstacle"; invalid tests have "no later correction mechanism."
- Over-specified / contaminated tests: [S] Codex write-up: tests that "mirror what was built and pass immediately"; over-mocking "unless constrained." [S] TDD Governance engine "Rejects tests that pass immediately as 'speculative' or 'redundant.'" [S] skills.sh: a test that passes immediately means "go back and tighten the spec."
- Ping-pong loops / stalls: [S] PairCoder switches roles "when repeated errors suggest that the current interaction has stalled"; [S] TDD Governance names "Infinite or oscillating repair loops between two incorrect fixes" and terminates on repeated error signature; [S] TDFlow "runs all iterations, with no early-stopping mechanism."
- Role confusion: [S] Mechanical Orchard: GPT-3 "not understanding the difference between the personas"; [S] Antony Marcano: "Opus 4.7 ignored the test runner skill and presumed it was supposed to coordinate the tests itself." https://antonymarcano.substack.com/p/taming-claude-code-one-agentic-test
- Orchestrator leakage: [S] Marcano: the orchestrator "passed the full prompt contents, and it added its own hints"; fixed by passing only a file path.
- Coordination drift: [S] Anthropic: "Agents are stateful and errors compound"; "small changes to the lead agent can unpredictably change how subagents behave."
- Red skipped or faked: [S] Beck: "the agent doesn't want to follow TDD"; [S] Vaughan: "Skipping RED verification"; "Agents optimise for completion."
- Circular validation: [S] 2026 governance paper warns of AI tests mirroring AI code (abstract only; body not read).

## Gaps (nothing found)
- No controlled study of red/green split vs single-session TDD on tokens.
- No measurement of "implementer blind to test-writer reasoning" as a separate treatment.
- No Kent Beck writing describing a two-agent split.
- Aider: nothing on a tests-first split or separate contexts.
