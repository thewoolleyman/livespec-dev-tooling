"""Which controller routes a query credential reaches and which need the control credential."""

from __future__ import annotations

from livespec_dev_tooling import incident_enablement as enable
from livespec_dev_tooling.incident_observer_query import ORDINARY_ACTION_PATH
from livespec_dev_tooling.incident_release_screen import RELEASE_SCREEN_PATH

__all__: list[str] = ["CONTROL_PATHS", "PUBLISH_PATH", "QUERY_PATHS"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-qmuk7z
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
QUERY_PATHS = (
    frozenset({"/current", "/admitted", "/provenance", "/ci/jobs/inspect", RELEASE_SCREEN_PATH})
    | {ORDINARY_ACTION_PATH}
    | enable.QUERY_PATHS
)
CONTROL_PATHS = (
    frozenset({"/arm", "/bind", "/invalidate-ci", "/recover", "/reconcile", "/ci/jobs/collect"})
    | enable.CONTROL_PATHS
)
# Neither credential reaches it: an incident CI job's PASSED aggregate, authenticated by
# the job's own forge-issued OIDC identity token exactly as a CI attachment is.
PUBLISH_PATH = "/ci/publish"
