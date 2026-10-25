"""`_gate_authority_skip` — which members leave a gate Job, and under whose name.

The unit tier for the Job half of the authority exception in this repository's
own `SPECIFICATION/contracts.md`, delegated pre-push gate section. The
end-to-end claim — that a consuming repository's rendered Job carries those
members under its own skip variable — is asserted at the consumer tier, in
`tests/consumer/test_delegated_gate_authority_skip_scenarios.py`, because it
spans the client, the bash renderer and the pod script. What is asserted HERE is
the resolution's own edges: the readings where the answer cannot be established,
each of which must come back as "nothing to tell the Job" rather than as a guess.

NONE OF THEM GUESSES A NAME, which is the one thing every reading here has in
common: exporting the list under a name invented from somewhere other than the
repository's own recipe would skip nothing while every surface reported a Job
that had been told.

WHAT THEY DIFFER ON IS WHETHER A JOB MAY STILL BE SUBMITTED, and that split is
the 2026-10-25 repair. A reading that establishes no skip variable for a
repository DECLARING an authority member is a refusal: there is nowhere to put
the list, so the member cannot be kept out of a pod the contract hands no
authority, and the assembly fails rather than rendering a Job that runs it. A
reading that establishes nothing because there is NOTHING TO TELL — no such
member, or a declaration this host cannot read and the host half reports instead
— stays on the success track carrying an empty list, because a Job that omits
nothing is the correct Job for a repository with nothing to omit.
"""

from __future__ import annotations

from pathlib import Path

from returns.pipeline import is_successful
from returns.result import Success

from livespec_dev_tooling._gate_authority_skip import (
    AUTHORITY_SKIP_ENV_FLAG,
    AUTHORITY_SKIP_MEMBER_FLAG,
    authority_skip_argv,
    check_skip_variable,
)

__all__: list[str] = []

# The member of the measured defect, and a SHIPPED one: its authority
# declaration is its own module's `CHECK_AUTHORITY` constant, so a fixture
# naming it declares what every real consumer declares.
_AUTHORITY_MEMBER = "check-branch-protection-alignment"
_PLAIN_MEMBER = "check-widget-lint"

# The fleet's own idiom, in the shape livespec's `check` recipe writes it.
_SKIP_READ = '    read -ra skip_targets <<< "${SKIP_TARGETS:-}"\n'


def _a_check_recipe(*, root: Path, body: str) -> Path:
    """A fixture repository whose `check` recipe carries `body` and names one member."""
    root.mkdir(parents=True, exist_ok=True)
    _ = (root / "justfile").write_text(
        "check:\n"
        "    #!/usr/bin/env bash\n"
        f"{body}"
        "    targets=(\n"
        f"        {_AUTHORITY_MEMBER}\n"
        f"        {_PLAIN_MEMBER}\n"
        "    )\n",
        encoding="utf-8",
    )
    return root


def test_a_repository_whose_justfile_declares_no_check_recipe_establishes_nothing(
    *, tmp_path: Path
) -> None:
    """A justfile with no `check:` recipe names no skip surface at all.

    READ AS AN ANSWER rather than as a failure. A repository can carry a justfile
    whose aggregate is spelled some other way, and refusing the whole delegated
    gate over it would refuse that repository's pushes to repair a reading that
    changes nothing for a repository declaring no authority member.
    """
    repo = tmp_path / "widget"
    repo.mkdir()
    _ = (repo / "justfile").write_text("verify:\n    echo hi\n", encoding="utf-8")

    assert check_skip_variable(repo_root=repo) is None


def test_a_read_into_an_array_that_is_not_a_skip_list_is_not_that_read(*, tmp_path: Path) -> None:
    """The expansion alone does not make a line the read that fills the skip list.

    A recipe legitimately reads other environment into other arrays, and a
    mechanism that exported the authority members into one of those would both
    skip nothing AND clobber a value the recipe needs — two wrongs from one
    match, neither of which announces itself.
    """
    repo = _a_check_recipe(
        root=tmp_path / "widget", body='    read -ra extra_flags <<< "${EXTRA_FLAGS:-}"\n'
    )

    assert check_skip_variable(repo_root=repo) is None


def test_a_recipe_reading_the_fleets_own_skip_idiom_names_its_variable(*, tmp_path: Path) -> None:
    """The positive control: the idiom both consuming repositories write resolves.

    Paired with the two readings above so each of them is a measured ABSENCE
    rather than a reader that answers `None` for everything.
    """
    repo = _a_check_recipe(root=tmp_path / "widget", body=_SKIP_READ)

    assert check_skip_variable(repo_root=repo) == "SKIP_TARGETS"
    assert authority_skip_argv(repo_root=repo) == Success(
        [
            AUTHORITY_SKIP_ENV_FLAG,
            "SKIP_TARGETS",
            AUTHORITY_SKIP_MEMBER_FLAG,
            _AUTHORITY_MEMBER,
        ]
    )


def test_a_recipe_naming_two_skip_variables_is_not_guessed_between(*, tmp_path: Path) -> None:
    """Two different skip variables in one recipe resolve to NEITHER, not to the first.

    This is the half of "every member the authority declaration does not name
    still runs" that a first-match reader loses. A recipe mid-rename, or one
    whose aggregate reads a caller list and a lane list, names two variables; a
    reader that took whichever came first would export the members into the
    WRONG one, which fails twice in one move and announces neither. The member
    that must leave the Job is not in the list the recipe actually skips on, so
    it runs and fails on the absent credential exactly as before — and the
    variable that WAS written is read for something else, so whatever it held is
    clobbered and members that should run may not.

    Naming the SAME variable twice is still one answer, because there is no
    ambiguity to refuse: both reads fill the same list.

    THE AMBIGUOUS REPOSITORY IS REFUSED rather than told nothing, because it
    declares a member this reader then cannot keep out of the Job — the same
    disposition a recipe naming no skip variable at all gets, and for the same
    reason: the member must not run in a pod the contract hands no authority.
    """
    ambiguous = _a_check_recipe(
        root=tmp_path / "widget",
        body=_SKIP_READ + '    read -ra skip_targets <<< "${LIVESPEC_CHECK_SKIP:-}"\n',
    )
    repeated = _a_check_recipe(root=tmp_path / "gadget", body=_SKIP_READ + _SKIP_READ)

    assert check_skip_variable(repo_root=ambiguous) is None
    assert not is_successful(authority_skip_argv(repo_root=ambiguous))
    assert check_skip_variable(repo_root=repeated) == "SKIP_TARGETS"


def test_an_unreadable_authority_declaration_tells_the_job_nothing(*, tmp_path: Path) -> None:
    """A declaration naming no authority this contract knows carries no skip.

    NOT LOST BY THAT. `run_host_authority_members` reads the same registry on the
    pushing host and reports it as the member it names FAILING, which refuses the
    push whatever this Job was told — so the malformed case is reported by the
    half that can say which member and which word, rather than twice in two
    different vocabularies.

    IT STAYS ON THE SUCCESS TRACK for that reason, even though the fixture's
    recipe DOES name a skip variable: nothing was established to carry, so there
    is nothing this resolution could refuse over, and refusing here would report
    a registry typo in the vocabulary of a missing skip surface.
    """
    repo = _a_check_recipe(root=tmp_path / "widget", body=_SKIP_READ)
    _ = (repo / "check-targets.txt").write_text(
        f"{_AUTHORITY_MEMBER}  # purity: world-reading  # authority: ledger\n"
        f"check-widget-approval  # purity: world-reading  # authority: nonsense\n",
        encoding="utf-8",
    )

    assert authority_skip_argv(repo_root=repo) == Success([])
