"""
agents/federal_law_agent.py — Searches federal statutes via Congress.gov.

RESPONSIBILITY:
  Given the intake_summary, find federal laws that apply to the user's case.
  Examples: Civil Rights Act, ADA, FLSA, 42 U.S.C. § 1983 (civil rights violations)

HOW IT WORKS:
  1. Builds a query string from intake_summary (incident + state + perpetrator)
  2. Calls search_congress() — which checks Redis cache first, then hits API
  3. Passes the raw API results + intake summary to the LLM for analysis
  4. LLM identifies relevant statutes and explains applicability
  5. Returns structured result for opinion_agent to synthesize

RUN ORDER:
  This runs IN PARALLEL with state_law_agent and case_law_agent inside
  fan_out_research (via asyncio.gather). Do not add slow blocking code here.

TEAM — WHERE HUMAN EFFORT IS NEEDED:
  1. Congress.gov API returns BILLS, not statutes directly. The LLM has
     to infer the relevant USC code from bill context. This can be
     inaccurate — test with known cases (e.g., employment discrimination in TX)
  2. SYSTEM_PROMPT quality directly affects output quality. Have the team
     member with most legal knowledge review and refine it.
  3. Add the Congress.gov API key to .env (free signup) — without it,
     DEMO_MODE mock data is used.

AI USAGE NOTE:
  To improve results: ask ChatGPT to add specific example citations to
  the system prompt for common case types (employment, civil rights, etc.)
  This gives the LLM better examples to follow (few-shot prompting).
"""

import json

# Import from state.py, NOT graph.py — avoids circular import
from app.agents.state import AgentState
from app.config import get_settings
from app.tools.congress_tool import search_congress
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

settings = get_settings()

SYSTEM_PROMPT = """You are a federal law research specialist.
Given a legal incident summary, identify the most relevant federal statutes and regulations.
For each law found, provide:
- Statute name and citation (e.g., 42 U.S.C. § 1983)
- Plain-language summary of what it protects
- How it applies to this specific case
- Strength of applicability (strong/moderate/weak)

Be precise and cite real statutes only."""


async def run_federal_law_agent(state: AgentState, config: dict) -> dict:
    intake = state.get("intake_summary", {})
    query = f"Incident: {intake.get('incident')} | State: {intake.get('state')} | Perpetrator: {intake.get('perpetrator')}"

    # Fetch from Congress.gov (cached)
    raw_results = await search_congress(query, intake.get("state", ""))

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"Case summary: {json.dumps(intake)}\n\nRaw federal data: {json.dumps(raw_results[:5])}"
        ),
    ]

    response = await llm.ainvoke(messages)

    stream_cb = (config or {}).get("configurable", {}).get("stream_callback")
    if stream_cb:
        await stream_cb("\n📋 **Federal Law Research complete**\n")

    return {
        "federal_law_results": [
            {"source": "Congress.gov", "raw": raw_results, "analysis": response.content}
        ]
    }
