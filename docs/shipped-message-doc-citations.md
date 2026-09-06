# Citing a document from a shipped message

**The rule.** A repo-relative path inside a message emitted by a SHIPPED
artifact — a hook denial, a check's remediation, a CLI `--help` — is a
PRODUCER-relative path being read in a CONSUMER context. It resolves in the
repo that owns the file and nowhere else, so it must name the repo that owns
it, and where the reader is mid-remediation it should carry the URL as well.

Suppressing the citation where it does not resolve is not the fix either: it
leaves a reader who has just been blocked with no way to reach the rationale at
all. The defect is the citation's ADDRESS, not its existence.

A path that names a file in the repo being INSPECTED (`.claude/settings.json`,
`dev-tooling/worktree.just`, `plan/<slug>/`) is consumer-relative and correct
as written — it is the address of the thing the message is telling the reader
to change.

## Why an ordinary dangling link is the lesser problem

Measured 2026-08-22T02:26Z in livespec-overseer, a consumer of this package
(livespec-dev-tooling-5ug6). The background guard's denial ended
`See .ai/gate-runtime-vs-harness-patience.md.`; that repo's `.ai/` holds one
unrelated file, and a fleet-wide search found the document only in this repo.
The citation fires at the moment an agent is blocked and reaching for help, so
following it costs a tool call, returns nothing, and invites the inference that
the guard is stale — exactly when the guard is right.

The fleet's guard for this class, `check-agents-ai-references-resolve`, reads
AGENTS.md-family documents. A reference embedded in a shipped Python message
string is outside its scope, so nothing mechanical sees these.

## Audit — 2026-09-06 (livespec-dev-tooling-5ug6)

Every non-docstring string literal under `livespec_dev_tooling/` (excluding
`_vendor/`) carrying a `.ai/`, `docs/`, `SPECIFICATION/`, `plan/`, `prose/`,
`.claude/`, `scripts/`, `dev-tooling/`, or `tests/` path was classified.
36 citation sites; 6 producer-relative, all repaired in that work-item.

| Site | Citation | Verdict |
| --- | --- | --- |
| `agent_hooks/_deny_hint.py` | `.ai/gate-runtime-vs-harness-patience.md` | **Producer-relative — the filed defect.** Now names the owning repo and carries the URL, and says the remedy stands without it. |
| `checks/work_item_interpolation_delimiters.py` | `docs/work-item-interpolation-delimiters.md` | **Producer-relative.** Same shape, same venue: the check ships, the doc does not. Repaired identically. |
| `vendor_update.py` ×3 | `SPECIFICATION/constraints.md` §"Vendoring procedure" / §"Lib admission policy" | **Sibling-relative.** Those headings live in livespec's spec, not in the repo the tool runs in — this one dangles even in the producing repo. Now `livespec SPECIFICATION/constraints.md`, matching the fourth site in the same module, which already had it. |
| `cross_repo/pin_autodiscovery.py` (`--help`) | `SPECIFICATION/contracts.md` §"Pin autodiscovery rules" | **Producer-relative.** The clause is this repo's; the tool walks consumer repos. Now `livespec-dev-tooling SPECIFICATION/contracts.md`. |
| `checks/hook_trees_not_io_exempt.py` ×2, `fleet/_reconcile_shims.py` ×4, `fleet/_contract_scope.py` ×4, `fleet/_adopter_lane.py` | `livespec SPECIFICATION/…`, `livespec-dev-tooling SPECIFICATION/…`, `livespec .ai/…`, `livespec-driver-claude's .claude/hooks/…` | Already self-locating — the shape the repairs above were written to match. |
| `fleet/_rows_claude_plugin.py`, `fleet/_rows_instructions.py` ×2, `fleet/ensure_plugins.py` ×2, `fleet/_contract_rows.py`, `cross_repo/_pin_claude_settings_format.py`, `config.py`, `checks/_primary_checkout_worktree_pack.py` ×3, `checks/plan_no_tombstone.py`, `red_leg_scope.py` ×4, `charters/charters.py` | `.claude/settings.json`, `dev-tooling/*.just`, `plan/archive/`, `tests/…`, `.ai/supervisor-protocol.md` | Consumer-relative and correct: each names a file in the repo being inspected or wired, which is where the reader must act. |

Docstrings were excluded from the count, being read in the source rather than
emitted at a reader who is blocked. Two carried the same shape and are recorded
here rather than repaired: `agent_hooks/pretooluse_background_guard.py`, fixed
alongside its message because it is the same sentence, and
`fleet/_credential_preflight.py`, which cites livespec's
`.ai/ci-gate-discipline.md` bare where `checks/master_ci_green.py` cites the
same file with its repo.

### Why no mechanical check was added

Telling the two classes apart needs to know which repo owns the cited file, and
the honest signal for that is the repo name in the string — which is the fix
itself, so a check would mostly be asserting its own convention. Arming one
would also mean a new entry in `SPECIFICATION/contracts.md` §"Shared check
inventory", a ratification this defect does not carry. The lighter guard is this
page plus the pointer in `livespec_dev_tooling/CLAUDE.md`: when a message cites
a document, name its repo.
