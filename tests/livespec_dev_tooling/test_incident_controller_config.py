"""Protected controller configuration rejects unsafe branch and freshness values."""

from __future__ import annotations

import pytest

from livespec_dev_tooling import incident_controller_config as module


@pytest.mark.parametrize("name", ["master", "repair/one", "v1.2-3"])
def test_plain_branch_names_are_accepted(name):
    assert module.valid_branch_name(name=name)


@pytest.mark.parametrize("name", ["", 3, "-x", "a..b", "a b", "/lead", "trail/", "x.lock"])
def test_non_plain_branch_names_are_refused(name):
    assert not module.valid_branch_name(name=name)


@pytest.mark.parametrize("value", [0, 1, 240])
def test_nonnegative_integer_freshness_bounds_are_accepted(value):
    assert module.valid_freshness_bound(value=value)


@pytest.mark.parametrize("value", [True, -1, "50", None])
def test_noninteger_or_negative_freshness_bounds_are_refused(value):
    assert not module.valid_freshness_bound(value=value)
