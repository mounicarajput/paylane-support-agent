"""Mock Paylane API. JSON-shaped in and out, in-memory state.

This layer is deliberately policy-free (like a real backend). Policy lives in guards.py.
"""
import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


class MockAPI:
    def __init__(self, customers: Optional[list] = None, transactions: Optional[list] = None):
        self._customers = copy.deepcopy(customers if customers is not None else _load("customers.json"))
        self._txns = copy.deepcopy(transactions if transactions is not None else _load("transactions.json"))
        self._refund_count = 0
        self._ticket_count = 0
        self.refunds: list = []
        self.tickets: list = []

    def get_customer(self, email: str) -> Optional[dict]:
        """Returns {id, name, card_last4, status, verified:false} or None if unknown."""
        email = (email or "").strip().lower()
        for c in self._customers:
            if c["email"].lower() == email:
                return {
                    "id": c["id"],
                    "name": c["name"],
                    "card_last4": c["card_last4"],
                    "status": c["status"],
                    "verified": False,
                }
        return None

    def get_transaction(self, customer_id: str, txn_id: str) -> dict:
        """Returns {amount, date, merchant, status}; not_found if absent or not the customer's."""
        for t in self._txns:
            if t["txn_id"] == txn_id and t["customer_id"] == customer_id:
                return {k: t[k] for k in ("amount", "date", "merchant", "status")}
        return {"ok": False, "reason": "not_found"}

    def issue_refund(self, txn_id: str, amount: float) -> dict:
        for t in self._txns:
            if t["txn_id"] != txn_id:
                continue
            if t["status"] == "refunded":
                return {"ok": False, "reason": "already_refunded"}
            if t["status"] != "settled":
                return {"ok": False, "reason": "not_settled"}
            if Decimal(str(amount)) != Decimal(str(t["amount"])):
                return {"ok": False, "reason": "amount_mismatch"}
            t["status"] = "refunded"
            self._refund_count += 1
            refund_id = f"rf_{self._refund_count:04d}"
            self.refunds.append({"refund_id": refund_id, "txn_id": txn_id, "amount": amount})
            return {"ok": True, "refund_id": refund_id}
        return {"ok": False, "reason": "not_found"}

    def escalate_to_human(self, customer_id: Optional[str], summary: str) -> dict:
        self._ticket_count += 1
        ticket_id = f"TKT-{self._ticket_count:04d}"
        self.tickets.append({"ticket_id": ticket_id, "customer_id": customer_id, "summary": summary})
        return {"ticket_id": ticket_id}

    def raw_transaction(self, txn_id: str) -> Optional[dict]:
        """Internal lookup for guards (includes owner). Not exposed to the model."""
        for t in self._txns:
            if t["txn_id"] == txn_id:
                return dict(t)
        return None
