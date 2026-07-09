"""


Four tools live here:
    search_knowledge_base     -- read-only, wraps the RAG retriever
    check_transaction_status  -- read-only, also the "agent looping" fixture
    check_kyc_limits          -- read-only
    raise_support_ticket      -- the one tool with a real side effect

DESIGN RULE THAT MATTERS FOR SCENARIO 6 (prompt injection / authorization):
None of these functions trust a user_id that arrives as an LLM-supplied
argument. Each one takes `session_user_id` as a keyword-only argument that
ONLY the orchestrator (graph.py) is allowed to set, from the real logged-in
session -- never from anything the model or the user typed. The dispatcher
at the bottom (call_tool) enforces this by stripping any "session_user_id"
the model tries to sneak into its tool-call arguments before the real one
is injected. That's "authorization outside the model": code does the
check, not the LLM's judgement.

DESIGN RULE FOR FAILURES: every tool returns a plain dict, always shaped
like {"ok": True, ...} or {"ok": False, "error": "<code>", "message": "..."}.
A tool function never raises an exception out to its caller -- the agent
can't recover from a Python traceback, but it CAN read an error dict and
decide to apologize, retry once, or escalate.
"""

from __future__ import annotations
from typing import Any

from src import database
from src import ingestion


# ---------------------------------------------------------------------------
# Tool 1: search_knowledge_base  (read-only)
# ---------------------------------------------------------------------------
# Inputs:        query: str, k: int (how many chunks to retrieve)
# Outputs:       {"ok": True, "results": [...], "results_found": bool}
#                {"ok": False, "error": "kb_unavailable", "message": str}
# Side effects:  none -- read-only vector search
# Failure mode:  if the vector store itself is missing/corrupt (e.g.
#                ingestion was never run), the underlying query raises --
#                we catch that and turn it into a typed error instead of
#                crashing the whole agent loop.
def search_knowledge_base(query: str, k: int = 4) -> dict[str, Any]:
    try:
        hits = ingestion.query_kb(query, k=k)
    except Exception as e:
        return {
            "ok": False,
            "error": "kb_unavailable",
            "message": f"Knowledge base could not be searched: {e}",
        }

    return {
        "ok": True,
        "results": hits,
        "results_found": len(hits) > 0,
    }


# ---------------------------------------------------------------------------
# Tool 2: check_transaction_status  (read-only)
# ---------------------------------------------------------------------------
# Inputs:        txn_id: str  (session_user_id is injected by code, not the LLM)
# Outputs:       {"ok": True, "transaction": {...}}
#                {"ok": False, "error": "not_found" | "unauthorized"
#                              | "service_unavailable", "message": str}
# Side effects:  none
# Failure mode:  TXN9999 is a deliberately reserved ID that always raises a
#                simulated downstream connection error -- NOT a "not found".
#                This is the fixture for the "agent looping" failure
#                scenario in Section 3: a real payments backend timing out,
#                which an agent might naively retry forever without a step
#                cap (built in guardrails.py, next file).
def check_transaction_status(txn_id: str, *, session_user_id: str) -> dict[str, Any]:
    try:
        if txn_id == "TXN9999":
            raise ConnectionError("transaction_service_unreachable")

        txn = database.get_transaction(txn_id)

        if txn is None:
            return {
                "ok": False,
                "error": "not_found",
                "message": f"No transaction found with ID {txn_id}.",
            }

        if txn["user_id"] != session_user_id:
            # This is the authorization check in action: even if the model
            # was tricked into asking for someone else's transaction, the
            # comparison is against session_user_id (set by code), never
            # against anything the model or user typed.
            return {
                "ok": False,
                "error": "unauthorized",
                "message": "You can only check the status of your own transactions.",
            }

        return {"ok": True, "transaction": txn}

    except ConnectionError as e:
        return {
            "ok": False,
            "error": "service_unavailable",
            "message": f"Transaction service is temporarily unreachable: {e}",
            "retryable": True,
        }


# ---------------------------------------------------------------------------
# Tool 3: check_kyc_limits  (read-only)
# ---------------------------------------------------------------------------
# Inputs:        none beyond session_user_id (a user can only ever check
#                their OWN limits -- there's deliberately no user_id
#                parameter exposed to the model at all for this one)
# Outputs:       {"ok": True, "kyc_tier": int, "limits": {...}}
#                {"ok": False, "error": "user_not_found", "message": str}
# Side effects:  none
def check_kyc_limits(*, session_user_id: str) -> dict[str, Any]:
    user = database.get_user(session_user_id)
    if user is None:
        return {
            "ok": False,
            "error": "user_not_found",
            "message": "Could not find your account.",
        }

    limits = database.get_kyc_limits_for_user(session_user_id)
    return {
        "ok": True,
        "kyc_tier": user["kyc_tier"],
        "limits": limits,
    }


