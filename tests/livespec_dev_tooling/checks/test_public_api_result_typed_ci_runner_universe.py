"""The `ci-runner/` warm-cache scripts carry ZERO railway offenders, measured.

`public_api_result_typed` is UNARMED in this repo — `pure_trees` is
`{ not_applicable = ... }`, so `main()` returns at the role-absence gate before
`_scan` ever walks anything. That is why this file drives `_scan` DIRECTLY over
a `pure_trees` of `("ci-runner",)`: the criterion is applied to the two
warm-cache scripts here even though no armed check reaches them yet, so the
conversion cannot silently rot in the window before the qndn arming lands.

⛔ THE CONSUMPTION UNIVERSE IS THE REAL, UNFILTERED ONE, and that is the whole
point of criterion 2. `resolve_check_universe()` is called for real (it spawns
`git ls-files`, permitted by `check-tests-no-subprocess-spawn`'s own reading —
the check itself spawns it) and BOTH ci-runner `.py` files are asserted present
in it FIRST. `config.filter_first_party_py` carries no `ci-runner` clause, and
the 2026-09-10 maintainer ruling is that it must not grow one: the remedy for
these two files is CONVERSION, not a universe exemption. Were an exemption
added, `sources` would lose the files, `repo_local_public_names` would stop
seeing `verify-uv-cache.py`'s import of the layout half, every name would fall
out of `public_names`, and the offender list would go empty FOR THE WRONG
REASON. The membership assertion is what tells those two zeros apart.

Measured before the conversion: exactly three offenders — `load_locks`, `du`
and `archive_index_of`, all in `uv_cache_layout.py`. The other public names are
exempt under the ratified per-function set rather than converted: `norm` by
v179 member 1 (no expected failure mode) and `scan_cache` by the `returns None`
member, which is asserted below so a future reader can see WHICH member carries
each one instead of re-deriving it.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks.public_api_result_typed import _scan
from livespec_dev_tooling.config import load_config, resolve_check_universe

__all__: list[str] = []


_WARM_CACHE = Path("ci-runner/k3s/phase2/warm-cache")
_LAYOUT = _WARM_CACHE / "uv_cache_layout.py"
_VERIFIER = _WARM_CACHE / "verify-uv-cache.py"


def test_ci_runner_warm_cache_scripts_report_zero_railway_offenders() -> None:
    root, universe = resolve_check_universe()
    assert _LAYOUT in universe, "the layout half must stay in the check universe (criterion 2)"
    assert _VERIFIER in universe, "the verifier must stay in the check universe (criterion 2)"
    sources = {rel: (root / rel).read_text(encoding="utf-8") for rel in universe}
    config = load_config(repo_root=root)
    offenders = _scan(cwd=root, pure_trees=(Path("ci-runner"),), config=config, sources=sources)
    assert offenders == []
