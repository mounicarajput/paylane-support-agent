"""Trusted per-session state. Only code mutates this, never the model."""
from dataclasses import dataclass
from typing import Optional

MAX_FAILED_CHECKS = 3


@dataclass
class SessionState:
    verified: bool = False
    customer_id: Optional[str] = None
    failed_checks: int = 0
    handoff_ticket_id: Optional[str] = None

    @property
    def locked(self) -> bool:
        """Three failed verification checks stop verification and account actions."""
        return self.failed_checks >= MAX_FAILED_CHECKS

    @property
    def handed_off(self) -> bool:
        return self.handoff_ticket_id is not None
