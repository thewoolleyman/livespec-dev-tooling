"""Outside-in test for `cross_repo/ci_yaml_canonical_reconcile.py`.

The module is the ci.yml sibling of `justfile_canonical_reconcile`: during the
`bump-pin-rewrite` composite Action it inserts every newly-adopted canonical
check slug into the consumer's `.github/workflows/ci.yml`
`strategy.matrix.target:` list — the one that ALREADY carries
`check-aggregate-completeness` — so the same bump commit that grows the
canonical set also grows CI's mirror of it.

The load-bearing defect this suite guards: the composite Action reconciled the
`justfile` ONLY. `check-ci-matrix-completeness` asserts the canonical slugs CI
RUNS are a superset of the canonical slugs the `justfile` `check:` aggregate
WIRES, so a bump that legitimately adopted a new canonical slug into the
justfile aggregate left CI's hand-maintained matrix short that entry — the bump
PR was red by construction, on a check whose diagnosis was correct.

The reconcile's slug arithmetic MIRRORS `ci_matrix_completeness._evaluate` (it
shares that check's `_ci_matrix_parse` parsers, so the written matrix and the
gate's expectation cannot drift): a slug is required when the justfile aggregate
wires it AND it is canonical AND it is not a WORLD GATE, and it is already
covered when ANY job runs it — via its own `strategy.matrix.target` list or via
a `just check-<slug>` run line (the dedicated full-history
`check-red-green-replay` job).

Coverage target: 100% line + branch of `ci_yaml_canonical_reconcile.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from livespec_dev_tooling.cross_repo import ci_yaml_canonical_reconcile

__all__: list[str] = []


# ---------------------------------------------------------------------------
# Fixtures — a representative consumer justfile + ci.yml pair.
# ---------------------------------------------------------------------------

# The consumer `check:` aggregate AFTER the sibling justfile reconcile has run:
# it already wires every canonical slug, including the newly-released
# `check-new-thing` and the world-gate `check-master-ci-green`.
_JUSTFILE = """check:
    targets=(
        check-aggregate-completeness
        check-all-declared
        check-master-ci-green
        check-new-thing
        check-red-green-replay
        check-wrapper-shape
    )
"""

# The consumer ci.yml BEFORE the reconcile. Four jobs exercise every arm of the
# coverage arithmetic: a non-matrix `setup` job (contributes nothing), the
# anchor matrix job (carries `check-aggregate-completeness` plus a trailing
# non-canonical repo-private extra and an interleaved comment), a dedicated
# full-history `check-red-green-replay` job (covers a canonical slug via a
# `just` RUN LINE rather than the matrix), and the `ci-green` fan-in gate.
_CI_YAML = """name: CI

on:
  pull_request:

jobs:
  setup:
    runs-on: ubuntu-latest
    steps:
      - run: echo setup

  checks:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        target:
          - check-aggregate-completeness
          - check-all-declared
          # An interleaved comment inside the target list.
          - check-wrapper-shape
          # Repo-private extras (non-canonical).
          - check-lint
    steps:
      - run: just ${{ matrix.target }}

  red-green-replay:
    runs-on: ubuntu-latest
    steps:
      - run: just check-red-green-replay

  ci-green:
    needs: [setup, checks, red-green-replay]
    runs-on: ubuntu-latest
    steps:
      - run: echo green
"""

# A consumer carrying TWO matrix jobs — the common fleet shape (a `.py`-gated
# matrix plus an unconditional metadata matrix). Only the SECOND carries
# `check-aggregate-completeness`, so only the second is the anchor. Its target
# list is also the last thing in the file, so the entry scan ends by exhaustion
# rather than on a following key.
_CI_YAML_TWO_MATRICES = """name: CI

jobs:
  py-checks:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        target:
          - check-all-declared
    steps:
      - run: just ${{ matrix.target }}

  metadata-checks:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        target:
          - check-aggregate-completeness
          - check-wrapper-shape
