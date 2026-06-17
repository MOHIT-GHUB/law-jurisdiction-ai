"""
agents/graph.py — LangGraph multi-agent workflow definition.

ARCHITECTURE OVERVIEW:
  This is the brain of LexAI. It defines the full agent pipeline as a
  directed graph. LangGraph manages execution order, state passing, and
  conditional branching.

PIPELINE (matches your architecture diagram):
  intake_agent (loops)
      │
      │  [when INTAKE_COMPLETE]
      ▼
  ┌─────────────────────────────────────────┐
  │  fan_out_research (parallel dispatcher) │
  └────────┬──────────────┬─────────────────┘
           │              │              │
     federal_law    state_law       case_law
           │              │              │
           └──────────────┴──────────────┘
                          │
                    opinion_agent  (synthesizes all 3 + generates case score)
                          │
                    referral_agent (finds nearby lawyers)
                          │
                         END

WHY fan_out_research NODE EXISTS:
  LangGraph does NOT automatically run 3 nodes concurrently when you add
  3 edges from one node. To truly parallelize, you need a dispatcher node
  that uses asyncio.gather() to run all 3 research agents simultaneously.
  Without this, they run sequentially which is slower.

CIRCULAR IMPORT FIX (BUG THAT WAS HERE BEFORE):
  ORIGINAL (broken): graph.py imported agents, agents imported AgentState
  from graph.py → Python circular import → ImportError on startup.
  FIX: AgentState is now defined in a separate file (agents/state.py)
  that has NO imports from any agent file. Both graph.py and all agents
  import from state.py. Problem solved.

  ⚠️ TEAM: Do NOT move AgentState back into graph.py or any agent file.
     Keep it in state.py. This is the correct pattern.

stream_callback SERIALIZATION FIX (BUG THAT WAS HERE BEFORE):
  ORIGINAL (broken): stream_callback: Any was in AgentState TypedDict.
  MemorySaver (the checkpointer) tries to serialize the entire state to
  memory between steps. A Python callable (async function) is NOT
  serializable → crash on second step.
  FIX: stream_callback is now passed via LangGraph's 'config' dict
  (config["configurable"]["stream_callback"]) which is never serialized.
  Agents read it from config, not from state.

TEAM — WHAT YOU MUST DO:
  1. Install dependencies: uv sync  (langgraph + langchain-openai are in pyproject.toml)
  2. The graph is compiled once at module import (bottom of file)
     and reused across all WebSocket connections — this is intentional.
  3. To invoke the graph from the WebSocket handler:
       config = {"configurable": {"thread_id": conversation_id,
                                  "stream_callback": ws_send_fn}}
       await graph.ainvoke(initial_state, config=config)
  4. 'thread_id' in config = LangGraph's memory key. Each conversation
     gets its own thread_id so state is isolated between users.

TEAM — WHERE HUMAN EFFORT IS NEEDED:
  - Test the fan_out_research node with asyncio.gather to confirm
    all 3 agents actually run in parallel (add timing logs)
  - Tune the opinion_agent prompt for quality of the case score
  - Validate that MemorySaver actually persists state across
    multiple WebSocket messages for the same conversation

AI USAGE NOTE:
  The graph topology (edges + nodes) is mostly complete. If you need to
  add a new agent node, ask an AI: "add a [NAME] node to this LangGraph
  StateGraph, called after opinion_agent". Show it this file.
"""

import asyncio

from app.agents.case_law_agent import run_case_law_agent
from app.agents.federal_law_agent import run_federal_law_agent

# ── Import agent runner functions ─────────────────────────────────────────────
# These imports are safe now because agent files import AgentState from
# state.py, NOT from graph.py. No circular dependency.
from app.agents.intake_agent import run_intake_agent
from app.agents.opinion_agent import run_opinion_agent
from app.agents.referral_agent import run_referral_agent

# ── Import AgentState from dedicated state file (fixes circular import) ───────
# agents/state.py has NO imports from any agent file — that's the key.
from app.agents.state import AgentState
from app.agents.state_law_agent import run_state_law_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langchain_core.runnables import RunnableConfig

# ── Dispatcher node: runs all 3 research agents in parallel ──────────────────


async def fan_out_research(state: AgentState, config: RunnableConfig) -> dict:
    """
    Parallel dispatcher — runs federal, state, and case law agents concurrently.

    WHY: Without this, LangGraph would run them sequentially (3x slower).
    With asyncio.gather, all 3 API calls happen at the same time.
    Total research time ≈ slowest single agent (not sum of all 3).

    TEAM: This is a critical performance node. Time it in tests.
    Expected: ~5-10s total vs ~15-30s sequential.
    """
    federal_result, state_result, case_result = await asyncio.gather(
        run_federal_law_agent(state, config),
        run_state_law_agent(state, config),
        run_case_law_agent(state, config),
    )
    # Merge all 3 result dicts into one update for the graph state
    return {
        **federal_result,
        **state_result,
        **case_result,
    }


# ── Routing: decides whether to keep collecting intake or start research ──────


def should_research(state: AgentState) -> str:
    """
    After intake_agent runs, check if all required info has been collected.
    Returns "research" to proceed, or "intake" to keep asking the user.
    intake_complete is set to True by intake_agent when [INTAKE_COMPLETE] fires.
    """
    if state.get("intake_complete"):
        return "research"
    return "intake"


# ── Graph construction ────────────────────────────────────────────────────────


def build_graph():
    """
    Builds and compiles the LangGraph StateGraph.
    Called once at module load — the compiled graph is a singleton.
    """
    builder = StateGraph(AgentState)

    # Register all nodes (name → async function)
    builder.add_node("intake_agent", run_intake_agent)
    builder.add_node("fan_out_research", fan_out_research)  # parallel dispatcher
    builder.add_node("opinion_agent", run_opinion_agent)
    builder.add_node("referral_agent", run_referral_agent)

    # First node to execute
    builder.set_entry_point("intake_agent")

    # After intake: loop back if incomplete, proceed to research if complete
    builder.add_conditional_edges(
        "intake_agent",
        should_research,
        {
            "intake": "intake_agent",  # loop: keep asking user for info
            "research": "fan_out_research",  # proceed: all info collected
        },
    )

    # Linear flow after research
    builder.add_edge("fan_out_research", "opinion_agent")
    builder.add_edge("opinion_agent", "referral_agent")
    builder.add_edge("referral_agent", END)

    # MemorySaver persists graph state in memory (per thread_id).
    # TEAM: For multi-server deployments, swap MemorySaver for
    # langgraph.checkpoint.postgres.AsyncPostgresSaver (uses your DB).
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


# Compiled graph singleton — import this in the WebSocket handler
graph = build_graph()
