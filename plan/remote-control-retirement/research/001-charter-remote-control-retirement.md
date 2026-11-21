## The maintainer's statement of what done means

So we need to just disable the remote control support completely and open a plan to figure out a different way to do it that doesn't leverage remote control or can guarantee that nothing ever gets deadlocked in this way. [and] disabling and Fixing the possibility of these deadlocks from happening until we redesign it is the absolute number one priority and that needs to get done

## Definition of Done assertions derived from that statement

- No component on any fleet host types /remote-control into a seat, and the caam-delivery-push re-issue and sweep take no Remote Control action after an account rotation.
- No seat launcher or brief on any fleet host passes --remote-control, including hxi-herdr-launch, the seat-overrides restore and the coordinator briefs.
- A watchdog running outside any agent session alarms or clears a seat stuck at an Enter-to-select dialog for over 2 minutes on every fleet host.
- A replacement for cross-machine seat messaging is designed so that no single component failure can leave seats waiting on an unanswered dialog, with the maintainer's one design question put to them as plain text with a recommendation.

Charter. Deadline 2026-11-21T12:30Z (maintainer priority 2; scope events on livespec-dev-tooling-6tgd2z, ~00:2xZ-00:3xZ). Cause chain: retro entry on livespec-dev-tooling-osyzv6, EGREGIOUS FAILURE 2. Interim half: disable the re-issue/sweep (overseer-fdwat6 code, fix item overseer-3qklg4), remove --remote-control from every launcher, ship an out-of-band stuck-dialog watchdog. Redesign half: replace herdr pane typing for cross-machine messaging. Assertions are SESSION-DERIVED, not maintainer-confirmed.