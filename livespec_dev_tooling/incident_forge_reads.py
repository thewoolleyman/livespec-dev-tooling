"""The controller account's read-only forge access, as the recovery App.

The observer serves with no `gh` credential by design: the account holds no
GH_TOKEN and no gh configuration, so a `gh api` read there can only fail. Its reads
go through the one forge credential the account does hold, the protected
`recovery-app.json` beside `controller.json`, with an installation token minted for
`contents: read` on the one observed repository. That is narrower than the
principal's `contents: write` token, and it adds no permission: the App's own
grants are unchanged and the token is refused if it reports any other grant.

One operation builds one `ForgeReads`. The token is minted on the first read and
reused for the rest of that operation, and a read that cannot be taken answers
`None`, which every caller already treats as "not authenticated" or "unavailable".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

from livespec_dev_tooling.incident_recovery_app import (
    RECOVERY_APP_CREDENTIAL,
    AppRefusal,
    RecoveryAppCredential,
    RecoveryForge,
)

if TYPE_CHECKING:
    from livespec_dev_tooling.incident_controller_installation import ControllerInstallation

__all__: list[str] = ["ForgeRead", "ForgeReads"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-x3wwwc
_HTTP_OK = 200

ForgeRead = Callable[[str], object]


@dataclass(frozen=True, kw_only=True)
class ForgeReads:
    """GETs under `repos/<repository>/`, spelled with that prefix as the callers build them."""

    connect: Callable[[], RecoveryForge | AppRefusal]

    @classmethod
    def installed(cls, *, installation: ControllerInstallation) -> ForgeReads:
        """Read as the recovery App named beside this installation's protected configuration."""

        def connect() -> RecoveryForge | AppRefusal:
            credential = RecoveryAppCredential.load(
                path=installation.config.parent / RECOVERY_APP_CREDENTIAL
            )
            if isinstance(credential, AppRefusal):
                return credential
            return RecoveryForge.connect(
                repository=installation.repository, credential=credential, access="read"
            )

        return cls(connect=cache(connect))

    def __call__(self, path: str) -> object:
        """The decoded resource, or None for a refused, absent or foreign read."""
        forge = self.connect()
        if isinstance(forge, AppRefusal):
            return None
        prefix = f"repos/{forge.repository}/"
        if not path.startswith(prefix):
            return None
        status, value = forge.request(method="GET", path=path.removeprefix(prefix))
        return value if status == _HTTP_OK else None
