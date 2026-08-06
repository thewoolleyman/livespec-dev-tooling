"""Ported charter defect detectors from livespec-overseer's prompt gate."""

from __future__ import annotations

import re

from livespec_dev_tooling.charters._shell import (
    code_blocks,
    decides_busy,
    is_comment,
    logical_lines,
    pipeline_segments,
    segment_effect,
    strip_trailing_comment,
)

BINDING = re.compile(
    "".join(
        (
            r"""^\s*(?:export\s+|readonly\s+|local\s+)?([A-Za-z_][A-Za-z0-9_]*)=""",
            r"""(['"]?)(=[^'"\s]*)\2\s*(?:#.*)?$""",
        )
    ),
    re.MULTILINE,
)
TARGET = re.compile(r"-t\s+((?:'[^']*')|(?:\"[^\"]*\")|(?:\S+))")
TMUX_LINE = re.compile(r"\btmux\b")
PATH_RESOLVE = re.compile(r"readlink\s+-f|\brealpath\b")
NONEMPTY_GUARD = re.compile(r"(?:test\s+-n|\[\s+-n|\[\[\s+-n|-z\s)")
CAPTURE_S_BOUND = re.compile(r"=\s*\$\(\s*[^)]*capture-pane[^)]*-S\s+-\d+")
CAPTURE_S_PIPED = re.compile(r"capture-pane[^\n|]*-S\s+-\d+[^\n]*\|[^\n]*grep")
SUPERVISOR_CHECK = re.compile(r"SUPERVISOR_TARGET=|grep\s+-\S+\s+'[^']*-supervisor'")
SUPERVISOR_PROOF_PS = '--ppid "$supervisor_pane_pid"'
SUPERVISOR_PROOF_GUARD = '[ -n "$supervisor_pane_pid" ]'
SUPERVISOR_PROOF_DISTINCT = '"$supervisor_pane_pid" != "$pane_pid"'
LIST_SESSIONS_GREP = re.compile(r"list-sessions[^\n|]*\|[^\n]*grep\s+(-\S+)")
BASH_PIPESTATUS = re.compile(r"\bPIPESTATUS\b")
BD_INVOCATION = re.compile(r"(?<![-\w])bd\s+(?:show|list|update|create|close)\b")
WRAPPER_NAME = r"with-[A-Za-z0-9_.-]+-env\.sh"
WRAPPER_DETECTED = re.compile(rf"command\s+-v\s+\"?{WRAPPER_NAME}")
WRAPPER_DIRECT = re.compile(rf"{WRAPPER_NAME}[^\n]*\bbd\b")
WRAPPER_VAR_DETECTED = re.compile(r"command\s+-v\s+\"?\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
WRAPPER_VAR_INVOKED = re.compile(r"\"?\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?\"?\s+(?:--\s+)?bd\b")
FIXED_CAP_READ = re.compile(r"sed\s+-n\s+['\"]?1,\s*\d+\s*p['\"]?")
TRUNCATION_NOTICE = re.compile(r"TRUNCATED")
MARKER_FILE_TEST = re.compile(r"(?:test|\[)\s+!?\s*-f\s+\"?\$\{?supervisor_marker")
MARKER_NONEMPTY_GUARD = re.compile(r"-[nz]\s+\"?\$\{?supervisor_marker")
DATE_ARGS = re.compile(r"\bdate\b((?:[ \t]+(?:'[^']*'|\"[^\"]*\"|[^\s;|&)]+))*)")
DATE_TOKEN = re.compile(r"'[^']*'|\"[^\"]*\"|\S+")
DATE_SHORT_BUNDLE = re.compile(r"\A-([A-Za-z]+)")
DATE_FILE_LONG = re.compile(r"\A--reference(?:=|\Z)")
DATE_UTC_LONG = re.compile(r"\A--(?:utc|universal)\Z")
DATE_UTC_LABEL = re.compile(r"(?<!%)Z|UTC")
RULE = "\u2500"
IDLE_PANE_RENDER = "\n".join(
    (
        "  main is clean and matches origin/main; the worktree and both refs are gone.",
        "  \u23bf  $ git worktree list --porcelain | head -40 (6m 50s \u00b7 4 lines)",
        "",
        f"{RULE} Worked for 24m 01s {RULE * 67}",
        "",
        "\u273b Worked for 14m 56s",
        "",
        "\u203b recap: the thread is fully complete; nothing remains.",
        "                       new task? /clear to save 625.9k tokens",
        f"{RULE * 32} 06-resilience-acceptance {RULE * 2}",
        "\u276f ",
        RULE * 61,
        "  Opus 5 (1M context) | /data/projects/livespec-overseer | master | Ctx: 49% left",
        "  \u23f5\u23f5 bypass permissions on (shift+tab to cycle) \u00b7 \u2190 for agents",
    )
)

__all__: list[str] = [
    "bare_targets",
    "bash_pipestatus_in_zsh_fleet",
    "busy_test_matches_idle_pane",
    "fixed_cap_marker_read",
    "history_fed_capture",
    "local_time_labelled_utc",
    "regex_session_existence_test",
    "supervisor_trusted_by_name",
    "unguarded_marker_binding",
    "unguarded_path_resolution",
    "wrapper_less_ledger_read",
]


def variable_name(*, token: str) -> str | None:
    if token.startswith("${") and token.endswith("}"):
        return token[2:-1]
    if token.startswith("$"):
        return token[1:]
    return None


def bare_targets(*, text: str) -> list[str]:
    """`tmux -t` arguments that do not resolve to the exact `'=name:'` form."""
    blocks = code_blocks(text=text)
    bound = {match.group(1) for match in BINDING.finditer("\n".join(blocks))}
    found: list[str] = []
    for block in blocks:
        for raw in block.splitlines():
            if not TMUX_LINE.search(raw) or is_comment(line=raw):
                continue
            line = strip_trailing_comment(line=raw)
            for match in TARGET.finditer(line):
                token = match.group(1).strip("'\"")
                name = variable_name(token=token)
                if not token.startswith("=") and (name is None or name not in bound):
                    found.append(line.strip())
    return found


def unguarded_path_resolution(*, text: str) -> list[str]:
    """Path resolution with no non-empty guard in the preceding three lines."""
    found: list[str] = []
    for block in code_blocks(text=text):
        lines = block.splitlines()
        for index, line in enumerate(lines):
            if not PATH_RESOLVE.search(line) or is_comment(line=line):
                continue
            window = "\n".join(lines[max(0, index - 3) : index + 1])
            if not NONEMPTY_GUARD.search(window):
                found.append(line.strip())
    return found


def history_fed_capture(*, text: str) -> list[str]:
    """`capture-pane -S -N` feeding the picker test or the pane diff."""
    return [
        line.strip()
        for block in code_blocks(text=text)
        for line in block.splitlines()
        if not is_comment(line=line)
        and (CAPTURE_S_BOUND.search(line) or CAPTURE_S_PIPED.search(line))
    ]


def bash_pipestatus_in_zsh_fleet(*, text: str) -> list[str]:
    """`PIPESTATUS` used in emitted code, which is silently empty under zsh."""
    return [
        line.strip()
        for block in code_blocks(text=text)
        for line in block.splitlines()
        if not is_comment(line=line) and BASH_PIPESTATUS.search(line)
    ]


def regex_session_existence_test(*, text: str) -> list[str]:
    """A `list-sessions | grep` presence test whose pattern is not literal."""
    found: list[str] = []
    for block in code_blocks(text=text):
        for raw in block.splitlines():
            match = LIST_SESSIONS_GREP.search(raw)
            if not is_comment(line=raw) and match is not None and "F" not in match.group(1):
                found.append(raw.strip())
    return found


def supervisor_trusted_by_name(*, text: str) -> list[str]:
    """A supervisor existence check with no liveness proof anywhere."""
    blocks = code_blocks(text=text)
    if not any(SUPERVISOR_CHECK.search(block) for block in blocks):
        return []
    joined = "\n".join(blocks)
    if all(
        needle in joined
        for needle in (SUPERVISOR_PROOF_PS, SUPERVISOR_PROOF_GUARD, SUPERVISOR_PROOF_DISTINCT)
    ):
        return []
    return ["supervisor existence checked but liveness never proven"]


def wrapper_less_ledger_read(*, text: str) -> list[str]:
    """A `bd` invocation with no credential wrapper anywhere in the charter."""
    blocks = code_blocks(text=text)
    invocations = [
        raw.strip()
        for block in blocks
        for raw in block.splitlines()
        if BD_INVOCATION.search(raw) and not is_comment(line=raw)
    ]
    if not invocations:
        return []
    joined = "\n".join("\n".join(logical_lines(block=block)) for block in blocks)
    if WRAPPER_DETECTED.search(joined) or WRAPPER_DIRECT.search(joined):
        return []
    proved = {match.group(1) for match in WRAPPER_VAR_DETECTED.finditer(joined)}
    invoked = {match.group(1) for match in WRAPPER_VAR_INVOKED.finditer(joined)}
    return [] if proved & invoked else invocations


def fixed_cap_marker_read(*, text: str) -> list[str]:
    """A fixed-line-count marker read that never announces its own truncation."""
    blocks = code_blocks(text=text)
    caps = [
        raw.strip()
        for block in blocks
        for raw in block.splitlines()
        if FIXED_CAP_READ.search(raw) and not is_comment(line=raw)
    ]
    return [] if not caps or TRUNCATION_NOTICE.search("\n".join(blocks)) else caps


def unguarded_marker_binding(*, text: str) -> list[str]:
    """A `supervisor_marker` file test with no non-empty guard on the binding."""
    blocks = code_blocks(text=text)
    tests = [
        raw.strip()
        for block in blocks
        for raw in block.splitlines()
        if MARKER_FILE_TEST.search(raw) and not is_comment(line=raw)
    ]
    return [] if not tests or MARKER_NONEMPTY_GUARD.search("\n".join(blocks)) else tests


def date_short_flags(*, token: str) -> str:
    match = DATE_SHORT_BUNDLE.match(token)
    return match.group(1) if match is not None else ""


def claims_utc(*, token: str) -> bool:
    if "u" in date_short_flags(token=token) or DATE_UTC_LONG.match(token):
        return True
    bare = token.strip("'\"")
    return bare.startswith("+") and DATE_UTC_LABEL.search(bare) is not None


def local_time_labelled_utc(*, text: str) -> list[str]:
    """A `date` invocation that reads a file and still claims UTC."""
    found: list[str] = []
    for block in code_blocks(text=text):
        for raw in block.splitlines():
            if is_comment(line=raw):
                continue
            for args in DATE_ARGS.findall(strip_trailing_comment(line=raw)):
                tokens = DATE_TOKEN.findall(args)
                reads_file = any(
                    "r" in date_short_flags(token=token) or DATE_FILE_LONG.match(token)
                    for token in tokens
                )
                if reads_file and any(claims_utc(token=token) for token in tokens):
                    found.append(raw.strip())
                    break
    return found


def busy_decisions(*, block: str, pane: str) -> list[tuple[str, re.Pattern[str], list[str]]]:
    """Each busy-deciding grep, with the pane lines still reaching it."""
    found: list[tuple[str, re.Pattern[str], list[str]]] = []
    lines = logical_lines(block=block)
    for index, line in enumerate(lines):
        if (
            is_comment(line=line)
            or "grep" not in line
            or not decides_busy(lines=lines, index=index)
        ):
            continue
        working = pane.splitlines()
        for segment in pipeline_segments(line=line):
            working, decider = segment_effect(segment=segment, lines=working)
            if decider is not None:
                found.append((line.strip(), decider, working))
                break
    return found


def busy_test_matches_idle_pane(*, text: str) -> list[str]:
    """A watcher busy test that fires on an idle pane, so it can only say busy."""
    return [
        line
        for block in code_blocks(text=text)
        for line, decider, reaching in busy_decisions(block=block, pane=IDLE_PANE_RENDER)
        if any(decider.search(candidate) for candidate in reaching)
    ]
