# An item master already satisfies

A failure measured in a CONSUMING repository is not evidence that the fix is
missing here. Before filing a fix item from such a measurement, check whether
livespec-dev-tooling master already carries it, then compare with the
consumer's pin:

```bash
git log --oneline -S '<identifier the fix would add>' origin/master
git tag --contains <sha> --sort=v:refname | head -1   # first release carrying it
grep -o 'livespec-dev-tooling.git", tag = "v[0-9.]*' <consumer>/pyproject.toml
```

If master has it and the consumer pins an older release, the remedy is the
consumer's pin bump, not a new item.

## The case that made this matter (2026-10-24/25)

`livespec-dev-tooling-tlfc3w` was filed after `check-master-ci-green` failed
inside livespec-runtime's delegated gate Job (gate-livespec-runtime-mkx42).
The fix had shipped on 2026-09-09 as 419a1115, first released in v1.83.0, and
livespec-runtime simply pinned v1.64.1. Factory run 01M5RB522MJK verified
every check green, found nothing to commit, and ended
`LIVESPEC_DEAD_IMPLEMENTER`, so a factory slot was spent proving a no-op. The
coordinator (gitops-fleet-capacity-monitoring) then made "check master
first" a rule.

## Closing one that slipped through

Neither valve fits an `active` item with no PR of its own:

- `accept:<id>` moves only an item already in `acceptance`.
- `dispatcher.py reconcile-merged` resolves the item's OWN merged PR. With
  none, it refuses at best and burns a rework attempt at worst.

Use the implement prose's admin closure instead: `close_work_item_and_reconcile`
with `resolution="resolved-out-of-band"` and a `reason` that names the
satisfying commit, its first release, and the run evidence. If any
host-captured leg rests on a consumer's pin bump, say so in the reason.
