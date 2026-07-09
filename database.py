"""
Mock "database" for the NimbusPay assistant.

"""

from __future__ import annotations
from typing import Optional


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
# kyc_tier matches the tiers described in data/kyc_overview.md (1 = Basic,
# 2 = Verified). Keeping these numbers in sync with the KB docs is
# deliberate -- a mismatch here would create an ACCIDENTAL contradiction,
# on top of the deliberate ones already planted in data/.

MOCK_USERS: dict[str, dict] = {
    "U1001": {"name": "Arya Gavasane", "phone": "+91-98xxxxxxxx", "kyc_tier": 1},
    "U1002": {"name": "User 2", "phone": "+91-97xxxxxxxx", "kyc_tier": 2},
    "U1003": {"name": "User 3", "phone": "+91-99xxxxxxxx", "kyc_tier": 2},
}

# ---------------------------------------------------------------------------
# KYC tier limits — copied straight from data/kyc_limits_tier1.md / tier2.md
# so the tool's answer always agrees with the knowledge base's answer.
# ---------------------------------------------------------------------------

KYC_TIER_LIMITS: dict[int, dict] = {
    1: {
        "daily_send_limit": 10_000,
        "monthly_send_limit": 50_000,
        "max_wallet_balance": 20_000,
        "bank_withdrawals_allowed": False,
    },
    2: {
        "daily_send_limit": 100_000,
        "monthly_send_limit": 1_000_000,
        "max_wallet_balance": 200_000,
        "bank_withdrawals_allowed": True,
        "daily_withdrawal_limit": 100_000,
    },
}

# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
# TXN9999 is a deliberate plant — reserved for later, when tools.py makes it
# always raise a simulated downstream error. That's your fixture for the
# "agent looping" failure scenario in Section 3. Don't "fix" it.

MOCK_TRANSACTIONS: dict[str, dict] = {
    "TXN1001": {"user_id": "U1001", "status": "completed", "amount": 500,
                "type": "p2p_transfer", "date": "2026-06-20"},
    "TXN1002": {"user_id": "U1002", "status": "pending", "amount": 15000,
                "type": "bank_withdrawal", "date": "2026-06-25"},
    "TXN1003": {"user_id": "U1002", "status": "failed", "amount": 2000,
                "type": "bill_payment", "date": "2026-06-26", "error_code": "E-101"},
    "TXN1004": {"user_id": "U1003", "status": "completed", "amount": 75000,
                "type": "bank_withdrawal", "date": "2026-06-15"},
}

# ---------------------------------------------------------------------------
# Support tickets — starts empty, grows as create_ticket() gets called
# ---------------------------------------------------------------------------

MOCK_TICKETS: list[dict] = []


# ---------------------------------------------------------------------------
# Read/write functions — tools.py calls these, nothing else touches the
# dicts above directly.
# ---------------------------------------------------------------------------

def get_user(user_id: str) -> Optional[dict]:
    """Return the user record, or None if user_id doesn't exist."""
    return MOCK_USERS.get(user_id)


def get_transaction(txn_id: str) -> Optional[dict]:
    """Return the transaction record, or None if txn_id doesn't exist."""
    return MOCK_TRANSACTIONS.get(txn_id)


def get_kyc_limits_for_user(user_id: str) -> Optional[dict]:
    """Look up a user's tier, then return that tier's limits. None if user unknown."""
    user = get_user(user_id)
    if user is None:
        return None
    return KYC_TIER_LIMITS.get(user["kyc_tier"])


def create_ticket(user_id: str, issue: str) -> dict:
    """Create a new support ticket and store it. Always succeeds (it's in-memory)."""
    ticket = {
        "ticket_id": f"TICKET{1001 + len(MOCK_TICKETS)}",
        "user_id": user_id,
        "issue": issue,
        "status": "open",
    }
    MOCK_TICKETS.append(ticket)
    return ticket


def list_tickets_for_user(user_id: str) -> list[dict]:
    """Return all tickets raised by this user, most recent first."""
    return [t for t in reversed(MOCK_TICKETS) if t["user_id"] == user_id]


if __name__ == "__main__":
    # Quick manual sanity check -- run this file directly in PyCharm
    # (right-click the file > Run 'database') to see it work before
    # anything else depends on it.
    print(get_user("U1001"))
    print(get_transaction("TXN1002"))
    print(get_kyc_limits_for_user("U1001"))
    print(create_ticket("U1001", "App keeps crashing on login"))
    print(list_tickets_for_user("U1001"))
