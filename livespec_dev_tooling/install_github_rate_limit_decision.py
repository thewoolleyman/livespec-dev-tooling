"""install_github_rate_limit_decision — install the canonical rate-limit decision body.

Writes the canonical GitHub rate-limit DECISION body into a Driver plugin
bundle's hooks directory. Mirrors `install_no_shadow_ledger` (Conformance-
Pattern concern #1): a single packaged carrier constant is the source of
truth, so the decision function every Driver's rate-limit guard runs never
drifts between per-Driver copies.

WHAT IS SINGLE-SOURCED, AND WHAT IS NOT. The guard splits along a seam the
measurement exposed: `mask_command` + `matched_rule` are PURE, stdlib-only and
harness-agnostic — the same shell text earns the same verdict under every
runtime — while the hook PROTOCOL around them (how the input arrives, how a
deny is spelled, where telemetry goes) is per-runtime by construction. Only
the pure half travels here. Each Driver keeps its own protocol wrapper and
imports the public names this body exports.

Hoisting waited on purpose. A per-Driver copy was the right shape while the
decision logic was unproven; single-sourcing it first would have meant
refactoring twice. The rollout verification re-measured the guard's
false-positive rate at 0.0% from v0.6.0 onward, against 40.5% before, so the
body being copied is now the body that was measured — and the hoist lands
BEFORE the Codex and pi ports, so those consume one source rather than adding
two more copies.

The canonical body ships as the module-level
`CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY` string constant in THIS module so
it travels in the wheel, exactly as `CANONICAL_NO_SHADOW_LEDGER_BODY` does in
`install_no_shadow_ledger`.

HARD CONSTRAINT ON THE BODY: it runs under bare system `python3` with no
virtualenv and no third-party packages — the guard fires before any venv
exists. The body therefore imports from the standard library ONLY. It must
never import `livespec_runtime`, `structlog`, or anything under `_vendor/`.

DESTINATION RESOLUTION IS BY DRIVER PROFILE, NOT BY A ROLE KEY, and the
difference is deliberate. `neutral_hook_body_path` is a REQUIRED role key, so
its Verifier is a canonical check every fleet consumer must wire. This body
lands only in a Driver bundle, and its Verifier accordingly lives under
`driver_checks/` (see that package's docstring and livespec-2exa) where the
canonical-set walk cannot reach it — which leaves no role key for it to gate
on. `driver_decision_body_path` is that gate instead: it names the bundle
layout and returns None off a Driver tree, so this installer and its Verifier
resolve the same path through the same function and cannot disagree.

CLI:
    python -m livespec_dev_tooling.install_github_rate_limit_decision
        Install (or idempotently re-install) the canonical decision body into
        the Driver bundle rooted at the current working directory. A tree that
        carries no Driver manifest is a sanctioned no-op at exit 0 — the same
        self-skip `driver_checks.plugin_structure` applies, and for the same
        reason: a non-Driver tree has nowhere for the body to go.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stdout.write` / `sys.stderr.write`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY",
    "DECISION_BODY_FILENAME",
    "driver_decision_body_path",
    "install_decision_body",
    "main",
]

# The emitter id carried on every structured event. Deliberately the module
# name rather than a check slug: this is a provisioning surface, and a consumer
# reading its stderr should be able to tell the installer's self-skip from the
# Verifier's.
_INSTALLER_ID = "install_github_rate_limit_decision"

# The name the body is installed under inside a Driver's hooks directory. The
# leading underscore matches the sibling-module convention a Driver's guard
# already follows for `_guard_telemetry.py`: a module the hook imports, never
# an entry point `hooks.json` invokes.
DECISION_BODY_FILENAME = "_github_rate_limit_decision.py"

# The two Driver bundle layouts, keyed on the manifest that identifies each —
# the SAME auto-detect `driver_checks.plugin_structure` runs, so a tree cannot
# be one profile to the installer and another to the structural gate.
_CLAUDE_MANIFEST = Path(".claude-plugin") / "plugin.json"
_CLAUDE_HOOKS_DIR = Path(".claude-plugin") / "hooks"
_CODEX_MANIFEST = Path(".agents") / "plugins" / "marketplace.json"
_CODEX_HOOKS_DIR = Path("livespec") / "hooks"


# The canonical GitHub rate-limit decision body. Embedded here as the
# wheel-safe carrier (see the module docstring). Every Driver's copy is held
# byte-identical to these bytes by
# `driver_checks.github_rate_limit_decision_body_identical`.
CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY = r'''#!/usr/bin/env python3
"""livespec github-rate-limit decision — the pure, harness-agnostic verdict.

