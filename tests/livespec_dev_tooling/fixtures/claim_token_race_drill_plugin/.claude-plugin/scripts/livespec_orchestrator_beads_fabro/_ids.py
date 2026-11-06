"""Fresh `<prefix>-XXXXXX` ids, as the released minter shapes them."""

from __future__ import annotations

import secrets

__all__: list[str] = ["new_work_item_id"]


def new_work_item_id(*, prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3)}"
