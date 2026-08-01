"""Both discovery components are railway-typed — `8o8e` pair B.

Lives in its own file rather than beside the other discovery tests for the
Red-leg reason `test_cli_e2e_railway.py` records: this repo enforces 100%
per-file coverage, and at the RED moment every line AFTER the first failing
assertion is unexecuted and therefore UNCOVERED. Every Red assertion here is
the LAST statement of its test; `test_cli_e2e_discovery.py`'s bare-`dict`
expectations move in the GREEN leg, where they pass again.

## WHAT THIS PINS, AND WHY THE HEADLINE TEST IS THE LAST ONE

`discover_skills` dropped a plugin root it could not read — `if prefix is
None: continue`. That emptied `discovered`, and the time-bomb coverage gate
computes `discovered - fixtured - exempt`, so `set() - anything` is empty and
the FAIL-CLOSED gate reported SATISFIED over a broken install. Not a crash: an
articulate wrong answer, which is this epic's whole subject.

⛔ THE INTUITIVE READING HAS IT BACKWARDS and the tests are ordered to say so.
An empty FIXTURE set alone still fails the gate correctly — `discovered` is
non-empty, so the difference is non-empty. Only the SKILLS drop empties the
minuend. `test_a_broken_plugin_install_no_longer_passes_the_gate_vacuously` is
the one that would have caught the real defect.

⚠️ NO `chmod 000` ANYWHERE HERE: this suite runs as ROOT, where a mode-based
fixture asserts nothing. Unreadability is spelled as a DIRECTORY where a file
is expected (`IsADirectoryError`) or a FILE where a directory is expected
(`NotADirectoryError`) — both `OSError`s that are NOT `FileNotFoundError`,
raised identically for every user. That distinction is load-bearing rather
than cosmetic: `FileNotFoundError` is the ANSWER arm at three of these sites,
so a fixture that conflated them would assert the opposite of the rule.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from test_cli_e2e import _FakeCliRunner, _make_fixture, _make_plugin, _two_skill_config

from livespec_dev_tooling.testing import cli_e2e
from livespec_dev_tooling.testing._cli_e2e_discovery import discover_fixtures, discover_skills

_VENDOR_DIR = Path(cli_e2e.__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []


# ---------------------------------------------------------------------------
# The success track carries the VALUE, not the container.
# ---------------------------------------------------------------------------


def test_discover_skills_carries_the_walk_on_the_success_track(*, tmp_path: Path) -> None:
    """A readable plugin root yields `IOSuccess` CARRYING the prefix→skills map.

    Reading the unwrapped VALUE is the load-bearing half. A conversion that
    hands the CONTAINER on satisfies any assertion that only checks the call
    succeeded — this repo shipped exactly that as `frozenset(IOResult.unwrap())`,
    where `.unwrap()` on an `IOResult` yields an `IO[...]` rather than the payload.
    """
    plugin = _make_plugin(root=tmp_path / "p", name="livespec", skills={"seed": True})

    outcome = discover_skills(plugin_install_dirs=(plugin,))

    assert isinstance(outcome, IOSuccess) and unsafe_perform_io(outcome.unwrap()) == {
        "livespec": ("seed",)
    }, f"a readable plugin root must yield IOSuccess carrying the map; got {outcome!r}"


def test_discover_fixtures_carries_the_load_on_the_success_track(*, tmp_path: Path) -> None:
    """A readable fixtures tree yields `IOSuccess` CARRYING the skill→fixture map."""
    root = tmp_path / "fixtures"
    _make_fixture(root=root, skill="seed", prompt="/livespec:seed", expected=("a.md",))

    outcome = discover_fixtures(fixtures_root=root)

    assert isinstance(outcome, IOSuccess) and set(unsafe_perform_io(outcome.unwrap())) == {
        "seed"
    }, f"a readable fixtures tree must yield IOSuccess carrying the map; got {outcome!r}"


# ---------------------------------------------------------------------------
# The ANSWER arms — an absent tree is not a failure.
# ---------------------------------------------------------------------------


def test_an_absent_fixtures_root_is_an_answer_not_a_failure(*, tmp_path: Path) -> None:
    """No fixtures tree yet is an ordinary state, so it stays on the SUCCESS track.

    The gate still convicts the consequence: `discovered` is non-empty, so
    `discovered - fixtured` is non-empty and the coverage gate fails. Putting
    this on the failure track would report a broken read where there is none.
    """
    outcome = discover_fixtures(fixtures_root=tmp_path / "never-created")

    assert (
        isinstance(outcome, IOSuccess) and unsafe_perform_io(outcome.unwrap()) == {}
    ), f"an absent fixtures root is an ANSWER, not a failure; got {outcome!r}"


def test_a_plugin_without_a_skills_dir_is_an_answer_not_a_failure(*, tmp_path: Path) -> None:
    """A plugin that ships no `skills/` at all discovers zero skills, successfully."""
    plugin_dir = tmp_path / "no-skills-dir"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(json.dumps({"name": "livespec"}), encoding="utf-8")

    outcome = discover_skills(plugin_install_dirs=(plugin_dir,))

    assert isinstance(outcome, IOSuccess) and unsafe_perform_io(outcome.unwrap()) == {
        "livespec": ()
    }, f"an absent skills/ dir is an ANSWER, not a failure; got {outcome!r}"


# ---------------------------------------------------------------------------
# The FAILURE arms — an unread tree is never reported as an empty one.
# ---------------------------------------------------------------------------


def test_a_plugin_root_without_a_manifest_lands_on_the_failure_track(*, tmp_path: Path) -> None:
    """A DECLARED plugin root with no `plugin.json` is a broken install.

    Measured before this was changed rather than assumed safe: all four
    consuming siblings pass exactly ONE directory and each is a real plugin
    root carrying a manifest, so turning the old silent skip into a failure
    breaks no live caller.
    """
    plugin_dir = tmp_path / "no-manifest"
    (plugin_dir / "skills").mkdir(parents=True)

    outcome = discover_skills(plugin_install_dirs=(plugin_dir,))

    assert (
        isinstance(outcome, IOFailure)
        and unsafe_perform_io(outcome.failure()).reason == "manifest-absent"
    ), f"a plugin root with no manifest is a broken install, not zero skills; got {outcome!r}"


def test_an_unreadable_manifest_is_named_apart_from_an_absent_one(*, tmp_path: Path) -> None:
    """`manifest-not-read` and `manifest-absent` are DIFFERENT operator problems.

    `is_file()` then `read_text()` fused them and left a TOCTOU race behind;
    one `try` splits them on `FileNotFoundError` for free.
    """
    plugin_dir = tmp_path / "manifest-is-a-dir"
    (plugin_dir / "plugin.json").mkdir(parents=True)

    outcome = discover_skills(plugin_install_dirs=(plugin_dir,))

    assert (
        isinstance(outcome, IOFailure)
        and unsafe_perform_io(outcome.failure()).reason == "manifest-not-read"
    ), f"an unreadable manifest must not be reported as an absent one; got {outcome!r}"


def test_an_unlistable_skills_dir_is_split_from_an_absent_one(*, tmp_path: Path) -> None:
    """A `skills` that EXISTS and cannot be listed is a failure, not zero skills."""
    plugin_dir = tmp_path / "skills-is-a-file"
    plugin_dir.mkdir()
    _ = (plugin_dir / "plugin.json").write_text(json.dumps({"name": "livespec"}), encoding="utf-8")
    _ = (plugin_dir / "skills").write_text("not a directory", encoding="utf-8")

    outcome = discover_skills(plugin_install_dirs=(plugin_dir,))

    assert (
        isinstance(outcome, IOFailure)
        and unsafe_perform_io(outcome.failure()).reason == "skills-dir-not-listed"
    ), f"an unlistable skills/ dir must not read as an absent one; got {outcome!r}"


def test_an_unlistable_fixtures_root_is_split_from_an_absent_one(*, tmp_path: Path) -> None:
    """The fixtures-root half of the same split `is_dir()` used to fuse."""
    root = tmp_path / "root-is-a-file"
    _ = root.write_text("not a directory", encoding="utf-8")

    outcome = discover_fixtures(fixtures_root=root)

    assert (
        isinstance(outcome, IOFailure)
        and unsafe_perform_io(outcome.failure()).reason == "fixtures-root-not-listed"
    ), f"an unlistable fixtures root must not read as an absent one; got {outcome!r}"


def test_an_unreadable_prompt_is_a_value_not_a_raised_oserror(*, tmp_path: Path) -> None:
    """The `read_text` was UNCAUGHT, so it raised out of a function annotated `dict`.

    That is livespec v179 clause (a) — the conviction is the raise itself,
    whichever flavour it wears.
    """
    root = tmp_path / "fixtures"
    (root / "seed" / "prompt.md").mkdir(parents=True)

    outcome = discover_fixtures(fixtures_root=root)

    assert (
        isinstance(outcome, IOFailure)
        and unsafe_perform_io(outcome.failure()).reason == "prompt-not-read"
    ), f"an unreadable prompt.md must flow as a value, not raise; got {outcome!r}"


def test_an_unreadable_expected_files_is_split_from_an_absent_one(*, tmp_path: Path) -> None:
    """An ABSENT `expected_files.txt` means no assertions; an unreadable one is broken."""
    root = tmp_path / "fixtures"
    seed = root / "seed"
    seed.mkdir(parents=True)
    _ = (seed / "prompt.md").write_text("/livespec:seed", encoding="utf-8")
    (seed / "expected_files.txt").mkdir()

    outcome = discover_fixtures(fixtures_root=root)

    assert (
        isinstance(outcome, IOFailure)
        and unsafe_perform_io(outcome.failure()).reason == "expected-files-not-read"
    ), f"an unreadable expected_files.txt must not read as an absent one; got {outcome!r}"


# ---------------------------------------------------------------------------
# THE HEADLINE — the vacuous pass the whole conversion exists to remove.
# ---------------------------------------------------------------------------


def test_a_broken_plugin_install_no_longer_passes_the_gate_vacuously(*, tmp_path: Path) -> None:
    """A plugin root that could not be READ must not produce a PASSING round trip.

    ⛔ THIS IS THE ONE THAT WOULD HAVE CAUGHT THE DEFECT. Before the conversion
    the unreadable root was dropped, `discovered` was empty, the fail-closed
    coverage gate computed `set() - anything` = empty and reported SATISFIED,
    zero steps ran, and the harness returned a PASSING `WorkflowResult`. Every
    signal was green and nothing had been exercised.

    The assertion reads the failure's `reason` rather than merely checking that
    a `Failure` came back: a round trip that failed for some OTHER reason would
    satisfy the weaker form and prove nothing about the gate.
    """
    broken = tmp_path / "broken-install"
    (broken / "skills" / "seed").mkdir(parents=True)
    _ = (broken / "skills" / "seed" / "SKILL.md").write_text("# seed\n", encoding="utf-8")
    fixtures_root = tmp_path / "fixtures"
    _make_fixture(root=fixtures_root, skill="seed", prompt="/seed", expected=())

    outcome = cli_e2e.test_workflow_full_round_trip(
        config=_two_skill_config(plugin=broken, fixtures_root=fixtures_root),
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
        injected_runner=_FakeCliRunner(creates={}),
    )

    assert (
        isinstance(outcome, Failure) and outcome.failure().reason == "manifest-absent"
    ), f"an unreadable plugin root must fail the round trip, not satisfy it; got {outcome!r}"