The DECISION half of the GitHub rate-limit guard, single-sourced from
livespec-dev-tooling and shipped byte-identically into every Driver bundle.
`mask_command` reduces a shell command to the text the shell will execute;
`matched_rule` names the conjunction that convicts it, or returns None. Both
are pure functions of their argument: no I/O, no environment, no harness.

The guard denies only the load-bearing conjunctions that exhaust GitHub
budgets quickly:

- `gh run`, `gh pr`, or UNCACHED read-only `gh api` calls driven by a loop
  whose iteration count is NOT readable off the command text, or by a loop
  that sleeps between iterations (a `gh api --cache <duration>` read is the
  remedy the guard prescribes, so it is exempt);
- shell loops or `xargs` combined with mutating `gh api` calls.

Both verdicts read a MASKED copy of the command in which quoted spans and
heredoc bodies have been removed, so a token that is data rather than a
command cannot convict. See `mask_command` for what survives masking and why.

The read verdict EXEMPTS a bounded literal loop: a `for NAME in <items>` whose
items are plain literal words -- no parameter expansion, no command
substitution, no glob, no brace expansion -- and which lists at most 10 of
them. `for id in 1 2 3 4 5 6` is six calls, and a read costs one point against
the same 900-point-per-minute primary ceiling the mutation verdict cites, so
ten reads spend about one percent of it even when the shell issues them all in
the same second. Ten is the threshold because it sits far below the point
where the count could matter AND about where a hand-typed list stops: past it
an author reaches for `$(seq ...)`, a glob, or a variable, whose sizes are NOT
readable from the text and which therefore stay denied at any apparent size.
The load-bearing property is that the iteration count is LEGIBLE, not the
exact number, so the threshold is a judgement call rather than a derived
constant.

The exemption covers ENUMERATION, not POLLING. A `sleep` inside a loop body
means the loop is waiting for state to change rather than fetching a known
list, so it denies at any size. ANYWHERE in the body counts -- first command or
last, on its own indented line or after a `;` -- and so does a sleep reached
through a command prefix such as `command sleep 10`, `mise exec -- sleep 10`,
`timeout 30 sleep 10` or a leading `TZ=UTC` assignment: a prefix chooses HOW
the sleep runs, never WHETHER it does. Conversely a `sleep` OUTSIDE every loop body
-- `sleep 30; gh api ...`, one polite poll -- no longer denies at all: 44 of
615 denials over the 7 days to 2026-08-26 were exactly that shape. `while`,
`until` and `select` carry no readable bound and are denied unchanged, as is
the whole mutation verdict -- a mutation costs five points, so even a
two-iteration literal loop over mutations stays denied.

`has_cached_gh_api` and `gh_at_command_position` are the AUDIT predicates a
caller carries on its verdict record rather than inputs to the verdict itself.
A `rate_limited` verdict whose command carried no `gh` at command position IS a
false positive by definition, so the rate this guard was last measured at
becomes a query rather than a transcript replay.

Self-contained by contract: a Driver ships this file under bare system
`python3` with no virtualenv and no third-party packages, so it imports from
the standard library ONLY -- never from `livespec_runtime`, never from a
sibling that is not shipped beside it.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "LOOP_MUTATION_RULE",
    "LOOP_READ_RULE",
    "MAX_LITERAL_ITERATIONS",
    "SLEEP_READ_RULE",
    "gh_at_command_position",
    "has_cached_gh_api",
    "mask_command",
    "matched_rule",
]

# The three conjunctions this guard convicts on, named so a verdict record can
# say WHICH one fired. The two read rules share one deny message -- the remedy
# is the same -- but they are different mistakes, and a dataset that cannot
# separate them cannot say which is over-convicting.
LOOP_READ_RULE = "loop+read"
SLEEP_READ_RULE = "sleep+read"
LOOP_MUTATION_RULE = "loop+mutation"

