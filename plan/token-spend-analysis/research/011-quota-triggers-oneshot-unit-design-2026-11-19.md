# 011 — quota_triggers.py oneshot unit and live read-back: design (2026-11-19)

Item: livespec-dev-tooling-caejh2. Ruling: legacy-coordinator-agent, 2026-11-19 (option a, three conditions). Parent
context: livespec-dev-tooling-jxyklc.

## What reading the role and the scripts showed

1. **The scripts have no read-only mode.** `quota_triggers.py` builds each trigger body inline inside `main()` and every
   path ends in a POST or PUT. A read-back that "compares what the script would set" cannot be written without first
   exposing the bodies. `build_triggers.py` is imported by it (`bt.call`, `bt.RECIPIENT`) and also PUTs on its own run.
2. **So the change spans two repositories and bumps two pins.** vps-info owns the bytes (no Python gate there; the
   livespec-dev-tooling gates reject them as written). The role pins them by commit sha and SHA-256. Order: vps-info
   first, then the role pin, per the role's own HOST_VARS.md.
3. **The units are not role-managed today.** The three `token-spend-*` units live in `~/.config/systemd/user/` on the
   vps and the role installs only scripts. They were hand-installed. The new unit is therefore the role's first unit,
   and it is user-scoped (it runs as `ubuntu` through `with-livespec-env.sh`, like `token-spend-fast.service`).
4. **Existing units already show the credential pattern:** `ExecStart=/usr/local/bin/with-livespec-env.sh -- /usr/bin/python3 -I %h/token-spend-report/scripts/<script>`.
   The new unit reuses it verbatim, so no key is stored in the unit or the repository.

## Design

- **vps-info PR (scripts):** in `quota_triggers.py`, move body construction into `desired()` returning `[(name, body)]`
  (the `main()` loop and the inline `tenant Claude account low` and `quota guard quiet` puts all use it), keeping
  behaviour identical. Add `quota_triggers_check.py`: for each `desired()` entry, GET the live trigger by name and
  compare description, query, frequency, threshold, alert_type, recipients and disabled; print one line per trigger,
  never the key; exit non-zero on any missing or differing trigger. Add a test with a fake `bt.call`.
- **Role PR (livespec-dev-tooling), as built:** pin the changed `quota_triggers.py` plus `quota_triggers_check.py` and
  `emit_spend_key.py` at vps-info 12cf60f0d6bd (vps-info#97, merged). Install `token-spend-quota-triggers.service`
  (Type=oneshot, no `[Install]`, no timer; ExecStart through `with-livespec-env.sh`) into `~ubuntu/.config/systemd/user`.
  The role starts it only when `quota_triggers.py`, `build_triggers.py` or `emit_spend_key.py` changed in that apply, or
  the unit changed. After every real apply the role runs `quota_triggers_check.py` through the wrapper as a plain
  command (stdout visible) and fails the play on any difference. Check mode starts nothing and skips the read-back, so
  a drift run never PUTs. One deliberate change from the first sketch: no separate check unit, because a failed
  oneshot start reports only "Job failed" and hides the DIFFERS lines the check prints.
- **Credential probe:** value-free (`printenv HONEYCOMB_CONFIG_KEY_LIVESPEC | wc -c` through the wrapper), recorded on
  the item, never echoed.
- **Gates on the first live apply, not the merge:** one fresh independent subagent second look, time-boxed to 30
  minutes, over the unit, the handler and the check. Then one deliberate committed apply, a read of the live
  "token-spend tenant Claude account low" description through the configuration key, and a value-free hash recorded on
  caejh2 and jxyklc.

## Open risk to name

`quota_triggers.py` imports `build_triggers`, which does `from emit_spend_key import HEARTBEAT_SOURCES` and reads
`HONEYCOMB_CONFIG_KEY_LIVESPEC` at import. `emit_spend_key` is one of the unpinned sibling modules on the vps. The unit
therefore depends on a file the role does not manage, which is the same gap qsa576 inventories. The check script has
the same import. Pinning `emit_spend_key.py` is the smallest fix and belongs in the vps-info PR above if it is
byte-identical to the vps copy; I will compare it over read-only ssh before deciding.

## Reversal

Remove the two units and the pins. Triggers already PUT stay in Honeycomb, unchanged.
