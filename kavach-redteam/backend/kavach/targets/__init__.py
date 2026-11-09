"""The voice agents Kavach can attack."""

from __future__ import annotations

from .bank import BankTarget
from .base import Reply, Session, Target, TargetError
from .saakshi import SaakshiTarget

TARGETS: dict[str, Target] = {t.id: t for t in (SaakshiTarget(), BankTarget())}


def get(target_id: str) -> Target:
    t = TARGETS.get(target_id)
    if not t:
        raise KeyError(target_id)
    return t


__all__ = ["TARGETS", "Reply", "Session", "Target", "TargetError", "get"]
