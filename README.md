# NimbusPay Intelligent Support & Routing Agent

An enterprise-grade, state-graph-orchestrated customer support routing assistant engineered for the NimbusPay fintech ecosystem. This system seamlessly bridges conversational artificial intelligence with core transaction ledgers, KYC profile data, and decentralized documentation repositories to automatically service multi-turn customer requests while strictly enforcing production guardrails.

---

## 🏗️ System Architecture & Engineering Highlights

- **State Graph Workflow Execution:** Driven by a modular state-machine pattern built on a deterministic `StateGraph` architecture. The engine maintains robust conversation state tracking across asynchronous turns, dynamically routing execution control through conditional edges, tool invocations, and manual supervisor escalation paths.
- **Decoupled LLM Infrastructure Tier:** Features a unified, production-agnostic interface that routes the standard OpenAI Python SDK client onto Groq's high-speed cloud infrastructure. The application targets the open-weights model `llama-3.3-70b-versatile` under a free developer tier, minimizing operational expenditure while ensuring sub-second response latencies.
- **Enterprise Security & Isolation Boundaries:** Programmatically mandates session token authentication. The model cannot bypass data layer perimeters; cross-tenant access attempts (e.g., User A requesting data for User B's transaction ID) are isolated and intercepted at the physical tool invocation boundary.
- **Advanced Automated Evaluation Matrix (`eval_harness.py`):** Ships with a 15-case automated regression and verification suite. The harness programmatically benchmarks model updates against structural edge cases, vocabulary mismatches, outdated documentation collisions, hallucination limits, and direct malicious prompt injections.

---

## 📁 Repository Structure

```text
NimbusPay/
├── src/
│   ├── __init__.py
│   ├── database.py       # Mock enterprise database (Transactions, Users, KYC profiles)
│   ├── graph.py          # StateGraph routing logic, LLM client initialization, system prompt
│   ├── ingestion.py      # Local vector storage indexing and text preprocessing
│   ├── tools.py          # Functional tool schemas executed by the agent graph
│   └── guardrails.py      # Groundedness, input scanning, and looping tripwires
├── data/                 # Knowledge Base storage markdown files (.md)
├── main.py               # Presentation-grade interactive terminal CLI module
├── eval_harness.py       # Automated regression framework and report generator
├── .gitignore            # Security exclusion boundaries (ignores .env, .venv, chroma_db)
└── pyproject.toml        # Unified project metadata and 'uv' lock file definitions