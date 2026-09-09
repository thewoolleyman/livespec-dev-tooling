"""The batched reconcile agrees with its own gate, and never double-writes.

A sibling of `test_ci_yaml_canonical_reconcile.py` rather than an addition to
it, following the `_edges.py` precedent: that file is byte-identity-bound to
its own Red commit.

Two properties, both about the BATCHED write target (`batch_anchor`), which the
main suite exercises for placement and spelling but never against the gate it
feeds:

- **Writer/gate parity.** The reconcile's whole reason to exist is that what it
  WRITES satisfies what `check-ci-matrix-completeness` DEMANDS. The main suite
  asserts the written text's shape; this asserts the property directly, by
  running `_ci_matrix_evaluate.evaluate` over the reconciled text with the
  same wired set and requiring NO findings. Asserting the shape alone trusts
  the shared parser to be the whole story — and the one time this pair drifted,
  it drifted for a reason no shape assertion would have caught: the writer read
  the justfile `targets=(...)` array while the gate resolved `check-targets.txt`
  first, so each was internally consistent and they disagreed on three fleet
  consumers.
- **No double-write in the batched shape.** A slug already covered by a
  DEDICATED job's own run line (the full-history `check-red-green-replay`
  shape) must not be mirrored into the batch block as well — it would run the
  check twice per PR. The main suite covers this for a MATRIX consumer; the
  batched consumer takes a different code path to the same coverage union, so
  it is asserted separately here.
"""

from __future__ import annotations

import textwrap

from livespec_dev_tooling.checks._ci_matrix_evaluate import evaluate
from livespec_dev_tooling.checks._ci_matrix_parse import parse_ci_jobs
from livespec_dev_tooling.cross_repo.ci_yaml_canonical_reconcile import reconcile_ci_yaml_text

__all__: list[str] = []

# A batched consumer: no `strategy.matrix.target:` list anywhere, the aggregate
# invoked from an accumulator run line. This is the shape livespec-overseer and
# this repo's OWN ci.yml carry.
_BATCHED_CI_YAML = textwrap.dedent(
    """\
    name: CI
    on: [push]

    jobs:
      metadata:
        runs-on: ubuntu-latest
        steps:
          - name: Run the batched metadata checks
            run: |
              failed=""
              just check-aggregate-completeness || failed="$failed check-aggregate-completeness"
              just check-wrapper-shape || failed="$failed check-wrapper-shape"
              if [ -n "$failed" ]; then exit 1; fi

      ci-green:
        needs: [metadata]
        runs-on: ubuntu-latest
        steps:
          - run: echo green
    """
)

_JUSTFILE = textwrap.dedent(
    """\
    check:
        targets=(
            check-aggregate-completeness
            check-new-thing
            check-wrapper-shape
        )
    """
)

_CANONICAL = ("check-aggregate-completeness", "check-new-thing", "check-wrapper-shape")


def test_batched_reconcile_satisfies_the_gate_it_feeds() -> None:
    """After reconciling, `evaluate` reports NO findings over the SAME wired set.

    The property the module exists to hold, asserted against the gate itself
    rather than against the written text's shape.
    """
    reconciled = reconcile_ci_yaml_text(
        ci_yaml_text=_BATCHED_CI_YAML,
        justfile_text=_JUSTFILE,
        canonical_slugs=_CANONICAL,
        world_gates=(),
    )
    assert "check-new-thing" in reconciled, "precondition: the slug must have been mirrored"

    findings = evaluate(
        canonical=_CANONICAL,
        world_gates=frozenset(),
        justfile_targets=list(_CANONICAL),
        jobs=parse_ci_jobs(source=reconciled),
    )
    assert findings == [], f"the reconciled ci.yml must satisfy its own gate: {findings}"


def test_gate_convicts_the_same_fixture_before_the_reconcile() -> None:
    """The parity assertion above is not vacuous: unreconciled, the gate CONVICTS.

    Without this control a writer that changed nothing would pass the parity
    test, because the finding it must clear would never have existed.
    """
    findings = evaluate(
        canonical=_CANONICAL,
        world_gates=frozenset(),
        justfile_targets=list(_CANONICAL),
        jobs=parse_ci_jobs(source=_BATCHED_CI_YAML),
    )
    assert [f.failure_mode for f in findings] == ["ci-matrix-missing-aggregate-slug"]


def test_batched_consumer_never_double_writes_a_dedicated_jobs_slug() -> None:
    """A slug covered by a dedicated job is NOT also inserted into the batch block.

    `check-red-green-replay` runs full-history in its own job, so the coverage
    union already holds it. Mirroring it into the batch too would run it twice
    per PR — and the batched consumer reaches that union by a different path
    than the matrix consumer the main suite covers.
    """
    text = _BATCHED_CI_YAML.replace(
        "  ci-green:\n    needs: [metadata]",
        "  red-green-replay:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: just check-red-green-replay\n"
        "\n"
        "  ci-green:\n"
        "    needs: [metadata, red-green-replay]",
    )
    assert "red-green-replay:" in text, "precondition: the dedicated job must have been spliced in"
    # The dedicated job's slug is the ONLY wiring candidate, so a correct
    # reconcile has nothing at all to do and the text must come back untouched.
    justfile = textwrap.dedent(
        """\
        check:
            targets=(
                check-aggregate-completeness
                check-red-green-replay
                check-wrapper-shape
            )
        """
    )
    reconciled = reconcile_ci_yaml_text(
        ci_yaml_text=text,
        justfile_text=justfile,
        canonical_slugs=(
            "check-aggregate-completeness",
            "check-red-green-replay",
            "check-wrapper-shape",
        ),
        world_gates=(),
    )
    assert reconciled == text, "an already-covered slug must leave the ci.yml byte-identical"
    assert reconciled.count("just check-red-green-replay") == 1, "must not run twice per PR"
