# onepassword_desktop -- per-host values for the inventory

None. Nothing in the role is a property of one machine. This file records what
the role cannot do for an operator.

## Out-of-band, not provisioned here

The application is installed and gated by the VNC session, which the role
asserts is running before its first changed task. What follows is interactive,
happens inside that session and cannot be checked from the host.

### Post-apply steps an operator still performs

1. **Sign in, on the first VNC connect after the apply.** Connect to the VNC
   desktop; the `x11vnc` hook starts 1Password when the client authenticates.
   Sign in to the account there. The sign-in lives in the app's own profile, so a
   rebuilt host has none until this is done.
2. **Set auto-lock to 15 minutes, in the same sitting.** In the app's settings
   set the auto-lock timer to 15 minutes. The unit's `RuntimeMaxSec=2h` caps the
   app's lifetime regardless, but auto-lock is what closes the vault sooner when
   nobody is watching, and it is app state the role does not write.
