# A skill's plugin path can lag the project's installed build

A skill's announced base directory names the build the session loaded at
start, for example
`~/.claude/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/<sha>`.
The SessionStart `ensure-plugins` step, or a later update, can move this
project's install to a newer build while the session keeps the old path.
Nothing warns you. A verb that is missing from the old build reads as a TRUE
absence.

## Measured 2026-11-01

The kubernetes-observability seat used build `65e2a78db708` from its skill
path. The project's install was `8ccf4103278a`, updated at 17:36Z that day.
The session ran `dispatcher.py --help`, found no classification verb, and told
the coordinator that no sanctioned path existed. The coordinator ruled that a
new orchestrator item should be filed. But `dispatcher.py classify-tier`
(bd-ib-sappap; orchestrator contracts.md "Dispatcher classify-tier invocation
surface") was in the installed build. The ruling had to be corrected, and a
duplicate item came close to being filed.

## Do this first

Read the project's install path, and run plugin scripts from that path:

```bash
python3 -c "
import json; d = json.load(open('$HOME/.claude/plugins/installed_plugins.json'))
for e in d['plugins']['livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro']:
    if e.get('projectPath') == '/data/projects/livespec-dev-tooling': print(e['installPath'], e['lastUpdated'])"
```

Before you report that a surface is absent, also grep the plugin's own repo
source and its spec for the surface. A ratified heading with a closed
implementing item means the surface exists somewhere. Then find out which
build has it.

## A partial read fakes absence too, even on the right build

On 2026-11-09 (00:0xZ) the ci-runtime-and-cost seat told the coordinator that
"no drive valve moves an item from active to ready". It had grepped `drive`'s
SKILL.md for reject, rework and ready-transition phrases. That prose lists only
the acceptance valves (`reject:<id>:rework|regroom`). The seat proposed a hand
`bd update --status ready` instead. The build was the installed one, and
the generic `move:<id>:backlog|ready|blocked` valve was in it. The coordinator
moved livespec-dev-tooling-jd4qle from active to ready with
`move:livespec-dev-tooling-jd4qle:ready`, and that valve also cleared the fabro
assignee that a hand write would have left behind.

So before reporting that a `drive` action is missing, read the installed build's
own list of accepted forms. It is `_UNSUPPORTED_ACTION_SUMMARY` in
`scripts/livespec_orchestrator_beads_fabro/commands/drive.py`, which is also the
error text an unknown action prints; the parse itself is in
`_drive_valve_grammar.py`. Do not rely on the SKILL.md summary. Prefer
`move:<id>:<status>` to a hand status write.