# A loop keyword only starts a loop in COMMAND POSITION: at the beginning of
# a line, after a `;`/`&`/`|` separator, or after `do`/`then`. Matching the
# bare word anywhere denied any `gh pr`/`gh run` command whose text merely
# contained "for", "while", "until" or "sleep" -- ordinary English that turns
# up constantly in PR titles, paths and jq filters.
#
# MULTILINE is load-bearing rather than incidental: requiring command position
# without it would stop matching a real loop that begins on any line after the
# first, which is the common shape for a multi-line command. The leading run of
# blanks is load-bearing for the same reason one level down: the body of a
# multi-line loop is INDENTED, and a bare `^` stopped at the indentation rather
# than at the command behind it.
_CMD_POS = r"(?:^[ \t]*|[;&|]\s*|\bdo\s+|\bthen\s+)"
_SHELL_SELECT = rf"{_CMD_POS}select\s+[A-Z_][A-Z0-9_]*(?=\s+(?:in|do)\b|\s*;)"
_SHELL_LOOP = rf"{_CMD_POS}(?:for|while|until)\b"
# A command reached through a PREFIX runs all the same: `command sleep 20`,
# `mise exec -- sleep 10`, `timeout 30 sleep 10`, `env sleep 10` and
# `TZ=UTC sleep 10` every one of them sleep. Command position alone saw none of
# them, so a real six-iteration `gh pr view` poll spaced by `command sleep 20`
# -- in the same 7-day population this guard's false-positive rate was measured
# against -- read as an enumeration rather than the poll it was.
_ASSIGNMENT = r"[A-Za-z_][A-Za-z0-9_]*=\S*"
# What a prefix consumes BEFORE the command word it hands off to: its own
# options, and `timeout`'s duration. A bare word is excluded deliberately --
# that word would BE the command being run.
_PREFIX_ARGUMENT = r"(?:-\S+|\d+(?:\.\d+)?[smhd]?)"
_PREFIX_COMMAND = r"(?:[\w./-]*/)?(?:command|env|exec|nohup|stdbuf|timeout)"
# A runner that separates its own arguments from the command with `--`.
_RUNNER_PREFIX = r"(?:[\w./-]*/)?mise\s+(?:exec|x)\s+(?:\S+\s+)*?--"
_CMD_PREFIX = (
    rf"(?:{_ASSIGNMENT}\s+|(?:{_PREFIX_COMMAND}|{_RUNNER_PREFIX})\s+(?:{_PREFIX_ARGUMENT}\s+)*)*"
)
# The `sleep` group, not the whole match, is what `_has_sleep_in_loop_body`
# measures against a body span: command position can begin at the very `do`
# that OPENED the body, and a prefix chain widens the gap further, so the
# match's own start says nothing about which body the sleep sits in.
_SHELL_SLEEP = rf"{_CMD_POS}{_CMD_PREFIX}(?P<sleep>sleep)\b"
_LOOP_OR_XARGS = re.compile(
    rf"{_SHELL_LOOP}|{_CMD_POS}xargs\b|{_SHELL_SELECT}",
    re.IGNORECASE | re.MULTILINE,
)
# A loop whose iteration count cannot be read off the command text at all:
# `while` and `until` run until a condition flips, and `select` re-prompts
# until the user breaks out. No apparent size makes any of them bounded.
_UNBOUNDED_LOOP = re.compile(
    rf"{_CMD_POS}(?:while|until)\b|{_SHELL_SELECT}",
    re.IGNORECASE | re.MULTILINE,
)
# A `for` loop and the header text between the keyword and the `do`.
_FOR_LOOP = re.compile(rf"{_CMD_POS}for\b(?P<header>[^\n;]*)", re.IGNORECASE | re.MULTILINE)
# `for NAME in <items>` is the ONE loop header that writes its own iteration
# count out in full. A C-style `for ((...))` header and the argument-less
# `for NAME; do` (which iterates the positional parameters) both fail to match.
_FOR_IN_HEADER = re.compile(r"^\s+[A-Za-z_][A-Za-z0-9_]*\s+in\s+(?P<items>\S.*?)\s*$")
# One item of a literal list. A `$`, a backtick, a glob metacharacter or a
# brace makes the shell expand the word into an unknown number of words, so it
# disqualifies the whole list.
_LITERAL_ITEM = re.compile(r"^[A-Za-z0-9_@%+=:,./^-]+$")
_SLEEP = re.compile(_SHELL_SLEEP, re.IGNORECASE | re.MULTILINE)
_DO_OR_DONE = re.compile(rf"{_CMD_POS}(?P<word>do|done)\b", re.IGNORECASE | re.MULTILINE)
MAX_LITERAL_ITERATIONS = 10
_GH_READ = re.compile(r"\bgh\s+(?:run|pr)\b", re.IGNORECASE)
_GH_API = re.compile(r"\bgh\s+api\b(?P<args>[^\n;&|]*)", re.IGNORECASE)
_MUTATING_METHOD = re.compile(
    r"(?:\s|^)(?:-X|--method)(?:=|\s+)(?P<method>delete|post|patch|put)\b",
    re.IGNORECASE,
)
# `gh api --cache <duration>` is the very remedy the read deny message
# prescribes: a cache hit answers 304, which spends no primary rate-limit
# budget. Counting it as a rate-limited read denied the agent for obeying the
# instruction it was just given -- 96 of 615 denials over the 7 days to
# 2026-08-26 were commands already in the sanctioned cached form.
#
# The duration is REQUIRED, not optional: a bare `--cache` is not valid `gh`,
# so a value that is absent or is the next flag buys no exemption.
_CACHED_READ = re.compile(r"(?:\s|^)--cache(?:=|\s+)(?!-)(?P<duration>[^\s]+)", re.IGNORECASE)
# A `gh` the shell would actually EXECUTE, as opposed to one that is merely
# spelled: command position, or the command word `xargs` runs. This is NOT the
# predicate the verdict is computed from -- it is the one the verdict is
# AUDITED by. A `rate_limited` verdict whose command carried no `gh` here is a
# false positive by definition, which is the whole point of emitting it: 109 of
# the 615 denials over the 7 days to 2026-08-26 were of exactly that shape,
# before masking landed, and it took a transcript replay to find that out.
# A subcommand is required so a bare word
# (`gh-pages`, `--author=gh`) cannot read as an invocation.
_GH_AT_COMMAND_POSITION = re.compile(
    rf"(?:{_CMD_POS}|\bxargs\s+(?:-\S+\s+)*)(?:[\w./-]*/)?gh\s+(?:api|run|pr)\b",
    re.IGNORECASE | re.MULTILINE,
)

