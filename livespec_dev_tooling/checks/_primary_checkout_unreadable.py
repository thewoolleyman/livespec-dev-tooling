"""_primary_checkout_unreadable — the one thing this check cannot decide.

Private sibling shared by `_primary_checkout_hook_files` and
`_primary_checkout_worktree_pack`, in its own module so neither arm has to
import the other for it. The same private-sibling shape as
`fleet/_pin_walk_failure.py` and `fleet/_invocation_failure.py`: a failure type
two converted callers share, extracted so there is one spelling of the
condition rather than one per arm.

WHY IT IS SO NARROW. Every other state the primary-checkout check meets is
something it OBSERVED — a hook absent, a hook whose bytes differ, a pack file
whose bytes are not valid UTF-8, a justfile with no `import?` line, a config
that is absent or unparseable. All of those are facts, they all stay on the
success track, and each is narrated as the violation it is. This type carries
ONLY the case where a read did not happen, because that is the only condition
under which the check has nothing to say about the repository at all.

⛔ AND IT IS DELIBERATELY NOT `OSError`-SHAPED. `FileNotFoundError` IS an
`OSError`, and an absent hook or an absent config is DEFINITIVE — the first is
the violation this check exists to report, the second is what makes a
directory ungoverned. Both callers reach a read only past an `is_file()`
probe, which is what keeps absence off this track. Spelling the arms "catch
OSError" would have swept two load-bearing definitive answers into a silent
non-answer, loosening the check while appearing to sharpen it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CheckInputUnreadable",
]


@dataclass(frozen=True)
class CheckInputUnreadable:
    """A file the check needed to read DID NOT ANSWER.

    `path` is the file and `detail` the OS diagnostic. Both exist so the
    operator is not left to guess which of the check's several reads failed;
    a bare "a read failed" would be the same manufactured-confidence shape the
    conversion removes, one level up.
    """

    path: str
    detail: str
