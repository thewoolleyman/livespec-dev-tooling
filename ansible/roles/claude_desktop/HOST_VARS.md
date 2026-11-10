# claude_desktop -- per-host values for the inventory

None. Nothing in the role is a property of one machine. This file records what
the role cannot do for an operator.

## Out-of-band, not provisioned here

The package, its apt repository and the keyring backend are installed by the
role. The VNC session it displays on is a warning rather than an assert, because
the install is complete and correct on a host with no desktop up.

### Post-apply steps an operator still performs

1. **Sign in, on the first VNC connect after the apply.** Start the VNC desktop,
   then open Claude from the XFCE menu (Office > Claude) and sign in. The
   sign-in is interactive and nothing in the role can perform it.
2. **Unlock the gnome-keyring in the same session.** The app keeps its session in
   the Secret Service keyring; without an unlocked keyring the sign-in does not
   survive a restart and the operator signs in again on every launch. Create or
   unlock the default keyring when the desktop first prompts for it.