# A heredoc redirection: `<<EOF`, `<<-EOF`, `<<'PY'`, `<<"PY"`. `<<<` is a
# HERE-STRING, not a heredoc, and is excluded for free -- its third `<` cannot
# start the delimiter word.
_HEREDOC_START = re.compile(
    r"<<-?\s*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)"
)
# The text immediately before a quoted span, when that span is the script
# argument of a SHELL interpreter (`sh`, `bash`, `dash`, `ksh`, `zsh`, by bare
# name or by path) reached through `-c` or a combined form such as `-lc`.
_SHELL_C_PAYLOAD = re.compile(
    r"(?:^|[\s;&|(])(?:[\w./-]*/)?(?:ba|da|k|z)?sh\s+(?:-\w+\s+)*-\w*c\s*$",
    re.IGNORECASE,
)
_QUOTES = "'\""
# A masked span collapses to one WORD character rather than to nothing or to a
# space. Nothing would JOIN the neighbouring text into a token the author never
# wrote; a space would erase the fact that an argument stood there at all, so
# `gh api --cache "10m"` would read as a bare `--cache` -- an UNCACHED read,
# denied for using the very form the deny message prescribes.
_MASKED_SPAN = "_"


def _strip_heredoc_bodies(*, command: str) -> str:
    """Drop every heredoc body, and its terminator, from the command text.

    A body runs from the line after the redirection to the line whose stripped
    content is the delimiter. An UNTERMINATED heredoc runs to the end, which is
    how the shell itself reads it.
    """
    lines = command.split("\n")
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        index += 1
        for match in _HEREDOC_START.finditer(line):
            delimiter = match.group("delimiter")
            while index < len(lines) and lines[index].strip() != delimiter:
                index += 1
            index += 1
    return "\n".join(kept)


