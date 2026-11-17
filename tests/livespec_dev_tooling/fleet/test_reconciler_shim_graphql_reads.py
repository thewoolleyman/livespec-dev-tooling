"""The reconciler reads a pull request's head, node id and opener without the REST diff computation.

REST `GET repos/<repo>/pulls/<n>` computes diff stats and answers a transient 422
"too many files changed" right after a force-push (measured on
livespec-dev-tooling#4889). The reconciler needs three scalars from a pull
request: the revert's head sha and the culprit's node id (both read through
GraphQL, which returns the current value without the diff computation) and the
reverted pull request's author login (read through `issues/<n>`, because
GraphQL's author login drops the `[bot]` suffix REST carries).
"""

from __future__ import annotations

import re

from livespec_dev_tooling.fleet._reconciler_shim import REUSABLE_RECONCILER_BODY

_HEAD_QUERY = re.compile(
    r"revert_head=\$\(gh api graphql -f query='[^']*pullRequest\(number: \$number\) \{ headRefOid \}"
    r"[^']*' -f owner=\"\$\{REPO%%/\*\}\" -f name=\"\$\{REPO##\*/\}\" -F number=\"\$\{revert_number\}\"(?: \\\n\s*| )"
    r"--jq '\.data\.repository\.pullRequest\.headRefOid // empty'\)\n\s*test -n \"\$\{revert_head\}\""
)
_NODE_QUERY = re.compile(
    r"pr_node=\$\(gh api graphql -f query='[^']*pullRequest\(number: \$number\) \{ id \}"
    r"[^']*' -f owner=\"\$\{REPO%%/\*\}\" -f name=\"\$\{REPO##\*/\}\" -F number=\"\$\{culprit\}\"(?: \\\n\s*| )"
    r"--jq '\.data\.repository\.pullRequest\.id // empty'\)\n\s*test -n \"\$\{pr_node\}\""
)


def test_the_revert_head_is_read_through_graphql_and_fails_closed_when_empty():
    assert _HEAD_QUERY.search(REUSABLE_RECONCILER_BODY) is not None
    assert 'pulls/${revert_number}"' not in REUSABLE_RECONCILER_BODY


def test_the_culprit_node_id_is_read_through_graphql_and_fails_closed_when_empty():
    assert _NODE_QUERY.search(REUSABLE_RECONCILER_BODY) is not None
    assert 'pulls/${culprit}"' not in REUSABLE_RECONCILER_BODY


def test_the_reverted_pull_request_opener_is_read_through_the_issues_endpoint():
    assert (
        "culprit_opener=$(gh api \"repos/${REPO}/issues/${reverted}\" --jq '.user.login')"
        in REUSABLE_RECONCILER_BODY
    )
    assert 'pulls/${reverted}"' not in REUSABLE_RECONCILER_BODY
