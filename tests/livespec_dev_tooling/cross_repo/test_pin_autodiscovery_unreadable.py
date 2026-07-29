"""A pin file the walk FOUND and could not READ lands on the failure track.

`pin_autodiscovery.discover` is the third of the three genuine Result-return
violations livespec-dev-tooling-9sl0 triaged. livespec v179 member 1 clause
(d) — the callee fixpoint — disqualifies it: all seven `walk_*` callees touch
the filesystem directly, through `path.read_text()` and `Path.glob`, not
through an injected seam. So `IOResult` rather than `Result`, and the
`unsafe_perform_io` discipline at every call site.

WHICH failure goes on the railway is the design decision the item flagged,
and the ratified contract decides it. `SPECIFICATION/contracts.md` §"Pin
autodiscovery rules" line 525 makes TWO tolerances normative — a MISSING file
yields no records, and an UNRECOGNIZED format is tolerated — so neither may
become a failure-track value without a spec change. It says nothing about a
third input: a file the walk found and could not READ. That case is not
tolerated today either; it propagates as an UNCAUGHT raise out of a function
whose contract is tolerance, which in the central fleet sweep means the whole
nine-member run dies partway through one member's walk.

Both spellings of it are reachable and are pinned below: non-UTF-8 bytes in a
file the walk reads (`UnicodeDecodeError`), and a walked path that is not a
readable file at all (`IsADirectoryError`, an `OSError`). Neither is exotic —
the fleet sweep materializes member files into a temp tree before walking them.

THE SECOND ONE IS DELIBERATELY NOT A PERMISSIONS TEST, and the reason is worth
keeping: `chmod(0o000)` denies nothing to **root**, and CI runs as root inside
the sandbox container. A permission-based test passes on a developer machine
and fails in CI — which is how it was found. `IsADirectoryError` is
uid-independent, populates the same `filename` slot, and exercises exactly the
same arm.

The separate finding that an UNPARSEABLE pin file reads as a PASS in the
pin-currency row is livespec-dev-tooling-2j2l, and is deliberately NOT this
file's subject: it is a different input with a different correct answer, and
the walk's tolerance of it is ratified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo.pin_autodiscovery import discover

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


def test_non_utf8_bytes_in_a_walked_pin_file_are_a_failure_not_a_raise(*, tmp_path: Path) -> None:
    """A `.livespec.jsonc` of undecodable bytes fails the walk by value.

    The failure names the file, because the operator reading it is walking a
    materialized copy of ANOTHER repo's tree and has no way to guess which of
    the seven formats' files was the undecodable one.
    """
    _ = (tmp_path / ".livespec.jsonc").write_bytes(b'{"a": "\xff\xfe"}')

    walked = discover(root=tmp_path, source_repo=None)

    assert isinstance(walked, IOFailure) and unsafe_perform_io(walked.failure()).file_path.endswith(
        ".livespec.jsonc"
    )


def test_a_walked_path_that_is_not_a_readable_file_is_a_failure_not_a_raise(
    *, tmp_path: Path
) -> None:
    """A `*.yml` the directory scan globs but cannot read fails the walk by value.

    A DIRECTORY named `ci.yml` is globbed by the workflow scan exactly like a
    file and raises `IsADirectoryError` on read. That is uid-independent —
    unlike a `chmod(0o000)` file, which denies nothing to root and so passes
    on a developer machine while failing in the root-run CI container.
    """
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").mkdir()

    walked = discover(root=tmp_path, source_repo=None)

    assert isinstance(walked, IOFailure) and unsafe_perform_io(walked.failure()).file_path.endswith(
        "ci.yml"
    )


def test_a_clean_walk_still_succeeds_and_carries_its_records(*, tmp_path: Path) -> None:
    """The success track carries the RECORDS, not merely a green verdict.

    Asserting only that the walk succeeded is exactly what an unwrap bug that
    degrades to an empty list also satisfies — and an empty record list is the
    shape that reads as "this member has no pins", which passes.
    """
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"self": {"compat": {"pinned": "v1.2.3", "livespec": "v1.2.3"}}}', encoding="utf-8"
    )

    walked = discover(root=tmp_path, source_repo=None)

    assert isinstance(walked, IOSuccess) and [
        record["current_value"] for record in unsafe_perform_io(walked.unwrap())
    ] == ["v1.2.3"]