def _closing_quote_index(*, text: str, quote: str, start: int) -> int:
    """Index of the quote closing this span, or -1 when the span is unterminated.

    A single-quoted span has no escapes; inside a double-quoted span a
    backslash escapes the character after it, `"` included.
    """
    if quote == "'":
        return text.find(quote, start)
    index = start
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index
        index += 1
    return -1


def _mask_quoted_spans(*, text: str) -> str:
    """Replace each quoted span with `_MASKED_SPAN`, keeping shell `-c` payloads."""
    masked: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\\":
            masked.append(text[index : index + 2])
            index += 2
            continue
        if character not in _QUOTES:
            masked.append(character)
            index += 1
            continue
        end = _closing_quote_index(text=text, quote=character, start=index + 1)
        body = text[index + 1 :] if end < 0 else text[index + 1 : end]
        if _SHELL_C_PAYLOAD.search("".join(masked)):
            masked.append(f"\n{mask_command(command=body)}\n")
        else:
            masked.append(_MASKED_SPAN)
        index = len(text) if end < 0 else end + 1
    return "".join(masked)


def mask_command(*, command: str) -> str:
    """Reduce the command to the text the SHELL will execute.

    `_CMD_POS` anchors a loop keyword to command position, but under MULTILINE
    every line of a heredoc body and every line of a quoted interpreter script
    begins a line, so the whole body reads as command position. The guard could
    not tell a shell loop from a Python loop, nor a command from a quoted
    argument: 109 of 615 denials over the 7 days to 2026-08-26 carried NO `gh`
    invocation at command position at all -- `gh` appeared only inside a string,
    a path or a regex -- and 31 of those were heredoc or quoted-script bodies.
    A `grep` whose SEARCH PATTERN spelled `gh api|for loop` was denied for the
    pattern it was searching FOR.

    The ONE quoted span that survives is a shell interpreter's `-c` payload:
    `cat ids | xargs -I{} bash -c 'gh api -X PATCH ...'` is a genuine mutation
    burst hiding one quoting level down, so that body is masked recursively and
    spliced back between newlines, where its own command positions read
    normally. A heredoc fed to a shell is NOT re-read: the measured population
    is Python, jq and Markdown bodies, and treating a heredoc body as data is
    the contract this guard is held to.
    """
    return _mask_quoted_spans(text=_strip_heredoc_bodies(command=command))


def _is_bounded_literal_for(*, header: str) -> bool:
    """Whether a `for` header enumerates a short, fully literal word list.

    A masked span is rejected outright: `"$@"` and `"${refs[@]}"` mask to the
    same single token as `"main"` yet expand to as many words as the caller
    supplied, so the guard cannot count what it deliberately cannot see.
    """
    match = _FOR_IN_HEADER.match(header)
    if match is None:
        return False
    items = match.group("items").split()
    return len(items) <= MAX_LITERAL_ITERATIONS and all(
        item != _MASKED_SPAN and _LITERAL_ITEM.match(item) for item in items
    )


def _loop_body_spans(*, command: str) -> list[tuple[int, int]]:
    """Character ranges of every `do ... done` body, innermost range first.

    An unterminated `do` runs to the end of the command, which is how far the
    shell would read it. A `done` with no open `do` is a shell syntax error; it
    closes nothing, so it is skipped rather than opening a range backwards.
    """
    opened: list[int] = []
    spans: list[tuple[int, int]] = []
    for match in _DO_OR_DONE.finditer(command):
        if match.group("word").lower() == "do":
            opened.append(match.end())
        elif opened:
            spans.append((opened.pop(), match.start()))
    spans.extend([(start, len(command)) for start in opened])
    return spans


def _has_sleep_in_loop_body(*, command: str) -> bool:
    spans = _loop_body_spans(command=command)
    return any(
        any(start <= match.start("sleep") < end for start, end in spans)
        for match in _SLEEP.finditer(command)
    )


