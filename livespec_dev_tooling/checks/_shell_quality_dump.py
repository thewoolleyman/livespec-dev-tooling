"""The shell-quality check's `just --dump` acquisition half.

Split from `_shell_quality_recipes` at the seam that module's own docstring
already named: it "reads the `just --dump` JSON and decides which RECIPES
violate policy". Those are two concerns, and only the first one touches the
world. This module owns obtaining the dump — running `just` in the repo under
judgement and interpreting its output — and knows nothing about what makes a
recipe conforming; the policy module owns that and knows nothing about how the
payload was obtained.

THE ACQUISITION IS NOT TOTAL, AND THE RETURN NOW SAYS SO
(livespec-dev-tooling-qndn.13). The policy decides nothing without this read,
so its answer is only as good as this one — and a payload degraded to `{}` gave
the policy no way to tell "this repo's recipes are clean" from "no recipes were
ever seen". Both spelled an empty finding list, and the second reached the
check as a PASS. Three ways to never see the recipes are now the FAILURE track:

- `just` absent from PATH, which used to `cast` a `None` binary into
  `subprocess.run` and die with a `TypeError` out of the check.
- A dump that exits non-zero — a justfile the parser rejects — which left
  `json.loads("")` raising a `JSONDecodeError` out of the check.
- A dump that exits 0 without emitting a JSON object, which was silently read
  as an empty justfile.

⛔ AN ABSENT JUSTFILE STAYS ON THE SUCCESS TRACK, and that half is load-bearing
rather than fastidious. A repo that keeps no justfile has no recipes to violate
recipe policy, so the empty answer there is the ANSWER — the same distinction
between a rule that found nothing and a rule that never ran which this whole
conversion exists to draw. Reading absence as a failure would convict every
justfile-free consumer of an unobtainable dump.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

# `returns` is VENDORED, not installed, so a bare import resolves only if some
# EARLIER import in the same process already put `_vendor/` on `sys.path`. This
# module is imported directly by its own tests as well as through the check, so
# it establishes the path itself rather than relying on whichever importer
# happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "JustDump",
    "JustRecipe",
    "JustSettings",
    "JustShell",
    "RecipeDumpUnavailable",
    "just_dump",
]


class JustShell(TypedDict, total=False):
    arguments: list[str]
    command: str


class JustSettings(TypedDict, total=False):
    positional_arguments: bool
    shell: JustShell | None


class JustRecipe(TypedDict, total=False):
    attributes: list[str]
    body: list[list[object]]
    doc: str | None
    name: str
    parameters: list[object]
    shebang: bool


class JustDump(TypedDict, total=False):
    recipes: dict[str, JustRecipe]
    settings: JustSettings


@dataclass(frozen=True, kw_only=True)
class RecipeDumpUnavailable:
    """A `just --dump` the recipe policy needed and did not obtain.

    Deliberately NOT inhabited by "this repo keeps no justfile": that is the
    dump the policy asked for, answered, and it travels the success track as
    the empty payload. What lands here is a repo that HAS recipes to judge and
    whose recipes nothing read.

    `reason` is the discriminator the check renders as the finding's own
    reason, so the three ways to lose the dump stay told apart downstream;
    `remedy` carries the one action that repairs THAT reason, because
    installing `just` and fixing a justfile the parser rejects are not the same
    repair and a single reason would spell them alike.
    """

    reason: str
    remedy: str


_JUST_UNAVAILABLE = RecipeDumpUnavailable(
    reason="just-unavailable",
    remedy=(
        "install `just` and expose it on PATH, for example with "
        "`mise install just` from the consumer repo"
    ),
)
_DUMP_UNPARSEABLE = RecipeDumpUnavailable(
    reason="just-dump-unparseable",
    remedy=(
        "`just --dump --dump-format json` exited 0 without emitting a JSON object — run "
        "it in the repo root, inspect the output, then re-run check-shell-quality"
    ),
)


def _dump_failed(*, repo_root: Path, returncode: int) -> RecipeDumpUnavailable:
    return RecipeDumpUnavailable(
        reason="just-dump-failed",
        remedy=(
            f"`just --dump --dump-format json` exited {returncode} in {repo_root} — run it "
            "there, fix the justfile error it reports, then re-run check-shell-quality"
        ),
    )


def _parsed_dump(*, stdout: str) -> IOResult[JustDump | None, RecipeDumpUnavailable]:
    """Read a dump that EXITED 0, refusing anything that is not a JSON object.

    Unparseable output and well-formed JSON that is not an object are one
    reason rather than two, because they are one condition to the reader: a
    `just` whose dump this module cannot interpret. The `except` binds no
    payload for the same reason — the parser's message describes bytes the
    operator is about to re-read by running the command themselves.
    """
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, Mapping):
        return IOFailure(_DUMP_UNPARSEABLE)
    return IOSuccess(cast(JustDump, parsed))


def just_dump(*, repo_root: Path) -> IOResult[JustDump | None, RecipeDumpUnavailable]:
    """The `just --dump` payload, or WHY there is none — never a silent `{}`.

    `None` on the success track means the one non-answer that IS an answer:
    the repo keeps no justfile, so it has no recipes. Everything else that
    stops the dump from arriving rides the failure track rather than being
    degraded into an empty payload the policy would report as clean.
    """
    if not (repo_root / "justfile").is_file():
        return IOSuccess(None)
    just_binary = shutil.which("just")
    if just_binary is None:
        return IOFailure(_JUST_UNAVAILABLE)
    completed = subprocess.run(
        [just_binary, "--dump", "--dump-format", "json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return IOFailure(_dump_failed(repo_root=repo_root, returncode=completed.returncode))
    return _parsed_dump(stdout=completed.stdout)
