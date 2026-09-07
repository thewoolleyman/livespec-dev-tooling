# The factory span receiver is the DISPATCHING PROJECT's plugin build

Read this before diagnosing a factory `build.cargo-*` span in Honeycomb that
is missing an attribute the sandbox shim is known to attach, before treating
such an absence as a shim defect, and before naming "the sandbox pin" as the
gate for any factory-telemetry evidence.

## The mechanism

A factory Rust dispatch emits its cargo-phase spans from INSIDE the sandbox,
through this repo's `livespec_dev_tooling/otel_cargo_phase.py` (baked into the
`python-rust` sandbox image as `cargo-phase-shim.sh`). The sandbox posts them
to the OTEL receiver of the orchestrator plugin running in the DISPATCHER LOOP
of the project that dispatched the item (`_otel_receive.py` in
livespec-orchestrator-beads-fabro). That receiver scrubs every attribute
through `_otel_scrub.ATTRIBUTE_ALLOWLIST` — an allowlist, never a denylist —
and only then forwards the span to Honeycomb under `build.env=factory`.

Two facts follow, and both were paid for on 2026-09-07:

- **Plugin installs are PER PROJECT.** `~/.claude/plugins/installed_plugins.json`
  records one `version` hash per `projectPath`, and `claude plugin update`
  moves only the project it runs in. Two repos on one host can run two
  orchestrator releases at once, and each repo's dispatcher scrubs with its
  own build's allowlist. On 2026-09-07 this repo's pointer was 0.138.0
  (allowlist widened for `build.cache.sccache.*` by orchestrator PR #2275)
  while the console repo's pointer was still 0.137.0, installed an hour
  BEFORE 0.138.0 was cut. A console Rust dispatch's 13 cargo spans arrived
  with every `build.cache.*` key stripped, and the plan handoff had named
  "the sandbox pin" as the gate — the wrong component.
- **A running dispatcher loop keeps its build for its whole life.** The
  wrapper's `_bootstrap.py` inserts the plugin cache path it was launched
  from into `sys.path`; a loop started before `claude plugin update` keeps
  the old code until it is stopped and restarted. "The plugin is updated" is
  not "the receiver runs the update" — confirm the reader before you trust
  its output (the ordering rule in `CLAUDE.md`).

## How to diagnose

1. The shim ALWAYS emits `build.cache.sccache.enabled` — `true`, or `false`
   when no sccache binary answers (`otel_cargo_phase.py`, the
   `parsed is not None` attribute). A factory span with NO `build.cache.*`
   key at all is therefore a receiver scrub, never a shim no-op.
2. Find the dispatching project's build:
   `python3 -c 'import json;[print(e["projectPath"],e["version"],e["lastUpdated"]) for e in json.load(open("/home/ubuntu/.claude/plugins/installed_plugins.json"))["plugins"]["livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"]]'`
3. Grep that cache build's allowlist:
   `grep -c build.cache.sccache ~/.claude/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/<hash>/scripts/livespec_orchestrator_beads_fabro/commands/_otel_scrub.py`
4. Check which cache path the LIVE loop runs from:
   `ps -eo pid,lstart,args | grep 'dispatcher.py loop'` — the path in argv is
   the build the receiver is running, whatever the pointer now says.

## The fix, in order

Update the plugin IN THE DISPATCHING PROJECT, restart that project's
dispatcher loop, THEN dispatch. A dispatch before the restart produces
scrubbed spans and looks exactly like a shim that attached nothing.
