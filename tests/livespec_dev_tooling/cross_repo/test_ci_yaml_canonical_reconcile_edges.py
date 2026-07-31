"""Green-leg edge for `ci_yaml_canonical_reconcile.py`'s railway conversion.

A `*_edges.py` sibling rather than an addition to
`test_ci_yaml_canonical_reconcile.py`, which is byte-identity-bound to its own
Red commit.

The branch is one the conversion CREATED: an unterminated `targets=(...)` array
used to be indistinguishable from an absent one, so the reconcile skipped with
the `no_targets_array` notice — telling the operator to add an array their
justfile already has. It now skips under its own notice.
"""

from __future__ import annotations

import textwrap

from livespec_dev_tooling.cross_repo.ci_yaml_canonical_reconcile import reconcile_ci_yaml_text

_CI_YAML = textwrap.dedent(
    """\
    jobs:
      checks:
        strategy:
          matrix:
            target:
              - check-aggregate-completeness
    """
)

# `check-aggregate-completeness` IS wired, so the reconcile gets past its
# `no_aggregate` guard, and the `check:` recipe DOES open a targets array —
# it simply never closes it before EOF.
_JUSTFILE_UNTERMINATED = textwrap.dedent(
    """\
    check:
        #!/usr/bin/env bash
        targets=(
          check-aggregate-completeness
          check-alpha
    """
)


def test_unterminated_targets_array_skips_without_adopting_anything() -> None:
    """The reconcile refuses to adopt from a recipe whose array it cannot close.

    Positive control on the fixture: `check-alpha` is canonical and absent from
    the ci.yml matrix, so a reconcile that DID read this justfile's targets
    would insert it. The text coming back unchanged is therefore evidence the
    skip fired, not evidence there was nothing to do.
    """
    reconciled = reconcile_ci_yaml_text(
        ci_yaml_text=_CI_YAML,
        justfile_text=_JUSTFILE_UNTERMINATED,
        canonical_slugs=["check-aggregate-completeness", "check-alpha"],
        world_gates=[],
    )

    assert reconciled == _CI_YAML
    assert "check-alpha" not in reconciled