def _has_unbounded_loop(*, command: str) -> bool:
    """Whether any loop here drives an iteration count the text does not state."""
    if _UNBOUNDED_LOOP.search(command):
        return True
    return any(
        not _is_bounded_literal_for(header=match.group("header"))
        for match in _FOR_LOOP.finditer(command)
    )


def _has_loop_or_xargs(*, command: str) -> bool:
    return bool(_LOOP_OR_XARGS.search(command))


def _has_mutating_gh_api(*, command: str) -> bool:
    return any(_MUTATING_METHOD.search(match.group("args")) for match in _GH_API.finditer(command))


def _has_read_gh_call(*, command: str) -> bool:
    # `gh run` / `gh pr` have no response cache, so no flag exempts them.
    if _GH_READ.search(command):
        return True
    for match in _GH_API.finditer(command):
        args = match.group("args")
        if _MUTATING_METHOD.search(args) or _CACHED_READ.search(args):
            continue
        return True
    return False


def has_cached_gh_api(*, command: str) -> bool:
    """Whether any `gh api` here is already in the sanctioned cached form.

    An AUDIT predicate: a caller carries it on the verdict record so "denied
    for obeying the remedy" is a query rather than a transcript replay. It is
    NOT an input to `matched_rule`, which reaches the same exemption through
    `_has_read_gh_call` per-call rather than command-wide.
    """
    return any(_CACHED_READ.search(match.group("args")) for match in _GH_API.finditer(command))


def gh_at_command_position(*, masked: str) -> bool:
    """Whether a `gh` sits where the shell would EXECUTE it.

    The second AUDIT predicate. A deny verdict whose command carried no `gh`
    here is a false positive by definition, so this is what makes the guard's
    measured rate a query instead of an investigation.
    """
    return bool(_GH_AT_COMMAND_POSITION.search(masked))


def matched_rule(*, masked: str) -> str | None:
    """Which conjunction convicts this command, or None when none does.

    The rule NAMES the verdict rather than merely producing it, because the
    name is what the telemetry record carries: a caller's deny-reason table
    collapses the two read conjunctions onto one message -- the remedy is the
    same -- and a dataset that cannot tell an unbounded loop from a polling
    sleep cannot say which of them is over-convicting.
    """
    if _has_loop_or_xargs(command=masked) and _has_mutating_gh_api(command=masked):
        return LOOP_MUTATION_RULE
    if not _has_read_gh_call(command=masked):
        return None
    if _has_unbounded_loop(command=masked):
        return LOOP_READ_RULE
    if _has_sleep_in_loop_body(command=masked):
        return SLEEP_READ_RULE
    return None
'''


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_INSTALLER_ID)


def driver_decision_body_path(*, project_root: Path) -> Path | None:
    """Where this tree's Driver bundle keeps the decision body, or None off a Driver.

    THE single resolution rule, shared by the installer and its Verifier so the
    pair cannot disagree about which file is under discussion. Returning None
    is the self-skip both surfaces honour: livespec core, the orchestrator
    plugins and this library itself carry no Driver manifest, and a body
    installed into one of them would be a file nothing loads.
    """
    if (project_root / _CLAUDE_MANIFEST).is_file():
        return project_root / _CLAUDE_HOOKS_DIR / DECISION_BODY_FILENAME
    if (project_root / _CODEX_MANIFEST).is_file():
        return project_root / _CODEX_HOOKS_DIR / DECISION_BODY_FILENAME
    return None


def install_decision_body(*, project_root: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Write the canonical body into this tree's Driver bundle; 0 either way."""
    destination = driver_decision_body_path(project_root=project_root)
    if destination is None:
        log.info(
            "no Driver plugin bundle at this root — nothing to install",
            installer_id=_INSTALLER_ID,
            status="skip",
            project_root=str(project_root),
        )
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    _ = destination.write_text(CANONICAL_GITHUB_RATE_LIMIT_DECISION_BODY, encoding="utf-8")
    log.info(
        "installed the canonical github rate-limit decision body",
        installer_id=_INSTALLER_ID,
        status="installed",
        path=str(destination),
    )
    return 0


def main() -> int:
    log = _configure_logger()
    return install_decision_body(project_root=Path.cwd(), log=log)


if __name__ == "__main__":
    raise SystemExit(main())
