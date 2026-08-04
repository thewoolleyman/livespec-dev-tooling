"""_cli_parser — the `fleet-conformance` argument parser.

Extracted from `fleet_conformance.py` verbatim. Pure CLI surface
construction with no behavior of its own: it is here so the entry-point
module carries the run logic rather than the flag inventory, and so that
module stays under the 250-LLOC hard ceiling it had reached.
"""

from __future__ import annotations

import argparse
from pathlib import Path

__all__: list[str] = []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleet-conformance",
        description=(
            "Central fleet-membership conformance check (livespec v108 "
            '§"Fleet membership contract").'
        ),
    )
    _ = parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner override; defaults to the origin remote's owner.",
    )
    _ = parser.add_argument(
        "--emit-member-verdicts",
        type=Path,
        default=None,
        help="Write per-member conformance verdicts as JSON to this path.",
    )
    _ = parser.add_argument(
        "--member-ci",
        action="store_true",
        help=(
            "Declare this run as a MEMBER's own CI leg: every member is still "
            "evaluated and reported, but only the running member's violations "
            "affect the exit status. Omit it for the fleet-level legs (the "
            "scheduled sweep, the release fan-out preflight), which fail on ANY "
            "member. Not a severity lever: no obligation is relaxed and no row "
            "stops being evaluated."
        ),
    )
    return parser
