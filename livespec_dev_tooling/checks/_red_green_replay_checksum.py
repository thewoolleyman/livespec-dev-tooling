"""Range validation verifies a commit's recorded Red test against that commit's own tree.

A commit carried `TDD-Red-Test` and `TDD-Red-Test-File-Checksum` trailers
naming a test file that its own tree did not hold, or held with other bytes, so
the recorded checksum matched nothing, and it merged
(work-item livespec-dev-tooling-a4w7qr). The trailer-presence checks never read
the tree.

The rule: a commit carrying BOTH trailers is refused unless (a) the named path
exists in that commit's own tree, (b) the sha256 of that blob's bytes equals
the trailer, and (c) the path is among the files that commit's own diff adds or
changes. Condition (c) catches the measured shape where the commit carried
another commit's trailers and the named test already sat, byte-identical, in
the base (livespec-orchestrator-beads-fabro 39ffe024c; work-item
livespec-dev-tooling-rd6reo). A Red commit stages its test and the Green amend
keeps those bytes, so a genuine pair always carries its test in its diff.

The checksum definition is the Red hook's own
(`_red_green_replay_modes`): `sha256:` plus the hex digest of the file bytes.

A commit with no `TDD-Red-Test` trailer or no checksum trailer (no Red block,
a `TDD-Suite-Green-*`-only commit) is not judged. The two exemptions the range
already has keep their effect: a commit admitted by a recorded incident, and a
forge-authored revert. A probe that could not start exempts nothing.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _red_green_replay_incident import (  # noqa: E402  — sibling private import
    admitted_by_recorded_incident,
)
from _red_green_replay_revert import (  # noqa: E402  — sibling private import
    is_forge_authored_revert,
)
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "CHECKSUM_HINT",
    "CHECK_ID",
    "admitted_by_recorded_incident",
    "is_forge_authored_revert",
    "verify_recorded_checksums",
]

CHECK_ID: str = "red-green-replay-range-recorded-checksum-mismatch"
CHECKSUM_HINT: str = (
    "Every commit that carries TDD-Red-Test and TDD-Red-Test-File-Checksum trailers must hold "
    "the named test file in its OWN tree, the sha256 of that file's bytes there must equal "
    "the recorded checksum, and the commit's own diff must add or change that file. "
    "A commit whose trailers name a test its diff never touched, or a "
    "rebase that changed the test under a stale checksum, fails this. Remedy: redo the change "
    "through the hook (Red commit staging the test alone, then the Green amend) so the "
    "trailers are earned on the tree the commit ships. No flag, skip or subject prefix "
    "exempts it."
)
_TEST_RE = re.compile(r"^TDD-Red-Test:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
_CHECKSUM_RE = re.compile(r"^TDD-Red-Test-File-Checksum:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)


def _git_bytes(*, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], capture_output=True, check=False)


def _diff_paths(*, sha: str) -> list[str]:
    return (
        _git_bytes(args=["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha])
        .stdout.decode("utf-8", "replace")
        .splitlines()
    )


def _problem(*, sha: str, module: str, recorded: str) -> str | None:
    """Return which condition failed for `module` on `sha`'s own tree, or None when both hold."""
    blob = _git_bytes(args=["cat-file", "blob", f"{sha}:{module}"])
    if blob.returncode != 0:
        return "absent: the named test path does not exist in the commit's own tree"
    actual = f"sha256:{hashlib.sha256(blob.stdout).hexdigest()}"
    if actual != recorded:
        return f"checksum: the file's sha256 in the commit's own tree is {actual}, not {recorded}"
    if module not in _diff_paths(sha=sha):
        return "diff: the named test path is not added or changed by the commit's own diff"
    return None


def _exempt(*, sha: str, message: str, base_ref: str) -> bool:
    if admitted_by_recorded_incident(sha=sha, message=message):
        return True
    touched = (
        _git_bytes(
            args=[
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "--root",
                "--diff-filter=d",
                sha,
            ]
        )
        .stdout.decode("utf-8", "replace")
        .splitlines()
    )
    product_paths = [p for p in touched if p.endswith(".py")]
    if not product_paths:
        return False
    forge = is_forge_authored_revert(sha=sha, product_paths=product_paths, base_ref=base_ref)
    return is_successful(forge) and bool(unsafe_perform_io(forge.unwrap()))


def verify_recorded_checksums(*, shas: list[str], base_ref: str) -> list[dict[str, str]]:
    """Return one finding per commit whose recorded Red test fails either condition."""
    findings: list[dict[str, str]] = []
    for sha in shas:
        message = _git_bytes(args=["log", "-1", "--format=%B", sha]).stdout.decode(
            "utf-8", "replace"
        )
        named = _TEST_RE.search(message)
        recorded = _CHECKSUM_RE.search(message)
        if named is None or recorded is None:
            continue
        module = named.group(1).split("::", 1)[0]
        problem = _problem(sha=sha, module=module, recorded=recorded.group(1))
        if problem is None:
            continue
        if _exempt(sha=sha, message=message, base_ref=base_ref):
            continue
        findings.append({"sha": sha, "test_path": module, "failed_condition": problem})
    return findings
