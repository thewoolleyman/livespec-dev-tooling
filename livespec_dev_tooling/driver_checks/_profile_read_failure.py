"""The failure track shared by BOTH Driver packaging profiles.

ONE type rather than one per profile. `_plugin_structure_claude` and
`_plugin_structure_codex` are two spellings of the same question — does
this bundle's committed manifest topology satisfy the contract — and they
already single-source `EXPECTED_SKILLS`, `FRONTMATTER_NAME_RE` and
`fenced_invocation_violations` for exactly that reason. Two byte-identical
dataclasses would be the `livespec-dev-tooling-8o8e.6` duplication shape,
where copies keep agreement by COPYING; `fleet/_invocation_failure.py` is
the worked precedent from the subprocess-seam trio.

A LEAF: imports nothing from `livespec_dev_tooling.driver_checks`, so both
profile modules may import it without a cycle.

WHAT BELONGS ON THIS TRACK, and it is narrower than "something went
wrong". Only "this run could not READ what it was asked to inspect". A
manifest that is ABSENT, or present and MALFORMED, is a definitive and
reproducible property of the Driver's committed bytes — an author must fix
it, so it stays a VIOLATION on the success track. An unreadable one says
nothing about the Driver at all and may not reproduce.

⛔ `FileNotFoundError` IS an `OSError`, so the split cannot be spelled as
"catch OSError". Absence is definitive and must stay a violation; catching
the parent alone would convert a real finding into a silent non-answer,
which is the loosening direction. This is
`livespec-dev-tooling-6ge`'s "a can't-read is not absent" rule and its
converse, applied together.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["ProfileUnreadable"]


@dataclass(frozen=True, kw_only=True)
class ProfileUnreadable:
    """A file the profile check had to read, and could not.

    `path` is carried because the diagnostic is useless without it — "the
    profile was unreadable" names nothing an operator can act on — and it
    is repo-RELATIVE so the message does not leak an absolute host path
    into CI logs.
    """

    path: str
    detail: str

    @property
    def reason(self) -> str:
        """One human-readable line naming the file and the cause."""
        return f"{self.path} could not be read: {self.detail}"