"""

_CANONICAL = (
    "check-aggregate-completeness",
    "check-all-declared",
    "check-master-ci-green",
    "check-new-thing",
    "check-red-green-replay",
    "check-wrapper-shape",
)
_WORLD_GATES = ("check-master-ci-green",)


def _bullet_order(*, text: str) -> list[str]:
    """Return the ordered `matrix.target:` bullet tokens of the reconciled ci.yml.

    A lone `- check-<slug>` bullet only. The dedicated job's `- run: just
    check-red-green-replay` step is NOT a matrix bullet and never appears here —
    which is exactly the point: that slug is CI-covered by the run line, so it
    must never be duplicated into the matrix.
    """
    return re.findall(r"^\s+-\s+(check-[\w-]+)\s*$", text, re.MULTILINE)


# ---------------------------------------------------------------------------
# reconcile_ci_yaml_text — the slug arithmetic + insertion position.
# ---------------------------------------------------------------------------


def test_newly_adopted_slug_lands_alphabetically_in_the_anchor_matrix() -> None:
    """The one genuinely-missing canonical slug is inserted; nothing else is.

    `check-new-thing` is wired in the justfile aggregate, is canonical, is not a
    world gate, and no job runs it — the exact set `check-ci-matrix-completeness`
    would flag. It must land in the anchor matrix in alphabetical position
    (after `check-all-declared`, before `check-wrapper-shape`).

    The three slugs that must NOT be added, each for a different reason:
    `check-master-ci-green` (a WORLD GATE the check subtracts from its
    assertion — running it in per-PR CI would deadlock every PR while master is
    red), `check-red-green-replay` (already covered by a `just` run line in its
    own dedicated job — re-adding it to the matrix would run it a second time in
    a job without the full history it needs), and `check-lint` (non-canonical, a
    repo-private extra that must stay put at the tail of the list).
    """
    result = ci_yaml_canonical_reconcile.reconcile_ci_yaml_text(
        ci_yaml_text=_CI_YAML,
        justfile_text=_JUSTFILE,
        canonical_slugs=_CANONICAL,
        world_gates=_WORLD_GATES,
    )
    assert _bullet_order(text=result) == [
        "check-aggregate-completeness",
        "check-all-declared",
        "check-new-thing",
        "check-wrapper-shape",
        "check-lint",
    ], "the missing canonical slug must land alphabetically inside the anchor matrix only"
    # The new entry lands ABOVE the comment block that annotates the entry it
    # sorts before — never between that comment and the entry it describes.
    # These consumer ci.yml files are hand-maintained and human-reviewed, and a
    # bump PR merges this insertion into master permanently: an entry wedged
    # under someone else's comment is a durable misattribution, not a transient
    # diff artifact. The inserted bullet also carries the list's own indent, so
    # the YAML still parses.
    assert (
        "          - check-all-declared\n"
        "          - check-new-thing\n"
        "          # An interleaved comment inside the target list.\n"
        "          - check-wrapper-shape\n"
    ) in result, "the inserted entry must not separate a comment from the entry it annotates"
    # The dedicated full-history job's run line is left as the sole coverage of
    # check-red-green-replay.
    assert "- run: just check-red-green-replay" in result
    # The repo-private extras comment survives too.
    assert "# Repo-private extras (non-canonical)." in result


def test_slug_sorting_last_lands_after_the_final_canonical_entry() -> None:
    """A slug sorting after every wired canonical token lands after the last one.

    It must NOT be appended after the trailing non-canonical `check-lint` extra:
    non-canonical tokens are never sort anchors, so the canonical block stays
    contiguous.
    """
    result = ci_yaml_canonical_reconcile.reconcile_ci_yaml_text(
        ci_yaml_text=_CI_YAML,
        justfile_text="check:\n    targets=(\n        check-aggregate-completeness\n"
        "        check-all-declared\n        check-wrapper-shape\n"
        "        check-zebra\n    )\n",
        canonical_slugs=(
            "check-aggregate-completeness",
            "check-all-declared",
            "check-wrapper-shape",
            "check-zebra",
        ),
        world_gates=(),
    )
    assert _bullet_order(text=result) == [
        "check-aggregate-completeness",
        "check-all-declared",
        "check-wrapper-shape",
        "check-zebra",
        "check-lint",
    ]


def test_anchor_without_canonical_tokens_inserts_at_the_list_head() -> None:
    """With no canonical sort anchor in the list, the slug lands at the list head.

    A defensive branch mirroring the justfile reconcile: the canonical set here
    names NONE of the tokens already in the anchor matrix (not even the
    aggregate slug, which the justfile still carries — that is what makes the
    list reconcilable at all), so there is no canonical entry to sort against and
    the slug goes to the head of the list.
    """
    result = ci_yaml_canonical_reconcile.reconcile_ci_yaml_text(
        ci_yaml_text=_CI_YAML,
        justfile_text="check:\n    targets=(\n        check-aggregate-completeness\n"
        "        check-new-thing\n    )\n",
        canonical_slugs=("check-new-thing",),
        world_gates=(),
    )
    assert _bullet_order(text=result) == [
        "check-new-thing",
        "check-aggregate-completeness",
        "check-all-declared",
        "check-wrapper-shape",
        "check-lint",
    ]


def test_only_the_matrix_carrying_the_aggregate_slug_is_touched() -> None:
    """With two matrix jobs, the slug lands in the aggregate-carrying one only.

    The fleet's common ci.yml shape is a `.py`-gated matrix plus an unconditional
    metadata matrix; a matrix that does not carry `check-aggregate-completeness`
    is not the mirror of the `just check` aggregate and is left alone. This
    fixture also ends the anchor's target list at end-of-file, so the entry scan
    terminates by exhaustion rather than on a following YAML key.
    """
    result = ci_yaml_canonical_reconcile.reconcile_ci_yaml_text(
        ci_yaml_text=_CI_YAML_TWO_MATRICES,
        justfile_text=_JUSTFILE,
        canonical_slugs=_CANONICAL,
        world_gates=_WORLD_GATES,
    )
    assert _bullet_order(text=result) == [
        # The non-anchor matrix is untouched — check-all-declared already covers
        # its canonical slug from here, and nothing new is added to it.
        "check-all-declared",
        # The anchor matrix adopts both slugs CI does not yet run.
        "check-aggregate-completeness",
        "check-new-thing",
        "check-red-green-replay",
        "check-wrapper-shape",
    ]


def test_nothing_missing_is_a_noop() -> None:
    """When CI already covers every required slug, the ci.yml is byte-identical."""
    result = ci_yaml_canonical_reconcile.reconcile_ci_yaml_text(
        ci_yaml_text=_CI_YAML,
        justfile_text=_JUSTFILE,
        canonical_slugs=("check-aggregate-completeness", "check-all-declared"),
        world_gates=(),
    )
    assert result == _CI_YAML


# ---------------------------------------------------------------------------
# reconcile_ci_yaml_text — the non-reconcilable justfile shapes (skip branches).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "justfile_text",
    [
        pytest.param("check-lint:\n    uv run ruff check .\n", id="no-aggregate-slug"),
        pytest.param(
            "check-aggregate-completeness:\n    uv run python -m x\n", id="no-bare-check-recipe"
        ),
        pytest.param("check:\n    just check-aggregate-completeness\n", id="no-targets-array"),
    ],
)
def test_non_reconcilable_justfile_shapes_return_ci_yaml_unchanged(*, justfile_text: str) -> None:
    """A justfile the aggregate gate itself cannot read leaves the ci.yml untouched.

    `check-ci-matrix-completeness` emits a PRECONDITION finding (not a
    missing-slug finding) for each of these shapes, so there is no slug the
    reconcile could correctly add.
    """
    result = ci_yaml_canonical_reconcile.reconcile_ci_yaml_text(
        ci_yaml_text=_CI_YAML,
        justfile_text=justfile_text,
        canonical_slugs=_CANONICAL,
        world_gates=_WORLD_GATES,
    )
    assert result == _CI_YAML


def test_ci_yaml_without_an_anchor_matrix_is_returned_unchanged() -> None:
    """With slugs to add but no anchor matrix, the pure core returns the input unchanged.

    `main()` turns this state into a `::error::` + non-zero exit rather than
    committing a ci.yml that is red by construction; the pure core just declines
    to guess where the entries belong.
    """
    ci_yaml = "name: CI\n\njobs:\n  lint:\n    steps:\n      - run: just check-lint\n"
    result = ci_yaml_canonical_reconcile.reconcile_ci_yaml_text(
        ci_yaml_text=ci_yaml,
        justfile_text=_JUSTFILE,
        canonical_slugs=_CANONICAL,
        world_gates=_WORLD_GATES,
    )
    assert result == ci_yaml


# ---------------------------------------------------------------------------
# main() — the IO + `::notice::` / `::error::` surface.
# ---------------------------------------------------------------------------


def _seed(*, root: Path, justfile_text: str, ci_yaml_text: str | None) -> Path:
    """Write a consumer justfile (+ optional ci.yml) into `root`; return the ci.yml path."""
    (root / "justfile").write_text(justfile_text, encoding="utf-8")
    ci_yaml = root / ".github" / "workflows" / "ci.yml"
    if ci_yaml_text is not None:
        ci_yaml.parent.mkdir(parents=True)
        ci_yaml.write_text(ci_yaml_text, encoding="utf-8")
    return ci_yaml


def test_main_no_justfile_emits_skip_notice(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no cwd justfile, main() emits the skip notice and exits 0."""
    monkeypatch.chdir(tmp_path)
    assert ci_yaml_canonical_reconcile.main() == 0
    assert "::notice::no justfile found" in capsys.readouterr().out


def test_main_no_ci_yaml_emits_skip_notice(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A consumer with no `.github/workflows/ci.yml` runs no CI, so there is nothing to gate."""
    _ = _seed(root=tmp_path, justfile_text=_JUSTFILE, ci_yaml_text=None)
    monkeypatch.chdir(tmp_path)
    assert ci_yaml_canonical_reconcile.main() == 0
    assert "::notice::no .github/workflows/ci.yml found" in capsys.readouterr().out


def test_main_skips_non_aggregate_justfile_unchanged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A justfile without the aggregate slug leaves the ci.yml byte-identical."""
    ci_yaml = _seed(
        root=tmp_path,
        justfile_text="check-lint:\n    uv run ruff check .\n",
        ci_yaml_text=_CI_YAML,
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANONICAL_JSON", '{"slugs": ["check-new-thing"]}')
    assert ci_yaml_canonical_reconcile.main() == 0
    assert "consumer does not carry check-aggregate-completeness" in capsys.readouterr().out
    assert ci_yaml.read_text(encoding="utf-8") == _CI_YAML


def test_main_reconciles_and_writes_ci_yaml(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() rewrites ci.yml in place and names the reconciled slug in a notice.

    The `CANONICAL_JSON` payload carries a non-string element (`123`) alongside
    the string slugs to exercise the defensive `isinstance(s, str)` filter, and
    `check-master-ci-green` to prove the LIVE world-gate registry (not a test
    double) is what `main()` subtracts.
    """
    ci_yaml = _seed(root=tmp_path, justfile_text=_JUSTFILE, ci_yaml_text=_CI_YAML)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "CANONICAL_JSON",
        '{"slugs": ["check-aggregate-completeness", "check-master-ci-green", '
        '"check-new-thing", "check-red-green-replay", 123]}',
    )
    assert ci_yaml_canonical_reconcile.main() == 0
    assert "reconciled canonical CI matrix wiring for: check-new-thing" in capsys.readouterr().out
    written = ci_yaml.read_text(encoding="utf-8")
    assert "\n          - check-new-thing\n" in written
    # The live world gate is never mirrored into the per-PR matrix...
    assert _bullet_order(text=written).count("check-master-ci-green") == 0
    # ...and the run-line-covered slug is never duplicated into it either.
    assert _bullet_order(text=written).count("check-red-green-replay") == 0
    assert "- run: just check-red-green-replay" in written


def test_main_already_current_emits_notice_without_write(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When CI already runs every required slug, main() writes nothing."""
    ci_yaml = _seed(root=tmp_path, justfile_text=_JUSTFILE, ci_yaml_text=_CI_YAML)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANONICAL_JSON", '{"slugs": ["check-aggregate-completeness"]}')
    assert ci_yaml_canonical_reconcile.main() == 0
    assert "canonical CI matrix wiring already current" in capsys.readouterr().out
    assert ci_yaml.read_text(encoding="utf-8") == _CI_YAML


def test_main_non_dict_payload_yields_empty_canonical_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-dict `CANONICAL_JSON` payload defensively yields an empty slug set (no reconcile)."""
    ci_yaml = _seed(root=tmp_path, justfile_text=_JUSTFILE, ci_yaml_text=_CI_YAML)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANONICAL_JSON", "[]")
    assert ci_yaml_canonical_reconcile.main() == 0
    assert "canonical CI matrix wiring already current" in capsys.readouterr().out
    assert ci_yaml.read_text(encoding="utf-8") == _CI_YAML


def test_main_missing_anchor_matrix_errors_naming_the_exact_lines(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No anchor matrix + slugs to add ⇒ a `::error::` naming the lines, and a NON-ZERO exit.

    Failing the bump job loudly is the whole point: opening a PR whose CI matrix
    is knowably short an entry `check-ci-matrix-completeness` will demand is
    opening a PR that is red by construction. The annotation carries the exact
    YAML bullet lines a maintainer must paste in.
    """
    ci_yaml = _seed(
        root=tmp_path,
        justfile_text=_JUSTFILE,
        ci_yaml_text="name: CI\n\njobs:\n  lint:\n    steps:\n      - run: just check-lint\n",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "CANONICAL_JSON",
        '{"slugs": ["check-aggregate-completeness", "check-new-thing"]}',
    )
    assert ci_yaml_canonical_reconcile.main() == 1
    out = capsys.readouterr().out
    assert out.startswith("::error::")
    assert "strategy.matrix.target" in out
    assert "- check-new-thing" in out
    # The file is left untouched — a half-reconciled ci.yml is never committed.
    assert "check-new-thing" not in ci_yaml.read_text(encoding="utf-8")
