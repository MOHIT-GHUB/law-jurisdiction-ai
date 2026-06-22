"""
agents/state_law_agent.py — Searches state statutes via Cornell LII.

RESPONSIBILITY:
  Find state-specific laws that apply. This is often MORE actionable than
  federal law because state courts handle most civil disputes.

  Key things to find:
  - Statute of limitations (CRITICAL — user must know their deadline)
  - State equivalents to federal protections (often stronger)
  - Small claims court eligibility
  - State attorney general complaint procedures

HOW IT WORKS:
  Same pattern as federal_law_agent but uses Cornell LII for state codes.
  Cornell LII covers all 50 state codes for free.

TEAM — WHERE HUMAN EFFORT IS NEEDED:
  1. STATUTE OF LIMITATIONS varies by state and claim type.
     This is the most important piece of information for the user.
     The LLM should always surface this — add it explicitly to SYSTEM_PROMPT.
  2. Cornell LII's search API is not officially documented. The URL used
     in cornell_lii_tool.py may need adjustment — TEST THIS FIRST.
     If the API doesn't work, set DEMO_MODE=True and update _DEMO_DATA
     with realistic state laws for common test cases.
  3. The 'state' from intake_summary must be a full state name (e.g. "Texas")
     not abbreviation ("TX") for LII to filter correctly.
     TEAM: Add normalization in intake_agent or here.

AI USAGE NOTE:
  If Cornell LII API is unreliable, ask an AI to write a scraper for
  specific state code URLs. Or use the Justia API as an alternative.
"""

import json

# Import from state.py, NOT graph.py — avoids circular import
from app.agents.state import AgentState
from app.config import get_settings
from app.tools.cornell_lii_tool import search_cornell_lii
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

settings = get_settings()

SYSTEM_PROMPT = """You are a state law research specialist focused on US state statutes.
Given a legal incident summary and the user's state, identify relevant state laws.
For each law:
- Statute citation (e.g., Texas Penal Code § 22.01)
- Plain-language explanation
- How it specifically applies to the case
- Statute of limitations for this type of claim in this state
- Strength: strong/moderate/weak"""


async def run_state_law_agent(state: AgentState, config: RunnableConfig) -> dict:
    intake = state.get("intake_summary", {})
    us_state = intake.get("state", "")

    raw_results = await search_cornell_lii(
        query=intake.get("incident", ""),
        state=us_state,
    )

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"State: {us_state}\nCase: {json.dumps(intake)}\nState law data: {json.dumps(raw_results[:5])}"
        ),
    ]
    response = await llm.ainvoke(messages)

    stream_cb = (config or {}).get("configurable", {}).get("stream_callback")
    if stream_cb:
        await stream_cb("\n⚖️ **State Law Research complete**\n")

    return {
        "state_law_results": [
            {
                "source": "Cornell LII",
                "state": us_state,
                "raw": raw_results,
                "analysis": response.content,
            }
        ]
    }
