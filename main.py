"""
Interactive CLI for the NimbusPay support assistant.

Run from the project root with:
    python main.py
"""

from __future__ import annotations
import logging
import sys

# Silence LangGraph / httpx / openai internal logs so they don't
# bleed into the chat UI during a demo.
logging.disable(logging.WARNING)

from dotenv import load_dotenv
load_dotenv()

from src import database
from src import graph
from src import ingestion


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _line(char: str = "-", width: int = 56) -> str:
    return char * width


def _banner() -> None:
    print(_line("="))
    print("   NimbusPay Support Assistant")
    print(_line("="))


def _menu() -> None:
    print(f"""
What would you like help with?

  1.  Check a transaction status
  2.  Check my sending / KYC limits
  3.  Raise a support ticket
  4.  Ask anything else about NimbusPay

  Type a number above, or just write your question directly.
  Type 'switch' to change user  |  'exit' to quit
""")


def _check_vector_store() -> None:
    if not ingestion.PERSIST_DIR.exists():
        print(
            "\n  Note: knowledge base not found (chroma_db/ missing).\n"
            "  Run  python -m src.ingestion  first to enable policy Q&A.\n"
        )


def _choose_user() -> str:
    print("\n  Select a user to log in as:\n")
    for uid, info in database.MOCK_USERS.items():
        tier = info["kyc_tier"]
        print(f"    {uid}  —  {info['name']}  (KYC Tier {tier})")
    while True:
        choice = input("\n  Enter user ID [default: U1001]: ").strip() or "U1001"
        if choice in database.MOCK_USERS:
            return choice
        print(f"  Unknown ID '{choice}'. Options: {', '.join(database.MOCK_USERS)}")


# Maps menu shortcut numbers to a pre-filled message that points the
# agent at the right tool without hard-coding any logic here.
_MENU_SHORTCUTS: dict[str, str] = {
    "1": "I'd like to check the status of a transaction. Please ask me for the transaction ID.",
    "2": "Can you show me my current KYC tier and sending limits?",
    "3": "I need to raise a support ticket. Please help me log my issue.",
}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    _banner()

    if graph.client is None:
        print(
            "\n  Error: GROQ_API_KEY is not set.\n"
            "  Add it to a .env file in the project root:\n"
            "    GROQ_API_KEY=gsk_your-key-here\n"
        )
        sys.exit(1)

    _check_vector_store()

    session_user_id = _choose_user()
    name = database.MOCK_USERS[session_user_id]["name"]
    print(f"\n  Logged in as {name} ({session_user_id}).")

    app = graph.build_graph()
    state = graph.new_session_state(session_user_id=session_user_id)
    first_turn = True

    while True:
        if first_turn:
            _menu()
            first_turn = False

        try:
            raw = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye.")
            break

        if not raw:
            continue

        if raw.lower() in ("exit", "quit"):
            print("\n  Goodbye.")
            break

        if raw.lower() == "switch":
            session_user_id = _choose_user()
            name = database.MOCK_USERS[session_user_id]["name"]
            state = graph.new_session_state(session_user_id=session_user_id)
            print(f"\n  Switched to {name} ({session_user_id}). Starting a fresh conversation.")
            first_turn = True
            continue

        # Expand menu shortcut numbers into real messages
        user_message = _MENU_SHORTCUTS.get(raw, raw)
        if user_message != raw:
            print(f"  [{user_message}]")

        try:
            state = graph.run_turn(app, state, user_message)
        except Exception as e:
            print(f"\n  [Something went wrong: {e}]\n")
            continue

        print(f"\nAssistant: {state['final_answer']}\n")

        if state.get("escalated"):
            print("  [This issue has been escalated to a human support agent.]\n")

        print(_line())


if __name__ == "__main__":
    main()