# ---------------------------------------------------------------------------
# Tool 4: raise_support_ticket  (the one tool with a SIDE EFFECT)
# ---------------------------------------------------------------------------
# Inputs:        issue: str  (session_user_id injected by code)
# Outputs:       {"ok": True, "ticket": {...}}
#                {"ok": False, "error": "invalid_input" | "user_not_found", ...}
# Side effects:  appends a new ticket to database.MOCK_TICKETS -- this is
#                the one tool that changes state rather than just reading it.
def raise_support_ticket(issue: str, *, session_user_id: str) -> dict[str, Any]:
    if not issue or not issue.strip():
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "Cannot raise a ticket with an empty issue description.",
        }

    user = database.get_user(session_user_id)
    if user is None:
        return {
            "ok": False,
            "error": "user_not_found",
            "message": "Could not find your account.",
        }

    ticket = database.create_ticket(session_user_id, issue.strip())
    return {"ok": True, "ticket": ticket}


# ---------------------------------------------------------------------------
# Tool schemas -- the function-calling descriptions the LLM actually sees.
# Note session_user_id appears in NONE of these: the model is never even
# given the option to supply it.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the NimbusPay knowledge base (FAQs, KYC policy, fees, "
                "refund policy, troubleshooting guides) for information relevant "
                "to a user's question. Use this for any general policy or "
                "how-to question that isn't about a specific user's account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "k": {"type": "integer", "description": "Number of chunks to retrieve.", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_transaction_status",
            "description": (
                "Look up the status of one specific transaction by its ID "
                "(e.g. 'TXN1002'). Use this only when the user references a "
                "specific transaction, not for general questions about how "
                "transfers work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "txn_id": {"type": "string", "description": "The transaction ID, e.g. TXN1002."},
                },
                "required": ["txn_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_kyc_limits",
            "description": (
                "Look up the CURRENT user's own KYC tier and the exact "
                "send/withdraw/balance limits for that tier. Use this when "
                "the user asks about their personal limits, not for general "
                "questions about how the KYC tier system works."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "raise_support_ticket",
            "description": (
                "Create a support ticket for the current user when their issue "
                "can't be resolved from the knowledge base or a tool lookup, "
                "or when they explicitly ask to escalate to a human."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string", "description": "A clear summary of the user's issue."},
                },
                "required": ["issue"],
            },
        },
    },
]

# Maps a tool name (as the LLM will name it) to the actual Python function.
TOOL_REGISTRY = {
    "search_knowledge_base": search_knowledge_base,
    "check_transaction_status": check_transaction_status,
    "check_kyc_limits": check_kyc_limits,
    "raise_support_ticket": raise_support_ticket,
}

# Tools that need the real session user injected (everything except KB search).
_NEEDS_SESSION_USER = {"check_transaction_status", "check_kyc_limits", "raise_support_ticket"}


def call_tool(name: str, arguments: dict, session_user_id: str) -> dict[str, Any]:
    """
    The ONLY way graph.py should ever invoke a tool. This is the
    authorization boundary described in Scenario 6 of the assignment:
    even if the model's tool-call arguments contain a "session_user_id"
    or "user_id" key (e.g. because a prompt injection tried to plant one),
    it's discarded here and overwritten with the real one before the tool
    runs. The model's word is never trusted for identity.
    """
    if name not in TOOL_REGISTRY:
        return {"ok": False, "error": "unknown_tool", "message": f"No such tool: {name}"}

    fn = TOOL_REGISTRY[name]
    safe_args = {k: v for k, v in arguments.items() if k not in ("session_user_id", "user_id")}

    if name in _NEEDS_SESSION_USER:
        safe_args["session_user_id"] = session_user_id

    try:
        return fn(**safe_args)
    except TypeError as e:
        # Wrong/missing arguments from the model -- still don't crash the loop.
        return {"ok": False, "error": "bad_arguments", "message": str(e)}


if __name__ == "__main__":
    # Manual sanity checks -- run this file directly in PyCharm.
    print("-- own transaction --")
    print(call_tool("check_transaction_status", {"txn_id": "TXN1001"}, session_user_id="U1001"))

    print("-- someone else's transaction (should be unauthorized) --")
    print(call_tool("check_transaction_status", {"txn_id": "TXN1002"}, session_user_id="U1001"))

    print("-- unknown transaction --")
    print(call_tool("check_transaction_status", {"txn_id": "TXN0000"}, session_user_id="U1001"))

    print("-- simulated downstream failure (TXN9999) --")
    print(call_tool("check_transaction_status", {"txn_id": "TXN9999"}, session_user_id="U1001"))

    print("-- kyc limits --")
    print(call_tool("check_kyc_limits", {}, session_user_id="U1002"))

    print("-- raise ticket --")
    print(call_tool("raise_support_ticket", {"issue": "App crashes on login"}, session_user_id="U1001"))

    print("-- injection attempt: model tries to pass its own user_id --")
    print(call_tool(
        "check_transaction_status",
        {"txn_id": "TXN1002", "session_user_id": "U1002"},  # should be ignored
        session_user_id="U1001",  # real session user
    ))
