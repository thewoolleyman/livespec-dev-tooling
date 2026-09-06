"""check_failure_digest — say the failure mode and its remedy LAST.

Work-item livespec-dev-tooling-b7dbne. Every check in the aggregate already
narrates itself well: a failing arm emits a structlog record carrying a
`failure_mode` and a `hint` composed for the checkout it fired in. What the
operator actually SAW was a bare `exit status 1`, because the record was
emitted 313 seconds and tens of thousands of lines before the aggregate
finished, and the pre-push hook printed nothing after it.

⛔ THE DEFECT IS PRESENTATION, NOT DETECTION, and that is why this module
INTERPRETS NOTHING. It re-reads the findings the failing targets already
emitted and re-prints them where a terminal still shows them. It knows no
failure mode by name — not even `worktree_pack_absent`, the one that was
measured — because a digest that enumerated modes would go stale the moment a
check added one, and would then be silent for exactly the new mode nobody yet
recognizes.

WHY IT IS BOUNDED. A mode reported against many files would re-create the
scroll-off this exists to fix, one digest deep instead of one aggregate deep.
So findings sharing a target, a mode and a remedy collapse into ONE entry that
lists the first few paths and counts the rest.

Output discipline: this module RENDERS; the dispatcher writes. That keeps the
direct-write contract in the one file that declares it
(`supervisor_entry_files`) and lets every rendering rule be asserted against a
returned string rather than against captured stdout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

__all__: list[str] = [
    "FailureFinding",
    "collect_failure_findings",
    "render_failure_digest",
]

# The structured-finding vocabulary the fleet's checks emit. `status` and
# `failure_mode` identify a finding; `hint` carries the remedy the emitting
# check composed; `path` names what to act on.
_STATUS_KEY = "status"
_FAIL_STATUS = "fail"
_FAILURE_MODE_KEY = "failure_mode"
_HINT_KEY = "hint"
_PATH_KEY = "path"

_DIGEST_HEADING = "=== failure modes reported above, with the remedy for each ==="
# A finding whose emitter composed no remedy still names its mode. Saying so
# beats a blank `remedy:` line, which reads as a remedy that is missing rather
# than as one the check never offered.
_MISSING_HINT = "(this finding carried no remedy — read the target's output above)"
_MAX_PATHS_PER_MODE = 3


@dataclass(frozen=True, kw_only=True)
class FailureFinding:
    """One `status=fail` record, lifted out of one target's captured output."""

    target: str
    failure_mode: str
    hint: str
    path: str


def _decoded_records(*, output: str) -> list[dict[str, object]]:
    """Return the JSON objects among `output`'s lines.

    Captured target output interleaves structlog JSON with prose from `just`,
    ruff, pytest and the checks' own progress lines. A line that is not a JSON
    object is not a finding — an ordinary ANSWER about that line, not a failure
    of this walk — so it is skipped rather than reported. A line that IS valid
    JSON but decodes to a scalar or an array is skipped on the same ground.
    """
    records: list[dict[str, object]] = []
    for line in output.splitlines():
        try:
            decoded = cast("object", json.loads(line))
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            records.append(cast("dict[str, object]", decoded))
    return records


def _text(*, record: dict[str, object], key: str, fallback: str) -> str:
    """Return `record[key]` when it is a non-empty string, else `fallback`.

    Absent, empty and non-string are one case deliberately: each means the
    record offers nothing to print for that key, and the digest's job is to
    print something true rather than to diagnose the emitter.
    """
    value = record.get(key)
    return value if isinstance(value, str) and value else fallback


def collect_failure_findings(*, target: str, output: str) -> list[FailureFinding]:
    """Return the `status=fail` findings `target` emitted, in emission order.

    A record must carry `status=fail` AND a non-empty string `failure_mode` to
    become a finding: the whole value of the digest is naming the mode, so a
    record that cannot name one has nothing to contribute to the tail and is
    left where it was emitted.
    """
    findings: list[FailureFinding] = []
    for record in _decoded_records(output=output):
        failure_mode = record.get(_FAILURE_MODE_KEY)
        if record.get(_STATUS_KEY) != _FAIL_STATUS or not isinstance(failure_mode, str):
            continue
        if not failure_mode:
            continue
        findings.append(
            FailureFinding(
                target=target,
                failure_mode=failure_mode,
                hint=_text(record=record, key=_HINT_KEY, fallback=_MISSING_HINT),
                path=_text(record=record, key=_PATH_KEY, fallback=""),
            )
        )
    return findings


def _render_entry(*, target: str, failure_mode: str, hint: str, paths: list[str]) -> list[str]:
    """Render one grouped entry: the mode, a bounded path list, then the remedy.

    The remedy is LAST by construction. The whole point of the digest is that
    the operator's terminal keeps the final lines, so the sentence that says
    what to run must be the sentence closest to the prompt.
    """
    plural = "" if len(paths) == 1 else "s"
    lines = [f"\n  {target}: {failure_mode} ({len(paths)} finding{plural})\n"]
    lines.extend(f"    path: {path}\n" for path in paths[:_MAX_PATHS_PER_MODE] if path)
    if len(paths) > _MAX_PATHS_PER_MODE:
        lines.append(f"    ... and {len(paths) - _MAX_PATHS_PER_MODE} more\n")
    lines.append(f"    remedy: {hint}\n")
    return lines


def render_failure_digest(*, findings: list[FailureFinding]) -> str:
    """Render the tail block for `findings`, or empty text when there are none.

    Findings are grouped by (target, failure mode, remedy) so one mode reported
    against many files costs one entry rather than many. Empty text is returned
    for an empty finding set rather than an empty heading: a target that failed
    without emitting a structured record has nothing this can add, and a
    heading over nothing would suggest the digest had looked and found the
    failure unexplained.
    """
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for finding in findings:
        key = (finding.target, finding.failure_mode, finding.hint)
        grouped.setdefault(key, []).append(finding.path)
    if not grouped:
        return ""
    lines = [f"\n{_DIGEST_HEADING}\n"]
    for (target, failure_mode, hint), paths in grouped.items():
        lines.extend(
            _render_entry(target=target, failure_mode=failure_mode, hint=hint, paths=paths)
        )
    return "".join(lines)
