# herdr tabs: create appends at the end; move them with the socket API

`herdr tab create` puts the new tab at the END of the workspace's tab list.
When a maintainer asks for a tab "to the right of" another tab, that is not
where it lands.

herdr CAN reorder tabs, but not through the CLI. The installed `herdr tab` CLI
offers only `list`, `create`, `get`, `focus`, `rename` and `close`. The socket
API has `tab.move`, plus `pane.move` and `workspace.move`; see
`herdr api schema --json`, definition `TabMoveParams`. On 2026-10-26 a session
read only the CLI help, twice told the maintainer that herdr had no move
command, and was corrected.

## How to place a tab right of the calling tab

1. Read the order: `herdr tab list --workspace "$HERDR_WORKSPACE_ID"`. The array
   order is the display order; find the index of `$HERDR_TAB_ID`.
2. Create the tab: `herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd <dir> --label <label> --no-focus`.
3. Send one JSON line to the socket:

   ```python
   import json, os, socket
   s = socket.socket(socket.AF_UNIX); s.connect(os.environ["HERDR_SOCKET_PATH"])
   s.sendall((json.dumps({"id": "move1", "method": "tab.move",
                          "params": {"tab_id": "<new tab id>", "insert_index": <caller index + 1>}}) + "\n").encode())
   print(s.recv(65536).decode())
   ```

   The reply is the reordered `tab_list`. Confirm it with `herdr tab list`.

Before you say herdr cannot do something, check `herdr api schema --json`, not
just the CLI help.

## Workspace placement

A seat's herdr tab goes in the workspace whose label matches its repository (the repo of its cwd). The only exception
is tabs of the throughput-improvements track, which live in the `throughput-improvements` workspace (maintainer,
2026-11-19: "it should be in the space that matches its repo. That is the rule. Only excewption is tabs in
throughput-improvements track.", asked after legacy-dispatcher-agent, cwd livespec-orchestrator-beads-fabro, was found
in the livespec-dev-tooling workspace).

To fix a wrong placement without killing the session, send the socket method `pane.move` with params
`{"pane_id": ..., "destination": ..., "focus": false}`, where the destination is
`{"type":"new_workspace","label":"<repo>","tab_label":"<plan-slug>"}` or
`{"type":"new_tab","workspace_id":"<id>","label":"<plan-slug>"}`. It keeps the process (same terminal id) and changes
the pane id, so address seats by plan and tab label, not by a remembered pane id. Measured 2026-11-19: moving
legacy-dispatcher-agent w3:pD -> wD:p1 left it working.
