"""
agents/state.py — Shared AgentState TypedDict used by ALL agents and graph.py.

WHY THIS FILE EXISTS (CRITICAL — DO NOT MOVE THIS CODE):
  Python has circular import rules: if file A imports from file B, and
  file B imports from file A, Python raises an ImportError at startup.

  The bug that existed before this file:
    graph.py       imported run_intake_agent from intake_agent.py
    intake_agent.py imported AgentState from graph.py
    → circular import → crash

  The fix: put AgentState in state.py which imports from NOTHING in our
  codebase. Both graph.py and all agent files import from state.py.
  No cycles possible.

  ⚠️ TEAM RULE: Never add any import from app.agents.* into this file.
     This file must remain import-free (stdlib only).

WHAT IS AgentState?
  TypedDict = a dict with type annotations. LangGraph passes this dict
  between every node in the graph, accumulating results.

  Think of it as the "shared whiteboard" for all agents:
  - intake_agent writes → intake_summary, intake_complete, messages
  - fan_out_research writes → federal_law_results, state_law_results, case_law_results
  - opinion_agent writes → opinion, case_strength_score, recommended_actions
  - referral_agent writes → referred_lawyers

HOW stream_callback WORKS (serialization-safe approach):
  The callback is an async function that sends tokens to the WebSocket.
  It cannot be stored in AgentState because MemorySaver serializes the
  state between steps and async functions are not serializable.

  Solution: pass it via LangGraph's 'config' dict:
    config = {"configurable": {"thread_id": "...", "stream_callback": fn}}
    await graph.ainvoke(state, config=config)

  In each agent, read it like:
    stream_cb = config.get("configurable", {}).get("stream_callback")
    if stream_cb:
        await stream_cb(token)

TEAM — WHERE HUMAN EFFORT IS NEEDED:
  - If you add a new agent, add its output fields here
  - Keep field names consistent with what agents return (dict keys must match)
"""
from typing import TypedDict


class AgentState(TypedDict):
    # ── Conversation identity ──────────────────────────────────────────────
    conversation_id: str   # UUID from the DB conversations table
    user_id: str           # UUID from the DB users table

    # ── Chat message history (sliding window) ─────────────────────────────
    # List of {"role": "user"|"assistant", "content": "..."} dicts.
    # Only the last MAX_CONTEXT_MESSAGES are sent to the LLM.
    # New messages are appended by intake_agent on every turn.
    messages: list[dict]

    # ── Intake agent output ───────────────────────────────────────────────
    # Set to True by intake_agent when [INTAKE_COMPLETE] tag appears in LLM response.
    # This is what triggers the conditional edge to fan_out_research.
    intake_complete: bool

    # Structured data extracted from the conversation:
    # {"incident": str, "location": str, "state": str,
    #  "perpetrator": str, "written_proof": str, "date_of_incident": str}
    intake_summary: dict

    # ── Research agent outputs (populated concurrently in fan_out_research) ─
    # Each is a list of dicts with keys: source, raw (API data), analysis (LLM text)
    federal_law_results: list[dict]   # from Congress.gov via federal_law_agent
    state_law_results: list[dict]     # from Cornell LII via state_law_agent
    case_law_results: list[dict]      # from CourtListener via case_law_agent

    # ── Opinion agent output ───────────────────────────────────────────────
    opinion: str                      # full markdown text of the legal analysis
    case_strength_score: int          # 0-100 — shown as a progress bar in the UI
    recommended_actions: list[str]    # e.g. ["File police report", "Contact EEOC"]

    # ── Referral agent output ──────────────────────────────────────────────
    # List of lawyer dicts: {name, address, phone, rating, specialty, url}
    referred_lawyers: list[dict]
